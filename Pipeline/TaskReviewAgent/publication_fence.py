"""Base-bound atomic publication of the approved, tested candidate commit.

The authoritative mainline mutation must be bound to the EXACT target-branch
commit that was validated. ``gh pr merge --match-head-commit`` pins only the
pull-request head, so a competing writer can advance the target branch between
the final mainline guard and the merge; the merge then lands against a base that
no required check, human approval or reintegration ever observed. A second read
immediately before the merge does not close that window, and the GitHub merge
API cannot express an expected base at all.

This module replaces that mutation with ONE atomic ref transaction that names
the expected old value explicitly::

    git push --atomic --porcelain \\
        --force-with-lease=refs/heads/<target>:<expected_main> \\
        <remote> <candidate>:refs/heads/<target>

``receive-pack`` applies the update only when the target branch is EXACTLY
``expected_main``; the old value travels in the push request itself, so this is a
genuine server-enforced compare-and-swap, not a read-then-write. Any other value
-- disjoint, conflicting, or even a commit already contained in the candidate --
is rejected with the branch untouched (``stale info`` client-side against the
advertisement, ``cannot lock ref '<ref>': is at X but expected Y`` server-side).

What is published
-----------------
The published commit is the approved candidate itself, never a freshly
synthesized merge commit. The delivery validation workflows check out
``github.event.pull_request.head.sha``, so the candidate head IS the commit the
required checks evaluated; publishing anything else would publish a topology no
check ever saw. ``expected_main`` is proven to be an ancestor of the candidate
before the transaction is issued -- that proof is what makes this update a
fast-forward, so the lease can never rewind history even though the flag would
otherwise permit it. Without that proof the transaction is refused outright.

The lease is only ever used in its exact-value form against the target branch.
A bare ``--force-with-lease``, a plain ``--force``, an inferred lease, a fallback
force push, and re-leasing against a newly observed base after a rejection are
all prohibited: a rejected publication returns to reintegration, revalidation and
renewed approval under a NEW operation, never to a retry with a fresher base.

Outcomes are typed and durable. ``NOT_ATTEMPTED``, ``REJECTED_BASE_MOVED``,
``PUBLISHED``, ``FAILED`` and ``UNCERTAIN`` are distinguishable from the
persisted record alone, so a crash never has to guess. ``UNCERTAIN`` never
retries: it quarantines for reconciliation.
"""

from __future__ import annotations

import re
import subprocess
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .contracts import GIT_SHA_RE, TaskReviewContractError, validate_task_id
from .git_identity_guard import validated_agent_git_identity

PUBLICATION_PROTOCOL_VERSION = "2.0"
OPERATION_TOKEN = re.compile(r"[0-9a-f]{32}\Z")

# Porcelain reasons that PROVE the remote refused the compare-and-swap. The ref
# transaction is atomic, so the target branch is unchanged in every case.
#: The lease failed against the ref advertisement: the branch is not at the
#: expected old value.
_STALE_LEASE_REASON = "stale info"
#: The proposed update is not a fast-forward, so the branch moved outside the
#: approved candidate.
_NOT_FAST_FORWARD_REASONS = frozenset({"fetch first", "non-fast-forward"})
#: Server-side exact-value rejection for this ref.
_SERVER_LEASE_MISMATCH = re.compile(
    r"cannot lock ref '[^']*': is at [0-9a-f]{40} but expected [0-9a-f]{40}"
)
# Proven ref-transaction lock contention: the lock protects the update, so the
# mutation definitely did not apply. Revalidated, never blindly retried.
_LOCK_CONTENTION = re.compile(
    r"cannot lock ref '[^']*': Unable to create '[^']*\.lock': File exists"
)


class PublicationFenceError(TaskReviewContractError):
    """Raised when a fenced publication cannot proceed or cannot be classified."""


