"""Build one scenario's world: a real Git fixture plus observed reservations.

A *world* is everything a scheduling cycle can see:

```text
source repository        real local Git, deterministic commits
task checkouts           real clones with tracked/staged/untracked changes
integration reservations OBSERVED from that Git state, never asserted
Stage-2 fresh ranking     declared fresh-candidate order for this scenario
resume authority          a separate durable resume claim, not a queue position
injected advisories       deterministic stand-ins for the model call
```

The distinction that matters: the manifest declares how to *construct* the
fixture, and this module then *observes* the result with ordinary Git commands.
Actual changed paths are therefore evidence, not a second copy of the
expectation. A scenario that claims a reservation touches `HUD.prefab` is
checked against what Git actually reports.

Two rules this module enforces for the verifier:

- **Resume authority is not queue order.** ``candidate_queue()`` returns fresh
  Stage-2 ranking only. ``resume_candidate()`` is a separate durable fact, so a
  scheduler cannot appear to honor resume priority merely because the manifest
  listed the resume task first.
- **Structured disjointness only.** ``compute_disjointness()`` derives its
  verdict from committed exclusive-resource tokens and contract identities.
  Advisory prose can explain a verdict but can never create one.

Worlds are disposable and live entirely inside a ``FixtureRoot`` this package
created.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import synthetic_repository as sr
from acceptance_lib import (
    AcceptanceFixtureError,
    FixtureRoot,
    SYNTHETIC_TASK_ID_RE,
    canonical_json,
    canonical_sha256,
    destroy_fixture_root,
    git_text,
    integration_fingerprint,
    normalize_observed_paths,
    normalize_tokens,
    synthetic_contract_sha256,
    unity_asset_identities,
    unity_serialized_assets,
)

RESERVATION_KINDS = (
    "durable_unmerged_branch",
    "human_hold_branch",
    "scheduler_active_checkout",
    "unobservable_surface",
)

EVIDENCE_UNKNOWN = "unobservable_surface"
EVIDENCE_BRANCH = "durable_branch_actual_git"
EVIDENCE_BRANCH_AND_CHECKOUT = "durable_branch_and_checkout_actual_git"
EVIDENCE_ACTIVE_PREDICTION = "scheduler_prediction"
EVIDENCE_ACTIVE_ACTUAL = "scheduler_prediction_and_actual_git"

ADVISORY_DEFECTS = (
    "wrong_task_id",
    "wrong_scenario_binding",
    "missing_predicted_change_surface",
    "unknown_structured_field",
    "non_numeric_confidence",
)

DISJOINT_PROVABLE = "provably_disjoint"
DISJOINT_NOT_PROVABLE = "not_provably_disjoint"
DISJOINT_OVERLAPPING = "overlapping_resources"


def validate_synthetic_task_id(value: Any) -> str:
    text = str(value).strip()
    if not SYNTHETIC_TASK_ID_RE.fullmatch(text):
        raise AcceptanceFixtureError(
            f"acceptance task IDs must be synthetic NSC-9##; got {value!r}"
        )
    return text


@dataclass(frozen=True)
class Reservation:
    """One piece of in-flight work, shaped like the scheduler's own view.

    Field names deliberately match the scheduler's integration-reservation
    record so the future real adapter can hand these straight through without a
    translation layer that could quietly drop `surface_unknown`.
    """

    task_id: str
    workflow_state: str | None
    phase: str | None
    branch: str | None
    head: str | None
    checkout_path: str | None
    exclusive_resources: tuple[str, ...]
    predicted_paths: tuple[str, ...]
    actual_paths: tuple[str, ...]
    unity_serialized_assets: tuple[str, ...]
    unity_asset_identities: tuple[str, ...]
    confidence: float
    evidence_type: str
    surface_unknown: bool
    local_active: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "workflow_state": self.workflow_state,
            "phase": self.phase,
            "branch": self.branch,
            "head": self.head,
            "checkout_path": self.checkout_path,
            "exclusive_resources": list(self.exclusive_resources),
            "predicted_paths": list(self.predicted_paths),
            "actual_paths": list(self.actual_paths),
            "unity_serialized_assets": list(self.unity_serialized_assets),
            "unity_asset_identities": list(self.unity_asset_identities),
            "confidence": self.confidence,
            "evidence_type": self.evidence_type,
            "surface_unknown": self.surface_unknown,
            "local_active": self.local_active,
        }


@dataclass(frozen=True)
class DisjointnessEvidence:
    """A structured, code-computed disjointness verdict.

    Prose never appears in this record. The verdict comes from committed
    exclusive-resource tokens plus the contract identities that declared them,
    so a scenario cannot argue a candidate into a START.
    """

    candidate_task_id: str
    reservation_task_id: str
    verdict: str
    candidate_resources: tuple[str, ...]
    reservation_resources: tuple[str, ...]
    overlapping_resources: tuple[str, ...]
    candidate_contract_sha256: str
    reservation_contract_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_task_id": self.candidate_task_id,
            "reservation_task_id": self.reservation_task_id,
            "verdict": self.verdict,
            "candidate_resources": list(self.candidate_resources),
            "reservation_resources": list(self.reservation_resources),
            "overlapping_resources": list(self.overlapping_resources),
            "candidate_contract_sha256": self.candidate_contract_sha256,
            "reservation_contract_sha256": self.reservation_contract_sha256,
        }


@dataclass
class _ReservationBuild:
    """How a reservation was constructed, so it can be re-observed later."""

    task_id: str
    kind: str
    workflow_state: str | None
    phase: str | None
    branch: str | None
    checkout_path: Path | None
    exclusive_resources: tuple[str, ...]
    predicted_paths: tuple[str, ...]
    confidence: float
    local_active: bool
    observable: bool


@dataclass(frozen=True)
class ResumeAuthority:
    """A durable resume claim that exists independently of Stage-2 ranking."""

    task_id: str
    workflow_state: str
    phase: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "workflow_state": self.workflow_state,
            "phase": self.phase,
        }


@dataclass
class ScenarioWorld:
    """Everything one scenario's scheduling cycles are allowed to observe."""

    scenario_id: str
    fixture_root: FixtureRoot
    source: sr.SourceFixture
    tasks: dict[str, dict[str, Any]]
    fresh_queue: tuple[str, ...]
    advisories: dict[str, dict[str, Any]]
    malformed_advisories: dict[str, dict[str, Any]] = field(default_factory=dict)
    resume_authority: ResumeAuthority | None = None
    architect_available: bool = True
    builds: dict[str, _ReservationBuild] = field(default_factory=dict)
    launched: list[dict[str, str]] = field(default_factory=list)
    transition_log: list[str] = field(default_factory=list)

    # -- observation ----------------------------------------------------

    @property
    def source_root(self) -> Path:
        return self.source.root

    @property
    def checkout_root(self) -> Path:
        return self.source.checkout_root

    @property
    def repository_identity(self) -> str:
        """The fixture's own immutable repository identity.

        Bound here so a live proof records the identity of the repository it
        actually ran against instead of a free-form label. The live verifier
        re-reads the same value from the checkout it is given.
        """

        return self.source.repository_identity

    def source_head(self) -> str:
        return git_text(self.source_root, "rev-parse", "HEAD")

    def source_tree(self) -> str:
        return git_text(self.source_root, "rev-parse", "HEAD^{tree}")

    def reservations(self) -> tuple[Reservation, ...]:
        return tuple(
            sorted(
                (self._observe(build) for build in self.builds.values()),
                key=lambda item: (item.task_id, item.evidence_type),
            )
        )

    def reservation_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.reservations()]

    def integration_fingerprint(self) -> str:
        return integration_fingerprint(self.reservation_dicts())

    def candidate_queue(self) -> tuple[str, ...]:
        """Fresh Stage-2 ranking for this pass, minus locally active tasks.

        This deliberately excludes the resume candidate. A scheduler that
        honors resume priority must read ``resume_candidate()``; it cannot get
        the right answer by taking the head of this list.
        """

        active = {
            build.task_id for build in self.builds.values() if build.local_active
        }
        launched = {entry["task_id"] for entry in self.launched}
        return tuple(
            task_id
            for task_id in self.fresh_queue
            if task_id not in active and task_id not in launched
        )

    def resume_candidate(self) -> str | None:
        """The durable resume claim, if this scenario declares one."""

        if self.resume_authority is None:
            return None
        task_id = self.resume_authority.task_id
        if any(entry["task_id"] == task_id for entry in self.launched):
            return None
        return task_id

    def task(self, task_id: str) -> dict[str, Any]:
        try:
            return dict(self.tasks[task_id])
        except KeyError as exc:
            raise AcceptanceFixtureError(
                f"scenario {self.scenario_id} has no task {task_id}"
            ) from exc

    def advisory(self, task_id: str) -> dict[str, Any] | None:
        """Return the architect advisory for a candidate, or ``None``.

        ``None`` means the invocation failed or produced nothing usable. A
        malformed advisory is returned as-is, defects included, because
        rejecting it is the scheduler's job and scenario H2 exists to prove the
        scheduler does that rather than the harness hiding it.
        """

        if not self.architect_available:
            return None
        if task_id in self.malformed_advisories:
            return dict(self.malformed_advisories[task_id])
        advisory = self.advisories.get(task_id)
        return dict(advisory) if advisory is not None else None

    def is_advisory_malformed(self, task_id: str) -> bool:
        return task_id in self.malformed_advisories

    def compute_disjointness(
        self, candidate_task_id: str, reservation_task_id: str
    ) -> DisjointnessEvidence:
        """Derive a disjointness verdict from committed structured data only."""

        candidate = self.task(candidate_task_id)
        reservation_task = self.task(reservation_task_id)
        candidate_resources = normalize_tokens(
            candidate.get("exclusive_resources", ())
        )
        reservation_resources = normalize_tokens(
            reservation_task.get("exclusive_resources", ())
        )
        folded_candidate = {value.casefold(): value for value in candidate_resources}
        folded_reservation = {
            value.casefold(): value for value in reservation_resources
        }
        overlapping = tuple(
            folded_candidate[key]
            for key in sorted(set(folded_candidate) & set(folded_reservation))
        )
        if overlapping:
            verdict = DISJOINT_OVERLAPPING
        elif candidate_resources and reservation_resources:
            verdict = DISJOINT_PROVABLE
        else:
            # Silence is never disjointness. If either side declares no
            # committed exclusive resource, nothing structured establishes that
            # the two surfaces cannot collide.
            verdict = DISJOINT_NOT_PROVABLE
        return DisjointnessEvidence(
            candidate_task_id=candidate_task_id,
            reservation_task_id=reservation_task_id,
            verdict=verdict,
            candidate_resources=candidate_resources,
            reservation_resources=reservation_resources,
            overlapping_resources=overlapping,
            candidate_contract_sha256=str(candidate.get("task_contract_sha256", "")),
            reservation_contract_sha256=str(
                reservation_task.get("task_contract_sha256", "")
            ),
        )

    def durable_state(self) -> dict[str, Any]:
        """Snapshot everything a WAIT is forbidden to change.

        Covers real Git state in the source repository and every checkout, the
        set of launched assignments, the resume claim, and the observed
        reservation set.
        """

        checkouts: dict[str, Any] = {}
        if self.checkout_root.is_dir():
            for path in sorted(self.checkout_root.iterdir()):
                if sr.is_git_checkout(path):
                    checkouts[path.name] = sr.observe_repository_state(path)
                elif path.is_dir():
                    checkouts[path.name] = {
                        "unobservable": sorted(
                            item.name for item in path.rglob("*") if item.is_file()
                        )
                    }
        return {
            "source": sr.observe_repository_state(self.source_root),
            "checkouts": checkouts,
            "launched": [dict(entry) for entry in self.launched],
            "resume_authority": (
                self.resume_authority.to_dict() if self.resume_authority else None
            ),
            "reservations": self.reservation_dicts(),
        }

    def durable_state_fingerprint(self) -> str:
        return canonical_sha256(self.durable_state())

    def _observe(self, build: _ReservationBuild) -> Reservation:
        if not build.observable:
            # An unreadable surface is recorded as UNKNOWN, never as "no paths".
            # Reporting empty here would be the most dangerous silent failure
            # the design names, so the fixture proves the distinction exists.
            return Reservation(
                task_id=build.task_id,
                workflow_state=build.workflow_state,
                phase=build.phase,
                branch=build.branch,
                head=None,
                checkout_path=(
                    str(build.checkout_path) if build.checkout_path else None
                ),
                exclusive_resources=build.exclusive_resources,
                predicted_paths=build.predicted_paths,
                actual_paths=(),
                unity_serialized_assets=unity_serialized_assets(
                    build.predicted_paths
                ),
                unity_asset_identities=unity_asset_identities(build.predicted_paths),
                confidence=build.confidence,
                evidence_type=EVIDENCE_UNKNOWN,
                surface_unknown=True,
                local_active=build.local_active,
            )
        actual: list[str] = []
        head: str | None = None
        saw_branch = False
        saw_checkout = False
        if build.branch:
            actual.extend(
                sr.observe_branch_paths(self.source_root, branch=build.branch)
            )
            head = git_text(self.source_root, "rev-parse", build.branch)
            saw_branch = True
        if build.checkout_path is not None and sr.is_git_checkout(build.checkout_path):
            actual.extend(sr.observe_working_tree_paths(build.checkout_path))
            saw_checkout = True
        actual_paths = normalize_observed_paths(actual)
        if build.local_active:
            evidence = (
                EVIDENCE_ACTIVE_ACTUAL if actual_paths else EVIDENCE_ACTIVE_PREDICTION
            )
        elif saw_branch and saw_checkout:
            evidence = EVIDENCE_BRANCH_AND_CHECKOUT
        elif saw_branch:
            evidence = EVIDENCE_BRANCH
        else:
            # A non-active reservation with neither a branch nor a readable
            # checkout has no observable surface at all. Recording it as
            # "known and empty" is exactly the silent failure this harness
            # exists to prevent, so the fixture is rejected instead.
            raise AcceptanceFixtureError(
                f"reservation {build.task_id} declares an observable surface but "
                "has neither a branch nor a readable checkout; declare "
                "reservation_kind 'unobservable_surface' if that is intended"
            )
        combined = (*actual_paths, *build.predicted_paths)
        return Reservation(
            task_id=build.task_id,
            workflow_state=build.workflow_state,
            phase=build.phase,
            branch=build.branch,
            head=head,
            checkout_path=(str(build.checkout_path) if build.checkout_path else None),
            exclusive_resources=build.exclusive_resources,
            predicted_paths=build.predicted_paths,
            actual_paths=actual_paths,
            unity_serialized_assets=unity_serialized_assets(combined),
            unity_asset_identities=unity_asset_identities(combined),
            confidence=build.confidence,
            evidence_type=evidence,
            surface_unknown=False,
            local_active=build.local_active,
        )

    # -- mutation -------------------------------------------------------

    def record_launch(self, task_id: str, worker_id: str) -> None:
        """Turn a START into a locally active reservation.

        A launch requires an observed non-empty worker ID. There is deliberately
        no fallback that invents one: an acceptance claim about "exactly one
        worker per task" is worthless if the harness can supply the identity the
        scheduler failed to record.
        """

        task_id = validate_synthetic_task_id(task_id)
        worker = str(worker_id or "").strip()
        if not worker:
            raise AcceptanceFixtureError(
                f"cannot record a launch for {task_id} without an observed, "
                "non-empty worker_id; missing evidence is never synthesized"
            )
        if any(entry["task_id"] == task_id for entry in self.launched):
            raise AcceptanceFixtureError(
                f"duplicate assignment for {task_id} in scenario {self.scenario_id}"
            )
        advisory = self.advisories.get(task_id) or {}
        surface = advisory.get("predicted_change_surface") or {}
        predicted = normalize_observed_paths(surface.get("exact_paths", ()))
        checkout = self.checkout_root / task_id
        self.launched.append({"task_id": task_id, "worker_id": worker})
        self.builds[task_id] = _ReservationBuild(
            task_id=task_id,
            kind="scheduler_active_checkout",
            workflow_state="scheduler_active",
            phase=None,
            branch=None,
            checkout_path=checkout if checkout.is_dir() else None,
            exclusive_resources=normalize_tokens(
                self.task(task_id).get("exclusive_resources", ())
            ),
            predicted_paths=predicted,
            confidence=float(advisory.get("confidence", 0.5)),
            local_active=True,
            observable=True,
        )

    def apply_transition(self, transition: Mapping[str, Any] | None) -> None:
        if not transition:
            return
        kind = str(transition.get("kind", "")).strip()
        handler = getattr(self, f"_transition_{kind}", None)
        if handler is None:
            raise AcceptanceFixtureError(f"unknown scenario transition: {kind!r}")
        handler(transition)
        self.transition_log.append(canonical_json(dict(transition)))

    def _transition_worker_actual_change(self, transition: Mapping[str, Any]) -> None:
        """A running worker actually edits files its prediction did not name."""

        task_id = validate_synthetic_task_id(transition.get("task_id"))
        build = self.builds.get(task_id)
        if build is None or not build.local_active:
            raise AcceptanceFixtureError(
                f"{task_id} is not locally active; cannot record actual changes"
            )
        checkout = self.checkout_root / task_id
        if not sr.is_git_checkout(checkout):
            checkout = sr.clone_checkout(
                self.source, task_id=task_id, branch=sr.DEFAULT_BRANCH
            )
        sr.apply_working_tree_edits(
            self.source,
            checkout,
            marker=f"{self.scenario_id}:{task_id}:actual",
            tracked_modified=transition.get("tracked_modified", ()),
            staged=transition.get("staged", ()),
            untracked=transition.get("untracked", ()),
        )
        build.checkout_path = checkout

    def _transition_integrate_reservation(
        self, transition: Mapping[str, Any]
    ) -> None:
        """Merge an unmerged branch so its reservation is genuinely released."""

        task_id = validate_synthetic_task_id(transition.get("task_id"))
        build = self.builds.pop(task_id, None)
        if build is None:
            raise AcceptanceFixtureError(f"no reservation to integrate for {task_id}")
        if build.branch:
            sr.merge_branch_into_main(
                self.source,
                branch=build.branch,
                commit_index=200 + len(self.transition_log),
            )

    def _transition_worker_finished(self, transition: Mapping[str, Any]) -> None:
        task_id = validate_synthetic_task_id(transition.get("task_id"))
        build = self.builds.get(task_id)
        if build is None or not build.local_active:
            raise AcceptanceFixtureError(f"{task_id} is not locally active")
        del self.builds[task_id]

    def _transition_architect_unavailable(
        self, _transition: Mapping[str, Any]
    ) -> None:
        self.architect_available = False

    def _transition_architect_restored(self, _transition: Mapping[str, Any]) -> None:
        self.architect_available = True


