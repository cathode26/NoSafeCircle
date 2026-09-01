#!/usr/bin/env python3
"""Deterministic smoke tests for the Software Architect Acceptance Gauntlet.

These are **HARNESS TESTS**. They prove the manifest, the synthetic fixture
generator, the adapter boundary, the path-containment rules, and the verifiers
behave correctly. They prove nothing whatsoever about the polling Software
Architect scheduler, which is not committed to this branch.

The adversarial block is the point of this file. Each test there reproduces a
finding from the independent audit and pins the corrected behavior, so a future
edit that reintroduces the weakness fails here rather than during a live proof.

Nothing here contacts a network, GitHub, or a model provider. Socket creation is
blocked for the whole run, a static scan asserts the package launches no
subprocess other than `git`, and no test ever deletes a directory this package
did not create.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import socket
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import acceptance_lib
import manifest as manifest_module
import scenario_world as sw
import scheduler_adapter
import synthetic_repository as sr
import verify_acceptance
import verify_live_evidence as live
from acceptance_lib import (
    ACCEPTANCE_STATUSES,
    ACCEPTANCE_DIR,
    DESTROY_ALREADY_DONE,
    DESTROY_REMOVED,
    AcceptanceFixtureError,
    AcceptanceManifestError,
    AcceptanceSafetyError,
    CAPABILITIES,
    EVIDENCE_SCHEMA_VERSION,
    FIXTURE_MARKER_NAME,
    OUTCOMES,
    PathContainmentError,
    READINESS_GATES,
    ROOT,
    STATUS_FIXTURE_FAIL,
    STATUS_FIXTURE_PASS,
    STATUS_HARNESS_FAIL,
    STATUS_HARNESS_PASS,
    STATUS_PENDING,
    DisposableParent,
    FixtureRoot,
    create_disposable_parent,
    create_fixture_root,
    destroy_disposable_parent,
    destroy_fixture_root,
    git_version,
    looks_like_production_repository,
    require_safe_target_repository,
    resolve_within,
)
from scheduler_adapter import (
    AdapterNotWired,
    ConflictObservation,
    CycleObservation,
    RealPollingArchitectAdapter,
    ScriptedAdapter,
)

MANIFEST_SHA = manifest_module.manifest_sha256()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_raises(exception, call, message: str) -> None:
    try:
        call()
    except exception:
        return
    raise AssertionError(message)


def _block_network() -> None:
    """Fail loudly if any test path tries to open a socket."""

    def refuse(*_args, **_kwargs):
        raise AssertionError(
            "the acceptance harness must never open a network connection"
        )

    socket.socket = refuse  # type: ignore[assignment]
    socket.create_connection = refuse  # type: ignore[assignment]


class _Fixture:
    """Context manager that owns one disposable parent and one fixture root."""

    def __init__(self, name: str = "test") -> None:
        self.name = name
        self.parent: DisposableParent | None = None
        self.root: FixtureRoot | None = None

    def __enter__(self) -> FixtureRoot:
        self.parent = create_disposable_parent()
        self.root = create_fixture_root(self.parent, self.name)
        return self.root

    def __exit__(self, *_exc) -> None:
        if self.root is not None:
            destroy_fixture_root(self.root)
        if self.parent is not None:
            destroy_disposable_parent(self.parent)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def test_manifest_is_valid_and_ids_are_unique() -> None:
    manifest = manifest_module.load_manifest()
    scenarios = manifest_module.scenarios(manifest)
    ids = [scenario["id"] for scenario in scenarios]
    require(len(ids) == len(set(ids)), "scenario ids are not unique")
    letters = {scenario["letter"] for scenario in scenarios}
    require(
        letters == set("ABCDEFGHIJ"),
        f"the active suite is A through J; found {sorted(letters)}",
    )


def test_manifest_states_are_recognized() -> None:
    manifest = manifest_module.load_manifest()
    for scenario in manifest_module.scenarios(manifest):
        require(
            scenario["readiness"] in READINESS_GATES,
            f"{scenario['id']}: unknown readiness gate",
        )
        for capability in scenario["required_capabilities"]:
            require(
                capability in CAPABILITIES,
                f"{scenario['id']}: unknown capability {capability}",
            )
        for step in scenario.get("steps", ()):
            require(
                step["expected"]["outcome"] in OUTCOMES,
                f"{scenario['id']}: unknown outcome",
            )


def test_manifest_carries_no_retired_decomposition_vocabulary() -> None:
    """K, L and M are future specifications, not silently disabled scenarios."""

    text = (ACCEPTANCE_DIR / "scenarios.json").read_text(encoding="utf-8")
    for banned in (
        "decomposition_expectation",
        "authority_chain",
        "graph_delta",
        "plan_sha256",
        "overlap_matrix",
    ):
        require(
            banned not in text,
            f"the active manifest still carries retired decomposition data: {banned}",
        )


def test_manifest_surface_matches_the_fixture_generator() -> None:
    """Every path any scenario names must be a path the generator creates."""

    manifest = manifest_module.load_manifest()
    generated = {item["path"] for item in sr.file_roles()}
    for task_id, task in manifest["tasks"].items():
        for path in task["intended_change_surface"]["exact_paths"]:
            require(
                path in generated,
                f"{task_id} names {path}, which the fixture generator never creates",
            )


def test_every_declared_task_is_referenced() -> None:
    manifest = manifest_module.load_manifest()
    require(
        not manifest_module.unused_task_ids(manifest),
        f"dead task declarations: {manifest_module.unused_task_ids(manifest)}",
    )


def test_scenarios_only_use_synthetic_task_ids() -> None:
    manifest = manifest_module.load_manifest()
    for task_id in manifest["tasks"]:
        require(
            re.fullmatch(r"NSC-9[0-9]{2}", task_id) is not None,
            f"{task_id} is outside the reserved synthetic range",
        )
        require(
            task_id != manifest_module.RESERVED_UNDECLARED_TASK_ID,
            "NSC-999 must stay undeclared so fabricated evidence is detectable",
        )


# ---------------------------------------------------------------------------
# Adversarial: strict manifest validation
# ---------------------------------------------------------------------------

def _mutate(mutation) -> None:
    manifest = manifest_module.load_manifest()
    mutation(manifest)
    manifest_module.validate_manifest(manifest)


def test_manifest_rejects_an_unknown_outcome() -> None:
    expect_raises(
        AcceptanceManifestError,
        lambda: _mutate(
            lambda m: m["scenarios"][0]["steps"][0]["expected"].update(
                outcome="definitely_not_real"
            )
        ),
        "the validator accepted an unknown outcome",
    )


def test_manifest_rejects_unknown_fields_everywhere() -> None:
    """ADVERSARIAL 10. Every authority-bearing object has an exact key set."""

    mutations = {
        "root": lambda m: m.update(extra_root_field=True),
        "source_identity": lambda m: m["source_identity"].update(extra=True),
        "task": lambda m: m["tasks"]["NSC-901"].update(priority="high"),
        "change_surface": lambda m: m["tasks"]["NSC-901"][
            "intended_change_surface"
        ].update(path_patterns=[]),
        "scenario": lambda m: m["scenarios"][0].update(severity="critical"),
        "world": lambda m: m["scenarios"][0]["world"].update(stage2_queue=[]),
        "reservation": lambda m: m["scenarios"][3]["world"]["reservations"][0].update(
            shared_systems=["hud"]
        ),
        "advisory": lambda m: m["scenarios"][0]["world"]["advisories"][
            "NSC-901"
        ].update(conflict_reasons=["because"]),
        "predicted_surface": lambda m: m["scenarios"][0]["world"]["advisories"][
            "NSC-901"
        ]["predicted_change_surface"].update(symbols_or_components=[]),
        "fixture_facts": lambda m: m["scenarios"][0]["fixture_facts"].update(
            trust_me=True
        ),
        "step": lambda m: m["scenarios"][0]["steps"][0].update(comment="x"),
        "expected": lambda m: m["scenarios"][0]["steps"][0]["expected"].update(
            commit_count=1
        ),
        "conflict": lambda m: m["scenarios"][1]["steps"][1]["expected"]["conflicts"][
            0
        ].update(severity="high"),
        "transition": lambda m: m["scenarios"][4]["steps"][1]["transition"].update(
            force=True
        ),
        "live_evidence": lambda m: m["scenarios"][0]["live_evidence"].update(
            best_effort_checks=[]
        ),
        "operation": lambda m: m["scenarios"][12]["operation"].update(timeout=30),
    }
    for label, mutation in mutations.items():
        expect_raises(
            AcceptanceManifestError,
            lambda mutation=mutation: _mutate(mutation),
            f"an unknown field was accepted on the {label} object",
        )


def test_manifest_rejects_broken_task_references() -> None:
    """ADVERSARIAL 11."""

    mutations = {
        "queue": lambda m: m["scenarios"][0]["world"]["fresh_queue"].append("NSC-955"),
        "reserved id": lambda m: m["scenarios"][0]["world"]["fresh_queue"].append(
            "NSC-999"
        ),
        "expected task": lambda m: m["scenarios"][0]["steps"][0]["expected"].update(
            task_id="NSC-910"
        ),
        "waited task": lambda m: m["scenarios"][0]["steps"][0]["expected"].update(
            waited_task_ids=["NSC-916"]
        ),
        "conflict pair": lambda m: m["scenarios"][1]["steps"][1]["expected"][
            "conflicts"
        ][0].update(conflicting_task_id="NSC-916"),
        "fixture fact": lambda m: m["scenarios"][0]["fixture_facts"].update(
            disjoint_pairs=[["NSC-901", "NSC-916"]]
        ),
    }
    for label, mutation in mutations.items():
        expect_raises(
            AcceptanceManifestError,
            lambda mutation=mutation: _mutate(mutation),
            f"a broken task reference was accepted: {label}",
        )


def test_manifest_rejects_an_unbacked_exclusive_resource_conflict() -> None:
    expect_raises(
        AcceptanceManifestError,
        lambda: _mutate(
            lambda m: m["scenarios"][11]["steps"][0]["expected"]["conflicts"][0].update(
                on=["logical:not-declared-by-either-task"]
            )
        ),
        "a conflict claimed an exclusive resource neither task declares",
    )


def test_manifest_requires_a_worker_id_for_every_start() -> None:
    expect_raises(
        AcceptanceManifestError,
        lambda: _mutate(
            lambda m: m["scenarios"][0]["steps"][0]["expected"].pop("require_worker_id")
        ),
        "a START was accepted without requiring an observed worker ID",
    )


def test_manifest_rejects_an_unknown_live_evidence_check() -> None:
    expect_raises(
        AcceptanceManifestError,
        lambda: _mutate(
            lambda m: m["scenarios"][0]["live_evidence"]["required_checks"].append(
                "looks_fine_to_me"
            )
        ),
        "an unknown live-evidence check name was accepted",
    )


def test_manifest_rejects_prearranged_resume_priority() -> None:
    """ADVERSARIAL 13. I1 may not encode resume priority as queue order."""

    expect_raises(
        AcceptanceManifestError,
        lambda: _mutate(
            lambda m: m["scenarios"][10]["world"]["fresh_queue"].insert(0, "NSC-906")
        ),
        "the resume task was allowed to sit in the fresh Stage-2 ranking",
    )
    expect_raises(
        AcceptanceManifestError,
        lambda: _mutate(
            lambda m: m["scenarios"][10]["world"].update(fresh_queue=[])
            or m["scenarios"][10]["world"]["advisories"].pop("NSC-901")
        ),
        "a resume scenario with no competing fresh candidate was accepted",
    )
    expect_raises(
        AcceptanceManifestError,
        lambda: _mutate(
            lambda m: m["scenarios"][10]["fixture_facts"].pop("resume_is_not_queue_order")
        ),
        "a resume-priority scenario was accepted without the anti-prearrangement fact",
    )


def test_manifest_rejects_a_singleton_scenario_with_scripted_steps() -> None:
    """ADVERSARIAL 15, first half. J must be an operation, never a step."""

    def add_steps(manifest):
        scenario = manifest["scenarios"][12]
        scenario["steps"] = [{"step": 1, "expected": {"outcome": "idle"}}]

    expect_raises(
        AcceptanceManifestError,
        lambda: _mutate(add_steps),
        "the singleton scenario was allowed to declare scripted steps",
    )


# ---------------------------------------------------------------------------
# Adversarial: path containment and destructive safety
# ---------------------------------------------------------------------------

def test_declared_paths_reject_every_escape_form() -> None:
    """ADVERSARIAL 8 and the containment half of blocker 3."""

    escapes = [
        "/etc/passwd",
        "//server/share/file.txt",
        "C:/Windows/system32/x.txt",
        "C:\\Windows\\system32\\x.txt",
        "\\\\server\\share\\x.txt",
        "SyntheticGame\\Scenes\\Game.unity",
        "SyntheticGame/../../outside.txt",
        "SyntheticGame/../outside.txt",
        "SyntheticGame/./Scenes/Game.unity",
        "SyntheticGame//Scenes/Game.unity",
        "../SyntheticGame/Scenes/Game.unity",
        "Assets/NoSafeCircle/Real.prefab",
        "SyntheticGame/Scenes/Game\x00.unity",
        "",
        "   ",
    ]
    for candidate in escapes:
        expect_raises(
            (PathContainmentError, AcceptanceFixtureError),
            lambda candidate=candidate: sr.validate_declared_paths([candidate]),
            f"a path escape was accepted: {candidate!r}",
        )
    require(
        sr.validate_declared_paths(["SyntheticGame/Scenes/Game.unity"])
        == ("SyntheticGame/Scenes/Game.unity",),
        "a legitimate nested synthetic path was rejected",
    )


def test_resolve_within_rejects_a_symlink_escape() -> None:
    with _Fixture("symlink") as fixture:
        outside = fixture.parent / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("not fixture data\n", encoding="utf-8")
        inside = fixture.path / "SyntheticGame"
        inside.mkdir(parents=True)
        link = inside / "Escape"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
            return
        expect_raises(
            PathContainmentError,
            lambda: resolve_within(fixture.path, "SyntheticGame/Escape/secret.txt"),
            "a symlink was allowed to redirect a write outside the fixture root",
        )
        require(
            isinstance(
                resolve_within(fixture.path, "SyntheticGame/Scenes/Game.unity"), Path
            ),
            "a contained path was rejected",
        )


def _forge(handle_type, copy_identity_from=None):
    """Build a lookalike ownership handle without the module's constructor.

    This is exactly what the audit did: `object.__new__` bypasses the private
    constructor token, and `object.__setattr__` defeats the handle's own
    immutability. Neither gains ownership, because the registry binds the
    authoritative facts to the *object* that was registered.
    """

    forged = object.__new__(handle_type)
    if copy_identity_from is not None:
        object.__setattr__(
            forged, "_handle_id", getattr(copy_identity_from, "_handle_id")
        )
    return forged


def test_destroy_refuses_everything_it_did_not_create() -> None:
    """ADVERSARIAL 7 and 9. `/` and a foreign temp directory are never deleted."""

    expect_raises(
        AcceptanceSafetyError,
        lambda: destroy_fixture_root("/"),
        "the string '/' was accepted as a deletion target",
    )
    expect_raises(
        AcceptanceSafetyError,
        lambda: destroy_fixture_root(Path("/")),
        "a bare path was accepted as a deletion target",
    )
    expect_raises(
        AcceptanceSafetyError,
        lambda: destroy_disposable_parent("/tmp"),
        "a bare path was accepted as a disposable parent",
    )
    parent = create_disposable_parent()
    try:
        real = create_fixture_root(parent, "genuine")
        (real.path / "content.txt").write_text("x\n", encoding="utf-8")

        # A tampered marker on a genuine root.
        (real.path / FIXTURE_MARKER_NAME).write_text(
            json.dumps({"token": "wrong"}), encoding="utf-8"
        )
        expect_raises(
            AcceptanceSafetyError,
            lambda: destroy_fixture_root(real),
            "a fixture root with a mismatched marker token was deleted",
        )
        require(real.path.is_dir(), "the tampered fixture root was removed anyway")
        # The package can no longer prove this root, by design, so the test
        # removes the directory it created itself.
        shutil.rmtree(real.path)

        # A symlink planted where the fixture root is registered.
        alias = create_fixture_root(parent, "aliased")
        target = alias.path
        for item in sorted(target.rglob("*"), reverse=True):
            item.unlink()
        target.rmdir()
        elsewhere = parent.path / "elsewhere"
        elsewhere.mkdir()
        target.symlink_to(elsewhere, target_is_directory=True)
        expect_raises(
            AcceptanceSafetyError,
            lambda: destroy_fixture_root(alias),
            "a symlink standing in for a fixture root was followed and deleted",
        )
        require(elsewhere.is_dir(), "the symlink target was removed")
        target.unlink()
    finally:
        destroy_disposable_parent(parent, destroy_registered_children=True)


def test_forged_ownership_handles_are_inert() -> None:
    """BLOCKER 3, regressions 1-4 and 8. A handle's fields are never authority."""

    for handle_type in (DisposableParent, FixtureRoot):
        expect_raises(
            AcceptanceSafetyError,
            lambda handle_type=handle_type: handle_type(),
            f"{handle_type.__name__} could be constructed directly",
        )
        require(
            handle_type.__slots__ == (),
            f"{handle_type.__name__} carries data fields a caller could set",
        )

    parents_before = len(acceptance_lib._ACTIVE_PARENTS)
    fixtures_before = len(acceptance_lib._ACTIVE_FIXTURES)

    parent = create_disposable_parent()
    foreign = Path(tempfile.mkdtemp(prefix="saa-foreign-"))
    (foreign / "precious.txt").write_text("do not delete\n", encoding="utf-8")
    try:
        real = create_fixture_root(parent, "genuine")

        # 1 and 2: a forged parent, with and without a copied handle ID.
        for label, forged in {
            "empty": _forge(DisposableParent),
            "copied id": _forge(DisposableParent, copy_identity_from=parent),
        }.items():
            expect_raises(
                AcceptanceSafetyError,
                lambda forged=forged: destroy_disposable_parent(forged),
                f"a forged DisposableParent ({label}) was accepted for deletion",
            )
            expect_raises(
                AcceptanceSafetyError,
                lambda forged=forged: create_fixture_root(forged, "child"),
                f"create_fixture_root accepted a forged parent ({label})",
            )
            expect_raises(
                AcceptanceSafetyError,
                lambda forged=forged: forged.path,
                f"a forged DisposableParent ({label}) exposed a path",
            )

        # 3: a forged fixture root plus a hand-written marker in a foreign
        # directory. The marker is the exact shape the real one has, including a
        # genuine token copied from a real fixture.
        (foreign / FIXTURE_MARKER_NAME).write_text(
            json.dumps(
                {
                    "marker": "software-architect-acceptance-fixture-root",
                    "token": real.token,
                    "path": str(foreign),
                    "device": foreign.stat().st_dev,
                    "inode": foreign.stat().st_ino,
                }
            ),
            encoding="utf-8",
        )
        for label, forged in {
            "empty": _forge(FixtureRoot),
            "copied id": _forge(FixtureRoot, copy_identity_from=real),
        }.items():
            expect_raises(
                AcceptanceSafetyError,
                lambda forged=forged: destroy_fixture_root(forged),
                f"a forged FixtureRoot ({label}) was accepted for deletion",
            )
        require(
            (foreign / "precious.txt").is_file(),
            "a foreign directory with a hand-written marker was deleted",
        )

        # 8: nothing above reached the registry.
        require(
            len(acceptance_lib._ACTIVE_PARENTS) == parents_before + 1
            and len(acceptance_lib._ACTIVE_FIXTURES) == fixtures_before + 1,
            "a forged handle registered ownership: "
            f"parents={len(acceptance_lib._ACTIVE_PARENTS)} "
            f"fixtures={len(acceptance_lib._ACTIVE_FIXTURES)}",
        )
    finally:
        for item in sorted(foreign.rglob("*"), reverse=True):
            item.unlink()
        foreign.rmdir()
        destroy_disposable_parent(parent, destroy_registered_children=True)