class PublicationStatus(str, Enum):
    """Durable, mutually exclusive publication outcomes.

    Every value answers "what happened to the authoritative branch?" from the
    persisted record alone, with no inference from process age, exit codes or
    current remote state.
    """

    #: The authoritative mutation was never issued.
    NOT_ATTEMPTED = "not_attempted"
    #: Identities bound and the candidate proven publishable; nothing pushed yet.
    PREPARED = "prepared"
    #: The ref transaction was issued and its outcome is not yet recorded.
    ATTEMPTING = "attempting"
    #: The remote refused because the branch was not the expected commit. Unchanged.
    REJECTED_BASE_MOVED = "rejected_base_moved"
    #: The remote refused on policy/permission grounds. Branch unchanged.
    REJECTED_BY_POLICY = "rejected_by_policy"
    #: Proven not applied for an operational reason. Branch unchanged.
    FAILED = "failed"
    #: Applied, swapping from exactly ``expected_main``.
    PUBLISHED = "published"
    #: Applied, but the transaction reported a different pre-image.
    PUBLISHED_UNEXPECTED_PRE_IMAGE = "published_unexpected_pre_image"
    #: The outcome is unknown. Quarantine and reconcile; never retry.
    UNCERTAIN = "uncertain"


#: Outcomes after which the authoritative branch definitely did not move.
DEFINITELY_NOT_PUBLISHED = frozenset({
    PublicationStatus.NOT_ATTEMPTED,
    PublicationStatus.PREPARED,
    PublicationStatus.REJECTED_BASE_MOVED,
    PublicationStatus.REJECTED_BY_POLICY,
    PublicationStatus.FAILED,
})
#: Outcomes after which the authoritative branch definitely did move.
DEFINITELY_PUBLISHED = frozenset({
    PublicationStatus.PUBLISHED,
    PublicationStatus.PUBLISHED_UNEXPECTED_PRE_IMAGE,
})
#: Outcomes that must not be retried and must not settle the task.
REQUIRES_RECONCILIATION = frozenset({
    PublicationStatus.ATTEMPTING,
    PublicationStatus.UNCERTAIN,
    PublicationStatus.PUBLISHED_UNEXPECTED_PRE_IMAGE,
})


def new_operation_id() -> str:
    return uuid.uuid4().hex


def validate_operation_id(value: Any) -> str:
    if not isinstance(value, str) or not OPERATION_TOKEN.fullmatch(value):
        raise PublicationFenceError(
            "publication operation identity must be an unguessable UUID hex value"
        )
    return value


