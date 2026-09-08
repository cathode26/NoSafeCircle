"""One immutable, commit-keyed view of the repository facts admission reads.

Admission re-reads the same immutable repository facts many times: once per
candidate while a portfolio is built, again for every architect batch, and
again before each individual launch. Each re-read cost its own Git
subprocess. In the measured 1,000-contract component run that was 6,306
``rev-parse`` observations (6,163 of them one-per-candidate HEAD checks), and
in the live path it is far worse: production Stage 2 loads every committed
task contract with its own ``git show``, so 1,000 contracts across 1,262
Stage-2 observations implies more than 1,262,000 task-contract subprocesses
before any other Git work.

A :class:`SourceCommitAdmissionSnapshot` is keyed strictly by ONE exact
verified source commit and holds only facts that cannot change while that
commit is the observed HEAD:

* every committed ``Tasks/<TASK-ID>.yaml`` contract, its exact bytes and the
  deterministic ``task_contract_sha256`` those bytes produce;
* the bulk TaskGraph state observation admission needs;
* the decomposition policy document and its repository-wide audit result;
* a lazy inventory of the paths that exist in the committed tree.

Everything here is derived from the commit alone, so two observations of the
same commit are the same answer and the snapshot may be shared.

What this module must never hold is the mutable coordination authority a
launch depends on: GitHub Issues, their comments, events and labels, Stage 1
claims, agent leases, integration reservations, active-checkout observations,
source-refresh outcomes, scheduler health, and worker/provider state. A
launched child can claim an Issue and change that authority underneath the
scheduler, so every launch must re-observe it. The snapshot deliberately
offers no way to store it.

The cache is bounded. Obsolete commits are evicted rather than accumulating
for the lifetime of a long-running scheduler, and
:func:`discard_source_commit_snapshots` is the explicit discard for a caller
that has just proven HEAD moved.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Iterable, Mapping

from .committed_tasks import CommittedTaskError
from .contracts import TASK_ID_RE, validate_task_id

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_TASKS_PREFIX = "Tasks/"
_TASKS_SUFFIX = ".yaml"
_DECOMPOSITION_POLICY_PATH = (
    "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
)
# Two commits are enough for the one legitimate overlap: an in-flight poll
# holding the commit it verified while a newer HEAD is observed. Anything
# older is obsolete by construction, so it is evicted instead of retained.
SNAPSHOT_CACHE_LIMIT = 2
_GIT_TIMEOUT_SECONDS = 300.0


class SourceCommitSnapshotError(CommittedTaskError):
    """Raised when the immutable facts of one exact commit cannot be proven."""


def _exact_commit(commit: Any) -> str:
    if type(commit) is not str or _COMMIT.fullmatch(commit) is None:
        raise SourceCommitSnapshotError(
            "admission snapshot requires one exact lowercase 40-character Git commit ID"
        )
    return commit


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ("git", "-C", str(root), *args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceCommitSnapshotError(
            f"Git observation failed for {root}: {type(exc).__name__}: {exc}"
        ) from exc


def _git_stdout(root: Path, *args: str) -> bytes:
    result = _run_git(root, *args)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SourceCommitSnapshotError(
            f"git {' '.join(args)} failed ({result.returncode})"
            + (f": {detail[:500]}" if detail else "")
        )
    return result.stdout


def _parse_contract(task_id: str, payload: bytes) -> dict[str, Any]:
    """Parse and validate one committed contract exactly as the loader does.

    This mirrors :func:`Pipeline.TaskReviewAgent.committed_tasks.load_committed_task`
    field for field, including the ``utf-8-sig`` decode and the
    ``exclusive_resources`` shape check, so a contract served from the
    snapshot is the same value and the same refusal as a contract read with
    its own ``git show``.
    """

    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceCommitSnapshotError(
            f"committed task contract is invalid JSON: {_TASKS_PREFIX}{task_id}{_TASKS_SUFFIX}"
        ) from exc
    if not isinstance(value, dict) or value.get("id") != task_id:
        raise SourceCommitSnapshotError(
            f"committed task identity mismatch: {_TASKS_PREFIX}{task_id}{_TASKS_SUFFIX}"
        )
    resources = value.get("exclusive_resources")
    if resources is not None and (
        not isinstance(resources, list)
        or any(not isinstance(item, str) or not item.strip() for item in resources)
    ):
        raise SourceCommitSnapshotError(
            "committed task exclusive_resources must be a list of non-empty strings: "
            f"{_TASKS_PREFIX}{task_id}{_TASKS_SUFFIX}"
        )
    return {**value, "task_contract_sha256": hashlib.sha256(payload).hexdigest()}


def _load_committed_blobs(
    root: Path, commit: str
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """Read admission's committed blobs in two subprocesses.

    ``git ls-tree`` names the exact blob for each contract and one
    ``git cat-file --batch`` streams all of them, so the cost is two
    processes for the whole repository instead of one ``git show`` per task.
    The bytes are the same bytes ``git show`` would print, so the
    ``task_contract_sha256`` derived from them is identical.

    Only the bytes are read here. Parsing stays per task
    (:meth:`SourceCommitAdmissionSnapshot.task`) because a malformed
    individual contract must reject exactly that task -- the behavior a
    per-task ``git show`` loader already had -- rather than failing the whole
    repository observation and hiding every other admissible task behind it.
    """

    listing = _git_stdout(
        root,
        "ls-tree",
        "-r",
        "-z",
        "--format=%(objectname) %(path)",
        commit,
        "--",
        "Tasks",
        _DECOMPOSITION_POLICY_PATH,
    )
    wanted: list[tuple[str, str, str]] = []
    for entry in listing.split(b"\x00"):
        if not entry:
            continue
        try:
            text = entry.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceCommitSnapshotError(
                "committed task listing was not UTF-8"
            ) from exc
        object_name, separator, path = text.partition(" ")
        if not separator:
            continue
        if path == _DECOMPOSITION_POLICY_PATH:
            wanted.append(("file", path, object_name))
            continue
        if not path.startswith(_TASKS_PREFIX) or not path.endswith(_TASKS_SUFFIX):
            continue
        task_id = path[len(_TASKS_PREFIX) : -len(_TASKS_SUFFIX)]
        if TASK_ID_RE.fullmatch(task_id) is None:
            continue
        wanted.append(("task", task_id, object_name))
    if not wanted:
        return {}, {}

    request = "".join(
        f"{object_name}\n" for _kind, _identity, object_name in wanted
    )
    try:
        batch = subprocess.run(
            ("git", "-C", str(root), "cat-file", "--batch"),
            input=request.encode("ascii"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceCommitSnapshotError(
            f"bulk committed task read failed for {root}: {type(exc).__name__}: {exc}"
        ) from exc
    if batch.returncode != 0:
        detail = batch.stderr.decode("utf-8", errors="replace").strip()
        raise SourceCommitSnapshotError(
            "bulk committed task read failed"
            + (f": {detail[:500]}" if detail else "")
        )

    blobs: dict[str, bytes] = {}
    committed_blobs: dict[str, bytes] = {}
    stream = batch.stdout
    offset = 0
    for kind, identity, object_name in wanted:
        newline = stream.find(b"\n", offset)
        if newline < 0:
            raise SourceCommitSnapshotError(
                f"bulk committed blob read ended before {identity}"
            )
        header = stream[offset:newline].decode("utf-8", errors="replace").split()
        if len(header) != 3 or header[0] != object_name or header[1] != "blob":
            raise SourceCommitSnapshotError(
                f"bulk committed blob read returned an unexpected object for {identity}: "
                f"{' '.join(header)[:200]}"
            )
        try:
            size = int(header[2])
        except ValueError as exc:
            raise SourceCommitSnapshotError(
                f"bulk committed blob read returned a malformed size for {identity}"
            ) from exc
        start = newline + 1
        end = start + size
        if end > len(stream):
            raise SourceCommitSnapshotError(
                f"bulk committed blob read was truncated at {identity}"
            )
        if kind == "task":
            blobs[identity] = stream[start:end]
        else:
            committed_blobs[identity] = stream[start:end]
        # git cat-file --batch writes one trailing newline after each blob.
        offset = end + 1
    return blobs, committed_blobs


@dataclass(frozen=True)
class SourceCommitAdmissionSnapshot:
    """Immutable repository facts for exactly one verified source commit.

    Every field is a fact of ``source_commit`` alone. Nothing mutable lives
    here: Issue state, claims, leases, reservations, checkout observations,
    refresh outcomes and worker state are re-observed per launch by their own
    owners and are deliberately unreachable from this object.
    """

    root: Path
    source_commit: str
    task_blobs: Mapping[str, bytes]
    committed_blobs: Mapping[str, bytes]
    _lazy: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def task_ids(self) -> tuple[str, ...]:
        """Every committed task ID at this commit, in deterministic order."""

        return tuple(sorted(self.task_blobs))

    def task(self, task_id: str) -> dict[str, Any]:
        """Return one committed contract, or fail exactly as a direct read would.

        A missing path and a malformed contract are per-task refusals of the
        same class the per-task loader raised, so one bad contract never
        turns into a repository-wide observation failure.
        """

        task_id = validate_task_id(task_id)
        payload = self.task_blobs.get(task_id)
        if payload is None:
            raise SourceCommitSnapshotError(
                f"committed task contract is missing at {self.source_commit}: "
                f"{_TASKS_PREFIX}{task_id}{_TASKS_SUFFIX}"
            )
        parsed = self._lazy.get(f"contract:{task_id}")
        if parsed is None:
            parsed = _parse_contract(task_id, payload)
            self._lazy[f"contract:{task_id}"] = parsed
        return dict(parsed)

    def task_loader(self) -> Callable[[str], dict[str, Any]]:
        """A ``TaskLoader`` that answers from this commit's bulk read."""

        return self.task

    def committed_json_document(self, relative_path: str) -> Mapping[str, Any]:
        """Parse one JSON authority document already captured at this commit."""

        payload = self.committed_blobs.get(relative_path)
        if payload is None:
            raise SourceCommitSnapshotError(
                f"committed admission document is missing at {self.source_commit}: "
                f"{relative_path}"
            )
        try:
            document = json.loads(payload.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceCommitSnapshotError(
                f"committed admission document is invalid JSON: {relative_path}"
            ) from exc
        if not isinstance(document, Mapping):
            raise SourceCommitSnapshotError(
                f"committed admission document must be a JSON object: {relative_path}"
            )
        return dict(document)

    def committed_path_probe(self) -> Callable[[str], bool]:
        """Return the lazy "does this exact path exist at this commit" oracle.

        The committed tree is listed at most once per snapshot and compared
        case-insensitively for the Windows/Unity checkout contract, so the
        answer is shared by every admission at this commit instead of being
        rebuilt for each architect batch.
        """

        probe = self._lazy.get("path_probe")
        if probe is None:
            probe = _CommittedPathProbe(self.root, self.source_commit)
            self._lazy["path_probe"] = probe
        return probe

    def cached_committed_paths(self) -> frozenset[str] | None:
        """The already-loaded path inventory, or ``None`` while still lazy."""

        probe = self._lazy.get("path_probe")
        return None if probe is None else probe.cached_paths()

    def memoized(self, key: str, produce: Callable[[], Any]) -> Any:
        """Compute one additional immutable fact of this commit exactly once.

        ``key`` names a fact that is derived from this commit alone -- the
        bulk TaskGraph state observation and the repository-wide decomposition
        policy audit are the two admission uses.

        Only a successful observation is memoized. A failure is deliberately
        NOT cached: an unprovable fact still fails closed for its own caller,
        but an operational failure such as a timeout must not become a sticky
        answer that survives for the whole life of the cached commit.
        """

        if type(key) is not str or not key:
            raise SourceCommitSnapshotError("memoized fact key must be exact text")
        memo_key = f"fact:{key}"
        if memo_key not in self._lazy:
            self._lazy[memo_key] = produce()
        return self._lazy[memo_key]


class _CommittedPathProbe:
    """Lazy, case-insensitive committed-path oracle for one exact commit."""

    def __init__(self, root: Path, commit: str) -> None:
        self._root = root
        self._commit = commit
        self._paths: frozenset[str] | None = None

    def cached_paths(self) -> frozenset[str] | None:
        return self._paths

    def _load(self) -> frozenset[str]:
        if self._paths is not None:
            return self._paths
        stdout = _git_stdout(
            self._root, "ls-tree", "-r", "--name-only", "-z", self._commit
        )
        try:
            values = stdout.decode("utf-8").split("\x00")
        except UnicodeDecodeError as exc:
            raise SourceCommitSnapshotError(
                "committed path observation was not UTF-8"
            ) from exc
        self._paths = frozenset(
            value.replace("\\", "/").casefold() for value in values if value
        )
        return self._paths

    def __call__(self, path: str) -> bool:
        normalized = str(path).replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized.casefold() in self._load()


_CACHE: "OrderedDict[tuple[str, str], SourceCommitAdmissionSnapshot]" = OrderedDict()


def source_commit_admission_snapshot(
    root: Path | str,
    source_commit: str,
    *,
    use_cache: bool = True,
) -> SourceCommitAdmissionSnapshot:
    """Return the immutable admission facts for one exact verified commit.

    The snapshot is cached by ``(root, source_commit)`` under a bounded limit,
    so repeated admissions at one HEAD share a single bulk read while obsolete
    commits are evicted instead of accumulating.
    """

    resolved = Path(root).resolve()
    commit = _exact_commit(source_commit)
    key = (str(resolved), commit)
    if use_cache:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key)
            return cached
    task_blobs, committed_blobs = _load_committed_blobs(resolved, commit)
    snapshot = SourceCommitAdmissionSnapshot(
        root=resolved,
        source_commit=commit,
        task_blobs=task_blobs,
        committed_blobs=committed_blobs,
    )
    if use_cache:
        _CACHE[key] = snapshot
        _CACHE.move_to_end(key)
        while len(_CACHE) > SNAPSHOT_CACHE_LIMIT:
            _CACHE.popitem(last=False)
    return snapshot