def _build_task(task_id: str, declared: Mapping[str, Any]) -> dict[str, Any]:
    task = {
        "id": task_id,
        "title": str(declared.get("title", "")),
        "summary": str(declared.get("summary", "")),
        "exclusive_resources": list(
            normalize_tokens(declared.get("exclusive_resources", ()))
        ),
        "intended_change_surface": {
            "exact_paths": list(
                sr.validate_declared_paths(
                    (declared.get("intended_change_surface") or {}).get(
                        "exact_paths", ()
                    ),
                    where=f"{task_id}.intended_change_surface",
                )
            )
        },
    }
    task["task_contract_sha256"] = synthetic_contract_sha256(task_id, task)
    return task


def _normalized_advisory(task_id: str, declared: Mapping[str, Any]) -> dict[str, Any]:
    surface = declared.get("predicted_change_surface") or {}
    escalation = declared.get("escalation") or {"category": "none", "question": ""}
    exact = sr.validate_declared_paths(
        surface.get("exact_paths", ()), where=f"{task_id}.predicted_change_surface"
    )
    return {
        "task_id": task_id,
        "predicted_change_surface": {
            "exact_paths": list(exact),
            "unity_serialized_assets": list(unity_serialized_assets(exact)),
            "unity_asset_identities": list(unity_asset_identities(exact)),
        },
        "integration_risk": str(declared.get("integration_risk", "unknown")),
        "parallel_recommendation": str(
            declared.get("parallel_recommendation", "wait")
        ),
        "confidence": float(declared.get("confidence", 0.0)),
        "conflicting_task_ids": list(
            normalize_tokens(declared.get("conflicting_task_ids", ()))
        ),
        "escalation": {
            "category": str(escalation.get("category", "none")),
            "question": str(escalation.get("question", "")),
        },
        "disjointness_claims": [
            validate_synthetic_task_id(entry)
            for entry in declared.get("disjointness_claims", ())
        ],
    }