def test_destroy_succeeds_for_an_exact_created_fixture() -> None:
    """BLOCKER 3, regressions 5 and 6."""

    parent = create_disposable_parent()
    try:
        root = create_fixture_root(parent, "exact")
        recorded = root.path
        (root.path / "content.txt").write_text("x\n", encoding="utf-8")
        require(root.marker_path.is_file(), "the fixture marker was not written")
        require(
            destroy_fixture_root(root) == DESTROY_REMOVED,
            "an exact created fixture root was not removed",
        )
        require(not recorded.exists(), "the fixture root was not removed")

        # Someone else reuses the path. A repeated destroy must be a no-op that
        # never touches the filesystem again.
        recorded.mkdir()
        (recorded / "someone-elses.txt").write_text("keep\n", encoding="utf-8")
        require(
            destroy_fixture_root(root) == DESTROY_ALREADY_DONE,
            "a repeated destroy did not report already-destroyed",
        )
        require(
            (recorded / "someone-elses.txt").is_file(),
            "a repeated destroy deleted a directory recreated at the same path",
        )
        for item in sorted(recorded.rglob("*"), reverse=True):
            item.unlink()
        recorded.rmdir()
    finally:
        destroy_disposable_parent(parent, destroy_registered_children=True)


def test_parent_cleanup_refuses_a_live_fixture_child() -> None:
    """BLOCKER 3, regression 7."""

    parent = create_disposable_parent()
    child = create_fixture_root(parent, "still-live")
    try:
        expect_raises(
            AcceptanceSafetyError,
            lambda: destroy_disposable_parent(parent),
            "a parent with a live registered fixture child was removed",
        )
        require(child.path.is_dir(), "the live child was removed anyway")
    finally:
        destroy_fixture_root(child)
        require(
            destroy_disposable_parent(parent) == DESTROY_REMOVED,
            "the parent was not removed once its child was gone",
        )


def test_fixture_roots_cannot_be_created_outside_a_disposable_parent() -> None:
    expect_raises(
        AcceptanceSafetyError,
        lambda: create_fixture_root(ROOT, "inside-the-repository"),  # type: ignore[arg-type]
        "a fixture root was created outside a disposable parent",
    )
    parent = create_disposable_parent()
    try:
        for name in ("..", "/absolute", "a/b", ""):
            expect_raises(
                AcceptanceSafetyError,
                lambda name=name: create_fixture_root(parent, name),
                f"an unsafe fixture root name was accepted: {name!r}",
            )
    finally:
        destroy_disposable_parent(parent)


def test_production_targets_are_refused() -> None:
    for repository in (
        "cathode26/NoSafeCircle",
        "cathode26/no-safe-circle",
        "cathode26/NoSafeCircle-Fork",
    ):
        require(
            looks_like_production_repository(repository),
            f"{repository} was not recognized as production",
        )
        expect_raises(
            AcceptanceSafetyError,
            lambda repository=repository: require_safe_target_repository(repository),
            f"{repository} was accepted as a target",
        )


# ---------------------------------------------------------------------------
# Fixture determinism
# ---------------------------------------------------------------------------

def _build_signature() -> tuple:
    with _Fixture("determinism") as fixture:
        source = sr.build_source_repository(fixture)
        branch_head = sr.create_work_branch(
            source,
            branch="task/NSC-905",
            paths=["SyntheticGame/Scenes/Game.unity"],
            marker="determinism",
            message="Synthetic in-flight work",
            commit_index=10,
        )
        checkout = sr.clone_checkout(source, task_id="NSC-905", branch="task/NSC-905")
        sr.apply_working_tree_edits(
            source,
            checkout,
            marker="determinism",
            tracked_modified=["SyntheticGame/Prefabs/HUD.prefab"],
            staged=["SyntheticGame/Scripts/UI/HudController.cs"],
            untracked=["SyntheticGame/Data/AudioCatalog.asset.meta"],
        )
        return (
            source.head,
            source.tree,
            branch_head,
            sr.observe_branch_paths(source.root, branch="task/NSC-905"),
            sr.observe_working_tree_paths(checkout),
            json.dumps(sr.observe_repository_state(source.root), sort_keys=True),
            json.dumps(sr.observe_repository_state(checkout), sort_keys=True),
        )


def test_fixture_generation_is_deterministic_across_two_runs() -> None:
    """Same host, same Git version. Nothing broader is claimed."""

    first = _build_signature()
    second = _build_signature()
    require(
        first == second,
        f"fixture generation is not deterministic on {git_version()}:\n{first}\n{second}",
    )
    require(len(first[0]) == 40, "source HEAD is not a full SHA")


def test_inherited_git_configuration_cannot_change_a_fixture() -> None:
    """The GIT_CONFIG_COUNT/KEY/VALUE command-scope form must be scrubbed."""

    baseline = _build_signature()
    polluted_environment = {
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "user.name",
        "GIT_CONFIG_VALUE_0": "Someone Else",
        "GIT_CONFIG_KEY_1": "core.autocrlf",
        "GIT_CONFIG_VALUE_1": "true",
        "GIT_AUTHOR_NAME": "Hijacked",
        "GIT_COMMITTER_DATE": "1234567890 +0500",
        "GIT_TEMPLATE_DIR": "/nonexistent-template",
    }
    saved = {key: os.environ.get(key) for key in polluted_environment}
    os.environ.update(polluted_environment)
    try:
        polluted = _build_signature()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    require(
        baseline == polluted,
        "inherited GIT_* configuration changed the fixture:\n"
        f"{baseline}\n{polluted}",
    )


def test_fixture_repositories_use_an_empty_hooks_directory() -> None:
    with _Fixture("hooks") as fixture:
        source = sr.build_source_repository(fixture)
        require(
            source.hooks_path.is_dir() and not any(source.hooks_path.iterdir()),
            f"the fixture hooks directory is not empty: {source.hooks_path}",
        )
        repository_hooks = source.root / ".git" / "hooks"
        installed = (
            list(repository_hooks.iterdir()) if repository_hooks.is_dir() else []
        )
        require(
            not installed,
            f"the fixture repository installed template hooks: {installed}",
        )


def test_local_branches_and_diffs_are_reproduced_exactly() -> None:
    with _Fixture("branches") as fixture:
        source = sr.build_source_repository(fixture)
        sr.create_work_branch(
            source,
            branch="task/NSC-906",
            paths=[
                "SyntheticGame/Data/EnemyTuning.asset",
                "SyntheticGame/Scripts/Enemy/RangedEnemyAttack.cs",
            ],
            marker="branches",
            message="two-file branch",
            commit_index=11,
        )
        paths = sr.observe_branch_paths(source.root, branch="task/NSC-906")
        require(
            paths
            == (
                "SyntheticGame/Data/EnemyTuning.asset",
                "SyntheticGame/Scripts/Enemy/RangedEnemyAttack.cs",
            ),
            f"branch diff did not reproduce the intended files: {paths}",
        )
        merged = sr.merge_branch_into_main(
            source, branch="task/NSC-906", commit_index=12
        )
        require(len(merged) == 40, "merge did not produce a commit")
        require(
            sr.observe_branch_paths(source.root, branch="task/NSC-906") == (),
            "an integrated branch still reports changed paths",
        )


def test_unobservable_surface_is_unknown_not_empty() -> None:
    with _Fixture("unknown") as fixture:
        source = sr.build_source_repository(fixture)
        checkout = sr.clone_checkout(source, task_id="NSC-905", branch="main")
        sr.apply_working_tree_edits(
            source,
            checkout,
            marker="unknown",
            tracked_modified=["SyntheticGame/Scenes/Game.unity"],
        )
        require(
            sr.observe_working_tree_paths(checkout)
            == ("SyntheticGame/Scenes/Game.unity",),
            "precondition failed: the checkout should have one changed path",
        )
        sr.make_surface_unobservable(source, checkout)
        require(
            not sr.is_git_checkout(checkout),
            "the surface is still observable after removing Git metadata",
        )


# ---------------------------------------------------------------------------
# Layer 1
# ---------------------------------------------------------------------------

def test_every_scenario_fixture_models_its_declared_facts() -> None:
    results, exit_code = verify_acceptance.verify_fixtures()
    require(exit_code == 0, "fixture verification failed")
    for result in results:
        require(
            result.status == STATUS_FIXTURE_PASS,
            f"{result.scenario_id}: expected {STATUS_FIXTURE_PASS}, got {result.status}",
        )


def test_fixture_verification_catches_a_wrong_declared_path() -> None:
    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(
        manifest, "SAA-D-human-held-unmerged-reservation"
    )
    scenario["fixture_facts"]["reservation_actual_paths"]["NSC-905"] = [
        "SyntheticGame/Scenes/Chapel.unity"
    ]
    with _Fixture("wrong-path") as fixture:
        result = verify_acceptance.run_fixture_scenario(
            scenario, manifest, fixture_root=fixture
        )
    require(
        result.status == STATUS_FIXTURE_FAIL,
        f"a wrong declared path did not fail layer 1: {result.status}",
    )


def test_g2_prose_alone_cannot_establish_disjointness() -> None:
    """ADVERSARIAL 12. Structured resources decide, not the architect's wording."""

    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(
        manifest, "SAA-G2-unknown-surface-provably-disjoint"
    )
    # Strip the committed exclusive resources that actually prove disjointness
    # and leave every persuasive claim in place.
    manifest["tasks"]["NSC-911"]["exclusive_resources"] = []
    manifest["tasks"]["NSC-910"]["exclusive_resources"] = []
    with _Fixture("g2-prose") as fixture:
        result = verify_acceptance.run_fixture_scenario(
            scenario, manifest, fixture_root=fixture
        )
    require(
        result.status == STATUS_FIXTURE_FAIL,
        "removing the structured evidence still left G2 provably disjoint",
    )
    failed = {check.name for check in result.failed_checks}
    require(
        "disjointness[NSC-911,NSC-910]" in failed,
        f"the disjointness recomputation did not fire: {sorted(failed)}",
    )

    # And the same computation, run directly, must refuse to call it disjoint.
    with _Fixture("g2-direct") as fixture:
        world = sw.build_world(scenario, manifest, fixture)
        try:
            verdict = world.compute_disjointness("NSC-911", "NSC-910")
        finally:
            sw.destroy_world(world)
    require(
        verdict.verdict == sw.DISJOINT_NOT_PROVABLE,
        f"silence was treated as disjointness: {verdict.verdict}",
    )


