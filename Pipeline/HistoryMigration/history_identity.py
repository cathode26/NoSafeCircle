#!/usr/bin/env python3
"""Deterministic tooling for sanitizing Git commit identities without changing trees."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "1.0"
REPORT_NAME = "history-identity-dry-run.json"
MIRROR_NAME = "mirror.git"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.invalid$", re.IGNORECASE)

DEFAULT_REPLACEMENTS: dict[str, str] = {
    "resilience@users.noreply.github.com": "resilience-fix@nosafecircle.invalid",
    "reintegration-bridge@users.noreply.github.com": "reintegration-bridge@nosafecircle.invalid",
    "pipeline@users.noreply.github.com": "pipeline@nosafecircle.invalid",
}


class HistoryIdentityError(RuntimeError):
    """Raised when an identity rewrite cannot be proven safe."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def semantic_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _run(
    cwd: Path,
    args: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise HistoryIdentityError(
            f"command failed ({result.returncode}): {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _text(cwd: Path, args: Sequence[str]) -> str:
    return _run(cwd, args).stdout.decode("utf-8").strip()


def _validate_sha(value: str, label: str) -> str:
    if not GIT_SHA_RE.fullmatch(value):
        raise HistoryIdentityError(f"{label} is not a lowercase 40-character Git SHA")
    return value


def _validate_replacements(replacements: Mapping[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for old, new in replacements.items():
        old_email = str(old).strip().lower()
        new_email = str(new).strip().lower()
        if not old_email or not new_email:
            raise HistoryIdentityError("identity replacement emails must be non-empty")
        if not old_email.endswith("@users.noreply.github.com"):
            raise HistoryIdentityError(
                f"rewrite source is not in GitHub's user noreply namespace: {old_email}"
            )
        if not SAFE_EMAIL_RE.fullmatch(new_email):
            raise HistoryIdentityError(
                f"rewrite target must use a reserved .invalid address: {new_email}"
            )
        if new_email.endswith("@users.noreply.github.com"):
            raise HistoryIdentityError("rewrite target cannot use GitHub's user noreply namespace")
        normalized[old_email] = new_email
    return normalized


def _clone_mirror(source: Path, output: Path) -> Path:
    if output.exists():
        raise HistoryIdentityError(f"output path already exists: {output}")
    output.mkdir(parents=True)
    mirror = output / MIRROR_NAME
    result = subprocess.run(
        ["git", "clone", "--mirror", "--no-local", str(source.resolve()), str(mirror)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        shutil.rmtree(output, ignore_errors=True)
        raise HistoryIdentityError(f"unable to create disposable mirror: {detail}")
    return mirror


def _object_type(mirror: Path, sha: str) -> str:
    return _text(mirror, ["git", "cat-file", "-t", sha])


def _refs(mirror: Path) -> list[tuple[str, str]]:
    output = _run(
        mirror,
        ["git", "for-each-ref", "--format=%(refname)%00%(objectname)", "refs/heads", "refs/tags"],
    ).stdout
    result: list[tuple[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        parts = line.split(b"\x00")
        if len(parts) != 2:
            raise HistoryIdentityError("unexpected for-each-ref output")
        ref = parts[0].decode("utf-8")
        sha = parts[1].decode("ascii")
        if _object_type(mirror, sha) != "commit":
            continue
        result.append((ref, _validate_sha(sha, f"{ref} target")))
    if not result:
        raise HistoryIdentityError("no branch/tag commit refs were found")
    return sorted(result)


def _tree(mirror: Path, sha: str) -> str:
    value = _text(mirror, ["git", "rev-parse", f"{sha}^{{tree}}"])
    return _validate_sha(value, f"{sha} tree")


def _reachable_commits(mirror: Path, refs: Iterable[tuple[str, str]]) -> list[str]:
    heads = [sha for _, sha in refs]
    output = _run(mirror, ["git", "rev-list", "--topo-order", *heads]).stdout
    commits = [line.decode("ascii") for line in output.splitlines() if line]
    for sha in commits:
        _validate_sha(sha, "reachable commit")
    return commits


@dataclass(frozen=True)
class ParsedCommit:
    raw: bytes
    headers: tuple[tuple[bytes, tuple[bytes, ...]], ...]
    message: bytes
    parents: tuple[str, ...]
    author_email: str
    committer_email: str
    has_signature: bool


_IDENTITY_RE = re.compile(
    rb"^(author|committer) (.*) <([^<>]+)> ([0-9]+) ([+-][0-9]{4})$"
)


def _parse_commit(raw: bytes) -> ParsedCommit:
    if b"\n\n" not in raw:
        raise HistoryIdentityError("Git commit object has no header/message separator")
    raw_headers, message = raw.split(b"\n\n", 1)
    blocks: list[tuple[bytes, tuple[bytes, ...]]] = []
    current: list[bytes] = []
    for line in raw_headers.split(b"\n"):
        if line.startswith(b" ") and current:
            current.append(line)
        else:
            if current:
                key = current[0].split(b" ", 1)[0]
                blocks.append((key, tuple(current)))
            current = [line]
    if current:
        key = current[0].split(b" ", 1)[0]
        blocks.append((key, tuple(current)))

    parents: list[str] = []
    author_email = ""
    committer_email = ""
    has_signature = False
    for key, lines in blocks:
        first = lines[0]
        if key == b"parent":
            value = first.split(b" ", 1)[1].decode("ascii")
            parents.append(_validate_sha(value, "parent"))
        elif key in {b"author", b"committer"}:
            match = _IDENTITY_RE.fullmatch(first)
            if not match:
                raise HistoryIdentityError(
                    f"unsupported {key.decode()} identity header: "
                    f"{first.decode('utf-8', 'replace')}"
                )
            email = match.group(3).decode("utf-8").strip().lower()
            if key == b"author":
                author_email = email
            else:
                committer_email = email
        elif key.startswith(b"gpgsig"):
            has_signature = True
    if not author_email or not committer_email:
        raise HistoryIdentityError("commit is missing author or committer identity")
    return ParsedCommit(
        raw=raw,
        headers=tuple(blocks),
        message=message,
        parents=tuple(parents),
        author_email=author_email,
        committer_email=committer_email,
        has_signature=has_signature,
    )


def _replace_identity_line(line: bytes, replacements: Mapping[str, str]) -> tuple[bytes, bool]:
    match = _IDENTITY_RE.fullmatch(line)
    if not match:
        raise HistoryIdentityError(
            f"unsupported identity header: {line.decode('utf-8', 'replace')}"
        )
    old_email = match.group(3).decode("utf-8").strip().lower()
    new_email = replacements.get(old_email)
    if new_email is None:
        return line, False
    rewritten = (
        match.group(1)
        + b" "
        + match.group(2)
        + b" <"
        + new_email.encode("utf-8")
        + b"> "
        + match.group(4)
        + b" "
        + match.group(5)
    )
    return rewritten, True


def _write_commit_object(mirror: Path, content: bytes) -> str:
    value = _run(
        mirror,
        ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
        input_bytes=content,
    ).stdout.decode("ascii").strip()
    return _validate_sha(value, "rewritten commit")


def _rewrite_commit(
    mirror: Path,
    sha: str,
    *,
    replacements: Mapping[str, str],
    cache: dict[str, str],
    parsed_cache: dict[str, ParsedCommit],
    report_rows: list[dict[str, Any]],
) -> str:
    if sha in cache:
        return cache[sha]
    parsed = parsed_cache[sha]
    mapped_parents = tuple(
        _rewrite_commit(
            mirror,
            parent,
            replacements=replacements,
            cache=cache,
            parsed_cache=parsed_cache,
            report_rows=report_rows,
        )
        for parent in parsed.parents
    )
    parent_changed = mapped_parents != parsed.parents
    identity_changed = (
        parsed.author_email in replacements or parsed.committer_email in replacements
    )
    if not parent_changed and not identity_changed:
        cache[sha] = sha
        return sha

    parent_index = 0
    output_blocks: list[bytes] = []
    removed_signature = False
    author_rewritten = False
    committer_rewritten = False
    for key, lines in parsed.headers:
        if key == b"parent":
            mapped = mapped_parents[parent_index]
            parent_index += 1
            output_blocks.append(b"parent " + mapped.encode("ascii"))
            continue
        if key == b"author":
            new_line, changed = _replace_identity_line(lines[0], replacements)
            author_rewritten = changed
            output_blocks.append(b"\n".join((new_line, *lines[1:])))
            continue
        if key == b"committer":
            new_line, changed = _replace_identity_line(lines[0], replacements)
            committer_rewritten = changed
            output_blocks.append(b"\n".join((new_line, *lines[1:])))
            continue
        if key.startswith(b"gpgsig"):
            removed_signature = True
            continue
        output_blocks.append(b"\n".join(lines))

    rewritten_raw = b"\n".join(output_blocks) + b"\n\n" + parsed.message
    new_sha = _write_commit_object(mirror, rewritten_raw)
    old_tree = _tree(mirror, sha)
    new_tree = _tree(mirror, new_sha)
    if old_tree != new_tree:
        raise HistoryIdentityError(
            f"tree changed while rewriting {sha}: {old_tree} != {new_tree}"
        )
    row = {
        "old_commit": sha,
        "new_commit": new_sha,
        "tree": old_tree,
        "parent_changed": parent_changed,
        "author_identity_changed": author_rewritten,
        "committer_identity_changed": committer_rewritten,
        "signature_removed": removed_signature,
        "old_author_email": parsed.author_email,
        "new_author_email": replacements.get(parsed.author_email, parsed.author_email),
        "old_committer_email": parsed.committer_email,
        "new_committer_email": replacements.get(
            parsed.committer_email, parsed.committer_email
        ),
    }
    report_rows.append(row)
    cache[sha] = new_sha
    return new_sha


def _audit_identities(
    mirror: Path,
    commits: Sequence[str],
    replacements: Mapping[str, str],
) -> tuple[dict[str, ParsedCommit], list[dict[str, Any]], list[dict[str, Any]]]:
    parsed_cache: dict[str, ParsedCommit] = {}
    all_noreply: list[dict[str, Any]] = []
    targeted: list[dict[str, Any]] = []
    for sha in commits:
        parsed = _parse_commit(_run(mirror, ["git", "cat-file", "commit", sha]).stdout)
        parsed_cache[sha] = parsed
        for role, email in (
            ("author", parsed.author_email),
            ("committer", parsed.committer_email),
        ):
            if email.endswith("@users.noreply.github.com"):
                entry = {"commit": sha, "role": role, "email": email}
                all_noreply.append(entry)
                if email in replacements:
                    targeted.append(
                        {**entry, "replacement_email": replacements[email]}
                    )
    if not targeted:
        raise HistoryIdentityError(
            "none of the configured unsafe identities are reachable from selected refs"
        )
    return parsed_cache, all_noreply, targeted


def dry_run(
    *,
    source: Path,
    output: Path,
    replacements: Mapping[str, str],
) -> dict[str, Any]:
    source = source.resolve()
    if not (source / ".git").exists() and not (source / "HEAD").exists():
        raise HistoryIdentityError(f"source is not a Git repository: {source}")
    if (source / ".git").exists():
        status = _run(source, ["git", "status", "--porcelain"]).stdout
        if status:
            raise HistoryIdentityError("source worktree must be completely clean")

    normalized_replacements = _validate_replacements(replacements)
    mirror = _clone_mirror(source, output)
    refs = _refs(mirror)
    reachable = _reachable_commits(mirror, refs)
    parsed_cache, all_noreply, targeted = _audit_identities(
        mirror, reachable, normalized_replacements
    )

    source_main = _text(mirror, ["git", "rev-parse", "refs/heads/main"])
    source_main_tree = _tree(mirror, source_main)

    cache: dict[str, str] = {}
    report_rows: list[dict[str, Any]] = []
    ref_rows: list[dict[str, Any]] = []
    for ref, old_sha in refs:
        new_sha = _rewrite_commit(
            mirror,
            old_sha,
            replacements=normalized_replacements,
            cache=cache,
            parsed_cache=parsed_cache,
            report_rows=report_rows,
        )
        if new_sha != old_sha:
            _run(mirror, ["git", "update-ref", ref, new_sha, old_sha])
        ref_rows.append(
            {
                "ref": ref,
                "old_commit": old_sha,
                "new_commit": new_sha,
                "changed": new_sha != old_sha,
            }
        )

    target_main = _text(mirror, ["git", "rev-parse", "refs/heads/main"])
    target_main_tree = _tree(mirror, target_main)
    if source_main_tree != target_main_tree:
        raise HistoryIdentityError(
            "main tree changed during identity rewrite; refusing to produce a valid report"
        )

    report_rows.sort(key=lambda item: item["old_commit"])
    ref_rows.sort(key=lambda item: item["ref"])
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "history_identity_dry_run",
        "source_repository": str(source),
        "source_main": source_main,
        "target_main": target_main,
        "source_main_tree": source_main_tree,
        "target_main_tree": target_main_tree,
        "trees_preserved": True,
        "replacement_emails": normalized_replacements,
        "reachable_commit_count": len(reachable),
        "rewritten_commit_count": len(report_rows),
        "identity_target_count": len(
            {(item["commit"], item["email"]) for item in targeted}
        ),
        "signature_removed_count": sum(
            1 for item in report_rows if item["signature_removed"]
        ),
        "github_user_noreply_identities": all_noreply,
        "targeted_identity_occurrences": targeted,
        "commit_map": report_rows,
        "ref_map": ref_rows,
    }
    report["report_sha256"] = semantic_sha256(report)
    report_path = output / REPORT_NAME
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _load_replacements(path: Path | None) -> dict[str, str]:
    if path is None:
        return dict(DEFAULT_REPLACEMENTS)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoryIdentityError(f"unable to read replacement map: {exc}") from exc
    if not isinstance(value, dict):
        raise HistoryIdentityError("replacement map must be a JSON object")
    return {str(key): str(item) for key, item in value.items()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a tree-preserving dry-run Git identity rewrite in a disposable mirror."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    dry = sub.add_parser("dry-run")
    dry.add_argument("--source", default=".")
    dry.add_argument("--output", required=True)
    dry.add_argument("--replacements")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "dry-run":
            report = dry_run(
                source=Path(args.source),
                output=Path(args.output),
                replacements=_load_replacements(
                    Path(args.replacements) if args.replacements else None
                ),
            )
            print(
                json.dumps(
                    {
                        "status": "dry_run_complete",
                        "source_main": report["source_main"],
                        "target_main": report["target_main"],
                        "tree": report["target_main_tree"],
                        "rewritten_commit_count": report["rewritten_commit_count"],
                        "identity_target_count": report["identity_target_count"],
                        "signature_removed_count": report["signature_removed_count"],
                        "report": str(Path(args.output) / REPORT_NAME),
                        "mirror": str(Path(args.output) / MIRROR_NAME),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
    except HistoryIdentityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