def _malformed_advisory(
    scenario_id: str, task_id: str, defects: Sequence[str]
) -> dict[str, Any]:
    """Synthesize a deterministic, structurally invalid architect response.

    The manifest declares *which* defects to inject from a closed vocabulary
    rather than embedding a free-form broken payload, so a malformed fixture
    stays reproducible and cannot smuggle an arbitrary object past validation.
    """

    payload: dict[str, Any] = {
        "task_id": task_id,
        "scenario_id": scenario_id,
        "predicted_change_surface": {
            "exact_paths": ["SyntheticGame/Scripts/Enemy/EnemyPursuit.cs"],
            "unity_serialized_assets": [],
            "unity_asset_identities": [],
        },
        "integration_risk": "low",
        "parallel_recommendation": "start",
        "confidence": 0.95,
        "conflicting_task_ids": [],
        "escalation": {"category": "none", "question": ""},
        "disjointness_claims": [],
        "advisory_defects": list(defects),
    }
    for defect in defects:
        if defect == "wrong_task_id":
            # A valid-looking but wrong ID: same synthetic range, different task.
            payload["task_id"] = "NSC-999"
        elif defect == "wrong_scenario_binding":
            payload["scenario_id"] = "SAA-not-this-scenario"
        elif defect == "missing_predicted_change_surface":
            payload.pop("predicted_change_surface", None)
        elif defect == "unknown_structured_field":
            payload["parallel_safe_because"] = "an invented field the schema forbids"
        elif defect == "non_numeric_confidence":
            payload["confidence"] = "very high"
        else:
            raise AcceptanceFixtureError(f"unknown advisory defect: {defect!r}")
    return payload