def test_i1_fixture_proves_resume_is_not_queue_order() -> None:
    """ADVERSARIAL 13, fixture half."""

    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(
        manifest, "SAA-I1-resume-outranks-tempting-fresh-work"
    )
    with _Fixture("i1") as fixture:
        world = sw.build_world(scenario, manifest, fixture)
        try:
            queue = world.candidate_queue()
            resume = world.resume_candidate()
            require(
                resume == "NSC-906",
                f"the resume claim was not observable separately: {resume}",
            )
            require(
                "NSC-906" not in queue and queue == ("NSC-901",),
                f"the resume task leaked into the fresh ranking: {queue}",
            )
        finally:
            sw.destroy_world(world)


def test_i2_detects_an_unauthorized_durable_mutation() -> None:
    """ADVERSARIAL 14. A WAIT that changes durable state must be caught."""

    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(
        manifest, "SAA-I2-resume-waits-and-steals-nothing"
    )

    class MutatingAdapter(ScriptedAdapter):
        """A scheduler that quietly commits while claiming it only waited."""

        def observe_cycle(self, world):
            sr.create_work_branch(
                world.source,
                branch="task/NSC-901",
                paths=["SyntheticGame/Scripts/Enemy/EnemyPursuit.cs"],
                marker="unauthorized",
                message="a mutation a WAIT must never make",
                commit_index=77,
            )
            return super().observe_cycle(world)

    expected = scenario["steps"][0]["expected"]
    adapter = MutatingAdapter(
        [
            CycleObservation(
                outcome=expected["outcome"],
                waited_task_ids=tuple(expected["waited_task_ids"]),
                conflicts=tuple(
                    ConflictObservation(
                        kind=conflict["kind"],
                        candidate_task_id=conflict["candidate_task_id"],
                        conflicting_task_id=conflict["conflicting_task_id"],
                        overlapping_values=tuple(conflict["on"]),
                        reason="scripted",
                    )
                    for conflict in expected["conflicts"]
                ),
            )
        ],
        capabilities=set(scenario["required_capabilities"]),
    )
    with _Fixture("i2-mutation") as fixture:
        result = verify_acceptance.run_harness_scenario(
            scenario, manifest, adapter=adapter, fixture_root=fixture
        )
    require(
        result.status == STATUS_HARNESS_FAIL,
        f"an unauthorized durable mutation during a WAIT was accepted: {result.status}",
    )
    require(
        any(
            check.name.endswith("forbid_durable_mutation")
            for check in result.failed_checks
        ),
        f"the durable-state snapshot did not catch it: {result.failed_checks}",
    )


# ---------------------------------------------------------------------------
# Adversarial: acceptance provenance
# ---------------------------------------------------------------------------

def test_harness_replay_can_never_reach_an_acceptance_status() -> None:
    results, _ = verify_acceptance.run_harness()
    require(
        any(result.status == STATUS_HARNESS_PASS for result in results),
        "no scenario was exercised by the harness replay",
    )
    for result in results:
        require(
            result.status not in ACCEPTANCE_STATUSES,
            f"{result.scenario_id}: the harness produced acceptance status "
            f"{result.status}",
        )


def test_spoofed_capabilities_and_identity_cannot_manufacture_a_pass() -> None:
    """ADVERSARIAL 1. The audit's exact reproduction, now impossible."""

    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(
        manifest, "SAA-D-human-held-unmerged-reservation"
    )
    expected = scenario["steps"][0]["expected"]
    adapter = ScriptedAdapter(
        [
            CycleObservation(
                outcome=expected["outcome"],
                waited_task_ids=tuple(expected["waited_task_ids"]),
                conflicts=tuple(
                    ConflictObservation(
                        kind=conflict["kind"],
                        candidate_task_id=conflict["candidate_task_id"],
                        conflicting_task_id=conflict["conflicting_task_id"],
                        overlapping_values=tuple(conflict["on"]),
                        reason="scripted",
                    )
                    for conflict in expected["conflicts"]
                ),
            )
        ],
        capabilities=set(CAPABILITIES),
    )
    # Every trick the audit used: claim every capability, and try to look like
    # the real adapter by any public attribute a verifier might once have read.
    adapter.adapter_kind = "real_polling_architect"  # type: ignore[attr-defined]
    adapter.__class__.__name__ = "RealPollingArchitectAdapter"
    adapter.is_real = True  # type: ignore[attr-defined]

    with _Fixture("spoof") as fixture:
        result = verify_acceptance.run_harness_scenario(
            scenario, manifest, adapter=adapter, fixture_root=fixture
        )
    require(
        result.status == STATUS_HARNESS_PASS,
        f"a spoofed adapter produced {result.status}",
    )
    require(
        result.status not in ACCEPTANCE_STATUSES,
        "a spoofed adapter reached an acceptance status",
    )


def test_acceptance_path_accepts_no_injected_adapter() -> None:
    """ADVERSARIAL 1, structural half. There is nothing to inject."""

    import inspect

    for function in (
        verify_acceptance.run_acceptance,
        verify_acceptance.run_acceptance_scenario,
    ):
        parameters = set(inspect.signature(function).parameters)
        require(
            "adapter" not in parameters,
            f"{function.__name__} accepts an adapter parameter: {sorted(parameters)}",
        )


def test_only_the_acceptance_path_can_emit_pass() -> None:
    """ADVERSARIAL 1, static half. Keeps the property through future edits."""

    source = (ACCEPTANCE_DIR / "verify_acceptance.py").read_text(encoding="utf-8")
    require(
        "adapter_kind" not in source,
        "verify_acceptance.py still reads a caller-controlled adapter identity",
    )
    for name in ("scheduler_adapter.py", "acceptance_lib.py", "scenario_world.py"):
        text = (ACCEPTANCE_DIR / name).read_text(encoding="utf-8")
        require(
            "adapter_kind" not in text,
            f"{name} still declares an adapter-kind string",
        )

    lines = source.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.startswith("def ") or line.startswith("class ")
    ]

    def owner(index: int) -> str:
        previous = [start for start in starts if start <= index]
        return lines[previous[-1]] if previous else "<module>"

    offenders = [
        f"line {index + 1} in {owner(index).strip()}"
        for index, line in enumerate(lines)
        if "STATUS_PASS" in line
        and "status =" in line
        and "run_acceptance_scenario" not in owner(index)
    ]
    require(
        not offenders,
        "STATUS_PASS is assigned outside run_acceptance_scenario: " + str(offenders),
    )


def test_missing_worker_id_cannot_reach_an_acceptance_pass() -> None:
    """ADVERSARIAL 2. A launch without an observed worker ID is a failure."""

    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(manifest, "SAA-A-parallel-safe-assignments")
    adapter = ScriptedAdapter(
        [
            CycleObservation(outcome="start", task_id="NSC-901", worker_id=None),
            CycleObservation(outcome="start", task_id="NSC-902", worker_id=""),
        ],
        capabilities=set(scenario["required_capabilities"]),
    )
    with _Fixture("no-worker") as fixture:
        result = verify_acceptance.run_harness_scenario(
            scenario, manifest, adapter=adapter, fixture_root=fixture
        )
    require(
        result.status == STATUS_HARNESS_FAIL,
        f"a launch with no worker ID was accepted: {result.status}",
    )
    require(
        any("require_worker_id" in check.name for check in result.failed_checks),
        "the worker-ID requirement did not fire",
    )


def test_world_refuses_to_synthesize_a_missing_worker_id() -> None:
    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(manifest, "SAA-A-parallel-safe-assignments")
    with _Fixture("synthesize") as fixture:
        world = sw.build_world(scenario, manifest, fixture)
        try:
            expect_raises(
                AcceptanceFixtureError,
                lambda: world.record_launch("NSC-901", ""),
                "the world invented a worker ID for an unidentified launch",
            )
        finally:
            sw.destroy_world(world)


def test_verifier_discriminates_a_wrong_scheduling_answer() -> None:
    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(
        manifest, "SAA-D-human-held-unmerged-reservation"
    )
    adapter = ScriptedAdapter(
        [CycleObservation(outcome="start", task_id="NSC-914", worker_id="w-1")],
        capabilities=set(scenario["required_capabilities"]),
    )
    with _Fixture("wrong-answer") as fixture:
        result = verify_acceptance.run_harness_scenario(
            scenario, manifest, adapter=adapter, fixture_root=fixture
        )
    require(
        result.status == STATUS_HARNESS_FAIL,
        f"the verifier accepted a launch into a human-held scene: {result.status}",
    )


def test_singleton_cannot_harness_pass_from_one_scripted_cycle() -> None:
    """ADVERSARIAL 15. One cycle can never prove an OS lock."""

    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(manifest, "SAA-J-scheduler-singleton")
    adapter = ScriptedAdapter(
        [CycleObservation(outcome="no_launch")], capabilities=set(CAPABILITIES)
    )
    with _Fixture("singleton") as fixture:
        result = verify_acceptance.run_harness_scenario(
            scenario, manifest, adapter=adapter, fixture_root=fixture
        )
    require(
        result.status == STATUS_PENDING,
        f"a scripted cycle claimed to prove the scheduler singleton: {result.status}",
    )
    require(
        not hasattr(ScriptedAdapter, "observe_singleton_contest"),
        "the scripted adapter can pretend to run a two-scheduler contest",
    )


def test_h2_malformed_output_waits_and_never_escalates() -> None:
    """ADVERSARIAL 16."""

    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(manifest, "SAA-H2-architect-output-malformed")
    with _Fixture("h2-world") as fixture:
        world = sw.build_world(scenario, manifest, fixture)
        try:
            advisory = world.advisory("NSC-901")
            require(advisory is not None, "the malformed advisory was not delivered")
            require(
                world.is_advisory_malformed("NSC-901"),
                "the world did not mark the advisory malformed",
            )
            require(
                advisory["task_id"] == "NSC-999",
                "the wrong-task-id defect was not injected",
            )
            require(
                "predicted_change_surface" not in advisory,
                "the missing-surface defect was not injected",
            )
            require(
                "parallel_safe_because" in advisory,
                "the unknown-structured-field defect was not injected",
            )
        finally:
            sw.destroy_world(world)

    # A scheduler that launches on it must fail, and so must one that escalates.
    for label, observation in {
        "launched": CycleObservation(
            outcome="start", task_id="NSC-901", worker_id="w-1"
        ),
        "escalated": CycleObservation(
            outcome="human_review",
            task_id="NSC-901",
            waited_task_ids=("NSC-901",),
            escalation_category="design_or_canon_ambiguity",
            escalation_question="is this advisory ok?",
        ),
    }.items():
        adapter = ScriptedAdapter(
            [observation], capabilities=set(scenario["required_capabilities"])
        )
        with _Fixture("h2-wrong") as fixture:
            result = verify_acceptance.run_harness_scenario(
                scenario, manifest, adapter=adapter, fixture_root=fixture
            )
        require(
            result.status == STATUS_HARNESS_FAIL,
            f"a malformed advisory that was {label} was accepted: {result.status}",
        )


# ---------------------------------------------------------------------------
# Adversarial: per-step event evidence
# ---------------------------------------------------------------------------

def _cycle_event(name: str, poll_id: str, **fields) -> dict:
    return {"event": name, "poll_id": poll_id, "scheduler_id": "sched-1", **fields}


def _cycle_poll(poll_id: str, poll_index: int, outcome: str, inner: list) -> tuple:
    """One complete in-process poll: start, decision records, terminal record."""

    return (
        _cycle_event("poll_started", poll_id, poll_index=poll_index),
        *inner,
        _cycle_event("poll_finished", poll_id, poll_index=poll_index, outcome=outcome),
    )


def _cycle_launch(poll_id: str, task_id: str, worker_id: str) -> dict:
    return _cycle_event(
        "worker_launched",
        poll_id,
        task_id=task_id,
        worker_id=worker_id,
        argv=[
            "docker",
            "compose",
            "run",
            "worker",
            "--task-id",
            task_id,
            "--worker-id",
            worker_id,
        ],
    )


def _cycle_wait(poll_id: str, task_id: str, other: str, values: list) -> dict:
    return _cycle_event(
        "candidate_waited",
        poll_id,
        task_id=task_id,
        wait_kind="exact_path_actual",
        conflicting_task_id=other,
        overlapping_values=values,
    )


def _step_evidence(scenario_id: str, observations: list) -> list:
    """Drive one scenario through the harness and return its per-step evidence."""

    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(manifest, scenario_id)
    adapter = ScriptedAdapter(
        observations, capabilities=set(scenario["required_capabilities"])
    )
    with _Fixture("evidence") as fixture:
        world = sw.build_world(scenario, manifest, fixture)
        try:
            return scenario, verify_acceptance.collect_step_evidence(
                scenario, world, adapter
            )
        finally:
            sw.destroy_world(world)


def _failed_evidence_checks(scenario, evidence) -> list:
    return [
        check.name
        for check in verify_acceptance.verify_step_evidence(scenario, evidence)
        if not check.passed
    ]


def test_decision_only_wait_cannot_prove_a_step() -> None:
    """BLOCKER 1, regression A. Scenario D returned the right summary, no events."""

    manifest = manifest_module.load_manifest()
    declared = manifest_module.scenario_by_id(
        manifest, "SAA-D-human-held-unmerged-reservation"
    )["steps"][0]["expected"]
    scenario, evidence = _step_evidence(
        "SAA-D-human-held-unmerged-reservation",
        [
            CycleObservation(
                outcome=declared["outcome"],
                waited_task_ids=tuple(declared["waited_task_ids"]),
                conflicts=tuple(
                    ConflictObservation(
                        kind=conflict["kind"],
                        candidate_task_id=conflict["candidate_task_id"],
                        conflicting_task_id=conflict["conflicting_task_id"],
                        overlapping_values=tuple(conflict["on"]),
                        reason="scripted",
                    )
                    for conflict in declared["conflicts"]
                ),
                events=(),
            )
        ],
    )
    require(
        evidence[0].events == (),
        "the evidence record did not preserve the empty event slice",
    )
    failed = _failed_evidence_checks(scenario, evidence)
    for expected_check in (
        "step1.evidence.poll_lifecycle",
        "step1.evidence.wait_event[NSC-914]",
        "step1.evidence.wait_conflict[NSC-914->NSC-905]",
    ):
        require(
            expected_check in failed,
            f"a decision-only WAIT was accepted; {expected_check} did not fail: "
            f"{failed}",
        )


def test_a_later_launch_event_cannot_satisfy_an_earlier_step() -> None:
    """BLOCKER 1, regression B. The audit's reused final observation."""

    scenario, evidence = _step_evidence(
        "SAA-A-parallel-safe-assignments",
        [
            # Step 1 claims a launch but emits no launch record at all.
            CycleObservation(
                outcome="start",
                task_id="NSC-901",
                worker_id="w-901",
                events=_cycle_poll("poll-1", 1, "start", []),
            ),
            # Step 2 emits a real one. It belongs to step 2 and to nothing else.
            CycleObservation(
                outcome="start",
                task_id="NSC-902",
                worker_id="w-902",
                events=_cycle_poll(
                    "poll-2", 2, "start", [_cycle_launch("poll-2", "NSC-902", "w-902")]
                ),
            ),
        ],
    )
    failed = _failed_evidence_checks(scenario, evidence)
    require(
        "step1.evidence.launch_event" in failed,
        f"step 1 was proven without a launch event of its own: {failed}",
    )
    require(
        not [name for name in failed if name.startswith("step2.")],
        f"step 2's own complete evidence was rejected: {failed}",
    )