def validate_commit(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not GIT_SHA_RE.match(value):
        raise PublicationFenceError(
            f"publication {field_name} must be an exact 40-character commit OID"
        )
    return value


@dataclass(frozen=True)
class PublicationBinding:
    """The exact identities publication authority is bound to.

    ``source_head`` is the approved candidate that will BE the new target-branch
    commit. ``validated_commit`` is the exact SHA for which required validation
    evidence was accepted; publication is refused unless they are the same
    commit, so the published topology is always the tested one.

    A binding is immutable. A legitimate base change after reintegration
    produces a NEW binding with a higher ``base_epoch``, a new operation
    identity and a new candidate, recorded as its own owner-bound transition.
    """

    protocol_version: str
    repository: str
    target_branch: str
    task_id: str
    run_id: str
    worker_id: str
    lease_id: str
    source_head: str
    validated_commit: str
    expected_main: str
    operation_id: str
    base_epoch: int

    FIELDS = (
        "protocol_version", "repository", "target_branch", "task_id", "run_id",
        "worker_id", "lease_id", "source_head", "validated_commit", "expected_main",
        "operation_id", "base_epoch",
    )

    def __post_init__(self) -> None:
        if self.protocol_version != PUBLICATION_PROTOCOL_VERSION:
            raise PublicationFenceError(
                "publication binding protocol version is not supported; "
                "reconcile the durable record explicitly"
            )
        for name in ("repository", "target_branch", "run_id", "worker_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise PublicationFenceError(f"publication binding requires an exact {name}")
        validate_task_id(self.task_id)
        validate_operation_id(self.operation_id)
        if not isinstance(self.lease_id, str) or not OPERATION_TOKEN.fullmatch(self.lease_id):
            raise PublicationFenceError("publication binding requires the exact gate lease identity")
        for name in ("source_head", "validated_commit", "expected_main"):
            validate_commit(getattr(self, name), field_name=name.replace("_", " "))
        if self.validated_commit != self.source_head:
            raise PublicationFenceError(
                "required validation evidence was accepted for "
                f"{self.validated_commit}, which is not the approved candidate "
                f"{self.source_head}; refusing to publish an untested topology"
            )
        if type(self.base_epoch) is not int or self.base_epoch < 1:
            raise PublicationFenceError("publication binding requires a positive base epoch")
        if self.expected_main == self.source_head:
            raise PublicationFenceError(
                "the target branch already holds the approved candidate; nothing to publish"
            )

    @property
    def destination(self) -> str:
        return f"refs/heads/{self.target_branch}"

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.FIELDS}

    @classmethod
    def from_dict(cls, value: Any) -> "PublicationBinding":
        if not isinstance(value, Mapping) or set(value) != set(cls.FIELDS):
            raise PublicationFenceError(
                "publication binding schema mismatch; never reinterpret a foreign or "
                "legacy record as authorized publication authority"
            )
        return cls(**{name: value[name] for name in cls.FIELDS})


@dataclass(frozen=True)
class PublicationOutcome:
    """A durable, self-describing result of one authoritative mutation attempt."""

    status: PublicationStatus
    binding: PublicationBinding
    publication_commit: str
    observed_pre_image: str | None = None
    observed_target: str | None = None
    detail: str = ""
    porcelain: tuple[str, ...] = field(default_factory=tuple)

    @property
    def published(self) -> bool:
        return self.status in DEFINITELY_PUBLISHED

    @property
    def target_unchanged(self) -> bool:
        return self.status in DEFINITELY_NOT_PUBLISHED


def _text(data: bytes | None) -> str:
    return (data or b"").decode("utf-8", errors="replace").strip()


def _git(
    runner: Callable[[Sequence[str], Path, float], "subprocess.CompletedProcess[bytes]"],
    root: Path,
    *args: str,
    check: bool = True,
    timeout_seconds: float = 600.0,
) -> "subprocess.CompletedProcess[bytes]":
    command = ("git", "-C", str(root), *args)
    result = runner(command, root, timeout_seconds)
    if check and result.returncode != 0:
        detail = _text(result.stderr) or _text(result.stdout)
        raise PublicationFenceError(
            f"publication git command failed ({result.returncode}): {' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _git_text(
    runner: Callable[[Sequence[str], Path, float], "subprocess.CompletedProcess[bytes]"],
    root: Path,
    *args: str,
    check: bool = True,
) -> str:
    return _text(_git(runner, root, *args, check=check).stdout)


def prove_publishable_candidate(
    runner: Callable[[Sequence[str], Path, float], "subprocess.CompletedProcess[bytes]"],
    checkout: Path,
    *,
    binding: PublicationBinding,
) -> str:
    """Prove the transaction can only fast-forward, then name the commit to publish.

    The exact-value lease is permitted ONLY alongside this proof: because
    ``expected_main`` is an ancestor of the candidate, applying the candidate to
    the target branch appends history and can never rewind it. Without the proof
    the publication is refused rather than attempted with a weaker fence.
    """

    for name in ("expected_main", "source_head"):
        commit = getattr(binding, name)
        resolved = _git_text(
            runner, checkout, "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}",
            check=False,
        )
        if resolved != commit:
            raise PublicationFenceError(
                f"publication {name.replace('_', ' ')} {commit} is not a commit in this checkout"
            )
    if (
        _git(
            runner, checkout, "merge-base", "--is-ancestor",
            binding.expected_main, binding.source_head, check=False,
        ).returncode
        != 0
    ):
        raise PublicationFenceError(
            f"expected base {binding.expected_main} is not an ancestor of the approved "
            f"candidate {binding.source_head}; publishing it would rewind or diverge "
            f"{binding.target_branch}. Reintegrate current main and revalidate."
        )
    return binding.source_head


def _porcelain_lines(stdout_text: str, destination: str) -> list[tuple[str, str]]:
    """(flag, summary) for every porcelain line targeting ``destination``."""

    found: list[tuple[str, str]] = []
    for line in stdout_text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        flag, refspec, summary = parts[0], parts[1], parts[2].strip()
        target = refspec.split(":", 1)[1] if ":" in refspec else refspec
        if target == destination:
            found.append((flag, summary))
    return found


def _reason(summary: str) -> str:
    if summary.endswith(")") and "(" in summary:
        return summary[summary.rindex("(") + 1 : -1].strip()
    return ""


def classify_publication_push(
    result: "subprocess.CompletedProcess[bytes]",
    *,
    destination: str,
) -> tuple[PublicationStatus, str | None, str]:
    """Classify one fenced publication push into (status, pre-image, detail).

    Only per-ref porcelain proof is credited. A failure with no machine-readable
    line for the exact destination ref is UNCERTAIN, never "failed": this process
    cannot prove the remote did not apply the update.
    """

    stdout_text = (result.stdout or b"").decode("utf-8", errors="replace")
    stderr_text = (result.stderr or b"").decode("utf-8", errors="replace")
    lines = _porcelain_lines(stdout_text, destination)
    detail = "\n".join(item for item in (stdout_text.strip(), stderr_text.strip()) if item)
    if len(lines) != 1:
        return PublicationStatus.UNCERTAIN, None, detail
    flag, summary = lines[0]
    if flag == "!":
        reason = _reason(summary)
        if reason == _STALE_LEASE_REASON or reason in _NOT_FAST_FORWARD_REASONS:
            return PublicationStatus.REJECTED_BASE_MOVED, None, detail
        if _SERVER_LEASE_MISMATCH.search(reason) or _SERVER_LEASE_MISMATCH.search(stderr_text):
            return PublicationStatus.REJECTED_BASE_MOVED, None, detail
        if _LOCK_CONTENTION.search(reason) or _LOCK_CONTENTION.search(stderr_text):
            return PublicationStatus.FAILED, None, detail
        if summary.startswith("[remote rejected]") or summary.startswith("[rejected]"):
            return PublicationStatus.REJECTED_BY_POLICY, None, detail
        return PublicationStatus.UNCERTAIN, None, detail
    if result.returncode != 0:
        # An accepted destination line inside a failed transaction is not proof.
        return PublicationStatus.UNCERTAIN, None, detail
    if flag == "=":
        # Already at the approved candidate: an idempotent replay of OUR update.
        return PublicationStatus.PUBLISHED, None, detail
    if flag == " ":
        pre_image = summary.split("..", 1)[0].strip() if ".." in summary else None
        return PublicationStatus.PUBLISHED, pre_image or None, detail
    return PublicationStatus.UNCERTAIN, None, detail


def publication_push_command(
    checkout: Path,
    *,
    binding: PublicationBinding,
    publication_commit: str,
    remote: str,
) -> tuple[str, ...]:
    """The one authoritative mutation command, in exact-lease form only."""

    return (
        "git",
        "-C",
        str(checkout),
        "push",
        "--atomic",
        "--porcelain",
        f"--force-with-lease={binding.destination}:{binding.expected_main}",
        remote,
        f"{publication_commit}:{binding.destination}",
    )


def publish_with_base_fence(
    runner: Callable[[Sequence[str], Path, float], "subprocess.CompletedProcess[bytes]"],
    checkout: Path,
    *,
    binding: PublicationBinding,
    publication_commit: str,
    remote: str = "origin",
    timeout_seconds: float = 900.0,
) -> PublicationOutcome:
    """Issue the one authoritative, base-bound ref transaction and classify it.

    The caller MUST have persisted ``binding`` and ``publication_commit``
    durably, with status ``ATTEMPTING``, before calling this. On any return the
    caller must record the outcome before draining or raising.
    """

    if publication_commit != binding.source_head:
        raise PublicationFenceError(
            "only the approved, validated candidate may be published"
        )
    prove_publishable_candidate(runner, checkout, binding=binding)
    command = publication_push_command(
        checkout, binding=binding, publication_commit=publication_commit, remote=remote
    )
    try:
        result = runner(command, checkout, timeout_seconds)
    except Exception as exc:  # transport/timeout: the remote may have applied it
        return PublicationOutcome(
            status=PublicationStatus.UNCERTAIN,
            binding=binding,
            publication_commit=publication_commit,
            detail=f"{type(exc).__name__}: {exc}",
        )
    status, pre_image, detail = classify_publication_push(
        result, destination=binding.destination
    )
    porcelain = tuple(
        line
        for line in (result.stdout or b"").decode("utf-8", errors="replace").splitlines()
        if line
    )
    if status is not PublicationStatus.PUBLISHED:
        return PublicationOutcome(
            status=status, binding=binding, publication_commit=publication_commit,
            detail=detail, porcelain=porcelain,
        )
    resolved = _resolve_pre_image(runner, checkout, pre_image)
    observed = observed_target_commit(
        runner, checkout, remote=remote, target_branch=binding.target_branch
    )
    if observed is not None and observed != publication_commit:
        return PublicationOutcome(
            status=PublicationStatus.UNCERTAIN, binding=binding,
            publication_commit=publication_commit, observed_pre_image=resolved,
            observed_target=observed,
            detail=f"target branch is {observed}, not the published commit\n{detail}",
            porcelain=porcelain,
        )
    if resolved is not None and resolved != binding.expected_main:
        return PublicationOutcome(
            status=PublicationStatus.PUBLISHED_UNEXPECTED_PRE_IMAGE, binding=binding,
            publication_commit=publication_commit, observed_pre_image=resolved,
            observed_target=observed,
            detail=(
                f"transaction swapped from {resolved}, not the bound expected base "
                f"{binding.expected_main}\n{detail}"
            ),
            porcelain=porcelain,
        )
    return PublicationOutcome(
        status=PublicationStatus.PUBLISHED, binding=binding,
        publication_commit=publication_commit, observed_pre_image=resolved,
        observed_target=observed, detail=detail, porcelain=porcelain,
    )


def _resolve_pre_image(
    runner: Callable[[Sequence[str], Path, float], "subprocess.CompletedProcess[bytes]"],
    checkout: Path,
    pre_image: str | None,
) -> str | None:
    """Expand the transaction's abbreviated pre-image to an exact OID."""

    if not pre_image or not re.fullmatch(r"[0-9a-f]{4,40}", pre_image):
        return None
    resolved = _git_text(
        runner, checkout, "rev-parse", "--verify", "--quiet", pre_image + "^{commit}",
        check=False,
    )
    return resolved if GIT_SHA_RE.match(resolved) else None


def observed_target_commit(
    runner: Callable[[Sequence[str], Path, float], "subprocess.CompletedProcess[bytes]"],
    checkout: Path,
    *,
    remote: str = "origin",
    target_branch: str,
) -> str | None:
    """Read the remote target branch. Advisory confirmation; never a fence."""

    destination = f"refs/heads/{target_branch}"
    result = _git(runner, checkout, "ls-remote", remote, destination, check=False)
    if result.returncode != 0:
        return None
    for line in _text(result.stdout).splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == destination and GIT_SHA_RE.match(parts[0]):
            return parts[0]
    return None
