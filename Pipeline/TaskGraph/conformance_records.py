from __future__ import annotations

"""Schema and Git-object helpers for immutable conformance records."""

import hashlib
import json
import os
import posixpath
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = "1.0"
CANON_PATH = "Docs/GDD/No_Safe_Circle_GDD.md"
EVIDENCE_ROOT = "Pipeline/TaskGraph/evidence"
TASK_ID_PATTERN = r"NSC-(?:[0-9]{3}|[1-9][0-9]{3,8})"
TASK_ID_RE = re.compile(rf"^{TASK_ID_PATTERN}$")
HEX_RE = re.compile(r"[0-9a-f]{40}")
FORBIDDEN_AUTHORITY_FIELDS = {"status", "complete", "current", "ready", "authorized"}

# One committed tree is enumerated with a single `git ls-tree -r -l` and its
# blobs are read with a single `git cat-file --batch`, the bulk pattern
# Pipeline/TaskReviewAgent/source_commit_snapshot.py already established for
# this regression class. Without it every path question costs its own Git
# process, so `taskcontrol.py states` spent ~603 processes and ~23 s asking
# about one unchanging commit.
#
# A blob larger than this is fetched on its own instead of riding along in a
# group read, so one large committed artifact cannot make its whole directory
# too expensive to batch.
_BULK_BLOB_MAX_BYTES = 128 * 1024
# The widest committed subtree a single group read may cover.
_BULK_GROUP_MAX_BLOBS = 4096
_BULK_GROUP_MAX_BYTES = 8 * 1024 * 1024
# Total committed content one repository handle will retain.
_BULK_CONTENT_MAX_BYTES = 64 * 1024 * 1024
# `<mode> SP <type> SP <object> SP <size> HT <path>` from `git ls-tree -r -l`.
_LS_TREE_ENTRY_RE = re.compile(rb"([0-7]{6}) ([a-z]+) ([0-9a-f]{40}) *(-|[0-9]+)\t(.+)")
_GIT_PATH_ESCAPES = {
    ord("a"): 7, ord("b"): 8, ord("f"): 12, ord("n"): 10, ord("r"): 13,
    ord("t"): 9, ord("v"): 11, ord("\\"): 92, ord('"'): 34,
}
# `git ls-tree` interprets these as pathspec magic or wildcards. A prefix that
# contains one is answered by Git itself rather than by a literal comparison.
_PATHSPEC_MAGIC = set("*?[]:")


class ConformanceRecordError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommittedRecord:
    path: str
    data: dict[str, Any]

    @property
    def record_id(self) -> str:
        return self.data["record_id"]

    @property
    def validated_commit(self) -> str:
        return self.data["validated_state"]["commit"]


def _unquote_git_path(raw: bytes) -> bytes | None:
    """Return the exact repository bytes `git ls-tree` printed as ``raw``.

    Git C-quotes a path that contains a control byte, a quote, a backslash or
    (with the default ``core.quotePath``) any byte above ASCII. Returns None
    for anything this decoder cannot reproduce exactly, which makes the whole
    listing unusable rather than guessed.
    """

    if not raw.startswith(b'"'):
        return raw
    if len(raw) < 2 or not raw.endswith(b'"'):
        return None
    body = raw[1:-1]
    decoded = bytearray()
    index = 0
    while index < len(body):
        byte = body[index]
        if byte != 0x5C:  # backslash
            decoded.append(byte)
            index += 1
            continue
        index += 1
        if index >= len(body):
            return None
        marker = body[index]
        if marker in _GIT_PATH_ESCAPES:
            decoded.append(_GIT_PATH_ESCAPES[marker])
            index += 1
            continue
        digits = body[index : index + 3]
        if len(digits) != 3 or any(digit not in b"01234567" for digit in digits):
            return None
        value = int(digits, 8)
        if value > 0xFF:
            return None
        decoded.append(value)
        index += 3
    return bytes(decoded)


