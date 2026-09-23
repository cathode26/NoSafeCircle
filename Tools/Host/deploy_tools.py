#!/usr/bin/env python
"""Deploy the host tools, and be able to answer whether the deployment is current.

The tools exist twice: tracked under `Tools/Host/`, and copied to
`<workspace>/tools/` where agents actually run them. That second copy is not in
version control, nothing recorded which commit it came from, and there was no
script to produce it - `MOVE-TOOLS-IN.ps1` was a one-time migration in September.
So the question "is the deployment current?" had no answer short of hashing every
file by hand against two commits, which is how the 2026-09-22 drift was found:
all seven GER tools went stale the moment a merge landed, and nothing said so.

**Three states, and the third is the one nothing could see before.**

    current   deployed == its recorded hash == the tracked file now
    stale     deployed == its recorded hash, but the tracked file has MOVED.
              A merge happened. Redeploy.
    modified  deployed != its recorded hash. Someone edited the deployment in
              place. The tracked file is not what is running, and no git history
              covers the difference.

`stale` is expected and routine. `modified` is not, and it is invisible without a
recorded per-file hash - which is the whole reason DEPLOYED.json exists rather
than just a commit id.

Two more states, reported but not failures by default:

    absent    declared in the manifest and not deployed. True of the entire
              closure family today; CLOSURE_PROTOCOL_CUTOVER.md says it must
              deploy, and saying so in prose is what let it be forgotten.
    extra     deployed and not declared. Either the manifest is wrong or
              somebody hand-placed a file.

**Line endings are normalised before hashing.** Deployed copies are CRLF in the
working tree and tracked blobs are LF, so a byte comparison reports every file
as different. The cutover document says "ignoring line endings" for the same
reason.

**This never writes to a deployment unless --apply is given**, and it refuses to
apply from a checkout with uncommitted changes to the files being deployed: a
recorded commit id that does not describe the bytes copied is worse than no
record, because it invites exactly the trust that the record is supposed to earn.

Usage:
    python -B deploy_tools.py --check                 # default; reports, exits 1 on drift
    python -B deploy_tools.py --check --require-complete   # absent also fails
    python -B deploy_tools.py --apply                 # copies, writes DEPLOYED.json
    python -B deploy_tools.py --apply --family ger    # one family
    python -B deploy_tools.py --check --workspace D:/somewhere   # for tests

Exit: 0 nothing to report; 1 drift (stale, modified or extra); 2 could not run -
      no manifest, no workspace, a dirty checkout on --apply, git unavailable.
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nsc_paths  # noqa: E402

MANIFEST_NAME = "deploy_manifest.json"
RECORD_NAME = "DEPLOYED.json"
SCHEMA_VERSION = 1

CURRENT = "current"
STALE = "stale"
MODIFIED = "modified"
ABSENT = "absent"
EXTRA = "extra"
# Deployed, undeclared, AND present in the host tree with different bytes.
# Worse than MODIFIED: a modified declared file is one --apply from correct,
# and this one is reachable by no command at all, because the manifest never
# declares it. Kept distinct from EXTRA so a stale tracked file cannot hide
# among .bak leftovers, which is exactly how three stale test files hid.
SHADOWED = "shadowed"
UNRECORDED = "unrecorded"

# Ordered worst-first, so a report reads top-down by how much it matters.
SEVERITY = [SHADOWED, MODIFIED, EXTRA, STALE, UNRECORDED, ABSENT, CURRENT]


class DeployError(Exception):
    """Cannot proceed, with a reason a person can act on."""


def normalise(data: bytes) -> bytes:
    r"""CRLF and lone CR to LF, so a deployed copy and its LF blob compare equal.

    Deliberately not `.replace(b"\r", b"")`: that would also strip a CR inside a
    string literal and make two genuinely different files hash the same.
    """
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def digest(data: bytes) -> str:
    return hashlib.sha256(normalise(data)).hexdigest()


def load_manifest(host: Path) -> dict:
    path = host / MANIFEST_NAME
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DeployError(f"cannot read {path}: {error}") from None
    except ValueError as error:
        raise DeployError(f"{MANIFEST_NAME} is not valid JSON: {error}") from None
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise DeployError(
            f"{MANIFEST_NAME} declares schema_version "
            f"{manifest.get('schema_version')!r}; this tool speaks {SCHEMA_VERSION}")
    return manifest


def tracked_paths(repo: Path) -> frozenset[str]:
    """Every file tracked at HEAD under Tools/Host, relative to Tools/Host.

    This is the set a deployment is allowed to draw from. Read from the COMMIT,
    not the index and not the filesystem, so it says what the recorded HEAD
    actually contains.
    """
    out = git_output(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", "Tools/Host")
    prefix = "Tools/Host/"
    return frozenset(
        line[len(prefix):] for line in out.splitlines()
        if line.startswith(prefix) and line[len(prefix):]
    )


def selected(host: Path, manifest: dict, only: str | None = None, *,
             tracked: frozenset[str]) -> list[str]:
    """Every path the manifest declares, relative to Tools/Host, sorted.

    MATCHED AGAINST THE TRACKED TREE, WHICH THIS DOCSTRING ALREADY CLAIMED AND
    THE CODE DID NOT DO. It globbed the filesystem: `root.glob(pattern)` over
    `host / family`. Combined with a dirty check that uses ordinary
    `git status` -- which omits IGNORED files -- a gitignored local `.py` sitting
    in an included family was copied into the deployment and then recorded in
    DEPLOYED.json as having come from a HEAD that contains no such file. **False
    provenance, and it ships a local helper by accident.** Found by Astra's main
    audit, 2026-09-23 (H1).

    `tracked` is keyword-only and has NO DEFAULT on purpose: there is no way to
    call this and quietly get the filesystem back.

    A pattern that matches nothing is still simply absent from the result, so a
    manifest may name a family before it exists.
    """
    paths: set[str] = set()

    if only in (None, ""):
        for name in manifest.get("root_files", []):
            if name in tracked:
                paths.add(name)

    for family, rule in sorted(manifest.get("families", {}).items()):
        if only and family != only:
            continue
        prefix = f"{family}/"
        for relative in tracked:
            if not relative.startswith(prefix):
                continue
            tail = relative[len(prefix):]
            # PurePosixPath.full_match has the same `**` semantics as
            # Path.glob, verified against this manifest's four patterns before
            # the swap: *.py, **/*.py, *.sh and templates/*.md all select the
            # same names either way.
            if not any(PurePosixPath(tail).full_match(pattern)
                       for pattern in rule.get("include", [])):
                continue
            if any(fnmatch.fnmatch(tail, skip)
                   or fnmatch.fnmatch(PurePosixPath(tail).name, skip)
                   for skip in rule.get("exclude", [])):
                continue
            if "__pycache__" in relative:
                continue
            paths.add(relative)

    return sorted(paths)


def read_record(tools: Path) -> dict | None:
    path = tools / RECORD_NAME
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def git_output(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode != 0:
        raise DeployError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def head_commit(repo: Path) -> str:
    return git_output(repo, "rev-parse", "HEAD").strip()


def dirty_among(repo: Path, relative_paths: list[str]) -> list[str]:
    """Which of these paths have uncommitted changes, relative to Tools/Host."""
    if not relative_paths:
        return []
    prefixed = [f"Tools/Host/{p}" for p in relative_paths]
    out = git_output(repo, "status", "--porcelain", "--", *prefixed)
    dirty = []
    for line in out.splitlines():
        name = line[3:].strip().strip('"')
        if " -> " in name:
            name = name.split(" -> ", 1)[1]
        if name.startswith("Tools/Host/"):
            dirty.append(name[len("Tools/Host/"):])
    return sorted(set(dirty))


def compare(host: Path, tools: Path, manifest: dict,
            only: str | None = None, *,
            tracked: frozenset[str]) -> tuple[dict[str, str], dict]:
    """Classify every declared path, plus anything deployed and not declared."""
    record = read_record(tools)
    recorded = (record or {}).get("files", {})
    if not isinstance(recorded, dict):
        recorded = {}

    states: dict[str, str] = {}
    for relative in selected(host, manifest, only, tracked=tracked):
        source = host / relative
        live = tools / relative
        if not live.is_file():
            states[relative] = ABSENT
            continue
        live_hash = digest(live.read_bytes())
        tracked_hash = digest(source.read_bytes())
        was = recorded.get(relative)
        if was is None:
            # Deployed, and this deployment has no record of it. Cannot tell a
            # stale copy from an edited one, which is its own finding.
            states[relative] = CURRENT if live_hash == tracked_hash else UNRECORDED
        elif live_hash != was:
            states[relative] = MODIFIED
        elif live_hash != tracked_hash:
            states[relative] = STALE
        else:
            states[relative] = CURRENT

    # Anything under a declared family that is deployed and not declared.
    declared = set(states)
    for family in sorted(manifest.get("families", {})):
        if only and family != only:
            continue
        root = tools / family
        if not root.is_dir():
            continue
        for found in sorted(root.rglob("*.py")):
            if "__pycache__" in found.as_posix():
                continue
            relative = found.relative_to(tools).as_posix()
            if relative in declared:
                continue
            # An undeclared file that ALSO exists in the host tree is not
            # litter: its deployed copy can be stale, and because the manifest
            # never declares it, no --apply repairs it.
            counterpart = host / relative
            if (counterpart.is_file()
                    and digest(counterpart.read_bytes()) != digest(found.read_bytes())):
                states[relative] = SHADOWED
            else:
                states[relative] = EXTRA

    return states, (record or {})


def report(states: dict[str, str], record: dict, tools: Path,
           head: str, quiet: bool = False) -> None:
    counts = {state: 0 for state in SEVERITY}
    for state in states.values():
        counts[state] = counts.get(state, 0) + 1

    print(f"deployment: {tools}")
    if record:
        deployed_from = record.get("deployed_from", "?")
        same = " (same as HEAD)" if deployed_from == head else ""
        print(f"  deployed_from: {deployed_from}{same}")
        print(f"  deployed_at:   {record.get('deployed_at_utc', '?')}")
    else:
        print(f"  deployed_from: UNKNOWN - no {RECORD_NAME}. This deployment "
              f"predates the record, so a file that matches nothing can be a "
              f"stale copy or an edited one and there is no way to tell.")
    print(f"  tracked HEAD:  {head}")
    print("  " + ", ".join(f"{state} {counts[state]}"
                           for state in SEVERITY if counts.get(state)))

    if quiet:
        return
    for state in SEVERITY:
        if state == CURRENT or not counts.get(state):
            continue
        print(f"\n{state.upper()}:")
        if state == SHADOWED:
            print("  Deployed, undeclared, and DIFFERENT from the host tree. No "
                  "--apply repairs these,")
            print("  because the manifest never declares them. Running one is "
                  "running an older copy.")
        for relative in sorted(p for p, s in states.items() if s == state):
            print(f"  {relative}")


def apply(host: Path, tools: Path, manifest: dict, repo: Path,
          only: str | None = None) -> dict:
    paths = selected(host, manifest, only, tracked=tracked_paths(repo))
    if not paths:
        raise DeployError("the manifest selected no files; nothing to deploy")

    dirty = dirty_among(repo, paths)
    if dirty:
        raise DeployError(
            "refusing to deploy from a checkout with uncommitted changes to "
            "these files:\n  " + "\n  ".join(dirty) +
            "\nA recorded commit id that does not describe the bytes copied is "
            "worse than no record at all. Commit, or stash, first.")

    head = head_commit(repo)
    files = {}
    for relative in paths:
        source = host / relative
        target = tools / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files[relative] = digest(target.read_bytes())

    record = {
        "schema_version": SCHEMA_VERSION,
        "deployed_from": head,
        "deployed_at_utc": datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "deployed_by": os.environ.get("NSC_ROLE") or "unknown",
        "manifest_sha256": digest((host / MANIFEST_NAME).read_bytes()),
        "partial_family": only,
        "files": files,
    }

    # The record LAST, and atomically: a crash part-way leaves files copied and
    # no record, which --check reports as `unrecorded` rather than as current.
    final = tools / RECORD_NAME
    if only and final.is_file():
        # A single-family deploy must not erase the other families' hashes.
        previous = read_record(tools) or {}
        merged = dict(previous.get("files") or {})
        merged.update(files)
        record["files"] = merged
        record["partial_family"] = only
    temporary = final.with_name(f".{RECORD_NAME}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, final)
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deploy the host tools, or report whether the deployment is current.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="report only; the default")
    mode.add_argument("--apply", action="store_true",
                      help="copy the declared files and write the record")
    parser.add_argument("--family", default=None,
                        help="limit to one family, e.g. ger")
    parser.add_argument("--workspace", type=Path, default=None,
                        help="deploy under this workspace instead of the "
                             "derived one; the deployment is <workspace>/tools")
    parser.add_argument("--repo", type=Path, default=None,
                        help="the checkout to deploy FROM; defaults to the "
                             "repository this file belongs to")
    parser.add_argument("--require-complete", action="store_true",
                        help="a declared file that is not deployed is a failure "
                             "too, not just a report")
    parser.add_argument("--quiet", action="store_true",
                        help="counts only, no per-file listing")
    args = parser.parse_args(argv)

    try:
        repo = args.repo
        if repo is None:
            containing = nsc_paths.containing_repo()
            if containing is None:
                raise DeployError(
                    "this file is not inside a git checkout, so there is no "
                    "source to deploy from. Pass --repo.")
            repo = containing.path
        host = Path(repo) / "Tools" / "Host"
        if not (host / MANIFEST_NAME).is_file():
            raise DeployError(f"no {MANIFEST_NAME} under {host}")

        workspace = args.workspace or nsc_paths.workspace().path
        tools = Path(workspace) / "tools"

        manifest = load_manifest(host)

        # A MISSPELLED --family SELECTED NOTHING AND PASSED. `--check
        # --require-complete --family jobz` reached the exit line below with an
        # EMPTY `states`, and `any()` over nothing is False, so it returned 0 --
        # a green "complete" from a run that checked not one file. Astra's main
        # audit, 2026-09-23 (H2). The apply path's own empty-selection guard
        # never protected check mode.
        known = set(manifest.get("families", {}))
        if args.family and args.family not in known:
            raise DeployError(
                f"--family {args.family!r} is not in {MANIFEST_NAME}; it "
                f"declares {', '.join(sorted(known)) or 'no families'}")

        if args.apply:
            tools.mkdir(parents=True, exist_ok=True)
            record = apply(host, tools, manifest, Path(repo), args.family)
            print(f"deployed {len(record['files'])} file(s) to {tools}")
            print(f"  from {record['deployed_from']}")
            print(f"  record: {tools / RECORD_NAME}")
            return 0

        if not tools.is_dir():
            raise DeployError(f"no deployment at {tools}")
        states, record = compare(host, tools, manifest, args.family,
                                 tracked=tracked_paths(Path(repo)))
        report(states, record, tools, head_commit(Path(repo)), args.quiet)

        bad = {SHADOWED, MODIFIED, EXTRA, STALE, UNRECORDED}
        if args.require_complete:
            bad = bad | {ABSENT}
            if not states:
                # The second half of H2, and the family check above does not
                # cover it: a legitimately declared family whose patterns match
                # nothing in the tracked tree also yields an empty inventory.
                # "Complete" over zero files is not a pass; it is a question
                # nobody asked.
                raise DeployError(
                    "--require-complete checked NOTHING: the manifest selected "
                    "no files"
                    + (f" for --family {args.family}" if args.family else "")
                    + ". An empty inventory cannot be complete.")
        return 1 if any(state in bad for state in states.values()) else 0

    except DeployError as error:
        print(f"deploy_tools: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
