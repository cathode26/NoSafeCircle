"""Shared vocabulary, safety primitives, and deterministic Git helpers.

This package is a **test fixture and acceptance harness**. It is not No Safe
Circle game-design canon, not TaskGraph authority, and not evidence that any
real task is complete. Every task ID it uses is synthetic (``NSC-901`` and
above) and every repository surface it creates lives inside a fixture root that
this package created itself.

Nothing here contacts GitHub, invokes a model provider, launches a real
TaskReviewAgent worker, or writes outside a fixture root it owns.

Two design rules govern this module:

1. **The verifier owns acceptance, not the adapter.** There is deliberately no
   adapter-kind string, capability declaration, or returned decision string in
   this module that a caller could set in order to manufacture an acceptance
   ``PASS``. See ``verify_acceptance.py`` for where that authority actually
   lives.
2. **Destructive cleanup is proven, not named.** Nothing in this package
   deletes a path because it looks disposable, and nothing deletes a path
   because a caller-supplied record says it owns it. A fixture root is deleted
   only when a module-private ownership registry, populated exclusively by the
   create functions, still binds this exact handle object to that exact
   directory, and the registered marker token plus device/inode identity still
   match on disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = ACCEPTANCE_DIR / "scenarios.json"

MANIFEST_SCHEMA_VERSION = "2.0"
EVIDENCE_SCHEMA_VERSION = "2.0"

SYNTHETIC_TASK_ID_RE = re.compile(r"^NSC-9[0-9]{2}$")
"""Every acceptance task ID is in the reserved synthetic ``NSC-9##`` range.

The production graph and the retired Orchestrator Gauntlet both stop below
``NSC-900``, so a leaked synthetic ID is immediately recognizable and can never
be confused with a real task contract.
"""

SYNTHETIC_SOURCE_DIRECTORY = "SyntheticGame"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AcceptanceSafetyError(RuntimeError):
    """Raised when an operation would touch production-looking state."""


class AcceptanceFixtureError(RuntimeError):
    """Raised when a fixture cannot be built exactly as declared."""


class AcceptanceManifestError(RuntimeError):
    """Raised when the scenario manifest is invalid."""


class PathContainmentError(AcceptanceSafetyError):
    """Raised when a path would escape the root that is allowed to contain it."""


# ---------------------------------------------------------------------------
# Readiness gates
#
# The polling Software Architect implementation is uncommitted. A scenario
# declares what must exist before it can produce an acceptance PASS rather than
# pretending a stub answer is a proof.
# ---------------------------------------------------------------------------

READINESS_GATES: dict[str, str] = {
    "harness_only": (
        "Provable now with fixtures alone. No scheduler behavior is claimed."
    ),
    "ready_after_architect_merge": (
        "Fixture is complete now; acceptance requires the polling architect "
        "scheduler to be committed and wired through the real adapter."
    ),
}

HARNESS_ONLY_GATE = "harness_only"


# ---------------------------------------------------------------------------
# Capabilities
#
# A scenario names the capabilities it consumes. An adapter declares the
# capabilities it actually provides. A capability declaration can only ever
# make a scenario report PENDING or let it run; it can never promote a harness
# answer into an acceptance PASS.
# ---------------------------------------------------------------------------

CAPABILITIES: dict[str, str] = {
    "stage2_candidate_selection": (
        "Deterministic Stage-2 candidate selection with per-pass exclusions."
    ),
    "integration_reservation_observation": (
        "Observation of in-flight work as integration reservations, including "
        "actual changed paths from Git."
    ),
    "deterministic_conflict_detection": (
        "Deterministic hard-conflict detection over exclusive resources and "
        "actual changed paths."
    ),
    "unity_serialized_asset_conflict": (
        "Unity serialized assets and their .meta companions are treated as one "
        "non-merge-safe asset identity."
    ),
    "unknown_surface_policy": (
        "Per-pair unknown-surface handling that waits without deadlocking "
        "unrelated work."
    ),
    "wait_admission_policy": (
        "Uncertainty-implies-WAIT admission with narrow HUMAN_REVIEW."
    ),
    "exact_task_id_launch": (
        "Worker launch with an exact task ID and a unique worker ID."
    ),
    "resume_priority": (
        "Resume authority outranks fresh Stage-2 ranking, under conflict safety."
    ),
    "scheduler_singleton": (
        "OS-backed scheduler singleton keyed by source and checkout root."
    ),
    "architect_failure_tolerance": (
        "A failed, unavailable, or malformed architect advisory waits instead "
        "of launching or escalating."
    ),
}


# ---------------------------------------------------------------------------
# Expected scheduling outcomes
# ---------------------------------------------------------------------------

OUTCOMES: dict[str, str] = {
    "start": "Exactly one worker is launched for the named exact task ID.",
    "idle": (
        "No safe candidate exists this pass; the scheduler idles. Named "
        "candidates are excluded for this pass only and nothing durable "
        "changes."
    ),
    "human_review": (
        "A named design/canon question is escalated. Merge or integration "
        "uncertainty must never reach this outcome."
    ),
    "blocked": (
        "The scheduler stops admitting work because a deterministic invariant "
        "failed. This is a defect signal, not a wait."
    ),
    "no_launch": (
        "The pass ends without a launch for a reason that is not a "
        "per-candidate wait, such as an exhausted invocation budget."
    ),
}

LAUNCH_OUTCOMES = frozenset({"start"})


# ---------------------------------------------------------------------------
# Result statuses
#
# There is no adapter-controlled path from a harness status to an acceptance
# status. verify_acceptance.py exposes two separate entry points, and only the
# verifier-owned acceptance path can emit PASS or FAIL.
# ---------------------------------------------------------------------------

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_HARNESS_PASS = "HARNESS_PASS"
STATUS_HARNESS_FAIL = "HARNESS_FAIL"
STATUS_FIXTURE_PASS = "FIXTURE_PASS"
STATUS_FIXTURE_FAIL = "FIXTURE_FAIL"
STATUS_PENDING = "PENDING_CAPABILITY"

FAILING_STATUSES = frozenset(
    {STATUS_FAIL, STATUS_HARNESS_FAIL, STATUS_FIXTURE_FAIL}
)

ACCEPTANCE_STATUSES = frozenset({STATUS_PASS, STATUS_FAIL})
"""Only these two statuses are architect acceptance claims.