def build_world(
    scenario: Mapping[str, Any],
    manifest: Mapping[str, Any],
    fixture_root: FixtureRoot,
) -> ScenarioWorld:
    """Materialize one scenario's Git fixture and observed reservations."""

    if not isinstance(fixture_root, FixtureRoot):
        raise AcceptanceFixtureError(
            "a scenario world may only be built inside a FixtureRoot created by "
            "acceptance_lib.create_fixture_root"
        )
    scenario_id = str(scenario["id"])
    world_spec = scenario.get("world") or {}

    source = sr.build_source_repository(fixture_root)
    source.checkout_root.mkdir(parents=True, exist_ok=True)

    declared_tasks: MutableMapping[str, Any] = dict(manifest.get("tasks") or {})
    resume_spec = world_spec.get("resume_authority")
    referenced = set(world_spec.get("fresh_queue") or ())
    referenced.update(
        str(item.get("task_id")) for item in (world_spec.get("reservations") or ())
    )
    if resume_spec:
        referenced.add(str(resume_spec.get("task_id")))
    tasks: dict[str, dict[str, Any]] = {}
    for task_id in sorted(referenced):
        task_id = validate_synthetic_task_id(task_id)
        if task_id not in declared_tasks:
            raise AcceptanceFixtureError(
                f"scenario {scenario_id} references undeclared task {task_id}"
            )
        tasks[task_id] = _build_task(task_id, declared_tasks[task_id])

    advisories = {
        validate_synthetic_task_id(task_id): _normalized_advisory(task_id, declared)
        for task_id, declared in (world_spec.get("advisories") or {}).items()
    }
    malformed = {
        validate_synthetic_task_id(task_id): _malformed_advisory(
            scenario_id, task_id, declared.get("defects", ())
        )
        for task_id, declared in (world_spec.get("malformed_advisories") or {}).items()
    }

    world = ScenarioWorld(
        scenario_id=scenario_id,
        fixture_root=fixture_root,
        source=source,
        tasks=tasks,
        fresh_queue=tuple(
            validate_synthetic_task_id(task_id)
            for task_id in (world_spec.get("fresh_queue") or ())
        ),
        advisories=advisories,
        malformed_advisories=malformed,
        resume_authority=(
            ResumeAuthority(
                task_id=validate_synthetic_task_id(resume_spec.get("task_id")),
                workflow_state=str(resume_spec.get("workflow_state", "")),
                phase=str(resume_spec.get("phase", "")),
            )
            if resume_spec
            else None
        ),
    )

    for index, declared in enumerate(world_spec.get("reservations") or ()):
        build = _install_reservation(world, declared, commit_index=10 + index)
        if build.task_id in world.builds:
            raise AcceptanceFixtureError(
                f"scenario {scenario_id} declares {build.task_id} twice"
            )
        world.builds[build.task_id] = build
    return world