def test_one_event_cannot_grade_two_steps() -> None:
    """BLOCKER 1, regression B, second half. A decision event is consumed once."""

    reused = _cycle_launch("poll-1", "NSC-901", "w-901")
    scenario, evidence = _step_evidence(
        "SAA-A-parallel-safe-assignments",
        [
            CycleObservation(
                outcome="start",
                task_id="NSC-901",
                worker_id="w-901",
                events=_cycle_poll("poll-1", 1, "start", [dict(reused)]),
            ),
            CycleObservation(
                outcome="start",
                task_id="NSC-902",
                worker_id="w-902",
                events=_cycle_poll("poll-2", 2, "start", [dict(reused)]),
            ),
        ],
    )
    failed = _failed_evidence_checks(scenario, evidence)
    require(
        "step2.evidence.events_are_this_step's" in failed,
        f"the same launch event graded two steps: {failed}",
    )
    require(
        "step2.evidence.launch_event" in failed,
        f"a launch of the wrong task satisfied step 2: {failed}",
    )


def test_two_correct_steps_prove_their_own_events() -> None:
    """BLOCKER 1, regression C. The event logic itself is sound when honest."""

    scenario, evidence = _step_evidence(
        "SAA-A-parallel-safe-assignments",
        [
            CycleObservation(
                outcome="start",
                task_id="NSC-901",
                worker_id="w-901",
                events=_cycle_poll(
                    "poll-1", 1, "start", [_cycle_launch("poll-1", "NSC-901", "w-901")]
                ),
            ),
            CycleObservation(
                outcome="start",
                task_id="NSC-902",
                worker_id="w-902",
                events=_cycle_poll(
                    "poll-2", 2, "start", [_cycle_launch("poll-2", "NSC-902", "w-902")]
                ),
            ),
        ],
    )
    failed = _failed_evidence_checks(scenario, evidence)
    require(not failed, f"honest per-step evidence was rejected: {failed}")

    # ...and it still cannot become an acceptance PASS, because the records were
    # produced by a harness adapter and the real one is unwired.
    authority = verify_acceptance._verify_evidence_authority(evidence)
    require(
        not all(check.passed for check in authority),
        "harness-produced evidence claimed real-scheduler authority",
    )
    require(
        all(
            record.authority == verify_acceptance.EVIDENCE_AUTHORITY_HARNESS
            for record in evidence
        ),
        "a caller-supplied adapter produced real-scheduler evidence",
    )


def test_a_contradictory_launch_fails_a_non_launch_step() -> None:
    """BLOCKER 1, regression D."""

    manifest = manifest_module.load_manifest()
    declared = manifest_module.scenario_by_id(
        manifest, "SAA-D-human-held-unmerged-reservation"
    )["steps"][0]["expected"]
    scenario, evidence = _step_evidence(
        "SAA-D-human-held-unmerged-reservation",
        [
            CycleObservation(
                outcome=declared["outcome"],
                waited_task_ids=tuple(declared["waited_task_ids"]),
                conflicts=tuple(
                    ConflictObservation(
                        kind=conflict["kind"],
                        candidate_task_id=conflict["candidate_task_id"],
                        conflicting_task_id=conflict["conflicting_task_id"],
                        overlapping_values=tuple(conflict["on"]),
                        reason="scripted",
                    )
                    for conflict in declared["conflicts"]
                ),
                events=_cycle_poll(
                    "poll-1",
                    1,
                    "idle",
                    [
                        _cycle_wait(
                            "poll-1",
                            "NSC-914",
                            "NSC-905",
                            ["SyntheticGame/Scenes/Game.unity"],
                        ),
                        _cycle_launch("poll-1", "NSC-914", "w-914"),
                    ],
                ),
            )
        ],
    )
    failed = _failed_evidence_checks(scenario, evidence)
    require(
        "step1.evidence.no_contradictory_launch" in failed,
        f"a WAIT step that also launched was accepted: {failed}",
    )


def test_evidence_fails_closed_on_unknown_or_incomplete_events() -> None:
    """An unknown event type or a missing required field is never ignored."""

    scenario, evidence = _step_evidence(
        "SAA-A-parallel-safe-assignments",
        [
            CycleObservation(
                outcome="start",
                task_id="NSC-901",
                worker_id="w-901",
                events=(
                    *_cycle_poll(
                        "poll-1",
                        1,
                        "start",
                        [
                            {
                                "event": "worker_launched",
                                "poll_id": "poll-1",
                                "task_id": "NSC-901",
                                "worker_id": "w-901",
                                "argv": ["--task-id", "NSC-901"],
                            },
                            {"event": "everything_is_fine", "poll_id": "poll-1"},
                        ],
                    ),
                ),
            ),
            CycleObservation(
                outcome="start",
                task_id="NSC-902",
                worker_id="w-902",
                events=_cycle_poll(
                    "poll-2", 2, "start", [_cycle_launch("poll-2", "NSC-902", "w-902")]
                ),
            ),
        ],
    )
    failed = _failed_evidence_checks(scenario, evidence)
    for expected_check in (
        "step1.evidence.known_events",
        "step1.evidence.required_event_fields",
    ):
        require(expected_check in failed, f"{expected_check} did not fail: {failed}")


def _acceptance_scenario(fixture, scenario_id: str):
    """Build one scenario's world for a direct real-adapter observation."""

    manifest = manifest_module.load_manifest()
    scenario = manifest_module.scenario_by_id(manifest, scenario_id)
    return scenario, sw.build_world(scenario, manifest, fixture)


def _argv_binds(argv, flag: str, value: str) -> bool:
    items = [str(item) for item in argv]
    return any(
        items[index] == flag and items[index + 1] == value
        for index in range(len(items) - 1)
    )


def test_real_adapter_advertises_only_ordinary_cycle_capabilities() -> None:
    """The wiring blocker is gone for ordinary cycles, and only for those."""

    adapter = RealPollingArchitectAdapter()
    capabilities = adapter.capabilities()
    require(
        capabilities == frozenset(CAPABILITIES) - {"scheduler_singleton"},
        f"the real adapter advertises {sorted(capabilities)}",
    )
    require(
        "scheduler_singleton" not in capabilities,
        "the real adapter claimed a singleton capability it does not implement",
    )
    manifest = manifest_module.load_manifest()
    for scenario in manifest_module.scenarios(manifest):
        missing = set(scenario.get("required_capabilities") or ()) - capabilities
        if scenario["id"] == "SAA-J-scheduler-singleton":
            require(
                missing == {"scheduler_singleton"},
                f"scenario J reported an unexpected capability gap {sorted(missing)}",
            )
        else:
            require(
                not missing,
                f"{scenario['id']} still reports a capability gap {sorted(missing)}",
            )


def test_scenario_j_stays_fail_closed_and_pending() -> None:
    """The singleton contest is out of this slice and must stay unanswered."""

    adapter = RealPollingArchitectAdapter()
    expect_raises(
        AdapterNotWired,
        lambda: adapter.observe_singleton_contest(None),
        "the real adapter answered a singleton contest it cannot run",
    )
    results, exit_code = verify_acceptance.run_acceptance(
        scenario_ids=["SAA-J-scheduler-singleton"]
    )
    require(exit_code == 0, "a pending capability must not fail the suite")
    require(
        results[0].status == STATUS_PENDING,
        f"scenario J reported {results[0].status} instead of PENDING_CAPABILITY",
    )


def test_real_adapter_drives_the_production_polling_orchestrator() -> None:
    """The answer comes from production seams, not from a prearranged reply."""

    production = scheduler_adapter._production()
    with _Fixture("real-seams") as fixture:
        _scenario, world = _acceptance_scenario(
            fixture, "SAA-A-parallel-safe-assignments"
        )
        try:
            adapter = RealPollingArchitectAdapter()
            observation = adapter.observe_cycle(world)
            orchestrator = adapter.orchestrator
            require(
                type(orchestrator) is production.orchestrator.PollingOrchestrator,
                "the adapter did not construct the production scheduler",
            )
            for name, expected in (
                ("plan_builder", adapter._build_plan),
                ("task_loader", adapter._load_task),
                ("reservation_observer", adapter._observe_reservations),
                ("architect_runner", adapter._architect_runner),
                ("process_factory", adapter.process_factory),
            ):
                require(
                    getattr(orchestrator, name) == expected,
                    f"the scheduler is not using the adapter's {name} seam",
                )
            require(
                type(orchestrator.events)
                is production.orchestrator.JsonEventEmitter,
                "the scheduler is not emitting through its own event emitter",
            )
            require(
                observation.outcome == "start" and observation.task_id == "NSC-901",
                f"production selected {observation.task_id!r} ({observation.outcome})",
            )
            names = {str(event.name) for event in observation.events}
            require(
                {"poll_started", "worker_launched", "poll_finished"} <= names,
                f"the observed poll produced only {sorted(names)}",
            )
        finally:
            sw.destroy_world(world)


def test_fresh_plan_translation_reaches_production_scheduling() -> None:
    """Stage-2 fresh ranking is handed over in the manifest's declared order."""

    with _Fixture("fresh-plan") as fixture:
        _scenario, world = _acceptance_scenario(
            fixture, "SAA-B-predicted-exact-path-conflict"
        )
        try:
            adapter = RealPollingArchitectAdapter()
            adapter._ensure_orchestrator(world, scheduler_adapter._production())
            plan = adapter._build_plan(source=world.source_root, worker_id="w")
            require(plan.decision == "fresh_candidate", f"decision={plan.decision}")
            require(plan.resume is None, "a scenario with no resume claim built one")
            require(
                [item["task_id"] for item in plan.ranked_eligible_candidates]
                == list(world.candidate_queue()),
                "the fresh pool was reordered on the way to the scheduler",
            )
            require(
                plan.source_commit == world.source_head(),
                "the plan did not carry the fixture's committed source HEAD",
            )
            require(
                all(
                    item["task_contract_sha256"]
                    == world.task(item["task_id"])["task_contract_sha256"]
                    for item in plan.ranked_eligible_candidates
                ),
                "a ranked candidate lost its task-contract identity",
            )
            excluded = adapter._build_plan(
                source=world.source_root,
                worker_id="w",
                excluded_task_ids={"NSC-903"},
            )
            require(
                "NSC-903"
                not in [
                    item["task_id"] for item in excluded.ranked_eligible_candidates
                ],
                "a per-poll exclusion was ignored",
            )
        finally:
            sw.destroy_world(world)


def test_resume_authority_is_translated_through_dispatch_plan_resume() -> None:
    """There is no resume_source seam, so resume travels in DispatchPlan.resume."""

    with _Fixture("resume-plan") as fixture:
        _scenario, world = _acceptance_scenario(
            fixture, "SAA-I1-resume-outranks-tempting-fresh-work"
        )
        try:
            adapter = RealPollingArchitectAdapter()
            adapter._ensure_orchestrator(world, scheduler_adapter._production())
            plan = adapter._build_plan(source=world.source_root, worker_id="w")
            require(plan.decision == "resume_existing", f"decision={plan.decision}")
            require(
                plan.resume is not None and plan.resume["task_id"] == "NSC-906",
                f"resume authority was not translated: {plan.resume}",
            )
            ranked = [item["task_id"] for item in plan.ranked_eligible_candidates]
            require(
                "NSC-906" not in ranked,
                "resume authority was smuggled into fresh queue order",
            )
            require(ranked == ["NSC-901"], f"fresh ranking was {ranked}")
            observation = adapter.observe_cycle(world)
            require(
                observation.outcome == "start" and observation.task_id == "NSC-906",
                f"production started {observation.task_id!r} instead of the resume task",
            )
        finally:
            sw.destroy_world(world)


def test_reservations_and_unknown_surface_reach_production_reasoning() -> None:
    """Reservation identity, resources and UNKNOWN survive the translation."""

    with _Fixture("unknown-surface") as fixture:
        _scenario, world = _acceptance_scenario(
            fixture, "SAA-G1-unknown-surface-blocks-unprovable-pair"
        )
        try:
            adapter = RealPollingArchitectAdapter()
            adapter._ensure_orchestrator(world, scheduler_adapter._production())
            observed = {
                reservation.task_id: reservation
                for reservation in adapter._observe_reservations()
            }
            require("NSC-905" in observed, f"observed {sorted(observed)}")
            unknown = observed["NSC-905"]
            require(
                unknown.surface_unknown is True,
                "surface_unknown was dropped on the way to the scheduler",
            )
            require(
                unknown.actual_paths == (),
                "an unobservable surface was reported as observed paths",
            )
            observation = adapter.observe_cycle(world)
            require(
                observation.outcome == "idle"
                and observation.waited_task_ids == ("NSC-901",),
                f"unknown surface produced {observation.outcome} "
                f"{observation.waited_task_ids}",
            )
        finally:
            sw.destroy_world(world)

    with _Fixture("exclusive-resource") as fixture:
        _scenario, world = _acceptance_scenario(
            fixture, "SAA-I2-resume-waits-and-steals-nothing"
        )
        try:
            adapter = RealPollingArchitectAdapter()
            adapter._ensure_orchestrator(world, scheduler_adapter._production())
            observed = {
                reservation.task_id: reservation
                for reservation in adapter._observe_reservations()
            }
            other = observed["NSC-916"]
            require(
                "logical:enemy-tuning-data" in other.exclusive_resources,
                f"exclusive resources were lost: {other.exclusive_resources}",
            )
            require(
                "SyntheticGame/Data/EnemyTuning.asset" in other.actual_paths,
                f"actual Git paths were lost: {other.actual_paths}",
            )
        finally:
            sw.destroy_world(world)


def test_architect_unavailable_and_malformed_fail_closed_through_production() -> None:
    """H1 and H2 exercise the production advisory path, not an adapter shortcut."""

    production = scheduler_adapter._production()
    with _Fixture("architect-unavailable") as fixture:
        _scenario, world = _acceptance_scenario(
            fixture, "SAA-H1-architect-invocation-unavailable"
        )
        try:
            adapter = RealPollingArchitectAdapter()
            adapter._ensure_orchestrator(world, production)
            world.apply_transition({"kind": "architect_unavailable"})
            expect_raises(
                production.preflight.ArchitectPreflightError,
                lambda: adapter._architect_runner(
                    task=world.task("NSC-901"),
                    source_head=world.source_head(),
                    reservations=(),
                    scheduler_id=adapter.scheduler_id,
                ),
                "an unavailable advisory did not fail closed",
            )
        finally:
            sw.destroy_world(world)

    with _Fixture("architect-malformed") as fixture:
        _scenario, world = _acceptance_scenario(
            fixture, "SAA-H2-architect-output-malformed"
        )
        try:
            adapter = RealPollingArchitectAdapter()
            adapter._ensure_orchestrator(world, production)
            task = world.task("NSC-901")
            payload = scheduler_adapter._production_advisory_payload(
                world.advisory("NSC-901"),
                task=task,
                source_head=world.source_head(),
            )
            require(
                payload["task_id"] == "NSC-999",
                "the wrong-task-id defect was repaired by the translation",
            )
            require(
                "predicted_change_surface" not in payload,
                "the missing-surface defect was repaired by the translation",
            )
            require(
                payload.get("scenario_id") == "SAA-not-this-scenario",
                "the wrong-scenario-binding defect was removed by the translation",
            )
            require(
                "parallel_safe_because" in payload,
                "the unknown-structured-field defect was removed by the translation",
            )
            expect_raises(
                production.preflight.ArchitectPreflightError,
                lambda: production.preflight.ArchitectAdvisory.from_dict(payload),
                "production validation accepted a malformed advisory",
            )
            expect_raises(
                production.preflight.ArchitectPreflightError,
                lambda: adapter._architect_runner(
                    task=task,
                    source_head=world.source_head(),
                    reservations=(),
                    scheduler_id=adapter.scheduler_id,
                ),
                "a malformed advisory did not fail closed",
            )
        finally:
            sw.destroy_world(world)