Every other status is deliberately a different word so a report can never be
read as "the architect passed" when the harness answered, when only the fixture
was checked, or when the capability does not exist yet.
"""

HARNESS_STATUSES = frozenset({STATUS_HARNESS_PASS, STATUS_HARNESS_FAIL})


# ---------------------------------------------------------------------------
# Live-evidence check vocabulary
#
# A scenario declares which of these must be PROVEN for a live run to be
# accepted. The caller cannot choose a lenient subset at the command line.
# ---------------------------------------------------------------------------

LIVE_EVIDENCE_CHECKS: dict[str, str] = {
    "exact_task_id_launch": (
        "Every launch names an exact manifest task ID and a non-empty worker ID."
    ),
    "unique_worker_ids": "No task was launched twice and no worker ID was reused.",
    "launch_argv_binding": (
        "Every launch argv carries the exact --task-id and --worker-id."
    ),
    "structured_wait_evidence": (
        "Every wait names a structured conflicting task and overlapping "
        "resources or paths, not only a prose reason."
    ),
    "human_review_is_narrow": (
        "No escalation for merge or integration uncertainty; any escalation "
        "carries a design/canon category and a specific question."
    ),
    "wait_then_start_transition": (
        "A named candidate waited, then started, with a bound before/after "
        "reservation state for the same task and scenario."
    ),
    "singleton_lock_ownership": (
        "Exactly one scheduler acquired the checkout-root lock; a competitor "
        "was rejected and mutated nothing."
    ),
    "no_launch_recorded": "The run launched no worker at all.",
}


MANDATORY_LIVE_GROUNDING_CHECKS: dict[str, str] = {
    "source_identity_grounded": (
        "The recorded source HEAD, tree and repository identity equal what Git "
        "reports in the checkout passed as --source."
    ),
    "run_poll_lifecycle": (
        "The run contains one complete, correlated poll execution per required "
        "step, each with its own start and terminal record."
    ),
    "poll_step_alignment": (
        "Poll k proves manifest step k: its terminal outcome, its launch or "
        "absence of one, and its structured waits."
    ),
    "scheduler_identity_consistent": (
        "Every event belongs to the scheduler that recorded the run, except a "
        "rejected competitor, which must name that scheduler as the holder."
    ),
    "conflict_evidence_grounded": (
        "Every wait token is real in both the scenario's contract facts and the "
        "reservation state the run actually observed."
    ),
}
"""Checks the live verifier always applies. Deliberately not manifest-selectable.