def _install_reservation(
    world: ScenarioWorld,
    declared: Mapping[str, Any],
    *,
    commit_index: int,
) -> _ReservationBuild:
    task_id = validate_synthetic_task_id(declared.get("task_id"))
    kind = str(declared.get("reservation_kind", "")).strip()
    if kind not in RESERVATION_KINDS:
        raise AcceptanceFixtureError(
            f"unknown reservation kind {kind!r} for {task_id}"
        )
    branch_paths = sr.validate_declared_paths(
        declared.get("branch_paths", ()), where=f"{task_id}.branch_paths"
    )
    checkout_spec = declared.get("checkout")
    branch: str | None = None
    if branch_paths:
        branch = f"task/{task_id}"
        sr.create_work_branch(
            world.source,
            branch=branch,
            paths=list(branch_paths),
            marker=f"{world.scenario_id}:{task_id}",
            message=f"Synthetic in-flight work for {task_id}",
            commit_index=commit_index,
        )
    checkout_path: Path | None = None
    if checkout_spec:
        checkout_path = sr.clone_checkout(
            world.source, task_id=task_id, branch=branch or sr.DEFAULT_BRANCH
        )
        sr.apply_working_tree_edits(
            world.source,
            checkout_path,
            marker=f"{world.scenario_id}:{task_id}:wt",
            tracked_modified=checkout_spec.get("tracked_modified", ()),
            staged=checkout_spec.get("staged", ()),
            untracked=checkout_spec.get("untracked", ()),
        )
    observable = kind != "unobservable_surface"
    if not observable:
        if checkout_path is not None:
            sr.make_surface_unobservable(world.source, checkout_path)
        branch = None
    return _ReservationBuild(
        task_id=task_id,
        kind=kind,
        workflow_state=declared.get("workflow_state"),
        phase=declared.get("phase"),
        branch=branch,
        checkout_path=checkout_path,
        exclusive_resources=normalize_tokens(
            world.tasks.get(task_id, {}).get("exclusive_resources", ())
        ),
        predicted_paths=sr.validate_declared_paths(
            declared.get("predicted_paths", ()), where=f"{task_id}.predicted_paths"
        ),
        confidence=float(declared.get("confidence", 0.5)),
        local_active=kind == "scheduler_active_checkout",
        observable=observable,
    )


