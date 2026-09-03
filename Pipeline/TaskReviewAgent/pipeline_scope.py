"""Bounded repository inspection and deterministic ExecutionCrew scope approval."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .contracts import (
    ExecutionScopePlan,
    ScopeValidationResult,
    TaskReviewContractError,
    semantic_sha256,
    validate_task_id,
)


SCOPE_SCHEMA_VERSION = "1.0"
_READ_PREFIXES = (
    "Assets/",
    "Packages/",
    "ProjectSettings/",
    "Tasks/",
    "Docs/GDD/",
    "Docs/Engineering/",
    "Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md",
    "Design/Approved/",
)
_IMPLEMENTATION_PREFIXES = ("Assets/", "Packages/", "ProjectSettings/")
_NEW_IMPLEMENTATION_PREFIXES = ("Assets/",)
_TEST_PREFIXES = ("Assets/", "Packages/")
_REQUIRED_POLICY_PATHS = (
    "Docs/Engineering/UNITY_TESTING_POLICY.md",
    "Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md",
)
_PROTECTED_TOP_LEVEL = {
    ".git",
    ".github",
    "Assignment3AgentCrew",
    "Assignment4RAG",
    "Assignment5GoalOriented",
    "Assignment6GER",
    "Assignment7StyleGuide",
    "Design",
    "Docs",
    "DynamicContentPipeline",
    "GoalOrientedAgent",
    "Pipeline",
    "Tasks",
}
_TEXT_SUFFIXES = {
    ".asmdef",
    ".asmref",
    ".asset",
    ".cs",
    ".inputactions",
    ".json",
    ".md",
    ".prefab",
    ".shader",
    ".txt",
    ".unity",
    ".uss",
    ".uxml",
    ".yaml",
    ".yml",
}


class RepositoryScopeError(TaskReviewContractError):
    """Raised when repository inspection or scope persistence fails closed."""


def _decode(data: bytes, *, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RepositoryScopeError(f"{label} was not valid UTF-8") from exc


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout_seconds: float = 180.0,
) -> subprocess.CompletedProcess[bytes]:
    if not args or any(type(item) is not str or not item for item in args):
        raise RepositoryScopeError("command arguments must be non-empty exact strings")
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            tuple(args),
            cwd=str(cwd),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RepositoryScopeError(
            f"repository command could not run: {' '.join(args)}"
        ) from exc
    if check and result.returncode != 0:
        stdout = _decode(result.stdout or b"", label="stdout").strip()
        stderr = _decode(result.stderr or b"", label="stderr").strip()
        detail = "\n".join(item for item in (stdout, stderr) if item)
        raise RepositoryScopeError(
            f"repository command failed ({result.returncode}): {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return _run(("git", "-C", str(root), *args), cwd=root, check=check)


def _git_text(root: Path, *args: str, check: bool = True) -> str:
    return _decode(_git(root, *args, check=check).stdout, label="git stdout").strip()


def _repo_path(value: Any, *, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise RepositoryScopeError(f"{field} must be a non-empty repository path")
    text = value.strip()
    if "\\" in text:
        raise RepositoryScopeError(f"{field} must use POSIX separators")
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts:
        raise RepositoryScopeError(f"{field} must be repository-relative")
    if any(part in ("", ".", "..") for part in path.parts):
        raise RepositoryScopeError(f"{field} contains an invalid path component")
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise RepositoryScopeError(f"{field} contains a control character")
    return text


def _under(path: str, prefixes: Iterable[str]) -> bool:
    folded = path.casefold()
    return any(folded.startswith(prefix.casefold()) for prefix in prefixes)


def _is_test_path(path: str) -> bool:
    return any(part.casefold() == "tests" for part in PurePosixPath(path).parts)


def _safe_json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


@dataclass(frozen=True)
class AcceptedExecutionScope:
    plan_id: str
    task_id: str
    lease_id: str
    source_head: str
    task_contract_sha256: str
    plan: ExecutionScopePlan

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCOPE_SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "lease_id": self.lease_id,
            "source_head": self.source_head,
            "task_contract_sha256": self.task_contract_sha256,
            "plan": self.plan.to_dict(),
        }


class RepositoryScopeAuthority:
    """Expose read-only repository tools and mint exact ExecutionCrew path authority."""

    def __init__(
        self,
        *,
        checkout: Path | str,
        task: Mapping[str, Any],
        lease_id: str,
        expected_branch: str,
        state_root: Path | str | None = None,
    ) -> None:
        self.checkout = Path(checkout).resolve()
        self.task_id = validate_task_id(task.get("task_id") or task.get("id"))
        self.task = _safe_json_copy(dict(task))
        self.lease_id = str(lease_id).strip()
        self.expected_branch = str(expected_branch).strip()
        self.task_contract_sha256 = str(task.get("task_contract_sha256") or "").strip()
        if not self.lease_id or not self.expected_branch:
            raise RepositoryScopeError("scope authority requires lease_id and expected_branch")
        if len(self.task_contract_sha256) != 64:
            raise RepositoryScopeError("scope authority requires task-contract SHA-256")
        self.state_root = Path(state_root or (self.checkout.parent / ".task-review-agent"))
        self.state_path = self.state_root / f"{self.task_id}.scope.json"
        self.source_head = ""
        self._tracked_paths: tuple[str, ...] | None = None
        self._accepted: AcceptedExecutionScope | None = None
        self._assert_checkout()
        self._load_current()

    @property
    def accepted(self) -> AcceptedExecutionScope | None:
        return self._accepted

    def _assert_checkout(self) -> None:
        if not self.checkout.is_dir():
            raise RepositoryScopeError(f"task checkout does not exist: {self.checkout}")
        top = _git_text(self.checkout, "rev-parse", "--show-toplevel", check=False)
        if not top or Path(top).resolve() != self.checkout:
            raise RepositoryScopeError("task checkout is not the standalone Git root")
        branch = _git_text(self.checkout, "branch", "--show-current", check=False)
        if branch != self.expected_branch:
            raise RepositoryScopeError(
                f"task checkout branch {branch!r} differs from {self.expected_branch!r}"
            )
        status = _git_text(
            self.checkout,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        if status:
            raise RepositoryScopeError("scope planning requires a clean task checkout")
        self.source_head = _git_text(self.checkout, "rev-parse", "--verify", "HEAD")
        contract_path = str(self.task.get("contract_path") or f"Tasks/{self.task_id}.yaml")
        contract = _git(self.checkout, "show", f"HEAD:{contract_path}", check=False)
        if contract.returncode != 0:
            raise RepositoryScopeError("task contract is absent from task checkout HEAD")
        import hashlib

        if hashlib.sha256(contract.stdout).hexdigest() != self.task_contract_sha256:
            raise RepositoryScopeError("task checkout contract hash differs from workflow task")

    def _tracked(self) -> tuple[str, ...]:
        if self._tracked_paths is None:
            raw = _git_text(self.checkout, "ls-tree", "-r", "--name-only", "HEAD")
            self._tracked_paths = tuple(line for line in raw.splitlines() if line)
        return self._tracked_paths

    def _resource_paths(self) -> tuple[str, ...]:
        result: list[str] = []
        for resource in self.task.get("exclusive_resources") or []:
            if type(resource) is not str or ":" not in resource:
                continue
            kind, value = resource.split(":", 1)
            if kind in ("repo-file", "unity-scene") and value:
                try:
                    result.append(_repo_path(value, field="exclusive resource path"))
                except RepositoryScopeError:
                    continue
        return tuple(sorted(set(result), key=str.casefold))

    def _ownership_roots(self) -> tuple[str, ...]:
        roots: set[str] = set()
        for value in self._resource_paths():
            parts = PurePosixPath(value).parts
            if len(parts) >= 3 and parts[0].casefold() == "assets" and parts[1].casefold() == "nosafecircle":
                roots.add("/".join(parts[:3]) + "/")
            elif len(parts) >= 2 and parts[0].casefold() == "assets" and parts[1].casefold() != "scenes":
                roots.add("/".join(parts[:2]) + "/")
        return tuple(sorted(roots, key=str.casefold))

    def facts(self) -> dict[str, Any]:
        self._assert_checkout()
        tracked = self._tracked()
        resource_paths = self._resource_paths()
        roots = self._ownership_roots()
        existing_resources = [path for path in resource_paths if path in tracked]
        absent_resources = [path for path in resource_paths if path not in tracked]

        title_tokens = {
            token.casefold()
            for token in str(self.task.get("title") or "").replace("-", " ").split()
            if len(token) >= 4
        }
        resource_stems = {
            PurePosixPath(path).stem.casefold()
            for path in resource_paths
            if PurePosixPath(path).stem
        }
        relevant: list[str] = []
        tests: list[str] = []
        for path in tracked:
            folded = path.casefold()
            if _is_test_path(path):
                if any(token in folded for token in title_tokens) or any(
                    stem in folded for stem in resource_stems
                ):
                    tests.append(path)
                continue
            if path in resource_paths or any(folded.startswith(root.casefold()) for root in roots):
                if PurePosixPath(path).suffix.casefold() in _TEXT_SUFFIXES:
                    relevant.append(path)
        return {
            "status": "ready",
            "authority": "real_read_only_repository_scope",
            "task_id": self.task_id,
            "lease_id": self.lease_id,
            "source_head": self.source_head,
            "task_contract_sha256": self.task_contract_sha256,
            "exclusive_resource_paths": list(resource_paths),
            "ownership_roots": list(roots),
            "existing_resource_paths": existing_resources,
            "absent_resource_paths": absent_resources,
            "required_policy_paths": [
                path for path in _REQUIRED_POLICY_PATHS if path in tracked
            ],
            "suggested_implementation_paths": relevant[:200],
            "suggested_test_paths": tests[:200],
            "accepted_plan_id": self._accepted.plan_id if self._accepted else None,
        }

    def list_files(self, *, prefix: str = "Assets/", limit: int = 200) -> dict[str, Any]:
        self._assert_checkout()
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise RepositoryScopeError("file-list limit must be from 1 through 1000")
        normalized = _repo_path(prefix, field="prefix")
        if not _under(normalized if normalized.endswith("/") else normalized + "/", _READ_PREFIXES):
            raise RepositoryScopeError("file-list prefix is outside approved read roots")
        matches = [
            path
            for path in self._tracked()
            if path.casefold().startswith(normalized.casefold())
        ]
        return {
            "prefix": normalized,
            "count": min(len(matches), limit),
            "truncated": len(matches) > limit,
            "paths": matches[:limit],
        }

    def search(
        self,
        *,
        query: str,
        prefixes: Iterable[str] = ("Assets/",),
        limit: int = 80,
    ) -> dict[str, Any]:
        self._assert_checkout()
        if type(query) is not str or not query.strip() or len(query) > 160:
            raise RepositoryScopeError("search query must be 1 through 160 characters")
        if any(ord(character) < 32 or ord(character) == 127 for character in query):
            raise RepositoryScopeError("search query contains a control character")
        if type(limit) is not int or not 1 <= limit <= 300:
            raise RepositoryScopeError("search limit must be from 1 through 300")
        normalized_prefixes: list[str] = []
        for item in prefixes:
            path = _repo_path(item, field="search prefix")
            check_path = path if path.endswith("/") else path + "/"
            if not _under(check_path, _READ_PREFIXES):
                raise RepositoryScopeError(f"search prefix is outside approved roots: {path}")
            normalized_prefixes.append(path)
        result = _git(
            self.checkout,
            "grep",
            "-n",
            "-I",
            "-F",
            "--",
            query,
            "HEAD",
            "--",
            *normalized_prefixes,
            check=False,
        )
        if result.returncode not in (0, 1):
            raise RepositoryScopeError("git grep failed while searching the task checkout")
        matches: list[dict[str, Any]] = []
        for line in _decode(result.stdout, label="git grep output").splitlines():
            try:
                identity, line_number, text = line.split(":", 2)
                path = identity.split(":", 1)[-1]
                matches.append(
                    {
                        "path": path,
                        "line": int(line_number),
                        "text": text[:500],
                    }
                )
            except (ValueError, TypeError):
                continue
            if len(matches) >= limit:
                break
        return {
            "query": query,
            "prefixes": normalized_prefixes,
            "count": len(matches),
            "truncated": len(matches) >= limit,
            "matches": matches,
        }

    def read_file(self, *, path: str, start_line: int = 1, end_line: int = 400) -> dict[str, Any]:
        self._assert_checkout()
        normalized = _repo_path(path, field="read path")
        if not _under(normalized, _READ_PREFIXES):
            raise RepositoryScopeError("read path is outside approved repository roots")
        if type(start_line) is not int or type(end_line) is not int:
            raise RepositoryScopeError("line bounds must be integers")
        if start_line < 1 or end_line < start_line or end_line - start_line > 800:
            raise RepositoryScopeError("read range is invalid or exceeds 801 lines")
        result = _git(self.checkout, "show", f"HEAD:{normalized}", check=False)
        if result.returncode != 0:
            raise RepositoryScopeError(f"read path is not a committed file: {normalized}")
        if len(result.stdout) > 512 * 1024:
            raise RepositoryScopeError("read file exceeds the 512 KiB inspection limit")
        text = _decode(result.stdout, label=normalized)
        lines = text.splitlines()
        selected = lines[start_line - 1 : end_line]
        return {
            "path": normalized,
            "start_line": start_line,
            "end_line": start_line + len(selected) - 1 if selected else start_line - 1,
            "total_lines": len(lines),
            "content": "\n".join(selected),
        }

    def _blob_at_head(self, path: str) -> bool:
        result = _git(self.checkout, "cat-file", "-t", f"HEAD:{path}", check=False)
        return result.returncode == 0 and _decode(result.stdout, label="git object type").strip() == "blob"

    def _tree_at_head(self, path: str) -> bool:
        if path in ("", "."):
            return True
        result = _git(self.checkout, "cat-file", "-t", f"HEAD:{path}", check=False)
        return result.returncode == 0 and _decode(result.stdout, label="git object type").strip() == "tree"

    def _is_ignored(self, path: str) -> bool:
        return _git(self.checkout, "check-ignore", "-q", "--", path, check=False).returncode == 0

    def _validate_plan(self, plan: ExecutionScopePlan) -> tuple[str, ...]:
        self._assert_checkout()
        reasons: list[str] = []
        implementation = (*plan.existing_implementation_paths, *plan.new_implementation_paths)
        tests = (*plan.existing_test_paths, *plan.new_test_paths)
        if len(implementation) > 16:
            reasons.append("implementation scope exceeds 16 exact files")
        if len(tests) > 16:
            reasons.append("test scope exceeds 16 exact files")
        if len(implementation) + len(tests) > 24:
            reasons.append("combined scope exceeds 24 exact files")

        tracked_casefold = {path.casefold(): path for path in self._tracked()}
        resource_paths = set(self._resource_paths())
        roots = self._ownership_roots()

        for path in plan.existing_implementation_paths:
            if not _under(path, _IMPLEMENTATION_PREFIXES):
                reasons.append(f"existing implementation path is outside production roots: {path}")
            if _is_test_path(path):
                reasons.append(f"implementation path is under a Tests directory: {path}")
            if not self._blob_at_head(path):
                reasons.append(f"existing implementation path is not a HEAD blob: {path}")
            absolute = self.checkout / PurePosixPath(path)
            if not absolute.is_file() or absolute.is_symlink():
                reasons.append(f"existing implementation path is not a regular checkout file: {path}")
            if resource_paths and path not in resource_paths and roots and not any(
                path.casefold().startswith(root.casefold()) for root in roots
            ):
                reasons.append(f"implementation path is outside task-owned resource roots: {path}")

        for path in plan.new_implementation_paths:
            if not _under(path, _NEW_IMPLEMENTATION_PREFIXES):
                reasons.append(f"new implementation path is outside Assets: {path}")
            if _is_test_path(path):
                reasons.append(f"new implementation path is under a Tests directory: {path}")
            if path.casefold() in tracked_casefold or self._blob_at_head(path):
                reasons.append(f"new implementation path already exists at HEAD: {path}")
            absolute = self.checkout / PurePosixPath(path)
            if absolute.exists() or absolute.is_symlink():
                reasons.append(f"new implementation path already exists in checkout: {path}")
            parent = str(PurePosixPath(path).parent)
            if not self._tree_at_head(parent):
                reasons.append(f"new implementation parent is not a committed Git tree: {parent}")
            if self._is_ignored(path):
                reasons.append(f"new implementation path is ignored: {path}")
            if roots and not any(path.casefold().startswith(root.casefold()) for root in roots):
                reasons.append(f"new implementation path is outside task-owned resource roots: {path}")

        for field, paths, expect_existing in (
            ("existing test", plan.existing_test_paths, True),
            ("new test", plan.new_test_paths, False),
        ):
            for path in paths:
                if not _under(path, _TEST_PREFIXES):
                    reasons.append(f"{field} path is outside Assets/Packages: {path}")
                if not _is_test_path(path):
                    reasons.append(f"{field} path is not under a Tests directory: {path}")
                if PurePosixPath(path).suffix.casefold() not in (".cs", ".asmdef", ".asmref"):
                    reasons.append(f"{field} path is not a Unity test source/assembly file: {path}")
                exists = self._blob_at_head(path)
                absolute = self.checkout / PurePosixPath(path)
                if expect_existing:
                    if not exists or not absolute.is_file() or absolute.is_symlink():
                        reasons.append(f"existing test path is not a regular HEAD file: {path}")
                else:
                    if exists or path.casefold() in tracked_casefold or absolute.exists() or absolute.is_symlink():
                        reasons.append(f"new test path already exists: {path}")
                    parent = str(PurePosixPath(path).parent)
                    if not self._tree_at_head(parent):
                        reasons.append(f"new test parent is not a committed Git tree: {parent}")
                    if self._is_ignored(path):
                        reasons.append(f"new test path is ignored: {path}")

        for path in (*implementation, *tests):
            top = PurePosixPath(path).parts[0]
            if top in _PROTECTED_TOP_LEVEL:
                reasons.append(f"protected repository area cannot be an ExecutionCrew write path: {path}")
            if PurePosixPath(path).suffix.casefold() not in _TEXT_SUFFIXES:
                reasons.append(f"write path is not an approved text asset type: {path}")

        if not any(PurePosixPath(path).suffix.casefold() == ".cs" for path in tests):
            reasons.append("test scope requires at least one C# test file")
        return tuple(dict.fromkeys(reasons))

    def validate(self, plan: ExecutionScopePlan) -> ScopeValidationResult:
        reasons = self._validate_plan(plan)
        if reasons:
            return ScopeValidationResult(False, reasons, None)
        identity = {
            "schema_version": SCOPE_SCHEMA_VERSION,
            "task_id": self.task_id,
            "lease_id": self.lease_id,
            "source_head": self.source_head,
            "task_contract_sha256": self.task_contract_sha256,
            "plan": plan.to_dict(),
        }
        plan_id = f"scope-{semantic_sha256(identity)}"
        accepted = AcceptedExecutionScope(
            plan_id=plan_id,
            task_id=self.task_id,
            lease_id=self.lease_id,
            source_head=self.source_head,
            task_contract_sha256=self.task_contract_sha256,
            plan=plan,
        )
        self.state_root.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(accepted.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, self.state_path)
        self._accepted = accepted
        return ScopeValidationResult(True, (), plan_id)

    def require(self, plan_id: str) -> AcceptedExecutionScope:
        if self._accepted is None or self._accepted.plan_id != plan_id:
            raise RepositoryScopeError("ExecutionCrew requires the current accepted plan_id")
        reasons = self._validate_plan(self._accepted.plan)
        if reasons:
            raise RepositoryScopeError(
                "previously accepted scope is no longer valid: " + "; ".join(reasons)
            )
        return self._accepted

    def _load_current(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            plan = ExecutionScopePlan.from_dict(raw["plan"])
            accepted = AcceptedExecutionScope(
                plan_id=raw["plan_id"],
                task_id=raw["task_id"],
                lease_id=raw["lease_id"],
                source_head=raw["source_head"],
                task_contract_sha256=raw["task_contract_sha256"],
                plan=plan,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, TaskReviewContractError):
            return
        if (
            raw.get("schema_version") != SCOPE_SCHEMA_VERSION
            or accepted.task_id != self.task_id
            or accepted.lease_id != self.lease_id
            or accepted.source_head != self.source_head
            or accepted.task_contract_sha256 != self.task_contract_sha256
        ):
            return
        expected_id = "scope-" + semantic_sha256(
            {
                "schema_version": SCOPE_SCHEMA_VERSION,
                "task_id": self.task_id,
                "lease_id": self.lease_id,
                "source_head": self.source_head,
                "task_contract_sha256": self.task_contract_sha256,
                "plan": plan.to_dict(),
            }
        )
        if accepted.plan_id != expected_id or self._validate_plan(plan):
            return
        self._accepted = accepted