def test_launch_evidence_uses_captured_production_argv() -> None:
    """Worker identity and argv are production's, and nothing is started."""

    with _Fixture("captured-argv") as fixture:
        _scenario, world = _acceptance_scenario(
            fixture, "SAA-A-parallel-safe-assignments"
        )
        try:
            adapter = RealPollingArchitectAdapter()
            observation = adapter.observe_cycle(world)
            worker_id = str(observation.worker_id or "").strip()
            require(worker_id, "a launch reported no observed worker ID")
            launches = adapter.process_factory.launches
            require(len(launches) == 1, f"captured {len(launches)} launches")
            argv = launches[0]["argv"]
            require(
                tuple(observation.launch_argv) == argv,
                "the reported argv is not the argv production attempted",
            )
            require(
                _argv_binds(argv, "--task-id", "NSC-901")
                and _argv_binds(argv, "--worker-id", worker_id),
                f"argv did not bind the exact task and worker IDs: {list(argv)}",
            )
            assignment = adapter.orchestrator.active_assignments["NSC-901"]
            require(
                type(assignment.process)
                is scheduler_adapter._PassiveWorkerProcess,
                "the scheduler was given something other than a passive process",
            )
            require(
                assignment.pid is None and assignment.process.poll() is None,
                "the acceptance harness reported a live process identity",
            )
        finally:
            sw.destroy_world(world)


def test_real_acceptance_needs_no_process_provider_or_network() -> None:
    """Sockets are refused for this whole run; this pins the remaining paths."""

    with _Fixture("no-provider") as fixture:
        _scenario, world = _acceptance_scenario(
            fixture, "SAA-A-parallel-safe-assignments"
        )
        try:
            adapter = RealPollingArchitectAdapter()
            adapter.observe_cycle(world)
            require(
                adapter.orchestrator.process_factory is adapter.process_factory,
                "the scheduler kept a process factory that could start a worker",
            )
            artifact_root = (
                fixture.path / scheduler_adapter.ADVISORY_ARTIFACT_DIRECTORY
            )
            artifacts = sorted(artifact_root.glob("*.json"))
            require(artifacts, "no production advisory artifact was persisted")
            payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
            require(
                payload["invocation"]["provider"] == "none"
                and payload["invocation"]["network_access"] is False,
                f"an advisory recorded a provider invocation: {payload['invocation']}",
            )
            parents = set(artifacts[0].parents)
            require(
                world.source_root not in parents
                and world.checkout_root not in parents,
                "advisory artifacts were written into observed durable state",
            )
        finally:
            sw.destroy_world(world)


def test_real_acceptance_answers_ordinary_cycles_and_leaves_j_pending() -> None:
    """End to end: the real adapter now answers A, and J stays honest."""

    results, _exit_code = verify_acceptance.run_acceptance(
        scenario_ids=[
            "SAA-A-parallel-safe-assignments",
            "SAA-J-scheduler-singleton",
        ]
    )
    by_id = {result.scenario_id: result for result in results}
    singleton = by_id["SAA-J-scheduler-singleton"]
    require(
        singleton.status == STATUS_PENDING,
        f"scenario J reported {singleton.status}",
    )
    ordinary = by_id["SAA-A-parallel-safe-assignments"]
    require(
        ordinary.status == acceptance_lib.STATUS_PASS,
        f"scenario A reported {ordinary.status}: "
        + "; ".join(check.detail for check in ordinary.failed_checks),
    )
    require(
        ordinary.answered_by == "real_scheduler",
        f"scenario A was answered by {ordinary.answered_by}",
    )


# ---------------------------------------------------------------------------
# Real-adapter adversarial evidence
#
# Everything below drives the **real** adapter over the committed scheduler and
# then corrupts exactly one production claim at a time. The point is that the
# evidence chain - PollCycleResult, the emitted `worker_launched` record, the
# argv production built, and the argv the passive process factory was actually
# handed - is cross-bound, so no single tampered source can reach a usable
# CycleObservation. A positive test pins the same chain agreeing.
# ---------------------------------------------------------------------------


class _EmitterProxy:
    """Route production's own emitter through a test hook.

    `hook(adapter, inner, event, values)` owns the call to the real
    `JsonEventEmitter`, so a test can corrupt exactly one field of one record
    while every other record still reaches the adapter's capture stream exactly
    as production wrote it.
    """

    def __init__(self, adapter, inner, hook) -> None:
        self.adapter = adapter
        self.inner = inner
        self.hook = hook

    def emit(self, event: str, **values) -> None:
        self.hook(self.adapter, self.inner, event, values)


class _RealCycle:
    """One real scenario world plus its real adapter, optionally tampered with.

    The adapter, the orchestrator, the plan, the advisory, the conflict verdict
    and every event are production's. Only the named corruption is the test's,
    and it is applied after the orchestrator is constructed so the scheduler
    itself is never reconfigured.
    """

    def __init__(
        self,
        name: str,
        *,
        scenario_id: str = "SAA-A-parallel-safe-assignments",
        hook=None,
        corrupt_result=None,
    ) -> None:
        self.fixture = _Fixture(name)
        self.scenario_id = scenario_id
        self.hook = hook
        self.corrupt_result = corrupt_result
        self.world = None
        self.adapter = None

    def __enter__(self) -> "_RealCycle":
        root = self.fixture.__enter__()
        try:
            _scenario, self.world = _acceptance_scenario(root, self.scenario_id)
            self.adapter = RealPollingArchitectAdapter()
            self.adapter._ensure_orchestrator(
                self.world, scheduler_adapter._production()
            )
            orchestrator = self.adapter.orchestrator
            if self.hook is not None:
                orchestrator.events = _EmitterProxy(
                    self.adapter, orchestrator.events, self.hook
                )
            if self.corrupt_result is not None:
                production_poll = orchestrator.poll_once
                corrupt = self.corrupt_result
                orchestrator.poll_once = lambda: corrupt(production_poll())
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def observe(self):
        return self.adapter.observe_cycle(self.world)

    def must_fail_closed(self, message: str) -> str:
        """Observe, requiring an evidence failure instead of an observation."""

        try:
            observation = self.observe()
        except scheduler_adapter.EventEvidenceError as exc:
            return str(exc)
        raise AssertionError(
            f"{message}; the adapter returned {observation.to_dict()}"
        )

    def __exit__(self, *exc) -> None:
        if self.world is not None:
            sw.destroy_world(self.world)
            self.world = None
        self.fixture.__exit__(*exc)


def _emit_extra_production_event(name: str, *, after: str = "poll_started"):
    """Emit one additional production record through production's own emitter."""

    def hook(adapter, inner, event, values) -> None:
        inner.emit(event, **values)
        if event == after:
            inner.emit(
                name,
                scheduler_id=adapter.scheduler_id,
                task_id="NSC-901",
                reason="an event kind this adapter has never seen",
            )

    return hook


def _corrupt_launch_fields(**replacements):
    """Replace named fields of the production `worker_launched` record only."""

    def hook(adapter, inner, event, values) -> None:
        if event == "worker_launched":
            values = {**values, **replacements}
        inner.emit(event, **values)

    return hook


def _rebind_launch_argv_flag(flag: str, value: str, *, sync_capture: bool):
    """Rebind one argv flag in the launch record production emits.

    With `sync_capture`, the passive factory's capture is rewritten to the same
    argv, so the *only* surviving disagreement is between that flag and the
    identity fields. Without it, the captured argv stays what production really
    handed the factory and the mismatch is captured-versus-reported.
    """

    def hook(adapter, inner, event, values) -> None:
        if event == "worker_launched":
            argv = [str(item) for item in (values.get("argv") or ())]
            index = argv.index(flag)
            argv[index + 1] = value
            values = {**values, "argv": argv}
            if sync_capture:
                adapter.process_factory.launches[-1]["argv"] = tuple(argv)
        inner.emit(event, **values)

    return hook


def _append_launch_argv_token(token: str):
    """Report an argv production never handed the process factory."""

    def hook(adapter, inner, event, values) -> None:
        if event == "worker_launched":
            argv = [str(item) for item in (values.get("argv") or ())]
            values = {**values, "argv": argv + [token]}
        inner.emit(event, **values)

    return hook


def _sole_argv_value(argv, flag: str) -> str:
    values = scheduler_adapter._argv_flag_values(argv, flag)
    require(len(values) == 1, f"argv bound {flag} {len(values)} times: {list(argv)}")
    return values[0]


def test_unknown_production_event_kinds_fail_closed() -> None:
    """A production event kind nobody named cannot vanish from the evidence."""

    unknown = "scheduler_content_safety_halt"
    require(
        unknown not in scheduler_adapter.PRODUCTION_DIAGNOSTIC_EVENTS,
        f"{unknown} is already allow-listed, so this test would prove nothing",
    )
    with _RealCycle(
        "unknown-event", hook=_emit_extra_production_event(unknown)
    ) as cycle:
        detail = cycle.must_fail_closed(
            "an unrecognized production event did not fail closed"
        )
        require(
            unknown in detail,
            f"the failure did not name the offending event: {detail}",
        )
        require(
            not cycle.adapter.event_log(),
            "an unrecognized production event still left canonical evidence "
            f"behind: {cycle.adapter.event_log()}",
        )
        require(
            any(
                str(record.get("event")) == unknown
                for record in cycle.adapter.production_event_log()
            ),
            "the offending production record was discarded instead of retained",
        )


def test_explicitly_ignored_diagnostic_events_stay_permitted() -> None:
    """A harmless diagnostic is ignored, and only because it is allow-listed."""

    ignored = "architect_started"
    require(
        ignored in scheduler_adapter.PRODUCTION_DIAGNOSTIC_EVENTS,
        f"{ignored} is not an intentionally ignored production event",
    )
    with _RealCycle(
        "ignored-diagnostic", hook=_emit_extra_production_event(ignored)
    ) as cycle:
        observation = cycle.observe()
        require(
            observation.outcome == "start" and observation.task_id == "NSC-901",
            f"the cycle reported {observation.task_id!r} ({observation.outcome})",
        )
        names = [str(event.name) for event in observation.events]
        require(
            {"poll_started", "worker_launched", "poll_finished"} <= set(names),
            f"ordinary evidence did not survive the diagnostic: {names}",
        )
        require(
            ignored not in names,
            f"an ignored diagnostic became canonical evidence: {names}",
        )
        require(
            str(observation.worker_id or "").strip()
            and tuple(observation.launch_argv),
            "the launch evidence did not survive an ignored diagnostic",
        )

    original = scheduler_adapter.PRODUCTION_DIAGNOSTIC_EVENTS
    scheduler_adapter.PRODUCTION_DIAGNOSTIC_EVENTS = original - {ignored}
    try:
        with _RealCycle(
            "unlisted-diagnostic", hook=_emit_extra_production_event(ignored)
        ) as cycle:
            detail = cycle.must_fail_closed(
                f"{ignored} was tolerated for a reason other than the allow-list"
            )
            require(
                ignored in detail,
                f"the failure did not name the de-listed event: {detail}",
            )
    finally:
        scheduler_adapter.PRODUCTION_DIAGNOSTIC_EVENTS = original


def test_result_worker_id_must_match_the_launch_record() -> None:
    """`PollCycleResult.worker_id` is one claim, not the authority."""

    with _RealCycle(
        "result-worker-mismatch",
        corrupt_result=lambda result: dataclasses.replace(
            result, worker_id=f"{result.worker_id}-tampered"
        ),
    ) as cycle:
        detail = cycle.must_fail_closed(
            "a PollCycleResult worker ID that contradicts the launch record was "
            "accepted"
        )
        require(
            "worker identity disagrees" in detail
            and "PollCycleResult.worker_id" in detail,
            f"the failure did not identify the contradicting claim: {detail}",
        )


def test_launch_record_worker_id_must_match_argv() -> None:
    """The worker ID production encoded in argv is an independent claim."""

    with _RealCycle(
        "argv-worker-mismatch",
        hook=_rebind_launch_argv_flag(
            "--worker-id", "polling-worker-tampered", sync_capture=True
        ),
    ) as cycle:
        detail = cycle.must_fail_closed(
            "an argv --worker-id that contradicts the launch record was accepted"
        )
        require(
            "worker identity disagrees" in detail and "--worker-id" in detail,
            f"the failure did not identify the contradicting claim: {detail}",
        )


def test_captured_process_argv_must_match_the_reported_argv() -> None:
    """What production handed the process factory is part of the chain."""

    with _RealCycle(
        "captured-argv-mismatch",
        hook=_append_launch_argv_token("--acceptance-tampered"),
    ) as cycle:
        detail = cycle.must_fail_closed(
            "a launch argv the process factory never received was accepted"
        )
        require(
            "actually tried to launch" in detail,
            f"the failure did not name the captured-argv contradiction: {detail}",
        )
        require(
            "--acceptance-tampered" in detail,
            f"the failure did not show the reported argv: {detail}",
        )


def test_task_identity_must_agree_across_every_production_source() -> None:
    """Corrupting the result's task ID, or argv's, is rejected either way."""

    with _RealCycle(
        "result-task-mismatch",
        corrupt_result=lambda result: dataclasses.replace(
            result, task_id="NSC-902"
        ),
    ) as cycle:
        detail = cycle.must_fail_closed(
            "a PollCycleResult task ID that contradicts the launch record was "
            "accepted"
        )
        require(
            "task identity disagrees" in detail
            and "PollCycleResult.task_id" in detail,
            f"the failure did not identify the contradicting claim: {detail}",
        )

    with _RealCycle(
        "argv-task-mismatch",
        hook=_rebind_launch_argv_flag("--task-id", "NSC-902", sync_capture=True),
    ) as cycle:
        detail = cycle.must_fail_closed(
            "an argv --task-id that contradicts the launch record was accepted"
        )
        require(
            "task identity disagrees" in detail and "--task-id" in detail,
            f"the failure did not identify the contradicting claim: {detail}",
        )


def test_event_only_launch_identity_mismatch_fails_closed() -> None:
    """A tampered `worker_launched` record is still a contradiction, alone.

    `_corrupt_launch_fields` only reaches the raw/canonical `worker_launched`
    event: `PollCycleResult.worker_id`/`task_id`, the argv flags production
    bound, and the passive process factory's captured argv are left exactly as
    production emitted them. Without an independent claim standing against the
    event, this is the one place the cross-binding could have missed a
    corrupted identity; it must still fail closed.
    """

    with _RealCycle(
        "event-only-worker-mismatch",
        hook=_corrupt_launch_fields(worker_id="event-only-tampered-worker"),
    ) as cycle:
        detail = cycle.must_fail_closed(
            "a worker_launched record whose own worker_id disagreed with the "
            "result and argv was accepted"
        )
        require(
            "worker identity disagrees" in detail,
            f"the failure did not identify the contradicting claim: {detail}",
        )

    with _RealCycle(
        "event-only-task-mismatch",
        hook=_corrupt_launch_fields(task_id="NSC-902"),
    ) as cycle:
        detail = cycle.must_fail_closed(
            "a worker_launched record whose own task_id disagreed with the "
            "result and argv was accepted"
        )
        require(
            "task identity disagrees" in detail,
            f"the failure did not identify the contradicting claim: {detail}",
        )


