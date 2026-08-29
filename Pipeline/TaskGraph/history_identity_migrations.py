from __future__ import annotations

"""Committed translation authority for deliberate Git history identity rewrites.

Immutable TaskGraph evidence records historical commit IDs. A repository-history
rewrite necessarily changes those IDs even when every file tree is byte-identical.
This module lets a later, human-approved migration manifest translate only those
explicit old commit IDs to tree-equivalent rewritten commits.

The manifest is not a general alias mechanism. It is accepted only when the
rewritten target main is an ancestor of the current HEAD, every translated target
commit is in that canonical rewritten history, and every translated target tree
matches the recorded pre-rewrite tree exactly.
"""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MIGRATION_SCHEMA_VERSION = "1.0"
MIGRATION_TYPE = "repository_history_identity"
MIGRATION_REASON = "git_identity_sanitization"
MIGRATION_ROOT = "Pipeline/TaskGraph/migrations"
MIGRATION_PREFIX = "repository-history-identity-"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MIGRATION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class HistoryIdentityMigrationError(RuntimeError):
    """Raised when committed history-translation authority is malformed or false."""


@dataclass(frozen=True)
class CommitTranslation:
    old_commit: str
    new_commit: str
    tree: str
    migration_id: str
    manifest_path: str
    rewrite_report_sha256: str