A scenario chooses which behavioral claims it must prove. It does not get to
choose whether its evidence is anchored to a real repository, to its own
declared facts, and to a complete run.
"""


# ---------------------------------------------------------------------------
# Unity hot-spot classification
# ---------------------------------------------------------------------------

UNITY_SERIALIZED_SUFFIXES = (".unity", ".prefab", ".asset", ".inputactions")
UNITY_META_SUFFIX = ".meta"


def is_unity_serialized_asset(path: str) -> bool:
    """True for a serialized Unity asset or its ``.meta`` companion."""

    return unity_asset_identity(path).casefold().endswith(UNITY_SERIALIZED_SUFFIXES)


def unity_asset_identity(path: str) -> str:
    """Collapse ``X.prefab`` and ``X.prefab.meta`` onto one asset identity.

    A ``.meta`` file carries the asset GUID. Editing ``HUD.prefab`` in one
    branch and ``HUD.prefab.meta`` in another is the same non-merge-safe asset,
    so both canonicalize to ``HUD.prefab``.
    """

    text = str(path)
    if text.casefold().endswith(UNITY_META_SUFFIX):
        return text[: -len(UNITY_META_SUFFIX)]
    return text


def unity_serialized_assets(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({p for p in paths if is_unity_serialized_asset(p)}))


def unity_asset_identities(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                unity_asset_identity(p)
                for p in paths
                if is_unity_serialized_asset(p)
            }
        )
    )


# ---------------------------------------------------------------------------
# Safety refusals
#
# Reused unchanged in spirit from the retired Orchestrator Gauntlet: no flag
# ever overrides these, and a path name is never authority.
# ---------------------------------------------------------------------------

FORBIDDEN_REPOSITORIES = frozenset(
    {"cathode26/nosafecircle", "cathode26/no-safe-circle"}
)


def looks_like_production_repository(repository: str) -> bool:
    normalized = str(repository).strip().casefold()
    if normalized in FORBIDDEN_REPOSITORIES:
        return True
    owner, _, name = normalized.partition("/")
    collapsed = name.replace("-", "").replace("_", "")
    return owner == "cathode26" and "nosafecircle" in collapsed


FIXTURE_IDENTITY_CONFIG_KEY = "nsc.acceptancefixtureidentity"
"""Repository-local Git config key that carries a fixture's own identity.