class _CommittedTree:
    """Every entry of one exact committed tree, read in a single Git process.

    The listing is the same tree `git cat-file -e`, `git rev-parse <commit>:`,
    `git show <commit>:` and `git ls-tree` would each walk on their own, so
    answering from it is the same answer with one process instead of one per
    question. It is only ever built for an exact commit ID, never for a name
    that can move.
    """

    __slots__ = ("names", "raw_paths", "blobs", "opaque", "directories", "_totals")

    def __init__(self) -> None:
        self.names: list[bytes] = []
        self.raw_paths: list[bytes] = []
        self.blobs: dict[str, tuple[str, int]] = {}
        self.opaque: set[str] = set()
        self.directories: set[str] = set()
        self._totals: dict[str, list[int]] = {"": [0, 0]}

    def _record_totals(self, path: str, size: int) -> None:
        """Accumulate the batch-eligible weight of every ancestor directory."""

        self._totals[""][0] += 1
        self._totals[""][1] += size
        cursor = ""
        for part in path.split("/")[:-1]:
            cursor = part if not cursor else f"{cursor}/{part}"
            totals = self._totals.setdefault(cursor, [0, 0])
            totals[0] += 1
            totals[1] += size

    def _fits(self, directory: str) -> bool:
        count, size = self._totals.get(directory, (0, 0))
        return count <= _BULK_GROUP_MAX_BLOBS and size <= _BULK_GROUP_MAX_BYTES

    def bulk_group(self, path: str) -> str | None:
        """The widest ancestor directory worth reading in one batch, or None.

        Reading the whole directory a wanted blob lives in collapses the
        repeated per-file reads this evaluator makes (every ``Tasks/*.yaml``,
        every committed record) into one process. Widening stops as soon as an
        ancestor exceeds the group caps, so a big subtree is never pulled in to
        answer a single question.
        """

        group = path.rpartition("/")[0]
        if not self._fits(group):
            return None
        while group:
            ancestor = group.rpartition("/")[0]
            if not self._fits(ancestor):
                break
            group = ancestor
        return group

    def group_blobs(self, group: str) -> Iterator[tuple[str, int]]:
        """Batch-eligible ``(object, size)`` pairs under ``group``, in tree order."""

        prefix = "" if not group else f"{group}/"
        for path, (object_name, size) in self.blobs.items():
            if size <= _BULK_BLOB_MAX_BYTES and path.startswith(prefix):
                yield object_name, size

    def listing(self, prefix: str) -> bytes:
        """Reproduce `git ls-tree -r --name-only <commit> -- <prefix>` exactly.

        Git matches a literal pathspec at path-component boundaries and prints
        entries in tree order using the same quoting this listing was parsed
        from, so the emitted bytes are the bytes Git would have emitted.
        """

        wanted = prefix.encode("utf-8")
        bounded = wanted + b"/"
        return b"".join(
            name + b"\n"
            for name, raw in zip(self.names, self.raw_paths)
            if raw == wanted or raw.startswith(bounded)
        )