def test_launch_cross_binding_agrees_on_a_real_production_launch() -> None:
    """The untampered chain agrees, so the adversarial tests are not vacuous."""

    with _RealCycle("cross-binding") as cycle:
        observation = cycle.observe()
        adapter = cycle.adapter
        require(
            observation.outcome == "start" and observation.task_id == "NSC-901",
            f"production reported {observation.task_id!r} ({observation.outcome})",
        )
        canonical = [
            event for event in observation.events if event.name == "worker_launched"
        ]
        production = [
            record
            for record in adapter.production_event_log()
            if str(record.get("event")) == "worker_launched"
        ]
        captured = adapter.process_factory.launches
        require(
            len(canonical) == 1 and len(production) == 1 and len(captured) == 1,
            f"the poll produced {len(canonical)} canonical, {len(production)} "
            f"production and {len(captured)} captured launch records",
        )
        worker_id = str(observation.worker_id or "").strip()
        task_id = str(observation.task_id)
        argv = tuple(str(item) for item in canonical[0]["argv"])
        require(
            {
                str(canonical[0]["worker_id"]),
                str(production[0]["worker_id"]),
                worker_id,
                _sole_argv_value(argv, "--worker-id"),
            }
            == {worker_id},
            "the launch worker identity is not the same in every production "
            f"record: {worker_id!r}, argv {list(argv)}",
        )
        require(
            {
                str(canonical[0]["task_id"]),
                str(production[0]["task_id"]),
                task_id,
                _sole_argv_value(argv, "--task-id"),
            }
            == {task_id},
            "the launch task identity is not the same in every production "
            f"record: {task_id!r}, argv {list(argv)}",
        )
        require(
            tuple(captured[0]["argv"]) == argv
            and tuple(observation.launch_argv) == argv,
            "the captured, reported and observed argv are not the same argv",
        )
        require(
            adapter._launch_task_by_worker == {worker_id: task_id}
            and adapter._launch_argv_by_worker == {worker_id: argv},
            "the adapter retained a different launch binding than it observed",
        )


def test_scenario_b_proves_a_real_predicted_exact_path_conflict() -> None:
    """Scenario B's WAIT is production's, on a shared ordinary C# script."""

    shared = "SyntheticGame/Scripts/Core/GameManager.cs"
    require(
        not acceptance_lib.is_unity_serialized_asset(shared),
        f"{shared} is a Unity serialized asset, so scenario B would be "
        "measuring Unity asset identity instead of exact-path prediction",
    )
    with _RealCycle(
        "scenario-b-exact-path",
        scenario_id="SAA-B-predicted-exact-path-conflict",
    ) as cycle:
        first = cycle.observe()
        require(
            first.outcome == "start" and first.task_id == "NSC-903",
            f"step 1 reported {first.task_id!r} ({first.outcome})",
        )
        second = cycle.observe()
        require(
            second.outcome == "start" and second.task_id == "NSC-901",
            f"step 2 reported {second.task_id!r} ({second.outcome})",
        )
        require(
            second.waited_task_ids == ("NSC-904",),
            f"step 2 waited {list(second.waited_task_ids)}",
        )
        require(
            len(second.conflicts) == 1,
            f"step 2 reported {len(second.conflicts)} conflicts",
        )
        conflict = second.conflicts[0]
        require(
            conflict.kind == "exact_path_predicted",
            f"production's conflict mapped to {conflict.kind!r}",
        )
        require(
            conflict.candidate_task_id == "NSC-904"
            and conflict.conflicting_task_id == "NSC-903",
            f"the conflict named {conflict.candidate_task_id}/"
            f"{conflict.conflicting_task_id}",
        )
        require(
            tuple(conflict.overlapping_values) == (shared,),
            f"the overlap was {list(conflict.overlapping_values)}",
        )
        production_kinds = {
            str(record.get("conflict_kind"))
            for record in cycle.adapter.production_event_log()
            if str(record.get("event")) in scheduler_adapter.PRODUCTION_WAIT_EVENTS
        }
        require(
            production_kinds == {"active_predicted_exact_path"},
            f"production reported conflict kinds {sorted(production_kinds)}",
        )
        for task_id in ("NSC-903", "NSC-904"):
            advisory = cycle.adapter._validated_advisories[task_id]
            surface = advisory.predicted_change_surface
            require(
                shared in surface.exact_paths,
                f"{task_id} did not predict {shared}: {list(surface.exact_paths)}",
            )
            require(
                not surface.unity_serialized_assets,
                f"{task_id} declared Unity serialized assets "
                f"{list(surface.unity_serialized_assets)}",
            )
        assignment = cycle.adapter.orchestrator.active_assignments["NSC-903"]
        require(
            not assignment.architect_surface.unity_serialized_assets,
            "the active NSC-903 assignment carried a Unity serialized asset "
            "identity, so the overlap is not a plain exact-path conflict",
        )

    results, exit_code = verify_acceptance.run_acceptance(
        scenario_ids=["SAA-B-predicted-exact-path-conflict"]
    )
    require(exit_code == 0, f"the acceptance path exited {exit_code}")
    result = results[0]
    require(
        result.status == acceptance_lib.STATUS_PASS,
        f"scenario B reported {result.status}: "
        + "; ".join(check.detail for check in result.failed_checks),
    )
    require(
        result.answered_by == "real_scheduler",
        f"scenario B was answered by {result.answered_by}",
    )


# ---------------------------------------------------------------------------
# Live-evidence envelope
#
# Every envelope here is grounded against one real Git checkout built by this
# package, because `--source` is no longer decorative: the recorded HEAD, tree
# and repository identity must equal what Git reports there.
# ---------------------------------------------------------------------------

_LIVE_SOURCE: dict = {}


def _grounded_source():
    """One real synthetic checkout shared by the live-evidence tests."""

    if not _LIVE_SOURCE:
        parent = create_disposable_parent()
        root = create_fixture_root(parent, "live-source")
        _LIVE_SOURCE.update(
            parent=parent, root=root, source=sr.build_source_repository(root)
        )
    return _LIVE_SOURCE["source"]


def _release_grounded_source() -> None:
    if _LIVE_SOURCE:
        destroy_fixture_root(_LIVE_SOURCE["root"])
        destroy_disposable_parent(_LIVE_SOURCE["parent"])
        _LIVE_SOURCE.clear()


def _metadata(scenario_id: str, overrides: dict | None = None) -> dict:
    source = _grounded_source()
    record = {
        "event": "run_metadata",
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "run_id": "run-0001",
        "scenario_id": scenario_id,
        "manifest_sha256": MANIFEST_SHA,
        "repository": source.repository_identity,
        "source_head": source.head,
        "source_tree": source.tree,
        "scheduler_id": "sched-1",
        "run_started_at": "2026-09-01T00:00:00Z",
    }
    record.update(overrides or {})
    return record


def _write_envelope(
    directory: Path,
    scenario_id: str,
    events: list[dict],
    metadata_overrides: dict | None = None,
) -> Path:
    records = [_metadata(scenario_id, metadata_overrides)]
    for index, event in enumerate(events, start=1):
        payload = dict(event)
        payload.setdefault("run_id", records[0]["run_id"])
        payload.setdefault("scenario_id", scenario_id)
        payload.setdefault("sequence", index)
        records.append(payload)
    path = directory / "events.jsonl"
    path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )
    return path


def _verify_grounded(path: Path):
    """Verify against the real checkout the envelopes claim to describe."""

    return live.verify(events_path=path, source=_grounded_source().root)


def _live_event(name: str, poll_id: str = "poll-1", **fields) -> dict:
    return {"event": name, "poll_id": poll_id, "scheduler_id": "sched-1", **fields}


def _live_poll(
    poll_id: str,
    poll_index: int,
    outcome: str,
    inner: list[dict],
    scheduler_id: str = "sched-1",
) -> list[dict]:
    """Wrap decision records in one complete, correlated poll execution."""

    return [
        _live_event(
            "poll_started",
            poll_id,
            poll_index=poll_index,
            scheduler_id=scheduler_id,
        ),
        *inner,
        _live_event(
            "poll_finished",
            poll_id,
            poll_index=poll_index,
            outcome=outcome,
            scheduler_id=scheduler_id,
        ),
    ]


def _launch(
    task_id: str,
    worker_id: str,
    scheduler_id: str = "sched-1",
    poll_id: str = "poll-1",
) -> dict:
    return _live_event(
        "worker_launched",
        poll_id,
        scheduler_id=scheduler_id,
        task_id=task_id,
        worker_id=worker_id,
        argv=[
            "docker",
            "compose",
            "run",
            "worker",
            "--task-id",
            task_id,
            "--worker-id",
            worker_id,
        ],
    )


def _reservations(entries: list[dict], poll_id: str = "poll-1") -> dict:
    return _live_event(
        "integration_reservations_observed", poll_id, reservations=entries
    )


def _wait(
    task_id: str,
    other: str,
    values: list[str],
    fingerprint: str,
    poll_id: str = "poll-1",
    kind: str = "exact_path_actual",
) -> dict:
    return _live_event(
        "candidate_waited",
        poll_id,
        task_id=task_id,
        wait_kind=kind,
        conflicting_task_id=other,
        overlapping_values=values,
        reservation_fingerprint=fingerprint,
    )


GAME_SCENE = "SyntheticGame/Scenes/Game.unity"


def _held_scene_reservations() -> list[dict]:
    return [
        {
            "task_id": "NSC-905",
            "actual_paths": [GAME_SCENE],
            "surface_unknown": False,
        }
    ]


def _lock_events(
    checkout_root: str,
    lock_identity: str,
    contest_id: str = "contest-1",
) -> list[dict]:
    lock_path = str(Path(checkout_root) / ".nsc-scheduler.lock")
    return [
        _live_event(
            "scheduler_lock_acquired",
            "poll-1",
            lock_identity=lock_identity,
            lock_path=lock_path,
            checkout_root=checkout_root,
            contest_id=contest_id,
        ),
        _live_event(
            "scheduler_already_active",
            "poll-1",
            scheduler_id="sched-2",
            lock_identity=lock_identity,
            lock_path=lock_path,
            checkout_root=checkout_root,
            contest_id=contest_id,
            holder_scheduler_id="sched-1",
        ),
    ]


def _singleton_envelope(directory: Path, lock_identity: str | None = None) -> Path:
    source = _grounded_source()
    checkout_root = str(source.checkout_root)
    if lock_identity is None:
        grounding = live.observe_source(source.root)
        lock_identity = live.expected_lock_identity(grounding, checkout_root)
    return _write_envelope(
        directory,
        "SAA-J-scheduler-singleton",
        _live_poll(
            "poll-1",
            1,
            "start",
            [
                *_lock_events(checkout_root, lock_identity),
                _launch("NSC-901", "w-901"),
            ],
        ),
    )


def _failed_required(report) -> set:
    return {check.name for check in report.unsatisfied_required}


def test_live_evidence_accepts_a_complete_bound_run() -> None:
    from acceptance_lib import canonical_sha256

    reservations = _held_scene_reservations()
    with tempfile.TemporaryDirectory(prefix="saa-ev-ok-") as tmp:
        path = _write_envelope(
            Path(tmp),
            "SAA-F-wait-becomes-start-after-integration",
            [
                *_live_poll(
                    "poll-1",
                    1,
                    "idle",
                    [
                        _reservations(reservations),
                        _wait(
                            "NSC-914",
                            "NSC-905",
                            [GAME_SCENE],
                            canonical_sha256(reservations),
                        ),
                    ],
                ),
                *_live_poll(
                    "poll-2",
                    2,
                    "start",
                    [
                        _reservations([], poll_id="poll-2"),
                        _launch("NSC-914", "w-914", poll_id="poll-2"),
                    ],
                ),
            ],
        )
        report, exit_code = _verify_grounded(path)
    require(
        exit_code == 0,
        f"a complete run failed: {[c.to_dict() for c in report.unsatisfied_required]}",
    )
    proven = {
        check.name for check in report.checks if check.status == live.STATUS_PROVEN
    }
    for name in (
        "wait_then_start_transition",
        "source_identity_grounded",
        "run_poll_lifecycle",
        "poll_step_alignment",
        "scheduler_identity_consistent",
        "conflict_evidence_grounded",
    ):
        require(name in proven, f"{name} was not proven by a complete bound run")

    # Optional is a schema declaration, never an inference. The scenario's own
    # checks carry their declared requiredness; the grounding checks are always
    # required and are not manifest-selectable.
    manifest = manifest_module.load_manifest()
    live_evidence = manifest_module.scenario_by_id(
        manifest, "SAA-F-wait-becomes-start-after-integration"
    )["live_evidence"]
    declared_required = set(live_evidence["required_checks"])
    declared_optional = set(live_evidence["optional_checks"])
    mandatory = set(live.MANDATORY_GROUNDING_CHECKS) | {live.STEP_ALIGNMENT_CHECK}
    reported = {check.name: check.required for check in report.checks}
    require(
        set(reported) == declared_required | declared_optional | mandatory,
        f"the report evaluated checks the scenario never declared: {sorted(reported)}",
    )
    require(
        all(reported[name] for name in declared_required | mandatory)
        and not any(reported[name] for name in declared_optional - mandatory),
        "a check's requiredness did not come from the manifest or the grounding set",
    )
    require(
        "no_launch_recorded" not in reported,
        "an inapplicable check was evaluated and could be misread as a finding",
    )


def test_live_evidence_accepts_minimal_a_and_d_shapes() -> None:
    """BLOCKER 2, regression 12. The honest minimum still passes."""

    from acceptance_lib import canonical_sha256

    with tempfile.TemporaryDirectory(prefix="saa-ev-min-a-") as tmp:
        path = _write_envelope(
            Path(tmp),
            "SAA-A-parallel-safe-assignments",
            [
                *_live_poll(
                    "poll-1", 1, "start", [_launch("NSC-901", "w-901")]
                ),
                *_live_poll(
                    "poll-2",
                    2,
                    "start",
                    [_launch("NSC-902", "w-902", poll_id="poll-2")],
                ),
            ],
        )
        report, exit_code = _verify_grounded(path)
    require(
        exit_code == 0,
        f"a minimal correct scenario A run failed: {sorted(_failed_required(report))}",
    )

    reservations = _held_scene_reservations()
    with tempfile.TemporaryDirectory(prefix="saa-ev-min-d-") as tmp:
        path = _write_envelope(
            Path(tmp),
            "SAA-D-human-held-unmerged-reservation",
            _live_poll(
                "poll-1",
                1,
                "idle",
                [
                    _reservations(reservations),
                    _wait(
                        "NSC-914",
                        "NSC-905",
                        [GAME_SCENE],
                        canonical_sha256(reservations),
                    ),
                ],
            ),
        )
        report, exit_code = _verify_grounded(path)
    require(
        exit_code == 0,
        f"a minimal correct scenario D run failed: {sorted(_failed_required(report))}",
    )