The synthetic fixture deliberately has no Git remote: it must never look like
something that could be fetched or pushed. It therefore records an immutable
identity of its own, written by the builder, so a verifier can still ground an
evidence envelope's ``repository`` field in the actual checkout rather than
accepting a free-form string.
"""

_SLUG = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_OWNER_NAME_RE = re.compile(rf"^{_SLUG}/{_SLUG}$")
_FIXTURE_IDENTITY_RE = re.compile(rf"^nsc-fixture://{_SLUG}(?:/{_SLUG})+$")
_KNOWN_REMOTE_PREFIXES = (
    "https://github.com/",
    "http://github.com/",
    "ssh://git@github.com/",
    "git@github.com:",
)


class RepositoryIdentityError(AcceptanceSafetyError):
    """Raised when a repository identity is missing or not recognizable."""


def normalize_repository_identity(value: Any, *, where: str = "repository") -> str:
    """Return a canonical repository identity or fail closed.

    Two forms are recognized and nothing else: a GitHub ``owner/name`` identity
    (accepted directly or derived from a canonical HTTPS/SSH remote URL) and the
    synthetic fixture scheme ``nsc-fixture://...``. A free-form string is
    rejected, because "it looked like a repository" is exactly how a fabricated
    evidence envelope used to pass.
    """

    text = str(value or "").strip()
    if not text:
        raise RepositoryIdentityError(f"{where}: repository identity is empty")
    if _FIXTURE_IDENTITY_RE.fullmatch(text):
        return text
    candidate = text
    matched_remote = False
    for prefix in _KNOWN_REMOTE_PREFIXES:
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :].strip("/")
            matched_remote = True
            break
    if not matched_remote and (
        text.startswith("/") or ":" in text or "\\" in text
    ):
        # A filesystem path or an unrecognized URL scheme. Accepting it would
        # let "the string had a slash in it" stand in for repository identity.
        raise RepositoryIdentityError(
            f"{where}: {text!r} is a path or an unsupported URL, not a "
            "repository identity"
        )
    if candidate.endswith(".git"):
        candidate = candidate[: -len(".git")]
    if not _OWNER_NAME_RE.fullmatch(candidate):
        raise RepositoryIdentityError(
            f"{where}: {text!r} is not a recognizable repository identity. "
            "Use 'owner/name', a canonical GitHub remote URL, or the synthetic "
            "'nsc-fixture://...' fixture identity."
        )
    return candidate


def read_repository_identity(root: Path | str) -> str:
    """Read one checkout's own repository identity from its Git configuration.

    A configured ``origin`` wins when one exists. The synthetic fixture has no
    remote, so its builder-written identity key is used instead. A checkout with
    neither is unusable as grounding and fails closed.
    """

    origin = run_git(root, "config", "--get", "remote.origin.url", check=False)
    if origin.returncode == 0 and origin.stdout.strip():
        return normalize_repository_identity(
            origin.stdout.strip(), where=f"{root} remote.origin.url"
        )
    marker = run_git(
        root, "config", "--get", FIXTURE_IDENTITY_CONFIG_KEY, check=False
    )
    if marker.returncode == 0 and marker.stdout.strip():
        return normalize_repository_identity(
            marker.stdout.strip(), where=f"{root} {FIXTURE_IDENTITY_CONFIG_KEY}"
        )
    raise RepositoryIdentityError(
        f"{root} declares neither an origin remote nor a "
        f"{FIXTURE_IDENTITY_CONFIG_KEY} identity, so nothing in it can ground a "
        "recorded repository claim"
    )


def require_safe_target_repository(repository: str) -> str:
    repository = str(repository).strip()
    if not repository or "/" not in repository:
        raise AcceptanceSafetyError(
            f"repository must be 'owner/name'; got {repository!r}"
        )
    if looks_like_production_repository(repository):
        raise AcceptanceSafetyError(
            f"refusing to target production-looking repository {repository!r}. "
            "There is no override flag."
        )
    return repository


# ---------------------------------------------------------------------------
# Repository-relative path containment
#
# A manifest-declared path is data from a file. It is validated before it is
# ever joined to a filesystem root, and the joined result is re-checked after
# symlink resolution so a link inside the fixture cannot redirect a write.
# ---------------------------------------------------------------------------

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def validate_repository_relative_path(value: Any, *, where: str = "path") -> str:
    """Return a safe repository-relative POSIX path or fail closed.

    Rejects absolute paths, Windows drive and UNC forms, backslash separators,
    empty components, ``.``, ``..``, control characters, and anything outside
    the synthetic source directory.
    """

    if not isinstance(value, str):
        raise PathContainmentError(f"{where}: path must be a string, got {value!r}")
    text = value.strip()
    if not text:
        raise PathContainmentError(f"{where}: path must not be empty")
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise PathContainmentError(f"{where}: path contains a control character")
    if "\\" in text:
        raise PathContainmentError(
            f"{where}: backslash separators and UNC forms are rejected: {text!r}"
        )
    if text.startswith("/"):
        raise PathContainmentError(f"{where}: absolute paths are rejected: {text!r}")
    if _WINDOWS_DRIVE_RE.match(text):
        raise PathContainmentError(
            f"{where}: drive-qualified paths are rejected: {text!r}"
        )
    if ":" in text:
        raise PathContainmentError(f"{where}: ':' is not allowed in a path: {text!r}")
    components = text.split("/")
    for component in components:
        if component in ("", ".", ".."):
            raise PathContainmentError(
                f"{where}: '{component}' is not an allowed path component in {text!r}"
            )
    normalized = "/".join(components)
    if not normalized.startswith(SYNTHETIC_SOURCE_DIRECTORY + "/"):
        raise PathContainmentError(
            f"{where}: {normalized!r} is outside the synthetic source directory "
            f"{SYNTHETIC_SOURCE_DIRECTORY}/"
        )
    return normalized


def validate_repository_relative_paths(
    values: Iterable[Any], *, where: str = "paths"
) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for value in values:
        seen[validate_repository_relative_path(value, where=where)] = None
    return tuple(sorted(seen))


def resolve_within(root: Path, relative: str, *, where: str = "path") -> Path:
    """Join ``relative`` to ``root`` and prove the result stays inside ``root``.

    The containment check runs against the fully symlink-resolved path, so a
    symlink planted inside the fixture cannot redirect a write outside it.
    """

    normalized = validate_repository_relative_path(relative, where=where)
    root_real = Path(os.path.realpath(root))
    candidate = root_real / normalized
    resolved = Path(os.path.realpath(candidate))
    if resolved == root_real or root_real not in resolved.parents:
        raise PathContainmentError(
            f"{where}: {relative!r} resolves to {resolved}, which is outside {root_real}"
        )
    return candidate


# ---------------------------------------------------------------------------
# Disposable fixture roots
#
# Fixture roots are CREATED here, never accepted from a caller as a deletion
# target. An independent audit showed that proving *containment* is not enough:
# a caller who hand-built a `DisposableParent` or a `FixtureRoot` record, or who
# wrote a marker file by hand, could still name a foreign directory and have it
# deleted, because the record's own fields were treated as ownership.
#
# Ownership is therefore no longer carried by the record. Each create function
# registers the authoritative facts (path, token, device, inode, parent) in a
# module-private, process-local registry and returns an **opaque handle** whose
# only content is an unguessable ID. Every destructive operation:
#
#   1. requires a handle this module constructed (private constructor token);
#   2. looks the handle up by ID **and** compares object identity against the
#      registered handle, so a copied ID grants nothing;
#   3. re-proves the registered facts against the filesystem before removing
#      anything;
#   4. removes only the exact registered directory and then deregisters it.
#
# There is deliberately no destroy-arbitrary-path primitive and no way to insert
# an entry into the registry from outside this module.
# ---------------------------------------------------------------------------

FIXTURE_MARKER_NAME = ".saa-fixture-root"
_MINIMUM_FIXTURE_DEPTH = 3

DESTROY_REMOVED = "destroyed"
DESTROY_ALREADY_DONE = "already_destroyed"

_CONSTRUCTOR_TOKEN = object()
"""Module-private sentinel. Only this module can construct an ownership handle."""


class _OwnershipHandle:
    """An opaque ownership handle.

    The object carries one random ID and nothing else. Path, marker token and
    device/inode identity live in the private registry, keyed by that ID and
    bound to this exact object, so a hand-built lookalike is inert.
    """

    __slots__ = ("_handle_id",)

    def __init__(self, *, constructor_token: Any = None) -> None:
        if constructor_token is not _CONSTRUCTOR_TOKEN:
            raise AcceptanceSafetyError(
                f"{type(self).__name__} may only be created by this module's "
                "create_* functions. A hand-built handle carries no ownership "
                "and is never authority to delete anything."
            )
        object.__setattr__(self, "_handle_id", secrets.token_hex(16))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AcceptanceSafetyError("ownership handles are immutable")

    def __delattr__(self, name: str) -> None:
        raise AcceptanceSafetyError("ownership handles are immutable")

    def __repr__(self) -> str:
        # Deliberately opaque: a repr that printed the path or the marker token
        # would turn a log line into forgery material.
        return f"<{type(self).__name__} opaque>"


class DisposableParent(_OwnershipHandle):
    """Opaque handle to a temporary directory this process created."""

    __slots__ = ()

    @property
    def path(self) -> Path:
        """The registered directory. Raises for an unregistered handle."""

        return _parent_ownership(self).path


class FixtureRoot(_OwnershipHandle):
    """Opaque handle to a fixture directory this package created."""

    __slots__ = ()

    @property
    def path(self) -> Path:
        return _fixture_ownership(self).path

    @property
    def parent(self) -> Path:
        return _fixture_ownership(self).parent_path

    @property
    def token(self) -> str:
        return _fixture_ownership(self).token

    @property
    def marker_path(self) -> Path:
        return self.path / FIXTURE_MARKER_NAME


@dataclass(frozen=True)
class _ParentOwnership:
    handle: DisposableParent
    path: Path
    device: int
    inode: int


@dataclass(frozen=True)
class _FixtureOwnership:
    handle: FixtureRoot
    parent_handle_id: str
    parent_path: Path
    path: Path
    token: str
    device: int
    inode: int


_ACTIVE_PARENTS: dict[str, _ParentOwnership] = {}
_ACTIVE_FIXTURES: dict[str, _FixtureOwnership] = {}
_RETIRED_HANDLES: dict[str, _OwnershipHandle] = {}
"""Handles whose directory this module already removed.