def _read_committed_tree(root: Path, commit: str) -> _CommittedTree | None:
    """List one exact commit in a single process, or None to defer to Git.

    Any listing this parser cannot reproduce byte for byte -- a failed
    command, an unexpected line, a quoted path it cannot decode -- yields None
    so every caller falls back to the exact per-object Git command instead of
    trusting a partial view.
    """

    result = subprocess.run(
        ["git", "ls-tree", "-r", "-l", commit], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        return None
    tree = _CommittedTree()
    for line in result.stdout.split(b"\n"):
        if not line:
            continue
        entry = _LS_TREE_ENTRY_RE.fullmatch(line)
        if entry is None:
            return None
        _mode, object_type, object_name, size_text, name = entry.groups()
        raw = _unquote_git_path(name)
        if raw is None:
            return None
        tree.names.append(name)
        tree.raw_paths.append(raw)
        try:
            path: str | None = raw.decode("utf-8")
        except UnicodeDecodeError:
            # No `str` a caller can pass encodes to these bytes, so the entry
            # is unreachable by path and only has to survive `files()`.
            path = None
        cursor = b""
        for part in raw.split(b"/")[:-1]:
            cursor = part if not cursor else cursor + b"/" + part
            try:
                tree.directories.add(cursor.decode("utf-8"))
            except UnicodeDecodeError:
                break
        if object_type != b"blob" or size_text == b"-":
            if path is not None:
                tree.opaque.add(path)
            continue
        size = int(size_text)
        if path is None:
            continue
        tree.blobs[path] = (object_name.decode("ascii"), size)
        if size <= _BULK_BLOB_MAX_BYTES:
            tree._record_totals(path, size)
    return tree


def _read_blob_batch(root: Path, requests: list[tuple[str, int]]) -> dict[str, bytes] | None:
    """Read many committed blobs through one `git cat-file --batch` process.

    `git cat-file --batch` streams the same raw object bytes
    `git show <commit>:<path>` prints, so a blob served from here is the same
    blob. Returns None on any protocol surprise, which sends the caller back
    to its own Git process rather than to a guess.
    """

    payload = "".join(f"{object_name}\n" for object_name, _size in requests)
    try:
        result = subprocess.run(
            ["git", "cat-file", "--batch"], cwd=root, input=payload.encode("ascii"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    except OSError:
        return None
    if result.returncode:
        return None
    stream = result.stdout
    contents: dict[str, bytes] = {}
    offset = 0
    for object_name, size in requests:
        newline = stream.find(b"\n", offset)
        if newline < 0:
            return None
        header = stream[offset:newline].split()
        if len(header) != 3 or header[0] != object_name.encode("ascii") or header[1] != b"blob":
            return None
        if not header[2].isdigit() or int(header[2]) != size:
            return None
        start = newline + 1
        end = start + size
        # `git cat-file --batch` writes exactly one newline after each object.
        if end >= len(stream) or stream[end] != 0x0A:
            return None
        contents[object_name] = stream[start:end]
        offset = end + 1
    if offset != len(stream):
        return None
    return contents


class GitRepository:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        # Committed content is immutable, so it is cached per exact commit ID
        # for the life of this handle. Nothing here is keyed by a name that can
        # move, and no mutable repository state (HEAD, the work tree, refs) is
        # ever cached.
        self._committed_trees: dict[str, _CommittedTree | None] = {}
        self._committed_blobs: dict[str, bytes] = {}
        self._committed_groups: set[tuple[str, str]] = set()
        self._committed_bytes = 0
        self._bulk_supported: bool | None = None

    def _run(self, *args: str, check: bool = True) -> bytes:
        result = subprocess.run(
            ["git", *args], cwd=self.root, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
        if check and result.returncode:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise ConformanceRecordError(f"git {' '.join(args)} failed: {detail}")
        return result.stdout

    def _bulk_reads_supported(self) -> bool:
        """Whether a bulk listing of this root can answer the same questions.

        `git ls-tree` resolves its pathspec and prints its paths relative to
        the current directory, while ``<commit>:<path>`` is always relative to
        the top of the tree. The two only agree when this root is the work-tree
        top level, so a subdirectory, a bare repository, or an externally
        pointed ``GIT_DIR``/``GIT_WORK_TREE`` keeps using the exact per-object
        commands instead of a listing that could mean something else.
        """

        if self._bulk_supported is None:
            self._bulk_supported = not any(
                os.environ.get(name)
                for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")
            ) and (self.root / ".git").exists()
        return self._bulk_supported

    def _committed_tree(self, commit: str) -> _CommittedTree | None:
        """The cached listing of an exact commit, or None to ask Git directly.

        Only a fully resolved 40-character commit ID is ever a cache key. A
        symbolic name such as ``HEAD``, a branch or a tag can point somewhere
        else between two calls, so it is never cached and never serves content.
        """

        if not self._bulk_reads_supported() or HEX_RE.fullmatch(commit) is None:
            return None
        if commit not in self._committed_trees:
            self._committed_trees[commit] = _read_committed_tree(self.root, commit)
        return self._committed_trees[commit]

    def _batch_request(
        self, tree: _CommittedTree, commit: str, path: str, object_name: str, size: int
    ) -> list[tuple[str, int]]:
        group = None
        if self._committed_bytes < _BULK_CONTENT_MAX_BYTES:
            group = tree.bulk_group(path)
        if group is None or (commit, group) in self._committed_groups:
            return [(object_name, size)]
        self._committed_groups.add((commit, group))
        requests = [(object_name, size)]
        wanted = {object_name}
        for candidate, length in tree.group_blobs(group):
            if candidate in wanted or candidate in self._committed_blobs:
                continue
            wanted.add(candidate)
            requests.append((candidate, length))
        return requests

    def _committed_blob(self, commit: str, path: str) -> bytes | None:
        """One committed blob's exact bytes from the bulk read, or None."""

        tree = self._committed_tree(commit)
        if tree is None:
            return None
        entry = tree.blobs.get(path)
        if entry is None:
            return None
        object_name, size = entry
        cached = self._committed_blobs.get(object_name)
        if cached is not None:
            return cached
        contents = _read_blob_batch(
            self.root, self._batch_request(tree, commit, path, object_name, size)
        )
        if contents is None:
            return None
        for name, payload in contents.items():
            if name not in self._committed_blobs:
                self._committed_blobs[name] = payload
                self._committed_bytes += len(payload)
        return contents.get(object_name)

    def head(self) -> str:
        return self._run("rev-parse", "HEAD").decode().strip()

    def tree(self, commit: str) -> str:
        return self._run("rev-parse", f"{commit}^{{tree}}").decode().strip()

    def read(self, commit: str, path: str) -> bytes:
        safe_repository_path(path, "Git object path")
        committed = self._committed_blob(commit, path)
        if committed is not None:
            return committed
        return self._run("show", f"{commit}:{path}")

    def blob(self, commit: str, path: str) -> str:
        safe_repository_path(path, "Git blob path")
        tree = self._committed_tree(commit)
        entry = None if tree is None else tree.blobs.get(path)
        if entry is not None:
            value = entry[0]
        else:
            value = self._run("rev-parse", f"{commit}:{path}").decode().strip()
        if not HEX_RE.fullmatch(value):
            raise ConformanceRecordError(f"{path!r} is not a committed blob at {commit}.")
        return value

    def exists(self, commit: str, path: str) -> bool:
        safe_repository_path(path, "Git object path")
        tree = self._committed_tree(commit)
        # A non-blob leaf (a submodule gitlink) exists only when its own object
        # is present in this repository, which the listing cannot say.
        if tree is not None and path not in tree.opaque:
            return path in tree.blobs or path in tree.directories
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}:{path}"], cwd=self.root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        return result.returncode == 0

    def files(self, commit: str, prefix: str) -> list[str]:
        safe_repository_path(prefix, "Git tree prefix")
        tree = None
        if not any(character in _PATHSPEC_MAGIC for character in prefix):
            tree = self._committed_tree(commit)
        if tree is not None:
            output = tree.listing(prefix)
        else:
            output = self._run("ls-tree", "-r", "--name-only", commit, "--", prefix)
        return [line for line in output.decode("utf-8").splitlines() if line]

    def is_ancestor(self, older: str, newer: str) -> bool:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer], cwd=self.root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        return result.returncode == 0

    def dirty(self) -> bool:
        return bool(self._run("status", "--porcelain"))

    def path_history(self, commit: str, path: str) -> list[str]:
        safe_repository_path(path, "Git history path")
        output = self._run("log", "--format=%H", commit, "--", path)
        return [line for line in output.decode("utf-8").splitlines() if line]


def safe_repository_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConformanceRecordError(f"{label} must be a non-empty repository path.")
    if any(ord(character) < 32 for character in value):
        raise ConformanceRecordError(f"{label} contains a control character.")
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
        raise ConformanceRecordError(f"{label} must be relative: {value!r}.")
    if "\\" in value or posixpath.normpath(value) != value or value in {".", ".."}:
        raise ConformanceRecordError(f"{label} is not a canonical repository path: {value!r}.")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ConformanceRecordError(f"{label} contains path traversal: {value!r}.")
    return value


def semantic_json_sha256(raw: bytes | str | Any) -> str:
    if isinstance(raw, bytes):
        value = json.loads(raw.decode("utf-8-sig"))
    elif isinstance(raw, str):
        value = json.loads(raw.lstrip("\ufeff"))
    else:
        value = raw
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_text_sha256(raw: bytes | str) -> str:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _object(value: Any, label: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConformanceRecordError(f"{label} must be an object.")
    extra = set(value) - fields
    missing = fields - set(value)
    if extra or missing:
        raise ConformanceRecordError(
            f"{label} fields differ from schema (missing={sorted(missing)}, extra={sorted(extra)})."
        )
    return value


def _text(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ConformanceRecordError(f"{label} must be a {'string' if allow_empty else 'non-empty string'}.")
    return value


def _sha(value: Any, label: str) -> str:
    value = _text(value, label)
    if not HEX_RE.fullmatch(value):
        raise ConformanceRecordError(f"{label} must be a lowercase 40-character Git SHA.")
    return value


def validate_record_shape(record: Any, path: str) -> dict[str, Any]:
    common = {
        "schema_version", "record_type", "record_id", "task_id", "task_contract",
        "canon", "validated_state", "conformance_surfaces", "gate_results",
        "human_approval", "recorded_at",
    }
    if not isinstance(record, dict):
        raise ConformanceRecordError(f"{path}: record must be an object.")
    forbidden = FORBIDDEN_AUTHORITY_FIELDS.intersection(record)
    if forbidden:
        raise ConformanceRecordError(f"{path}: mutable authority fields are forbidden: {sorted(forbidden)}.")
    record_type = record.get("record_type")
    specific = (
        "delivery" if record_type == "delivery"
        else "baseline" if record_type == "baseline"
        else "revalidation" if record_type == "revalidation"
        else None
    )
    if specific is None:
        raise ConformanceRecordError(f"{path}: record_type must be delivery, baseline, or revalidation.")
    _object(record, path, common | {specific})
    if record["schema_version"] != SCHEMA_VERSION:
        raise ConformanceRecordError(f"{path}: unsupported schema_version {record['schema_version']!r}.")

    task_id = _text(record["task_id"], f"{path}.task_id")
    if not TASK_ID_RE.fullmatch(task_id):
        raise ConformanceRecordError(f"{path}: invalid task_id {task_id!r}.")
    record_id = _text(record["record_id"], f"{path}.record_id")
    prefix = {"delivery": "DEL-", "baseline": "BASE-", "revalidation": "REV-"}[record_type]
    if not record_id.startswith(f"{prefix}{task_id}-"):
        raise ConformanceRecordError(f"{path}: record_id prefix/task identity mismatch.")
    expected_prefix = f"{EVIDENCE_ROOT}/{task_id}/records/"
    if not path.startswith(expected_prefix) or path != f"{expected_prefix}{record_id}.json":
        raise ConformanceRecordError(f"{path}: record path, task_id, filename, and record_id disagree.")

    contract = _object(record["task_contract"], f"{path}.task_contract", {"path", "revision", "sha256"})
    safe_repository_path(contract["path"], f"{path}.task_contract.path")
    if isinstance(contract["revision"], bool) or not isinstance(contract["revision"], int) or contract["revision"] < 1:
        raise ConformanceRecordError(f"{path}.task_contract.revision must be a positive integer.")
    if not re.fullmatch(r"[0-9a-f]{64}", _text(contract["sha256"], f"{path}.task_contract.sha256")):
        raise ConformanceRecordError(f"{path}.task_contract.sha256 must be lowercase SHA-256.")
    canon = _object(record["canon"], f"{path}.canon", {"path", "sha256"})
    safe_repository_path(canon["path"], f"{path}.canon.path")
    if not re.fullmatch(r"[0-9a-f]{64}", _text(canon["sha256"], f"{path}.canon.sha256")):
        raise ConformanceRecordError(f"{path}.canon.sha256 must be lowercase SHA-256.")
    state = _object(record["validated_state"], f"{path}.validated_state", {"commit", "tree"})
    _sha(state["commit"], f"{path}.validated_state.commit")
    _sha(state["tree"], f"{path}.validated_state.tree")

    surfaces = record["conformance_surfaces"]
    if not isinstance(surfaces, list):
        raise ConformanceRecordError(f"{path}.conformance_surfaces must be a list.")
    surface_paths: set[str] = set()
    for index, raw in enumerate(surfaces):
        surface = _object(raw, f"{path}.conformance_surfaces[{index}]", {"path", "blob_sha", "role"})
        item_path = safe_repository_path(surface["path"], f"{path}.conformance_surfaces[{index}].path")
        if item_path in surface_paths:
            raise ConformanceRecordError(f"{path}: duplicate conformance surface path {item_path!r}.")
        surface_paths.add(item_path)
        _sha(surface["blob_sha"], f"{path}.conformance_surfaces[{index}].blob_sha")
        _text(surface["role"], f"{path}.conformance_surfaces[{index}].role")

    gates = record["gate_results"]
    if not isinstance(gates, list):
        raise ConformanceRecordError(f"{path}.gate_results must be a list.")
    gate_ids: set[str] = set()
    for index, raw in enumerate(gates):
        gate = _object(raw, f"{path}.gate_results[{index}]", {"gate_id", "result", "evidence", "notes"})
        gate_id = _text(gate["gate_id"], f"{path}.gate_results[{index}].gate_id")
        if gate_id in gate_ids:
            raise ConformanceRecordError(f"{path}: duplicate gate_id {gate_id!r}.")
        gate_ids.add(gate_id)
        if gate["result"] != "pass":
            raise ConformanceRecordError(f"{path}: only a pass gate result can establish conformance.")
        if not isinstance(gate["evidence"], list):
            raise ConformanceRecordError(f"{path}.gate_results[{index}].evidence must be a list.")
        for evidence_index, raw_evidence in enumerate(gate["evidence"]):
            evidence = _object(raw_evidence, f"{path}.gate_results[{index}].evidence[{evidence_index}]", {"path", "blob_sha"})
            safe_repository_path(evidence["path"], f"{path}.gate_results[{index}].evidence[{evidence_index}].path")
            _sha(evidence["blob_sha"], f"{path}.gate_results[{index}].evidence[{evidence_index}].blob_sha")
        _text(gate["notes"], f"{path}.gate_results[{index}].notes", allow_empty=True)

    approval = _object(record["human_approval"], f"{path}.human_approval", {"required", "decision", "approved_by", "notes"})
    if not isinstance(approval["required"], bool):
        raise ConformanceRecordError(f"{path}.human_approval.required must be boolean.")
    if approval["decision"] not in {"approved", "not_required"}:
        raise ConformanceRecordError(f"{path}.human_approval.decision is unsupported.")
    _text(approval["approved_by"], f"{path}.human_approval.approved_by", allow_empty=True)
    _text(approval["notes"], f"{path}.human_approval.notes", allow_empty=True)
    _text(record["recorded_at"], f"{path}.recorded_at")

    if record_type == "delivery":
        delivery = _object(record["delivery"], f"{path}.delivery", {"base_commit", "candidate_commit", "integrated_commit", "integrated_tree"})
        for field in delivery:
            _sha(delivery[field], f"{path}.delivery.{field}")
        if state["commit"] != delivery["integrated_commit"] or state["tree"] != delivery["integrated_tree"]:
            raise ConformanceRecordError(f"{path}: delivery integrated and validated states must match.")
    elif record_type == "baseline":
        baseline = _object(record["baseline"], f"{path}.baseline", {"reason_type", "summary"})
        if baseline["reason_type"] != "pre_evidence_existing_implementation":
            raise ConformanceRecordError(f"{path}.baseline.reason_type is unsupported.")
        _text(baseline["summary"], f"{path}.baseline.summary")
    else:
        revalidation = _object(record["revalidation"], f"{path}.revalidation", {"basis_record_id", "reason_type", "summary"})
        _text(revalidation["basis_record_id"], f"{path}.revalidation.basis_record_id")
        if revalidation["reason_type"] not in {"code_change", "gdd_change", "contract_change", "periodic", "manual"}:
            raise ConformanceRecordError(f"{path}.revalidation.reason_type is unsupported.")
        _text(revalidation["summary"], f"{path}.revalidation.summary")
    return record


def load_committed_records(repo: GitRepository, head: str, task_id: str) -> list[CommittedRecord]:
    prefix = f"{EVIDENCE_ROOT}/{task_id}/records"
    records: list[CommittedRecord] = []
    ids: set[str] = set()
    for path in repo.files(head, prefix):
        if not path.endswith(".json"):
            raise ConformanceRecordError(f"Unsupported committed record file: {path}.")
        if len(repo.path_history(head, path)) != 1:
            raise ConformanceRecordError(
                f"Immutable record {path} was modified, deleted/recreated, or has ambiguous history."
            )
        try:
            value = json.loads(repo.read(head, path).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConformanceRecordError(f"Unable to parse committed record {path}: {exc}") from exc
        validate_record_shape(value, path)
        if value["record_id"] in ids:
            raise ConformanceRecordError(f"Duplicate record_id {value['record_id']!r}.")
        ids.add(value["record_id"])
        records.append(CommittedRecord(path, value))
    return records