def test_live_evidence_requires_a_grounded_source() -> None:
    """BLOCKER 2A. Without --source nothing anchors the envelope to a repository."""

    with tempfile.TemporaryDirectory(prefix="saa-ev-nosrc-") as tmp:
        path = _write_envelope(
            Path(tmp),
            "SAA-A-parallel-safe-assignments",
            [
                *_live_poll("poll-1", 1, "start", [_launch("NSC-901", "w-901")]),
                *_live_poll(
                    "poll-2",
                    2,
                    "start",
                    [_launch("NSC-902", "w-902", poll_id="poll-2")],
                ),
            ],
        )
        report, exit_code = live.verify(events_path=path)
        require(exit_code == 1, "an ungrounded run exited 0")
        require(
            "source_identity_grounded" in _failed_required(report),
            f"the grounding check did not gate: {sorted(_failed_required(report))}",
        )


def test_live_evidence_rejects_fabricated_source_identity() -> None:
    """BLOCKER 2A, regressions 3, 4 and 5."""

    source = _grounded_source()
    events = [
        *_live_poll("poll-1", 1, "start", [_launch("NSC-901", "w-901")]),
        *_live_poll(
            "poll-2", 2, "start", [_launch("NSC-902", "w-902", poll_id="poll-2")]
        ),
    ]
    for label, override in {
        "head": {"source_head": "a" * 40},
        "tree": {"source_tree": "b" * 40},
        "repository": {"repository": "cathode26/some-other-repository"},
    }.items():
        with tempfile.TemporaryDirectory(prefix="saa-ev-src-") as tmp:
            path = _write_envelope(
                Path(tmp),
                "SAA-A-parallel-safe-assignments",
                events,
                metadata_overrides=override,
            )
            report, exit_code = _verify_grounded(path)
        require(exit_code == 1, f"a fabricated source {label} was accepted")
        require(
            "source_identity_grounded" in _failed_required(report),
            f"the {label} mismatch did not fail the grounding check",
        )
    require(
        source.head != "a" * 40, "the fixture source HEAD was not read from Git"
    )


def test_live_evidence_rejects_malformed_run_identity() -> None:
    """BLOCKER 2A, regressions 5 and 6: repository shape and timestamp."""

    for label, override in {
        "repository": {"repository": "not a repository id!"},
        "repository path": {"repository": "/tmp/some/checkout"},
        "timestamp": {"run_started_at": "yesterday afternoon"},
        "impossible timestamp": {"run_started_at": "2026-13-45T99:99:99Z"},
        "run id": {"run_id": "!!"},
        "scheduler id": {"scheduler_id": ""},
    }.items():
        with tempfile.TemporaryDirectory(prefix="saa-ev-mal-") as tmp:
            path = _write_envelope(
                Path(tmp),
                "SAA-A-parallel-safe-assignments",
                _live_poll("poll-1", 1, "start", [_launch("NSC-901", "w-901")]),
                metadata_overrides=override,
            )
            expect_raises(
                live.LiveEvidenceError,
                lambda path=path: _verify_grounded(path),
                f"a malformed {label} was accepted",
            )


def test_live_evidence_rejects_an_incomplete_run() -> None:
    """BLOCKER 2B, regressions 1, 2 and 10."""

    with tempfile.TemporaryDirectory(prefix="saa-ev-poll-") as tmp:
        path = Path(tmp) / "events.jsonl"
        path.write_text('{"event":"poll_started"}\n', encoding="utf-8")
        expect_raises(
            live.LiveEvidenceError,
            lambda: live.verify(events_path=path),
            "an unbound poll_started-only file was parsed as evidence",
        )

        # A poll that never finished is not a poll.
        unfinished = _write_envelope(
            Path(tmp),
            "SAA-D-human-held-unmerged-reservation",
            [
                _live_event("poll_started", "poll-1", poll_index=1),
                _reservations(_held_scene_reservations()),
            ],
        )
        expect_raises(
            live.LiveEvidenceError,
            lambda: _verify_grounded(unfinished),
            "a poll with no terminal record was accepted",
        )

        # A complete poll that decided nothing: parsed, but nothing is proven.
        empty = _write_envelope(
            Path(tmp),
            "SAA-A-parallel-safe-assignments",
            _live_poll("poll-1", 1, "idle", []),
        )
        report, exit_code = _verify_grounded(empty)
    require(exit_code == 1, "a run that proved nothing exited 0")
    require(
        {"run_poll_lifecycle", "poll_step_alignment"} <= _failed_required(report),
        f"an incomplete run passed its lifecycle checks: {sorted(_failed_required(report))}",
    )


def test_live_evidence_rejects_one_launch_where_two_are_required() -> None:
    """BLOCKER 2B, regression 2. The audit's scenario-A envelope."""

    with tempfile.TemporaryDirectory(prefix="saa-ev-one-") as tmp:
        path = _write_envelope(
            Path(tmp),
            "SAA-A-parallel-safe-assignments",
            _live_poll("poll-1", 1, "start", [_launch("NSC-901", "w-901")]),
        )
        report, exit_code = _verify_grounded(path)
    require(exit_code == 1, "one launch satisfied a two-launch scenario")
    require(
        {"run_poll_lifecycle", "poll_step_alignment"} <= _failed_required(report),
        f"the missing second poll was not reported: {sorted(_failed_required(report))}",
    )


def test_live_evidence_rejects_a_foreign_launch_scheduler() -> None:
    """BLOCKER 2A, regression 7."""

    with tempfile.TemporaryDirectory(prefix="saa-ev-sched-") as tmp:
        path = _write_envelope(
            Path(tmp),
            "SAA-A-parallel-safe-assignments",
            [
                *_live_poll(
                    "poll-1",
                    1,
                    "start",
                    [_launch("NSC-901", "w-901", scheduler_id="sched-other")],
                ),
                *_live_poll(
                    "poll-2",
                    2,
                    "start",
                    [_launch("NSC-902", "w-902", poll_id="poll-2")],
                ),
            ],
        )
        report, exit_code = _verify_grounded(path)
    require(exit_code == 1, "a launch by a different scheduler was accepted")
    require(
        "scheduler_identity_consistent" in _failed_required(report),
        f"the scheduler binding did not fail: {sorted(_failed_required(report))}",
    )


def test_live_evidence_requires_grounded_conflict_evidence() -> None:
    """BLOCKER 2C, regressions 8 and 9. Scenario D's wait must be real."""

    from acceptance_lib import canonical_sha256

    reservations = _held_scene_reservations()
    fingerprint = canonical_sha256(reservations)

    with tempfile.TemporaryDirectory(prefix="saa-ev-nores-") as tmp:
        # No reservation observation at all: the state the wait claims to have
        # seen was never recorded.
        path = _write_envelope(
            Path(tmp),
            "SAA-D-human-held-unmerged-reservation",
            _live_poll(
                "poll-1",
                1,
                "idle",
                [_wait("NSC-914", "NSC-905", [GAME_SCENE], fingerprint)],
            ),
        )
        report, exit_code = _verify_grounded(path)
        require(exit_code == 1, "a wait with no reservation observation was accepted")
        require(
            "conflict_evidence_grounded" in _failed_required(report),
            f"the grounding check did not fail: {sorted(_failed_required(report))}",
        )

    with tempfile.TemporaryDirectory(prefix="saa-ev-token-") as tmp:
        # An invented overlap token: syntactically valid, in neither surface.
        invented = [{**reservations[0], "actual_paths": [GAME_SCENE]}]
        path = _write_envelope(
            Path(tmp),
            "SAA-D-human-held-unmerged-reservation",
            _live_poll(
                "poll-1",
                1,
                "idle",
                [
                    _reservations(invented),
                    _wait(
                        "NSC-914",
                        "NSC-905",
                        ["SyntheticGame/Prefabs/HUD.prefab"],
                        canonical_sha256(invented),
                    ),
                ],
            ),
        )
        report, exit_code = _verify_grounded(path)
        require(exit_code == 1, "an invented overlap token was accepted")
        require(
            "conflict_evidence_grounded" in _failed_required(report),
            f"the invented token was not caught: {sorted(_failed_required(report))}",
        )

    with tempfile.TemporaryDirectory(prefix="saa-ev-unseen-") as tmp:
        # The named path is in the candidate's contract but not in the observed
        # reservation surface, so the run never saw the collision it claims.
        unseen = [
            {"task_id": "NSC-905", "actual_paths": [], "surface_unknown": False}
        ]
        path = _write_envelope(
            Path(tmp),
            "SAA-D-human-held-unmerged-reservation",
            _live_poll(
                "poll-1",
                1,
                "idle",
                [
                    _reservations(unseen),
                    _wait(
                        "NSC-914",
                        "NSC-905",
                        [GAME_SCENE],
                        canonical_sha256(unseen),
                    ),
                ],
            ),
        )
        report, exit_code = _verify_grounded(path)
        require(exit_code == 1, "a wait over an unobserved surface was accepted")
        require(
            "conflict_evidence_grounded" in _failed_required(report),
            f"the unobserved surface was not caught: {sorted(_failed_required(report))}",
        )


def test_live_evidence_rejects_a_fabricated_task_id() -> None:
    """ADVERSARIAL 4. NSC-999 belongs to no scenario."""

    with tempfile.TemporaryDirectory(prefix="saa-ev-999-") as tmp:
        path = _write_envelope(
            Path(tmp),
            "SAA-A-parallel-safe-assignments",
            _live_poll("poll-1", 1, "start", [_launch("NSC-999", "w-999")]),
        )
        expect_raises(
            live.LiveEvidenceError,
            lambda: _verify_grounded(path),
            "a fabricated NSC-999 launch was accepted",
        )
    with tempfile.TemporaryDirectory(prefix="saa-ev-other-") as tmp:
        # A real task ID, but not one this scenario declares.
        path = _write_envelope(
            Path(tmp),
            "SAA-A-parallel-safe-assignments",
            _live_poll("poll-1", 1, "start", [_launch("NSC-916", "w-916")]),
        )
        expect_raises(
            live.LiveEvidenceError,
            lambda: _verify_grounded(path),
            "a launch for a task outside the scenario was accepted",
        )


def test_live_evidence_rejects_mismatched_identity() -> None:
    """ADVERSARIAL 5."""

    cases = {
        "manifest hash": {"manifest_sha256": "0" * 64},
        "schema version": {"schema_version": "1.0"},
        "unknown scenario": {"scenario_id": "SAA-K-decomposition-required-broad-task"},
        "production repository": {"repository": "cathode26/NoSafeCircle"},
        "short source head": {"source_head": "abc"},
    }
    for label, override in cases.items():
        with tempfile.TemporaryDirectory(prefix="saa-ev-id-") as tmp:
            path = _write_envelope(
                Path(tmp),
                "SAA-A-parallel-safe-assignments",
                _live_poll("poll-1", 1, "start", [_launch("NSC-901", "w-901")]),
                metadata_overrides=override,
            )
            expect_raises(
                live.LiveEvidenceError,
                lambda path=path: _verify_grounded(path),
                f"mismatched identity accepted: {label}",
            )

    for label, mutation in {
        "run id": lambda e: e.update(run_id="another-run"),
        "scenario id": lambda e: e.update(scenario_id="SAA-B-predicted-exact-path-conflict"),
        "sequence": lambda e: e.update(sequence=9),
        "poll id": lambda e: e.update(poll_id="poll-elsewhere"),
    }.items():
        with tempfile.TemporaryDirectory(prefix="saa-ev-bind-") as tmp:
            events = _live_poll("poll-1", 1, "start", [_launch("NSC-901", "w-901")])
            events[1].update(
                run_id="run-0001",
                scenario_id="SAA-A-parallel-safe-assignments",
                sequence=2,
            )
            mutation(events[1])
            path = _write_envelope(
                Path(tmp), "SAA-A-parallel-safe-assignments", events
            )
            expect_raises(
                live.LiveEvidenceError,
                lambda path=path: _verify_grounded(path),
                f"an unbound event was accepted: {label}",
            )


def test_live_evidence_rejects_decomposition_and_unknown_events() -> None:
    """ADVERSARIAL 6. Decomposition parsing is gone, so its events are unknown."""

    for event in (
        {"event": "decomposition_proposed", "plan_sha256": "a" * 64},
        {"event": "decomposition_authorized", "actor_kind": "human"},
        {"event": "graph_delta_applied", "plan_sha256": "a" * 64},
        {"event": "everything_is_fine"},
    ):
        with tempfile.TemporaryDirectory(prefix="saa-ev-unknown-") as tmp:
            path = _write_envelope(
                Path(tmp), "SAA-A-parallel-safe-assignments", [dict(event)]
            )
            expect_raises(
                live.LiveEvidenceError,
                lambda path=path: _verify_grounded(path),
                f"an unknown event type was accepted: {event['event']}",
            )


def test_live_evidence_rejects_unknown_and_missing_event_fields() -> None:
    with tempfile.TemporaryDirectory(prefix="saa-ev-fields-") as tmp:
        extra = _launch("NSC-901", "w-1")
        extra["looks_fine"] = True
        path = _write_envelope(
            Path(tmp),
            "SAA-A-parallel-safe-assignments",
            _live_poll("poll-1", 1, "start", [extra]),
        )
        expect_raises(
            live.LiveEvidenceError,
            lambda: _verify_grounded(path),
            "an unknown event field was accepted",
        )

        for label, mutation in {
            "worker id": lambda event: event.pop("worker_id"),
            "poll id": lambda event: event.pop("poll_id"),
            "scheduler id": lambda event: event.pop("scheduler_id"),
        }.items():
            incomplete = _launch("NSC-901", "w-1")
            mutation(incomplete)
            path = _write_envelope(
                Path(tmp),
                "SAA-A-parallel-safe-assignments",
                _live_poll("poll-1", 1, "start", [incomplete]),
            )
            expect_raises(
                live.LiveEvidenceError,
                lambda path=path: _verify_grounded(path),
                f"a launch missing its {label} was accepted",
            )

        empty_worker = _launch("NSC-901", "")
        path = _write_envelope(
            Path(tmp),
            "SAA-A-parallel-safe-assignments",
            _live_poll("poll-1", 1, "start", [empty_worker]),
        )
        expect_raises(
            live.LiveEvidenceError,
            lambda: _verify_grounded(path),
            "a launch with an empty worker ID was accepted",
        )


def test_live_evidence_requires_structured_wait_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="saa-ev-wait-") as tmp:
        prose_only = _live_event(
            "candidate_waited",
            "poll-1",
            task_id="NSC-914",
            wait_kind="exact_path_actual",
            conflicting_task_id="NSC-905",
            overlapping_values=[],
            reason="it felt risky to run these together",
            reservation_fingerprint="f" * 64,
        )
        path = _write_envelope(
            Path(tmp),
            "SAA-D-human-held-unmerged-reservation",
            _live_poll("poll-1", 1, "idle", [prose_only]),
        )
        expect_raises(
            live.LiveEvidenceError,
            lambda: _verify_grounded(path),
            "a wait with a prose reason and no overlapping values was accepted",
        )