def destroy_world(world: ScenarioWorld) -> None:
    """Delete the fixture root this world owns, with full identity proof."""

    destroy_fixture_root(world.fixture_root)


def surface_overlap(left: Iterable[str], right: Iterable[str]) -> tuple[str, ...]:
    """Case-insensitive overlap between two change surfaces.

    Unity serialized assets are compared by asset identity, so a task editing
    ``HUD.prefab`` overlaps a task editing ``HUD.prefab.meta``: they are the
    same non-merge-safe asset.
    """

    folded: dict[str, str] = {}
    for value in normalize_observed_paths(left):
        folded.setdefault(_overlap_key(value), value)
    other = {_overlap_key(value) for value in normalize_observed_paths(right)}
    return tuple(sorted(folded[key] for key in sorted(set(folded) & other)))


def _overlap_key(value: str) -> str:
    from acceptance_lib import is_unity_serialized_asset, unity_asset_identity

    if is_unity_serialized_asset(value):
        return unity_asset_identity(value).casefold()
    return value.casefold()


def declared_surface(world: ScenarioWorld, task_id: str) -> tuple[str, ...]:
    """The paths a scenario says a task intends to change."""

    task = world.task(task_id)
    return normalize_observed_paths(
        (task.get("intended_change_surface") or {}).get("exact_paths", ())
    )


def reservation_surface(reservation: Reservation) -> tuple[str, ...]:
    return normalize_observed_paths(
        (*reservation.actual_paths, *reservation.predicted_paths)
    )