The handle object itself is retained so a repeated destroy can be answered as
`already_destroyed` by object identity, without ever touching the filesystem and
without letting a copied ID answer for someone else's handle.
"""


def _handle_id(handle: Any, expected: type, kind: str) -> str:
    if not isinstance(handle, expected):
        raise AcceptanceSafetyError(
            f"expected a {expected.__name__} created by this package; got "
            f"{type(handle).__name__}. There is deliberately no "
            f"destroy-arbitrary-path primitive for a {kind}."
        )
    value = getattr(handle, "_handle_id", None)
    if not isinstance(value, str) or not value:
        raise AcceptanceSafetyError(
            f"this {kind} handle carries no ownership identity at all"
        )
    return value


def _registered(
    handle: Any,
    *,
    expected: type,
    registry: Mapping[str, Any],
    kind: str,
) -> Any:
    identity = _handle_id(handle, expected, kind)
    entry = registry.get(identity)
    if entry is None:
        raise AcceptanceSafetyError(
            f"this {kind} handle is not registered as owned by this process. "
            "Ownership comes from the create function, never from a record's "
            "fields."
        )
    if entry.handle is not handle:
        raise AcceptanceSafetyError(
            f"this {kind} handle reuses a registered ID but is not the object "
            "that was registered. A copied handle ID transfers no ownership."
        )
    return entry


def _parent_ownership(parent: Any) -> _ParentOwnership:
    return _registered(
        parent,
        expected=DisposableParent,
        registry=_ACTIVE_PARENTS,
        kind="disposable parent",
    )


def _fixture_ownership(root: Any) -> _FixtureOwnership:
    return _registered(
        root, expected=FixtureRoot, registry=_ACTIVE_FIXTURES, kind="fixture root"
    )


def _retired(handle: Any, identity: str) -> bool:
    return _RETIRED_HANDLES.get(identity) is handle


def _require_directory_identity(path: Path, device: int, inode: int, *, kind: str) -> Path:
    """Re-prove that the registered directory is still the same directory."""

    if path.is_symlink():
        raise AcceptanceSafetyError(
            f"refusing to delete a symlink alias of a {kind}: {path}"
        )
    if not path.is_dir():
        raise AcceptanceSafetyError(f"registered {kind} is not a directory: {path}")
    stat = path.stat()
    if (stat.st_dev, stat.st_ino) != (device, inode):
        raise AcceptanceSafetyError(
            f"refusing to delete {path}: device/inode identity changed since the "
            f"{kind} was created"
        )
    return path


def _assert_outside_repository(path: Path) -> Path:
    resolved = Path(os.path.realpath(path))
    repository_root = Path(os.path.realpath(ROOT))
    if resolved == repository_root or repository_root in resolved.parents:
        raise AcceptanceSafetyError(
            f"refusing to use a fixture location inside the source repository: {resolved}"
        )
    collapsed = str(resolved).casefold().replace("\\", "/")
    collapsed = collapsed.replace("-", "").replace("_", "")
    if "nosafecircle" in collapsed and "gauntlet" not in collapsed:
        raise AcceptanceSafetyError(
            f"refusing to use a production-looking fixture location: {resolved}"
        )
    return resolved


def create_disposable_parent(prefix: str = "saa-") -> DisposableParent:
    """Create the one canonical parent directory that may contain fixtures."""

    system_temp = Path(os.path.realpath(tempfile.gettempdir()))
    _assert_outside_repository(system_temp)
    created = Path(tempfile.mkdtemp(prefix=prefix, dir=str(system_temp)))
    resolved = _assert_outside_repository(created)
    if resolved == system_temp or system_temp not in resolved.parents:
        raise AcceptanceSafetyError(
            f"temporary directory {resolved} is not inside {system_temp}"
        )
    handle = DisposableParent(constructor_token=_CONSTRUCTOR_TOKEN)
    stat = resolved.stat()
    _ACTIVE_PARENTS[_handle_id(handle, DisposableParent, "disposable parent")] = (
        _ParentOwnership(
            handle=handle,
            path=resolved,
            device=stat.st_dev,
            inode=stat.st_ino,
        )
    )
    return handle


def create_fixture_root(parent: DisposableParent, name: str) -> FixtureRoot:
    """Create one marked fixture root beneath a registered disposable parent.

    The parent's path is read from the registry, never from the handed-in
    object, so a forged parent record cannot direct a creation (or the later
    deletion) anywhere.
    """

    parent_entry = _parent_ownership(parent)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", str(name)):
        raise AcceptanceSafetyError(f"unsafe fixture root name: {name!r}")
    parent_real = _require_directory_identity(
        parent_entry.path,
        parent_entry.device,
        parent_entry.inode,
        kind="disposable parent",
    )
    path = parent_real / str(name)
    if path.exists():
        raise AcceptanceFixtureError(f"fixture root already exists: {path}")
    path.mkdir(parents=True)
    token = secrets.token_hex(16)
    stat = path.stat()
    marker = {
        "marker": "software-architect-acceptance-fixture-root",
        "token": token,
        "path": str(path),
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "pid": os.getpid(),
    }
    (path / FIXTURE_MARKER_NAME).write_text(
        json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8"
    )
    handle = FixtureRoot(constructor_token=_CONSTRUCTOR_TOKEN)
    _ACTIVE_FIXTURES[_handle_id(handle, FixtureRoot, "fixture root")] = (
        _FixtureOwnership(
            handle=handle,
            parent_handle_id=_handle_id(
                parent, DisposableParent, "disposable parent"
            ),
            parent_path=parent_real,
            path=path,
            token=token,
            device=stat.st_dev,
            inode=stat.st_ino,
        )
    )
    return handle


def destroy_fixture_root(root: FixtureRoot) -> str:
    """Delete a fixture root only after proving it is the exact one created.

    Returns ``DESTROY_REMOVED`` or ``DESTROY_ALREADY_DONE``. Every refusal below
    is a real failure mode the audit reproduced: ``/`` and other short roots, the
    canonical temp parent itself, a parent directory, a symlink alias, a foreign
    temporary directory carrying a forged marker, and a forged handle that copies
    a genuine handle's apparent values.
    """

    identity = _handle_id(root, FixtureRoot, "fixture root")
    if identity not in _ACTIVE_FIXTURES and _retired(root, identity):
        # A second destroy of a handle this module already retired. Nothing is
        # inspected or removed, so a directory that was later recreated at the
        # same path by someone else is untouched.
        return DESTROY_ALREADY_DONE
    entry = _fixture_ownership(root)
    system_temp = Path(os.path.realpath(tempfile.gettempdir()))
    registered = entry.path
    parent_real = entry.parent_path

    if len(registered.parts) < _MINIMUM_FIXTURE_DEPTH:
        raise AcceptanceSafetyError(
            f"refusing to delete a short root path: {registered}"
        )
    if registered == parent_real or parent_real not in registered.parents:
        raise AcceptanceSafetyError(
            f"refusing to delete {registered}: it is not a strict descendant of "
            f"the disposable parent {parent_real}"
        )
    if parent_real == system_temp or system_temp not in parent_real.parents:
        raise AcceptanceSafetyError(
            f"refusing to delete {registered}: its parent {parent_real} is not "
            f"inside the system temporary directory {system_temp}"
        )
    _assert_outside_repository(registered)

    if not registered.exists():
        # The directory disappeared underneath us. Retire the handle without
        # deleting anything so a later path reuse cannot be hit.
        _ACTIVE_FIXTURES.pop(identity, None)
        _RETIRED_HANDLES[identity] = root
        return DESTROY_ALREADY_DONE

    resolved = _require_directory_identity(
        registered, entry.device, entry.inode, kind="fixture root"
    )
    marker_path = resolved / FIXTURE_MARKER_NAME
    if marker_path.is_symlink() or not marker_path.is_file():
        raise AcceptanceSafetyError(
            f"refusing to delete {resolved}: no regular fixture marker file"
        )
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcceptanceSafetyError(
            f"refusing to delete {resolved}: unreadable fixture marker: {exc}"
        ) from exc
    if not isinstance(marker, dict) or marker.get("token") != entry.token:
        raise AcceptanceSafetyError(
            f"refusing to delete {resolved}: fixture marker token does not match"
        )
    if marker.get("path") != str(entry.path):
        raise AcceptanceSafetyError(
            f"refusing to delete {resolved}: marker records a different path "
            f"{marker.get('path')!r}"
        )
    if (marker.get("device"), marker.get("inode")) != (entry.device, entry.inode):
        raise AcceptanceSafetyError(
            f"refusing to delete {resolved}: the marker's device/inode identity "
            "does not match the registered fixture root"
        )
    shutil.rmtree(resolved)
    _ACTIVE_FIXTURES.pop(identity, None)
    _RETIRED_HANDLES[identity] = root
    return DESTROY_REMOVED


def destroy_disposable_parent(
    parent: DisposableParent, *, destroy_registered_children: bool = False
) -> str:
    """Remove a disposable parent created by this package.

    By default a parent that still owns a live registered fixture root is
    refused, because removing it would delete a directory whose own ownership
    proof has not been run. A caller that genuinely owns the whole group (the
    scenario runner's cleanup path) may opt in to destroying exactly this
    parent's registered children first, each through the full
    ``destroy_fixture_root`` proof.
    """

    identity = _handle_id(parent, DisposableParent, "disposable parent")
    if identity not in _ACTIVE_PARENTS and _retired(parent, identity):
        return DESTROY_ALREADY_DONE
    entry = _parent_ownership(parent)
    children = [
        child
        for child in list(_ACTIVE_FIXTURES.values())
        if child.parent_handle_id == identity
    ]
    if children and not destroy_registered_children:
        raise AcceptanceSafetyError(
            f"refusing to remove {entry.path}: it still owns "
            f"{len(children)} live fixture root(s). Destroy them first."
        )
    for child in children:
        destroy_fixture_root(child.handle)

    system_temp = Path(os.path.realpath(tempfile.gettempdir()))
    if entry.path == system_temp or system_temp not in entry.path.parents:
        raise AcceptanceSafetyError(
            f"refusing to remove {entry.path}: it is not inside {system_temp}"
        )
    _assert_outside_repository(entry.path)
    if entry.path.exists():
        _require_directory_identity(
            entry.path, entry.device, entry.inode, kind="disposable parent"
        )
        shutil.rmtree(entry.path)
        status = DESTROY_REMOVED
    else:
        status = DESTROY_ALREADY_DONE
    _ACTIVE_PARENTS.pop(identity, None)
    _RETIRED_HANDLES[identity] = parent
    return status


# ---------------------------------------------------------------------------
# Deterministic Git identity
#
# Fixed identity plus fixed timestamps make generated commit SHAs reproducible
# on one host with one Git version. Every inherited GIT_* variable is removed,
# including the GIT_CONFIG_COUNT/KEY/VALUE command-scope form, so a developer's
# shell cannot change a fixture SHA.
# ---------------------------------------------------------------------------

FIXTURE_AUTHOR_NAME = "Software Architect Acceptance Fixture"
FIXTURE_AUTHOR_EMAIL = "architect-acceptance-fixture@nosafecircle.invalid"
FIXTURE_EPOCH_SECONDS = 1_767_225_600  # 2026-01-01T00:00:00Z, fixed forever.
FIXTURE_TIMEZONE = "+0000"


def fixture_git_environment(
    commit_index: int, *, hooks_path: Path | str | None = None
) -> dict[str, str]:
    """Return a scrubbed environment that makes one fixture commit reproducible."""

    if commit_index < 0:
        raise AcceptanceFixtureError("commit index must be non-negative")
    stamp = f"{FIXTURE_EPOCH_SECONDS + commit_index} {FIXTURE_TIMEZONE}"
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    # GIT_CONFIG_COUNT/GIT_CONFIG_KEY_n/GIT_CONFIG_VALUE_n, GIT_CONFIG_PARAMETERS,
    # GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, GIT_TEMPLATE_DIR and every other
    # inherited GIT_* variable were removed by the comprehension above.
    environment.update(
        {
            "GIT_AUTHOR_NAME": FIXTURE_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": FIXTURE_AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": FIXTURE_AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": FIXTURE_AUTHOR_EMAIL,
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "XDG_CONFIG_HOME": os.devnull,
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
        }
    )
    if hooks_path is not None:
        environment["GIT_CONFIG_COUNT"] = "1"
        environment["GIT_CONFIG_KEY_0"] = "core.hooksPath"
        environment["GIT_CONFIG_VALUE_0"] = str(hooks_path)
    return environment


def run_git(
    root: Path | str,
    *args: str,
    commit_index: int = 0,
    hooks_path: Path | str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one Git command with stdout and stderr kept separate.

    Machine data is read from ``stdout`` only, so an ordinary Git warning can
    never become a filename, SHA, or path in a fixture assertion.
    """

    result = subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
        env=fixture_git_environment(commit_index, hooks_path=hooks_path),
        timeout=120,
    )
    if check and result.returncode != 0:
        raise AcceptanceFixtureError(
            f"git {' '.join(args)} failed ({result.returncode}) in {root}: "
            f"{result.stderr.strip()[:500]}"
        )
    return result