def test_live_evidence_rejects_a_start_with_no_state_change() -> None:
    from acceptance_lib import canonical_sha256

    reservations = _held_scene_reservations()
    with tempfile.TemporaryDirectory(prefix="saa-ev-nochange-") as tmp:
        path = _write_envelope(
            Path(tmp),
            "SAA-F-wait-becomes-start-after-integration",
            [
                *_live_poll(
                    "poll-1",
                    1,
                    "idle",
                    [
                        _reservations(reservations),
                        _wait(
                            "NSC-914",
                            "NSC-905",
                            [GAME_SCENE],
                            canonical_sha256(reservations),
                        ),
                    ],
                ),
                *_live_poll(
                    "poll-2",
                    2,
                    "start",
                    [
                        _reservations(reservations, poll_id="poll-2"),
                        _launch("NSC-914", "w-914", poll_id="poll-2"),
                    ],
                ),
            ],
        )
        report, exit_code = _verify_grounded(path)
    require(exit_code == 1, "a start with no observable state change was accepted")
    require(
        any(
            check.name == "wait_then_start_transition"
            and check.status == live.STATUS_FAILED
            for check in report.checks
        ),
        "the wait-then-start check did not fail",
    )


def test_live_evidence_rejects_an_unbound_wait_fingerprint() -> None:
    with tempfile.TemporaryDirectory(prefix="saa-ev-fp-") as tmp:
        path = _write_envelope(
            Path(tmp),
            "SAA-F-wait-becomes-start-after-integration",
            [
                *_live_poll(
                    "poll-1",
                    1,
                    "idle",
                    [
                        _reservations(_held_scene_reservations()),
                        _wait("NSC-914", "NSC-905", [GAME_SCENE], "0" * 64),
                    ],
                ),
                *_live_poll(
                    "poll-2",
                    2,
                    "start",
                    [
                        _reservations([], poll_id="poll-2"),
                        _launch("NSC-914", "w-914", poll_id="poll-2"),
                    ],
                ),
            ],
        )
        report, exit_code = _verify_grounded(path)
    require(exit_code == 1, "a WAIT not bound to its own reservation state was accepted")
    require(
        {"wait_then_start_transition", "conflict_evidence_grounded"}
        <= _failed_required(report),
        f"the fingerprint binding check did not fail: {sorted(_failed_required(report))}",
    )


def test_live_evidence_rejects_merge_uncertainty_escalation() -> None:
    from acceptance_lib import canonical_sha256

    reservations = _held_scene_reservations()
    with tempfile.TemporaryDirectory(prefix="saa-ev-escalate-") as tmp:
        path = _write_envelope(
            Path(tmp),
            "SAA-D-human-held-unmerged-reservation",
            _live_poll(
                "poll-1",
                1,
                "idle",
                [
                    _reservations(reservations),
                    _wait(
                        "NSC-914",
                        "NSC-905",
                        [GAME_SCENE],
                        canonical_sha256(reservations),
                    ),
                    _live_event(
                        "architect_human_review",
                        "poll-1",
                        task_id="NSC-914",
                        escalation_category="merge_uncertainty",
                        escalation_question="should I risk it?",
                    ),
                ],
            ),
        )
        report, exit_code = _verify_grounded(path)
    require(exit_code == 1, "a merge-uncertainty escalation was accepted")
    require(
        any(
            check.name == "human_review_is_narrow"
            and check.status == live.STATUS_FAILED
            for check in report.checks
        ),
        "the narrow-escalation check did not fail",
    )


def test_live_evidence_singleton_requires_a_real_contest() -> None:
    """BLOCKER 2D, regressions 11 and 12."""

    scenario_id = "SAA-J-scheduler-singleton"
    source = _grounded_source()
    checkout_root = str(source.checkout_root)
    grounded_identity = live.expected_lock_identity(
        live.observe_source(source.root), checkout_root
    )
    with tempfile.TemporaryDirectory(prefix="saa-ev-single-") as tmp:
        # Nothing contested: UNPROVEN, and UNPROVEN is required here.
        path = _write_envelope(
            Path(tmp),
            scenario_id,
            _live_poll(
                "poll-1",
                1,
                "no_launch",
                [
                    _lock_events(checkout_root, grounded_identity)[0],
                ],
            ),
        )
        _, exit_code = _verify_grounded(path)
        require(exit_code == 1, "an uncontested lock was accepted as singleton proof")

        # Two fabricated lock strings: well-formed, correlated to nothing real.
        path = _singleton_envelope(Path(tmp), lock_identity="sha256:" + "0" * 64)
        report, exit_code = _verify_grounded(path)
        require(
            exit_code == 1,
            "two fabricated lock strings were accepted as a singleton contest",
        )
        require(
            "singleton_lock_ownership" in _failed_required(report),
            f"the ungrounded lock identity was not caught: "
            f"{sorted(_failed_required(report))}",
        )

        # A contest whose two halves are not the same contest.
        events = _live_poll(
            "poll-1",
            1,
            "start",
            [
                *_lock_events(checkout_root, grounded_identity),
                _launch("NSC-901", "w-901"),
            ],
        )
        events[2]["contest_id"] = "contest-elsewhere"
        path = _write_envelope(Path(tmp), scenario_id, events)
        report, exit_code = _verify_grounded(path)
        require(exit_code == 1, "two uncorrelated lock events were accepted")

        # The loser launched anyway.
        events = _live_poll(
            "poll-1",
            1,
            "start",
            [
                *_lock_events(checkout_root, grounded_identity),
                _launch("NSC-901", "w-901", scheduler_id="sched-2"),
            ],
        )
        path = _write_envelope(Path(tmp), scenario_id, events)
        report, exit_code = _verify_grounded(path)
        require(exit_code == 1, "a rejected scheduler that launched work was accepted")

        # A genuine, grounded contest.
        path = _singleton_envelope(Path(tmp))
        report, exit_code = _verify_grounded(path)
        require(
            exit_code == 0,
            f"a genuine singleton contest failed: "
            f"{[c.to_dict() for c in report.unsatisfied_required]}",
        )


def test_live_evidence_rejects_a_corrupt_or_unbound_file() -> None:
    with tempfile.TemporaryDirectory(prefix="saa-ev-corrupt-") as tmp:
        path = Path(tmp) / "events.jsonl"
        for content in (
            '{"event": "run_metadata"}\nnot json\n',
            "",
            '{"not_an_event": 1}\n',
        ):
            path.write_text(content, encoding="utf-8")
            expect_raises(
                live.LiveEvidenceError,
                lambda: live.verify(events_path=path),
                f"a corrupt evidence file was parsed: {content!r}",
            )


# ---------------------------------------------------------------------------
# Package hygiene
# ---------------------------------------------------------------------------

PACKAGE_FILES = (
    "README.md",
    "OLD_GAUNTLET_REUSE.md",
    "LIVE_PROOF_CHECKLIST.md",
    "scenarios.json",
    "acceptance_lib.py",
    "manifest.py",
    "synthetic_repository.py",
    "scenario_world.py",
    "scheduler_adapter.py",
    "verify_acceptance.py",
    "verify_live_evidence.py",
    "acceptance_smoke_test.py",
)


def test_package_contains_exactly_the_expected_files() -> None:
    present = sorted(
        item.name for item in ACCEPTANCE_DIR.iterdir() if item.is_file()
    )
    require(
        present == sorted(PACKAGE_FILES),
        f"unexpected package contents: {present}",
    )


def test_source_files_are_whitespace_clean() -> None:
    """A direct byte scan. `git diff --check` alone does not cover untracked files."""

    offenders: list[str] = []
    for name in PACKAGE_FILES:
        path = ACCEPTANCE_DIR / name
        raw = path.read_bytes()
        if b"\r" in raw:
            offenders.append(f"{name}: contains CR bytes")
        if not raw.endswith(b"\n"):
            offenders.append(f"{name}: no final newline")
        if raw.endswith(b"\n\n"):
            offenders.append(f"{name}: blank line at end of file")
        text = raw.decode("utf-8")
        for number, line in enumerate(text.split("\n"), start=1):
            if line != line.rstrip():
                offenders.append(f"{name}:{number}: trailing whitespace")
            if "\t" in line:
                offenders.append(f"{name}:{number}: tab character")
    require(not offenders, "whitespace defects: " + "; ".join(offenders))


def test_fixtures_refuse_to_be_built_inside_the_repository() -> None:
    for path in (ROOT, ACCEPTANCE_DIR, ROOT / "Assets"):
        expect_raises(
            AcceptanceSafetyError,
            lambda path=path: create_fixture_root(path, "x"),  # type: ignore[arg-type]
            f"a fixture would have been built inside {path}",
        )


def test_package_launches_no_process_other_than_git() -> None:
    """Static invariant: the only subprocess this package can start is Git."""

    offenders: list[str] = []
    for path in sorted(ACCEPTANCE_DIR.glob("*.py")):
        if path == HERE:
            # This file names the banned imports as literals in order to search
            # for them, so scanning it would always report itself.
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"subprocess\.(run|Popen|call|check_output)", text):
            window = text[match.start() : match.start() + 400]
            if '"git"' not in window and "'git'" not in window:
                offenders.append(f"{path.name}: {window.splitlines()[0]}")
        for banned in ("import requests", "import urllib", "from urllib", "http.client"):
            if banned in text:
                offenders.append(f"{path.name}: {banned}")
    require(not offenders, f"non-Git or network process usage found: {offenders}")


TESTS = (
    # Manifest
    test_manifest_is_valid_and_ids_are_unique,
    test_manifest_states_are_recognized,
    test_manifest_carries_no_retired_decomposition_vocabulary,
    test_manifest_surface_matches_the_fixture_generator,
    test_every_declared_task_is_referenced,
    test_scenarios_only_use_synthetic_task_ids,
    # Strict manifest validation
    test_manifest_rejects_an_unknown_outcome,
    test_manifest_rejects_unknown_fields_everywhere,
    test_manifest_rejects_broken_task_references,
    test_manifest_rejects_an_unbacked_exclusive_resource_conflict,
    test_manifest_requires_a_worker_id_for_every_start,
    test_manifest_rejects_an_unknown_live_evidence_check,
    test_manifest_rejects_prearranged_resume_priority,
    test_manifest_rejects_a_singleton_scenario_with_scripted_steps,
    # Path containment and destructive safety
    test_declared_paths_reject_every_escape_form,
    test_resolve_within_rejects_a_symlink_escape,
    test_destroy_refuses_everything_it_did_not_create,
    test_forged_ownership_handles_are_inert,
    test_destroy_succeeds_for_an_exact_created_fixture,
    test_parent_cleanup_refuses_a_live_fixture_child,
    test_fixture_roots_cannot_be_created_outside_a_disposable_parent,
    test_production_targets_are_refused,
    # Determinism
    test_fixture_generation_is_deterministic_across_two_runs,
    test_inherited_git_configuration_cannot_change_a_fixture,
    test_fixture_repositories_use_an_empty_hooks_directory,
    test_local_branches_and_diffs_are_reproduced_exactly,
    test_unobservable_surface_is_unknown_not_empty,
    # Layer 1
    test_every_scenario_fixture_models_its_declared_facts,
    test_fixture_verification_catches_a_wrong_declared_path,
    test_g2_prose_alone_cannot_establish_disjointness,
    test_i1_fixture_proves_resume_is_not_queue_order,
    test_i2_detects_an_unauthorized_durable_mutation,
    # Acceptance provenance
    test_harness_replay_can_never_reach_an_acceptance_status,
    test_spoofed_capabilities_and_identity_cannot_manufacture_a_pass,
    test_acceptance_path_accepts_no_injected_adapter,
    test_only_the_acceptance_path_can_emit_pass,
    test_missing_worker_id_cannot_reach_an_acceptance_pass,
    test_world_refuses_to_synthesize_a_missing_worker_id,
    test_verifier_discriminates_a_wrong_scheduling_answer,
    test_singleton_cannot_harness_pass_from_one_scripted_cycle,
    test_h2_malformed_output_waits_and_never_escalates,
    # Per-step event evidence
    test_decision_only_wait_cannot_prove_a_step,
    test_a_later_launch_event_cannot_satisfy_an_earlier_step,
    test_one_event_cannot_grade_two_steps,
    test_two_correct_steps_prove_their_own_events,
    test_a_contradictory_launch_fails_a_non_launch_step,
    test_evidence_fails_closed_on_unknown_or_incomplete_events,
    # Real adapter integration
    test_real_adapter_advertises_only_ordinary_cycle_capabilities,
    test_scenario_j_stays_fail_closed_and_pending,
    test_real_adapter_drives_the_production_polling_orchestrator,
    test_fresh_plan_translation_reaches_production_scheduling,
    test_resume_authority_is_translated_through_dispatch_plan_resume,
    test_reservations_and_unknown_surface_reach_production_reasoning,
    test_architect_unavailable_and_malformed_fail_closed_through_production,
    test_launch_evidence_uses_captured_production_argv,
    test_real_acceptance_needs_no_process_provider_or_network,
    test_real_acceptance_answers_ordinary_cycles_and_leaves_j_pending,
    # Real-adapter adversarial evidence
    test_unknown_production_event_kinds_fail_closed,
    test_explicitly_ignored_diagnostic_events_stay_permitted,
    test_result_worker_id_must_match_the_launch_record,
    test_launch_record_worker_id_must_match_argv,
    test_captured_process_argv_must_match_the_reported_argv,
    test_task_identity_must_agree_across_every_production_source,
    test_event_only_launch_identity_mismatch_fails_closed,
    test_launch_cross_binding_agrees_on_a_real_production_launch,
    test_scenario_b_proves_a_real_predicted_exact_path_conflict,
    # Live evidence
    test_live_evidence_accepts_a_complete_bound_run,
    test_live_evidence_accepts_minimal_a_and_d_shapes,
    test_live_evidence_requires_a_grounded_source,
    test_live_evidence_rejects_fabricated_source_identity,
    test_live_evidence_rejects_malformed_run_identity,
    test_live_evidence_rejects_an_incomplete_run,
    test_live_evidence_rejects_one_launch_where_two_are_required,
    test_live_evidence_rejects_a_foreign_launch_scheduler,
    test_live_evidence_requires_grounded_conflict_evidence,
    test_live_evidence_rejects_a_fabricated_task_id,
    test_live_evidence_rejects_mismatched_identity,
    test_live_evidence_rejects_decomposition_and_unknown_events,
    test_live_evidence_rejects_unknown_and_missing_event_fields,
    test_live_evidence_requires_structured_wait_evidence,
    test_live_evidence_rejects_a_start_with_no_state_change,
    test_live_evidence_rejects_an_unbound_wait_fingerprint,
    test_live_evidence_rejects_merge_uncertainty_escalation,
    test_live_evidence_singleton_requires_a_real_contest,
    test_live_evidence_rejects_a_corrupt_or_unbound_file,
    # Package hygiene
    test_package_contains_exactly_the_expected_files,
    test_source_files_are_whitespace_clean,
    test_fixtures_refuse_to_be_built_inside_the_repository,
    test_package_launches_no_process_other_than_git,
)


def main() -> int:
    _block_network()
    try:
        for test in TESTS:
            test()
            print(f"PASS {test.__name__}")
    finally:
        _release_grounded_source()
    print("")
    print(
        f"Software Architect Acceptance HARNESS TESTS: PASS ({len(TESTS)} tests)"
    )
    print(
        "These prove the fixtures, manifest, containment rules, adapter boundary "
        "and verifiers. They prove nothing about the polling architect scheduler."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