class HistoryIdentityMigrationResolver:
    """Resolve exact historical commit IDs through committed migration manifests."""

    def __init__(self, root: Path | str, head: str) -> None:
        self.root = Path(root).resolve()
        self.head = _sha(head, "history migration HEAD")
        self._translations = self._load()
        self._validate_chains()

    def resolve(self, commit: str) -> str:
        """Return the final translated commit for an exact 40-character SHA."""

        if not isinstance(commit, str) or not GIT_SHA_RE.fullmatch(commit):
            return commit
        cursor = commit
        seen: set[str] = set()
        while cursor in self._translations:
            if cursor in seen:
                raise HistoryIdentityMigrationError(
                    f"history identity migration contains a cycle at {cursor}"
                )
            seen.add(cursor)
            cursor = self._translations[cursor].new_commit
        return cursor

    def translation_for(self, commit: str) -> CommitTranslation | None:
        return self._translations.get(commit)

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {
            old: {
                "new_commit": entry.new_commit,
                "tree": entry.tree,
                "migration_id": entry.migration_id,
                "manifest_path": entry.manifest_path,
                "rewrite_report_sha256": entry.rewrite_report_sha256,
            }
            for old, entry in sorted(self._translations.items())
        }

    def _run(self, *args: str, check: bool = True) -> bytes:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise HistoryIdentityMigrationError(
                f"git {' '.join(args)} failed while loading history migration: {detail}"
            )
        return result.stdout

    def _exists(self, commit: str) -> bool:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=self.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0

    def _tree(self, commit: str) -> str:
        return _sha(
            self._run("rev-parse", f"{commit}^{{tree}}").decode("ascii").strip(),
            f"{commit} tree",
        )

    def _is_ancestor(self, older: str, newer: str) -> bool:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer],
            cwd=self.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0

    def _manifest_paths(self) -> list[str]:
        output = self._run(
            "ls-tree", "-r", "--name-only", self.head, "--", MIGRATION_ROOT
        ).decode("utf-8")
        paths = []
        for path in output.splitlines():
            name = path.rsplit("/", 1)[-1]
            if name.startswith(MIGRATION_PREFIX) and name.endswith(".json"):
                paths.append(path)
        return sorted(paths)

    def _read_json(self, path: str) -> dict[str, Any]:
        try:
            value = json.loads(
                self._run("show", f"{self.head}:{path}").decode("utf-8-sig")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HistoryIdentityMigrationError(
                f"unable to parse history migration manifest {path}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise HistoryIdentityMigrationError(
                f"history migration manifest {path} must contain an object"
            )
        return value

    def _load(self) -> dict[str, CommitTranslation]:
        translations: dict[str, CommitTranslation] = {}
        for path in self._manifest_paths():
            manifest = self._read_json(path)
            entries = self._validate_manifest(path, manifest)
            for entry in entries:
                existing = translations.get(entry.old_commit)
                if existing is not None and existing != entry:
                    raise HistoryIdentityMigrationError(
                        f"conflicting history translations for {entry.old_commit}: "
                        f"{existing.manifest_path} and {entry.manifest_path}"
                    )
                translations[entry.old_commit] = entry
        return translations

    def _validate_manifest(
        self, path: str, manifest: Mapping[str, Any]
    ) -> list[CommitTranslation]:
        expected = {
            "schema_version",
            "migration_type",
            "migration_id",
            "reason",
            "approved_by",
            "approved_at",
            "source_main",
            "source_main_tree",
            "target_main",
            "target_main_tree",
            "rewrite_report_sha256",
            "commit_map",
        }
        if set(manifest) != expected:
            raise HistoryIdentityMigrationError(
                f"{path}: history migration fields differ from schema "
                f"(missing={sorted(expected-set(manifest))}, "
                f"extra={sorted(set(manifest)-expected)})"
            )
        if manifest.get("schema_version") != MIGRATION_SCHEMA_VERSION:
            raise HistoryIdentityMigrationError(
                f"{path}: unsupported history migration schema_version"
            )
        if manifest.get("migration_type") != MIGRATION_TYPE:
            raise HistoryIdentityMigrationError(f"{path}: unsupported migration_type")
        if manifest.get("reason") != MIGRATION_REASON:
            raise HistoryIdentityMigrationError(f"{path}: unsupported migration reason")
        migration_id = _text(manifest.get("migration_id"), f"{path}.migration_id")
        if not MIGRATION_ID_RE.fullmatch(migration_id):
            raise HistoryIdentityMigrationError(f"{path}: invalid migration_id")
        expected_name = f"{MIGRATION_ROOT}/{MIGRATION_PREFIX}{migration_id}.json"
        if path != expected_name:
            raise HistoryIdentityMigrationError(
                f"{path}: migration_id and manifest filename disagree"
            )
        _text(manifest.get("approved_by"), f"{path}.approved_by")
        _text(manifest.get("approved_at"), f"{path}.approved_at")
        report_hash = _text(
            manifest.get("rewrite_report_sha256"), f"{path}.rewrite_report_sha256"
        )
        if not SHA256_RE.fullmatch(report_hash):
            raise HistoryIdentityMigrationError(
                f"{path}: rewrite_report_sha256 must be lowercase SHA-256"
            )

        source_main = _sha(manifest.get("source_main"), f"{path}.source_main")
        source_tree = _sha(
            manifest.get("source_main_tree"), f"{path}.source_main_tree"
        )
        target_main = _sha(manifest.get("target_main"), f"{path}.target_main")
        target_tree = _sha(
            manifest.get("target_main_tree"), f"{path}.target_main_tree"
        )
        if source_main == target_main:
            raise HistoryIdentityMigrationError(
                f"{path}: source_main and target_main must differ"
            )
        if source_tree != target_tree:
            raise HistoryIdentityMigrationError(
                f"{path}: canonical main tree changed across history rewrite"
            )
        if not self._exists(target_main):
            raise HistoryIdentityMigrationError(
                f"{path}: rewritten target_main is unavailable: {target_main}"
            )
        if self._tree(target_main) != target_tree:
            raise HistoryIdentityMigrationError(
                f"{path}: target_main tree does not match recorded target_main_tree"
            )
        if not self._is_ancestor(target_main, self.head):
            raise HistoryIdentityMigrationError(
                f"{path}: rewritten target_main is not an ancestor of current HEAD"
            )
        if self._exists(source_main) and self._tree(source_main) != source_tree:
            raise HistoryIdentityMigrationError(
                f"{path}: available source_main tree disagrees with manifest"
            )

        raw_map = manifest.get("commit_map")
        if not isinstance(raw_map, list) or not raw_map:
            raise HistoryIdentityMigrationError(
                f"{path}.commit_map must be a non-empty list"
            )
        result: list[CommitTranslation] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_map):
            label = f"{path}.commit_map[{index}]"
            if not isinstance(raw, Mapping) or set(raw) != {
                "old_commit",
                "new_commit",
                "tree",
            }:
                raise HistoryIdentityMigrationError(
                    f"{label} must contain old_commit, new_commit, and tree"
                )
            old_commit = _sha(raw.get("old_commit"), f"{label}.old_commit")
            new_commit = _sha(raw.get("new_commit"), f"{label}.new_commit")
            tree = _sha(raw.get("tree"), f"{label}.tree")
            if old_commit == new_commit:
                raise HistoryIdentityMigrationError(
                    f"{label}: old_commit and new_commit must differ"
                )
            if old_commit in seen:
                raise HistoryIdentityMigrationError(
                    f"{path}: duplicate old_commit {old_commit}"
                )
            seen.add(old_commit)
            if not self._exists(new_commit):
                raise HistoryIdentityMigrationError(
                    f"{label}: translated commit is unavailable: {new_commit}"
                )
            if self._tree(new_commit) != tree:
                raise HistoryIdentityMigrationError(
                    f"{label}: translated commit tree differs from recorded tree"
                )
            if not self._is_ancestor(new_commit, target_main):
                raise HistoryIdentityMigrationError(
                    f"{label}: translated commit is not in rewritten canonical history"
                )
            if self._exists(old_commit) and self._tree(old_commit) != tree:
                raise HistoryIdentityMigrationError(
                    f"{label}: available historical commit tree differs from recorded tree"
                )
            result.append(
                CommitTranslation(
                    old_commit=old_commit,
                    new_commit=new_commit,
                    tree=tree,
                    migration_id=migration_id,
                    manifest_path=path,
                    rewrite_report_sha256=report_hash,
                )
            )
        return result

    def _validate_chains(self) -> None:
        for old_commit in self._translations:
            self.resolve(old_commit)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoryIdentityMigrationError(f"{label} must be a non-empty string")
    return value.strip()


def _sha(value: Any, label: str) -> str:
    text = _text(value, label)
    if not GIT_SHA_RE.fullmatch(text):
        raise HistoryIdentityMigrationError(
            f"{label} must be a lowercase 40-character Git SHA"
        )
    return text