def discard_source_commit_snapshots(
    *, root: Path | str | None = None, keep_commit: str | None = None
) -> None:
    """Explicitly drop cached snapshots that are known to be obsolete.

    ``keep_commit`` retains the one commit a caller has just verified, which
    is what a scheduler wants after proving HEAD moved.
    """

    if root is None:
        if keep_commit is None:
            _CACHE.clear()
            return
        for key in [key for key in _CACHE if key[1] != keep_commit]:
            _CACHE.pop(key, None)
        return
    resolved = str(Path(root).resolve())
    for key in [
        key
        for key in _CACHE
        if key[0] == resolved and (keep_commit is None or key[1] != keep_commit)
    ]:
        _CACHE.pop(key, None)


def cached_snapshot_commits(root: Path | str | None = None) -> tuple[str, ...]:
    """The commits currently cached, oldest first. Diagnostics and tests only."""

    if root is None:
        return tuple(commit for _root, commit in _CACHE)
    resolved = str(Path(root).resolve())
    return tuple(commit for key_root, commit in _CACHE if key_root == resolved)


def snapshot_task_ids(snapshot: SourceCommitAdmissionSnapshot) -> list[str]:
    """Committed task IDs as the plain list Stage 2 enumerates."""

    return list(snapshot.task_ids)


def iter_snapshot_contracts(
    snapshot: SourceCommitAdmissionSnapshot,
) -> Iterable[tuple[str, Mapping[str, Any]]]:
    """Deterministic ``(task_id, contract)`` pairs for bulk consumers.

    Skips a contract this commit cannot parse, because a bulk consumer asks
    for the tasks that exist rather than for a repository-wide refusal.
    """

    for task_id in snapshot.task_ids:
        try:
            yield task_id, snapshot.task(task_id)
        except SourceCommitSnapshotError:
            continue


__all__ = [
    "SNAPSHOT_CACHE_LIMIT",
    "SourceCommitAdmissionSnapshot",
    "SourceCommitSnapshotError",
    "cached_snapshot_commits",
    "discard_source_commit_snapshots",
    "iter_snapshot_contracts",
    "snapshot_task_ids",
    "source_commit_admission_snapshot",
]