def git_text(root: Path | str, *args: str) -> str:
    return run_git(root, *args).stdout.strip()


def git_lines(root: Path | str, *args: str) -> tuple[str, ...]:
    return tuple(
        line for line in run_git(root, *args).stdout.splitlines() if line.strip()
    )


def git_z_paths(root: Path | str, *args: str) -> tuple[str, ...]:
    raw = run_git(root, *args).stdout
    return normalize_observed_paths(item for item in raw.split("\0") if item)


def git_version() -> str:
    result = subprocess.run(
        ("git", "--version"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=fixture_git_environment(0),
        timeout=60,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Normalization and hashing
# ---------------------------------------------------------------------------

def normalize_observed_path(value: str) -> str:
    """Normalize a path Git reported. Git emits clean relative POSIX paths."""

    return str(value).strip().replace("\\", "/").rstrip("/")


def normalize_observed_paths(values: Iterable[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for value in values:
        normalized = normalize_observed_path(value)
        if normalized:
            seen[normalized] = None
    return tuple(sorted(seen))


def normalize_tokens(values: Iterable[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for value in values:
        text = str(value).strip()
        if text:
            seen[text] = None
    return tuple(sorted(seen))


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path | str) -> str:
    """Hash a file's LF-normalized bytes.

    Normalizing means a Windows checkout with CRLF translation computes the
    same manifest hash as a Linux container, so evidence recorded on one host
    can be verified on the other.
    """

    raw = Path(path).read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def synthetic_contract_sha256(task_id: str, task: Mapping[str, Any]) -> str:
    """Stable synthetic stand-in for ``task_contract_sha256``.

    The acceptance harness never fabricates a production contract hash. This
    value exists only so a scenario world can carry a stable contract identity
    through structured disjointness evidence.
    """

    return canonical_sha256({"task_id": task_id, "task": dict(task)})


def integration_fingerprint(reservations: Sequence[Mapping[str, Any]]) -> str:
    """Fingerprint the in-flight reservation set.

    Reused concept: a WAIT is bound to the state that produced it, so any
    change to the in-flight set forces reconsideration and a cached WAIT can
    never become a permanent blacklist.
    """

    payload = [
        {
            "task_id": item.get("task_id"),
            "actual_paths": list(item.get("actual_paths", ())),
            "predicted_paths": list(item.get("predicted_paths", ())),
            "unity_serialized_assets": list(
                item.get("unity_serialized_assets", ())
            ),
            "exclusive_resources": list(item.get("exclusive_resources", ())),
            "surface_unknown": bool(item.get("surface_unknown", False)),
            "local_active": bool(item.get("local_active", False)),
        }
        for item in sorted(
            reservations, key=lambda entry: str(entry.get("task_id", ""))
        )
    ]
    return canonical_sha256(payload)


def load_json(path: Path | str) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_contained_text(root: Path, relative: str, text: str) -> Path:
    """Write UTF-8 LF text at a path proven to stay inside ``root``."""

    target = resolve_within(root, relative, where="fixture write")
    body = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        handle.write(body.encode("utf-8"))
    return target
