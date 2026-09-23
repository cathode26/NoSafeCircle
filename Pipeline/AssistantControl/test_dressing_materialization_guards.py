"""Guards for the room-dressing prefab materialization route.

Covers the new dressing-specific checks added alongside the five approved
``ROOM_SCENE_BUILDERS``:

* ``Pipeline/TaskReviewAgent/door_prototype_materialization.py`` --
  ``resolve_dressing_builder``, ``declares_dressing_entry_point``, and the
  two post-Unity-launch blocks inside ``run_door_prototype_builder`` that
  raise ``builder_modified_source_input``, ``dressing_builder_modified_scene``
  and ``registered_prefab_output_missing``.
* ``Pipeline/AssistantControl/unity_materialization.py`` --
  ``_require_dressing_sources`` (``dressing_builder_scope_mismatch``,
  ``builder_source_not_regular``, ``builder_entry_point_missing``,
  ``catalog_source_missing``, ``catalog_source_invalid``) and the
  ``_CandidateMaterials.dressing`` / ``dressing_journal`` plumbing through
  ``materialize_candidate``.

The dressing builder, catalog and their compiled behaviour do NOT exist on
main -- the crew authors them per candidate -- so every check here reads them
at the exact candidate commit inside a real temporary git repository. No real
Unity, Docker or provider ever runs; every Unity call is an injected fake.

Pure resolver characterization (``resolve_generated_builder`` /
``is_dressing_prefab_location`` / the registry's own internal consistency,
including "a dressing prefab plus an unassigned generated asset refuses" --
``DressingHasNoAbsorptionUnlikeARoom.test_dressing_plus_an_unassigned_generated_asset_refuses``)
already lives in ``test_dressing_prefab_registry.py``. What is added here is
the full materialization boundary: real git commits read at an exact SHA, an
injected Unity command runner, and the journal/record side effects -- plus
proving that same non-absorption refusal fires BEFORE Unity ever launches
through ``run_door_prototype_builder`` itself, not only inside the pure
resolver.

Fixture machinery (temp git repo, task contract, Checkouts, scope plan,
hand-built crew candidate receipt) follows the pattern established in
``test_unity_materialization.py``'s ``MaterializationTests`` and
``RoomSceneMaterializationTests``, factored into ``DressingFixtureMixin``
here because this file drives it with many more deliberate single-defect
variations than any one class there needs.

One receipt fact worth stating once, because several refusal cases in this
file rely on it: ``_candidate_receipt`` (unity_materialization.py) checks a
receipt's own self-hash and its identity fields (task id, commit, tree,
plan_id, lease_id) but never independently re-diffs ``changed_paths`` against
real git output. A test is therefore free to commit exactly one deliberate
defect to the checkout while still *claiming* the paths needed to clear the
earlier identity/overlap gates, which is what isolates one guard at a time
below instead of tripping an unrelated earlier check.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path
from typing import Sequence

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.unity_materialization import (
    MaterializationError,
    materialize_candidate,
)
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.door_prototype_materialization import (
    DOOR_PROTOTYPE_ROOT,
    DRESSING_PREFAB_BUILDERS,
    DoorPrototypeMaterializationError,
    DressingPrefabBuilder,
    declares_dressing_entry_point,
    run_door_prototype_builder,
)
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity
from Pipeline.TaskReviewAgent.local_candidate_commit import LocalCandidateCommitReceipt


def _dressing_for(room: str) -> DressingPrefabBuilder:
    """The one DRESSING_PREFAB_BUILDERS entry for ``room``, read from the
    live registry so this file never hand-copies its paths.
    """
    (builder,) = (b for b in DRESSING_PREFAB_BUILDERS.values() if b.room == room)
    return builder


def _good_builder_source(dressing: DressingPrefabBuilder) -> str:
    return (
        f"namespace {dressing.namespace}\n"
        "{\n"
        f"    public static class {dressing.class_name}\n"
        "    {\n"
        "        public static void Build()\n"
        "        {\n"
        "        }\n"
        "    }\n"
        "}\n"
    )


def _builder_source_missing_entry_point(dressing: DressingPrefabBuilder) -> str:
    """Compiles fine, declares the right class, never declares ``Build``."""
    return (
        f"namespace {dressing.namespace}\n"
        "{\n"
        f"    public static class {dressing.class_name}\n"
        "    {\n"
        "        public static void NotBuild() { }\n"
        "    }\n"
        "}\n"
    )


def _good_catalog(dressing: DressingPrefabBuilder) -> str:
    return json.dumps({"room": dressing.room, "props": []}) + "\n"


GOOD_PREFAB_META = (
    b"fileFormatVersion: 2\n"
    b"guid: 0123456789abcdef0123456789abcdef\n"
    b"PrefabImporter:\n"
    b"  externalObjects: {}\n"
)


class DressingFixtureMixin:
    """Shared construction for a room-dressing candidate.

    Follows ``test_unity_materialization.py``'s temp-git-repo pattern (a
    disposable directory rather than ``tempfile.TemporaryDirectory``, whose
    ACL some Windows sandboxes cannot traverse).
    """

    def _bootstrap(
        self, room: str, task_id: str, *, omit_resource: str | None = None,
    ) -> DressingPrefabBuilder:
        """Build a source repo + owned checkout + accepted scope for ``room``.

        ``omit_resource`` drops one of {"prefab", "builder", "catalog"} from
        the task's own ``exclusive_resources`` while the ExecutionScopePlan
        still names all three -- used only by the scope-mismatch case, whose
        refusal fires on the ``exclusive_resources`` side of the check.

        Nothing about the prefab, builder or catalog is written to the SOURCE
        repo: they do not exist on main. Only ``ProjectVersion.txt``, the
        fixture policy-runner stubs, the task contract, and one pre-existing
        test source file are committed before ``prepare()``.
        """
        dressing = _dressing_for(room)
        self.dressing = dressing
        self.task_id = task_id
        test_root = Path.cwd() / ".test-work"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"dressing-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git(self.source, "init", "-q")
        name, email = validated_agent_git_identity()
        self.git(self.source, "config", "user.name", name)
        self.git(self.source, "config", "user.email", email)
        self.test_path = (
            "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Environment/"
            f"{dressing.class_name}Tests.cs"
        )
        for relative, content in (
            (self.test_path, f"class {dressing.class_name}Tests {{}}\n"),
            ("ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000.1.8f1\n"),
            ("Pipeline/Testing/run_unity_tests_clean.ps1", "# fixture\n"),
            ("Pipeline/TaskGraph/taskcontrol.py", "print('taskcontrol validate: PASS')\n"),
        ):
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        resources = {
            "prefab": f"repo-file:{dressing.prefab_path}",
            "builder": f"repo-file:{dressing.builder_source_path}",
            "catalog": f"repo-file:{dressing.catalog_path}",
        }
        if omit_resource is not None:
            del resources[omit_resource]
        task = {
            "schema_version": "2.0", "id": task_id, "contract_revision": 1,
            "contract_disposition": "active", "title": f"Fixture {room} dressing",
            "reconciliation_key": f"fixture-{room.lower()}-dressing",
            "kind": "implementation", "type": "world-foundation",
            "execution_scope": "single_agent", "execution_reason": "fixture",
            "decomposition_state": "concrete", "decomposition_reason": "fixture",
            "parent": None, "depends_on": [],
            "exclusive_resources": [
                *resources.values(), f"repo-file:{self.test_path}",
            ],
            "acceptance_criteria": [], "completion_gates": [],
            "downstream_integration_obligations": [], "gdd_evidence": [],
            "basis": "direct_gdd", "source_scope": "required", "confidence": "high",
        }
        task_path = self.source / f"Tasks/{task_id}.yaml"
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(json.dumps(task), encoding="utf-8", newline="\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-q", "-m", "fixture")
        self.manager = Checkouts(self.source, self.root / "checkouts")
        prepared = self.manager.prepare(task_id)
        self.checkout = Path(prepared["checkout"])
        self.unity = self.root / "Unity.exe"
        self.unity.write_bytes(b"fixture")
        self.scope = AssistantScopePlanner(self.manager).plan(
            task_id,
            ExecutionScopePlan(
                (), (dressing.prefab_path, dressing.builder_source_path,
                     dressing.catalog_path),
                (self.test_path,), (),
            ),
            lease_id="fixture-lease",
        )
        return dressing

    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ("git", "-C", str(root), *args), capture_output=True, check=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def write_and_stage(self, relative: str, content) -> None:
        target = self.checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, newline="\n")
        self.git(self.checkout, "add", "--", relative)

    def commit(self, message: str) -> str:
        self.git(self.checkout, "commit", "-q", "-m", message)
        return self.git(self.checkout, "rev-parse", "HEAD")

    def stage_symlink_entry(self, path: str, target: str) -> None:
        """Stage a mode-120000 (symlink) tree entry at ``path`` without
        needing real OS symlink support.

        ``git update-index --add --cacheinfo`` writes the tree entry
        directly. The underlying git OBJECT is still a genuine, readable
        blob -- git stores a symlink's target text as an ordinary blob; only
        the tree mode marks it as a symlink -- which is exactly what makes
        this shape distinct from "absent": a caller that keys off object
        existence and length alone (rather than mode and type) will find a
        valid sha here and read straight past it.

        ``core.symlinks=false`` is set explicitly (matching how this
        Windows git installation already behaves by default, confirmed by
        probe) so a later ``git checkout -- <path>`` materializes the link
        target text as an ordinary working-tree file instead of failing or
        requiring elevated privilege, and the checkout reads clean.
        """
        self.git(self.checkout, "config", "core.symlinks", "false")
        blob = subprocess.run(
            ("git", "-C", str(self.checkout), "hash-object", "-w", "--stdin"),
            input=target.encode("utf-8"), capture_output=True, check=False,
        )
        if blob.returncode:
            raise AssertionError(blob.stderr.decode(errors="replace"))
        sha = blob.stdout.decode().strip()
        self.git(
            self.checkout, "update-index", "--add", "--cacheinfo", f"120000,{sha},{path}",
        )

    def register_candidate_at_head(self, *, changed_paths: Sequence[str]) -> str:
        """Register the checkout's current HEAD as the owned crew candidate.

        See the module docstring: ``changed_paths`` is the receipt's OWN
        claim, never independently re-diffed by the code under test, so
        callers pass exactly the paths needed to clear the earlier identity
        gates regardless of what the commit(s) leading to HEAD really touched.
        """
        commit = self.git(self.checkout, "rev-parse", "HEAD")
        tree = self.git(self.checkout, "rev-parse", "HEAD^{tree}")
        record_path = self.manager.records / f"{self.task_id}.json"
        record = json.loads(record_path.read_text())
        receipt = LocalCandidateCommitReceipt(
            task_id=self.task_id, lease_id="fixture-lease", plan_id=self.scope["plan_id"],
            run_id="fixture-crew", source_base=record["source_commit"],
            candidate_commit=commit, candidate_tree=tree,
            candidate_parent=record["source_commit"],
            task_contract_sha256=record["task_contract_sha256"],
            execution_result_sha256="a" * 64, candidate_patch_sha256="b" * 64,
            changed_paths=tuple(sorted(set(changed_paths), key=str.casefold)),
            validation_sha256="c" * 64,
        )
        record["candidate"] = {
            "commit": commit, "tree": tree, "parent": record["source_commit"],
            "run_id": "fixture-crew", "lease_id": "fixture-lease",
            "plan_id": self.scope["plan_id"], "receipt": receipt.to_dict(),
        }
        record["status"] = "awaiting_human"
        record["approval"] = None
        write_record(record_path, record)
        return commit

    def register_good_candidate(self) -> str:
        """Commit valid builder + catalog content and register the candidate.

        The common starting point for every case that needs to get PAST
        ``_require_dressing_sources`` cleanly (provenance, and the two
        post-launch guards), so only the one deliberate defect under test
        remains.
        """
        dressing = self.dressing
        self.write_and_stage(dressing.builder_source_path, _good_builder_source(dressing))
        self.write_and_stage(dressing.catalog_path, _good_catalog(dressing))
        self.commit("crew dressing candidate")
        return self.register_candidate_at_head(
            changed_paths=(dressing.builder_source_path, dressing.catalog_path),
        )

    def passing_validation(self, **kwargs):
        commit = self.git(kwargs["checkout"], "rev-parse", "HEAD")
        self.assertEqual(kwargs["commit"], commit)
        self.assertEqual("", self.git(kwargs["checkout"], "status", "--porcelain=v1"))
        return ({
            "test_platform": "EditMode",
            "test_filter": f"{self.dressing.class_name}Tests",
            "commit": commit,
            "tree": self.git(kwargs["checkout"], "rev-parse", "HEAD^{tree}"),
            "total": 1, "passed": 1,
        },)


class DressingHappyPathMaterializesTheRegisteredPrefab(DressingFixtureMixin, unittest.TestCase):
    """Case A: at least two rooms, driven end to end through materialize_candidate."""

    def _run_happy_path(self, room: str, task_id: str) -> None:
        dressing = self._bootstrap(room, task_id)
        original = self.register_good_candidate()

        calls: list[tuple] = []

        def dressing_runner(args, cwd, timeout):
            calls.append(tuple(args))
            self.assertEqual(self.checkout.resolve(), cwd.resolve())
            args = list(args)
            self.assertIn("-executeMethod", args)
            method_index = args.index("-executeMethod") + 1
            self.assertEqual(dressing.build_method, args[method_index])
            joined = " ".join(str(item).casefold() for item in args)
            self.assertNotIn(".unity", joined)
            (cwd / dressing.prefab_path).write_text("prefab body\n", newline="\n")
            (cwd / (dressing.prefab_path + ".meta")).write_bytes(GOOD_PREFAB_META)
            return subprocess.CompletedProcess(args, 0, b"builder complete\n", b"")

        result = materialize_candidate(
            self.manager, task_id, original, unity_executable=self.unity,
            unity_command_runner=dressing_runner,
            validation_runner=self.passing_validation,
        )
        self.assertEqual(1, len(calls), "Unity must launch exactly once")
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual("unity_materialized", result["candidate"]["kind"])
        changed = result["candidate"]["changed_paths"]
        self.assertIn(dressing.prefab_path, changed)
        self.assertIn(dressing.prefab_path + ".meta", changed)

        journal = json.loads((
            self.manager.records / f"{task_id}.unity-materialization.{original}.json"
        ).read_text())
        self.assertEqual(dressing.build_method, journal.get("dressing_build_method"))
        self.assertEqual(dressing.prefab_path, journal.get("dressing_primary_prefab"))
        self.assertEqual(dressing.room, journal.get("dressing_room"))
        self.assertTrue(journal.get("dressing_builder_source_blob"))
        self.assertTrue(journal.get("dressing_catalog_blob"))

    def test_happy_path_materializes_bone_archive_dressing(self):
        self._run_happy_path("BoneArchive", "NSC-510")

    def test_happy_path_materializes_final_room_dressing(self):
        self._run_happy_path("FinalRoom", "NSC-511")


class DressingBuilderScopeMismatchRefuses(DressingFixtureMixin, unittest.TestCase):
    """dressing_builder_scope_mismatch: a registered path outside the task's
    own exclusive_resources refuses before Unity launches, even though the
    ExecutionScopePlan itself still names all three paths.
    """

    def test_dressing_builder_scope_mismatch(self):
        dressing = self._bootstrap("RuinedEntry", "NSC-520", omit_resource="catalog")
        self.write_and_stage(dressing.builder_source_path, _good_builder_source(dressing))
        self.write_and_stage(dressing.catalog_path, _good_catalog(dressing))
        self.commit("crew dressing candidate")
        original = self.register_candidate_at_head(
            changed_paths=(dressing.builder_source_path, dressing.catalog_path),
        )

        def exploding_runner(*_args, **_kwargs):
            raise AssertionError("Unity must not launch on a scope mismatch")

        with self.assertRaisesRegex(
            MaterializationError,
            f"dressing_builder_scope_mismatch: {dressing.catalog_path}",
        ):
            materialize_candidate(
                self.manager, "NSC-520", original, unity_executable=self.unity,
                unity_command_runner=exploding_runner,
                validation_runner=self.passing_validation,
            )


class DressingBuilderSourceNotRegularRefuses(DressingFixtureMixin, unittest.TestCase):
    """builder_source_not_regular: committed but not valid UTF-8.

    The catalog is fully valid so the failure is isolated to the builder's
    own decode step (the third check in ``_require_dressing_sources``, after
    both existence checks pass).
    """

    def test_builder_source_not_regular(self):
        dressing = self._bootstrap("RuinedEntry", "NSC-521")
        self.write_and_stage(dressing.builder_source_path, b"\xff\xfe\x00not-utf8")
        self.write_and_stage(dressing.catalog_path, _good_catalog(dressing))
        self.commit("crew dressing candidate")
        original = self.register_candidate_at_head(
            changed_paths=(dressing.builder_source_path, dressing.catalog_path),
        )

        def exploding_runner(*_args, **_kwargs):
            raise AssertionError("Unity must not launch on an unreadable builder source")

        with self.assertRaisesRegex(
            MaterializationError,
            f"builder_source_not_regular: {dressing.builder_source_path} at {original}",
        ):
            materialize_candidate(
                self.manager, "NSC-521", original, unity_executable=self.unity,
                unity_command_runner=exploding_runner,
                validation_runner=self.passing_validation,
            )


class DressingBuilderEntryPointMissingRefuses(DressingFixtureMixin, unittest.TestCase):
    """builder_entry_point_missing: valid C#, wrong/missing entry point."""

    def test_builder_entry_point_missing(self):
        dressing = self._bootstrap("RuinedEntry", "NSC-522")
        self.write_and_stage(
            dressing.builder_source_path, _builder_source_missing_entry_point(dressing),
        )
        self.write_and_stage(dressing.catalog_path, _good_catalog(dressing))
        self.commit("crew dressing candidate")
        original = self.register_candidate_at_head(
            changed_paths=(dressing.builder_source_path, dressing.catalog_path),
        )

        def exploding_runner(*_args, **_kwargs):
            raise AssertionError("Unity must not launch when the entry point is absent")

        with self.assertRaisesRegex(
            MaterializationError,
            f"builder_entry_point_missing: {dressing.build_method} in "
            f"{dressing.builder_source_path} at {original}",
        ):
            materialize_candidate(
                self.manager, "NSC-522", original, unity_executable=self.unity,
                unity_command_runner=exploding_runner,
                validation_runner=self.passing_validation,
            )


class DressingCatalogSourceMissingRefuses(DressingFixtureMixin, unittest.TestCase):
    """catalog_source_missing: builder exists; catalog was never committed."""

    def test_catalog_source_missing(self):
        dressing = self._bootstrap("RuinedEntry", "NSC-523")
        self.write_and_stage(dressing.builder_source_path, _good_builder_source(dressing))
        self.commit("crew dressing candidate (no catalog)")
        original = self.register_candidate_at_head(
            changed_paths=(dressing.builder_source_path, dressing.catalog_path),
        )

        def exploding_runner(*_args, **_kwargs):
            raise AssertionError("Unity must not launch when the catalog is missing")

        with self.assertRaisesRegex(
            MaterializationError,
            f"catalog_source_missing: {dressing.catalog_path} at {original}",
        ):
            materialize_candidate(
                self.manager, "NSC-523", original, unity_executable=self.unity,
                unity_command_runner=exploding_runner,
                validation_runner=self.passing_validation,
            )


class DressingCatalogSourceInvalidRefuses(DressingFixtureMixin, unittest.TestCase):
    """catalog_source_invalid: valid UTF-8, not valid JSON.

    The builder is fully valid so the failure is isolated to the catalog's
    own JSON parse, the last check in ``_require_dressing_sources``.
    """

    def test_catalog_source_invalid(self):
        dressing = self._bootstrap("RuinedEntry", "NSC-524")
        self.write_and_stage(dressing.builder_source_path, _good_builder_source(dressing))
        self.write_and_stage(dressing.catalog_path, "{ this is not json\n")
        self.commit("crew dressing candidate")
        original = self.register_candidate_at_head(
            changed_paths=(dressing.builder_source_path, dressing.catalog_path),
        )

        def exploding_runner(*_args, **_kwargs):
            raise AssertionError("Unity must not launch when the catalog is invalid JSON")

        with self.assertRaisesRegex(
            MaterializationError,
            f"catalog_source_invalid: {dressing.catalog_path} at {original}",
        ):
            materialize_candidate(
                self.manager, "NSC-524", original, unity_executable=self.unity,
                unity_command_runner=exploding_runner,
                validation_runner=self.passing_validation,
            )


class DressingBuilderModifiedSourceInputRefuses(DressingFixtureMixin, unittest.TestCase):
    """builder_modified_source_input: Unity itself rewrites the builder .cs.

    Unlike the five cases above, this guard runs AFTER Unity launches (it
    inspects git status once the injected runner returns), so the runner IS
    called once -- proven here rather than asserted as zero.
    """

    def test_builder_modified_source_input(self):
        dressing = self._bootstrap("RuinedEntry", "NSC-525")
        original = self.register_good_candidate()

        calls: list[tuple] = []

        def sabotaging_runner(args, cwd, timeout):
            calls.append(tuple(args))
            # Unity behaving badly: it rewrites the crew's own builder source
            # instead of only producing the prefab.
            (cwd / dressing.builder_source_path).write_text(
                _good_builder_source(dressing) + "// touched by Unity\n", newline="\n",
            )
            (cwd / dressing.prefab_path).write_text("prefab body\n", newline="\n")
            (cwd / (dressing.prefab_path + ".meta")).write_bytes(GOOD_PREFAB_META)
            return subprocess.CompletedProcess(args, 0, b"", b"")

        with self.assertRaisesRegex(
            MaterializationError,
            f"builder_modified_source_input: {dressing.builder_source_path}",
        ):
            materialize_candidate(
                self.manager, "NSC-525", original, unity_executable=self.unity,
                unity_command_runner=sabotaging_runner,
                validation_runner=self.passing_validation,
            )
        self.assertEqual(1, len(calls), "the guard fires only after Unity actually ran")


class DressingBuilderModifiedSceneRefuses(DressingFixtureMixin, unittest.TestCase):
    """dressing_builder_modified_scene: Unity writes/touches any .unity file.

    Also a post-launch guard; the runner is called exactly once.
    """

    def test_dressing_builder_modified_scene(self):
        dressing = self._bootstrap("RuinedEntry", "NSC-526")
        original = self.register_good_candidate()
        scene_path = "Assets/Scenes/Rooms/LowerVault.unity"

        calls: list[tuple] = []

        def scene_touching_runner(args, cwd, timeout):
            calls.append(tuple(args))
            (cwd / dressing.prefab_path).write_text("prefab body\n", newline="\n")
            (cwd / (dressing.prefab_path + ".meta")).write_bytes(GOOD_PREFAB_META)
            target = cwd / scene_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("a scene Unity had no business touching\n", newline="\n")
            return subprocess.CompletedProcess(args, 0, b"", b"")

        with self.assertRaisesRegex(
            MaterializationError, f"dressing_builder_modified_scene: {scene_path}",
        ):
            materialize_candidate(
                self.manager, "NSC-526", original, unity_executable=self.unity,
                unity_command_runner=scene_touching_runner,
                validation_runner=self.passing_validation,
            )
        self.assertEqual(1, len(calls), "the guard fires only after Unity actually ran")


class DressingRegisteredPrefabOutputMissingRefuses(DressingFixtureMixin, unittest.TestCase):
    """registered_prefab_output_missing: Unity exits 0 but never writes the prefab.

    Also a post-launch guard; the runner is called exactly once.
    """

    def test_registered_prefab_output_missing(self):
        dressing = self._bootstrap("RuinedEntry", "NSC-527")
        original = self.register_good_candidate()

        calls: list[tuple] = []

        def empty_runner(args, cwd, timeout):
            calls.append(tuple(args))
            # Exits cleanly, touches nothing -- the failure Unity gives no
            # error for at all.
            return subprocess.CompletedProcess(args, 0, b"", b"")

        with self.assertRaisesRegex(
            MaterializationError,
            f"registered_prefab_output_missing: {dressing.prefab_path}",
        ):
            materialize_candidate(
                self.manager, "NSC-527", original, unity_executable=self.unity,
                unity_command_runner=empty_runner,
                validation_runner=self.passing_validation,
            )
        self.assertEqual(1, len(calls), "the guard fires only after Unity actually ran")


class DressingProvenanceReadsOnlyTheExactCandidateCommit(DressingFixtureMixin, unittest.TestCase):
    """Case C: valid source on an earlier commit cannot rescue an invalid C.

    The builder declares the entry point correctly at commit A, then a second
    commit B reverts it. B is what gets registered as the candidate, so the
    witness must still refuse -- proving it reads the exact candidate SHA
    rather than "has this class ever been valid in this checkout's history".
    """

    def test_reverted_entry_point_still_refuses_at_the_candidate_commit(self):
        dressing = self._bootstrap("ChapelOfAsh", "NSC-530")
        self.write_and_stage(dressing.builder_source_path, _good_builder_source(dressing))
        self.write_and_stage(dressing.catalog_path, _good_catalog(dressing))
        good_commit = self.commit("crew dressing candidate (valid entry point)")

        self.write_and_stage(
            dressing.builder_source_path, _builder_source_missing_entry_point(dressing),
        )
        reverted_commit = self.commit("crew reverts the entry point before review")
        self.assertNotEqual(good_commit, reverted_commit)

        original = self.register_candidate_at_head(
            changed_paths=(dressing.builder_source_path, dressing.catalog_path),
        )
        self.assertEqual(reverted_commit, original)

        def exploding_runner(*_args, **_kwargs):
            raise AssertionError("Unity must not launch when the candidate C is invalid")

        with self.assertRaisesRegex(
            MaterializationError,
            f"builder_entry_point_missing: {dressing.build_method} in "
            f"{dressing.builder_source_path} at {reverted_commit}",
        ):
            materialize_candidate(
                self.manager, "NSC-530", original, unity_executable=self.unity,
                unity_command_runner=exploding_runner,
                validation_runner=self.passing_validation,
            )
        # And not merely "some commit" in the message -- the exact reverted
        # commit, not the earlier valid one.
        try:
            materialize_candidate(
                self.manager, "NSC-530", original, unity_executable=self.unity,
                unity_command_runner=exploding_runner,
                validation_runner=self.passing_validation,
            )
            self.fail("expected MaterializationError")
        except MaterializationError as exc:
            self.assertIn(reverted_commit, str(exc))
            self.assertNotIn(good_commit, str(exc))


class DeclaresDressingEntryPointDecoys(unittest.TestCase):
    """Case D: pure syntactic witness checks, no git and no Unity at all."""

    @classmethod
    def setUpClass(cls):
        cls.dressing = _dressing_for("LowerVault")

    def _wrap(self, body: str, *, namespace: str | None = None) -> str:
        ns = self.dressing.namespace if namespace is None else namespace
        return f"namespace {ns}\n{{\n{body}\n}}\n"

    # -- decoys: every one of these must be False -----------------------

    def test_method_name_only_in_a_line_comment_is_false(self):
        source = self._wrap(
            f"    public static class {self.dressing.class_name}\n"
            "    {\n"
            "        // public static void Build() { }\n"
            "        public static void NotBuild() { }\n"
            "    }"
        )
        self.assertFalse(declares_dressing_entry_point(source, self.dressing))

    def test_method_name_only_in_a_string_literal_is_false(self):
        source = self._wrap(
            f"    public static class {self.dressing.class_name}\n"
            "    {\n"
            '        public static string Description = "public static void Build()";\n'
            "    }"
        )
        self.assertFalse(declares_dressing_entry_point(source, self.dressing))

    def test_method_name_only_in_a_verbatim_string_is_false(self):
        source = self._wrap(
            f"    public static class {self.dressing.class_name}\n"
            "    {\n"
            '        public static string Description = @"public static void Build()";\n'
            "    }"
        )
        self.assertFalse(declares_dressing_entry_point(source, self.dressing))

    def test_entry_point_in_a_nested_inner_class_is_false(self):
        source = self._wrap(
            f"    public static class {self.dressing.class_name}\n"
            "    {\n"
            "        public static class Inner\n"
            "        {\n"
            "            public static void Build() { }\n"
            "        }\n"
            "    }"
        )
        self.assertFalse(declares_dressing_entry_point(source, self.dressing))

    def test_declared_in_the_wrong_namespace_is_false(self):
        source = self._wrap(
            f"    public static class {self.dressing.class_name}\n"
            "    {\n"
            "        public static void Build() { }\n"
            "    }",
            namespace="NoSafeCircle.DoorPrototype.Editor.SomeOtherPlace",
        )
        self.assertFalse(declares_dressing_entry_point(source, self.dressing))

    def test_declared_non_public_is_false(self):
        source = self._wrap(
            f"    public static class {self.dressing.class_name}\n"
            "    {\n"
            "        internal static void Build() { }\n"
            "    }"
        )
        self.assertFalse(declares_dressing_entry_point(source, self.dressing))

    def test_declared_with_a_parameter_is_false(self):
        source = self._wrap(
            f"    public static class {self.dressing.class_name}\n"
            "    {\n"
            "        public static void Build(int roomSeed) { }\n"
            "    }"
        )
        self.assertFalse(declares_dressing_entry_point(source, self.dressing))

    def test_declared_extern_with_no_body_is_false(self):
        source = self._wrap(
            f"    public static class {self.dressing.class_name}\n"
            "    {\n"
            "        public static extern void Build();\n"
            "    }"
        )
        self.assertFalse(declares_dressing_entry_point(source, self.dressing))

    # -- required shapes: every one of these must be True ----------------

    def test_block_scoped_namespace_is_true(self):
        source = self._wrap(
            f"    public static class {self.dressing.class_name}\n"
            "    {\n"
            "        public static void Build()\n"
            "        {\n"
            "        }\n"
            "    }"
        )
        self.assertTrue(declares_dressing_entry_point(source, self.dressing))

    def test_file_scoped_namespace_is_true(self):
        source = (
            f"namespace {self.dressing.namespace};\n\n"
            f"public static class {self.dressing.class_name}\n"
            "{\n"
            "    public static void Build()\n"
            "    {\n"
            "    }\n"
            "}\n"
        )
        self.assertTrue(declares_dressing_entry_point(source, self.dressing))

    def test_reversed_modifier_order_is_true(self):
        source = self._wrap(
            f"    static public class {self.dressing.class_name}\n"
            "    {\n"
            "        static public void Build()\n"
            "        {\n"
            "        }\n"
            "    }"
        )
        self.assertTrue(declares_dressing_entry_point(source, self.dressing))


class DressingHasNoGenericAbsorptionAtTheBoundary(unittest.TestCase):
    """Case E: a dressing prefab plus an unrelated DoorPrototype output still
    refuses as ambiguous when driven through run_door_prototype_builder, not
    only through the pure resolver.

    ``test_dressing_prefab_registry.py``'s ``DressingHasNoAbsorptionUnlikeARoom``
    already proves ``resolve_generated_builder`` itself refuses this payload.
    What that file cannot show is WHEN it refuses relative to Unity launching
    -- this proves it is still a pre-launch refusal at the real boundary
    (the same call that, for a single room alone, silently absorbs its own
    generated tile per ``ARoomAbsorbsItsOwnGeneratedOutputs`` in
    test_unity_materialization.py) by using an exploding runner: if dressing
    ever gained the room's absorption behaviour, this would either stop
    raising or would raise only after Unity had already launched.
    """

    def setUp(self):
        test_root = Path.cwd() / ".test-work"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"dressing-absorption-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.records = self.root / "records"
        self.records.mkdir()
        self.git("init", "-q")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        self.git("commit", "--allow-empty", "-q", "-m", "fixture")
        self.unity = self.root / "Unity.exe"
        self.unity.write_bytes(b"fixture")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ("git", "-C", str(self.checkout), *args), capture_output=True, check=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def test_dressing_plus_unassigned_asset_refuses_before_unity_launches(self):
        dressing = _dressing_for("RuinedEntry")
        unrelated = DOOR_PROTOTYPE_ROOT + "Generated/MaterializationGuardTile.asset"

        def exploding_runner(*_args, **_kwargs):
            raise AssertionError(
                "Unity must not launch for a dressing request with no single owner"
            )

        with self.assertRaisesRegex(
            DoorPrototypeMaterializationError, "more than one builder method",
        ) as caught:
            run_door_prototype_builder(
                checkout=self.checkout, task_id="NSC-540",
                state_root=self.records, initial_changed_paths=(),
                unity_executable=self.unity, unity_command_runner=exploding_runner,
                allowed_generated_paths=tuple(sorted(
                    (dressing.prefab_path, unrelated), key=str.casefold)),
            )
        message = str(caught.exception)
        self.assertIn(dressing.build_method, message)


class DressingBuilderSourceNonBlobRefuses(DressingFixtureMixin, unittest.TestCase):
    """builder_source_not_regular / catalog_source_missing for a PRESENT but
    non-ordinary tree entry, not merely an ABSENT one.

    Gap found by the Pipeline Maintainer's mutation of ``_regular_blob`` in
    unity_materialization.py: weakening its check from
    ``fields[1] != "blob" or fields[0] not in {"100644","100755"}`` down to
    just ``len(fields) < 3`` left ``DressingBuilderSourceNotRegularRefuses``
    (above) still green, because that test's defect is an ABSENT companion
    reason (invalid UTF-8 on an otherwise ordinary 100644 blob) -- it never
    exercises the type/mode branch of ``_regular_blob`` at all, since a
    normal 100644 blob has exactly the same 3 ls-tree fields either way.

    A symlink-mode (120000) entry is the case the mutation actually changes:
    its underlying git object genuinely IS a readable blob (confirmed by
    probe: ``git ls-tree`` reports ``120000 blob <sha>``, and
    ``git cat-file blob <sha>`` succeeds and returns the link target text).
    Unmutated, the mode check still refuses it as not-regular. Mutated, the
    weakened length-only check lets it through, the "source" gets decoded as
    the link target text, and the failure moves to a LATER, different
    guard -- ``builder_entry_point_missing`` for the builder side,
    ``catalog_source_invalid`` for the catalog twin -- which is exactly what
    makes the assertions below fail under that mutation instead of merely
    asserting something weaker.
    """

    def test_builder_source_symlink_entry_is_not_regular(self):
        dressing = self._bootstrap("RuinedEntry", "NSC-528")
        self.write_and_stage(dressing.catalog_path, _good_catalog(dressing))
        self.stage_symlink_entry(dressing.builder_source_path, "elsewhere/target.cs")
        original = self.commit("crew dressing candidate (builder is a symlink entry)")
        # Materialize the link-target text as an ordinary working-tree file
        # (core.symlinks=false) so the checkout is genuinely clean -- without
        # this, _require_candidate would refuse earlier on "not the exact
        # clean owned commit" and the guard under test would never run.
        self.git(self.checkout, "checkout", "--", dressing.builder_source_path)
        self.assertEqual("", self.git(self.checkout, "status", "--porcelain=v1"))
        registered = self.register_candidate_at_head(
            changed_paths=(dressing.builder_source_path, dressing.catalog_path),
        )
        self.assertEqual(original, registered)

        def exploding_runner(*_args, **_kwargs):
            raise AssertionError("Unity must not launch when the builder path is a symlink entry")

        with self.assertRaisesRegex(
            MaterializationError,
            f"builder_source_not_regular: {dressing.builder_source_path} at {registered}",
        ):
            materialize_candidate(
                self.manager, "NSC-528", registered, unity_executable=self.unity,
                unity_command_runner=exploding_runner,
                validation_runner=self.passing_validation,
            )

    def test_catalog_source_symlink_entry_is_missing(self):
        """Optional twin named in the report: same non-blob shape, catalog side.

        The builder is fully valid here (correct entry point), isolating the
        failure to the catalog's own existence+regular check.
        """
        dressing = self._bootstrap("RuinedEntry", "NSC-529")
        self.write_and_stage(dressing.builder_source_path, _good_builder_source(dressing))
        self.stage_symlink_entry(dressing.catalog_path, "elsewhere/target.json")
        original = self.commit("crew dressing candidate (catalog is a symlink entry)")
        self.git(self.checkout, "checkout", "--", dressing.catalog_path)
        self.assertEqual("", self.git(self.checkout, "status", "--porcelain=v1"))
        registered = self.register_candidate_at_head(
            changed_paths=(dressing.builder_source_path, dressing.catalog_path),
        )
        self.assertEqual(original, registered)

        def exploding_runner(*_args, **_kwargs):
            raise AssertionError("Unity must not launch when the catalog path is a symlink entry")

        with self.assertRaisesRegex(
            MaterializationError,
            f"catalog_source_missing: {dressing.catalog_path} at {registered}",
        ):
            materialize_candidate(
                self.manager, "NSC-529", registered, unity_executable=self.unity,
                unity_command_runner=exploding_runner,
                validation_runner=self.passing_validation,
            )


class DressingReceiptMustNameTheBuilderRefuses(DressingFixtureMixin, unittest.TestCase):
    """"crew candidate did not change the <builder> builder": the receipt's
    OWN changed_paths list must literally name the resolved dressing
    builder source, even when the checkout content is otherwise entirely
    valid and the builder file really was written.

    Gap found by the Pipeline Maintainer's mutation of ``_require_candidate``
    in unity_materialization.py: replacing
    ``if builder_source not in receipt["changed_paths"]:`` with ``if False:``
    left every existing test in this file, test_unity_materialization.py and
    test_post_crew_workflow.py green, because every existing fixture always
    claims the builder path truthfully in its receipt. Nothing exercised a
    receipt that omits it while the rest of the candidate is valid.
    """

    def test_receipt_omitting_the_builder_source_refuses(self):
        dressing = self._bootstrap("RuinedEntry", "NSC-531")
        self.write_and_stage(dressing.builder_source_path, _good_builder_source(dressing))
        self.write_and_stage(dressing.catalog_path, _good_catalog(dressing))
        self.commit("crew dressing candidate")
        # The checkout genuinely DOES change the builder source above; only
        # the receipt's CLAIM omits it -- which is exactly what this guard
        # reads, per _candidate_receipt never re-diffing changed_paths
        # against real git output (see the module docstring).
        original = self.register_candidate_at_head(changed_paths=(dressing.catalog_path,))

        def exploding_runner(*_args, **_kwargs):
            raise AssertionError(
                "Unity must not launch when the receipt never claims the builder changed"
            )

        with self.assertRaisesRegex(
            MaterializationError,
            f"crew candidate did not change the {dressing.builder_source_path} builder",
        ):
            materialize_candidate(
                self.manager, "NSC-531", original, unity_executable=self.unity,
                unity_command_runner=exploding_runner,
                validation_runner=self.passing_validation,
            )


class DressingBuilderSelectionReadsThePayloadNotTheEnlargedSet(unittest.TestCase):
    """run_door_prototype_builder must resolve the builder from
    builder_payload_paths, never by re-resolving the (possibly enlarged)
    allowed_generated_paths.

    Gap found by the Pipeline Maintainer: making the function ignore
    builder_payload_paths and always resolve from allowed_generated_paths
    went undetected, because every fixture elsewhere in this file is
    file-only (no directory resource), so ``_generated_resource_roots``
    always derives an empty companion set and the two lists happen to be
    identical everywhere they were exercised together.

    This drives run_door_prototype_builder directly with the two lists
    genuinely DIFFERENT: ``allowed_generated_paths`` carries one extra,
    unassigned DoorPrototype-root folder ``.meta`` that
    ``builder_payload_paths`` does not. Unmutated, selection reads the
    narrower payload (the dressing prefab alone), resolves to exactly one
    owner, and the run succeeds. Under the described mutation, resolution
    would instead see both paths -- the extra ``.meta`` falls to the
    default builder as unassigned DoorPrototype output, alongside the
    dressing prefab's own owner -- and refuse as ambiguous before Unity
    ever launches. Asserting the clean success below (one Unity call, the
    dressing method, the admitted prefab output) is what makes this test
    fail outright under that mutation, rather than merely asserting a
    weaker negative.
    """

    def setUp(self):
        test_root = Path.cwd() / ".test-work"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"dressing-payload-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.records = self.root / "records"
        self.records.mkdir()
        self.git("init", "-q")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        self.dressing = _dressing_for("LowerVault")
        for relative, content in (
            (self.dressing.builder_source_path, _good_builder_source(self.dressing)),
            (self.dressing.catalog_path, _good_catalog(self.dressing)),
        ):
            target = self.checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")
        self.unity = self.root / "Unity.exe"
        self.unity.write_bytes(b"fixture")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ("git", "-C", str(self.checkout), *args), capture_output=True, check=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def test_selection_reads_the_narrower_payload_not_the_enlarged_allowed_set(self):
        dressing = self.dressing
        # A realistic "extra" path: a folder .meta elsewhere under the
        # DoorPrototype root that nobody assigned to this request, but which
        # would legitimately be in allowed_generated_paths whenever a task
        # also owns a directory resource.
        extra_unassigned_meta = DOOR_PROTOTYPE_ROOT + "Art/Environment.meta"

        calls: list[tuple] = []

        def payload_runner(args, cwd, timeout):
            calls.append(tuple(args))
            args_list = list(args)
            self.assertIn("-executeMethod", args_list)
            method_index = args_list.index("-executeMethod") + 1
            self.assertEqual(dressing.build_method, args_list[method_index])
            (cwd / dressing.prefab_path).write_text("prefab body\n", newline="\n")
            (cwd / (dressing.prefab_path + ".meta")).write_bytes(GOOD_PREFAB_META)
            return subprocess.CompletedProcess(args, 0, b"", b"")

        result = run_door_prototype_builder(
            checkout=self.checkout, task_id="NSC-541",
            state_root=self.records, initial_changed_paths=(),
            unity_executable=self.unity, unity_command_runner=payload_runner,
            allowed_generated_paths=tuple(sorted(
                (dressing.prefab_path, extra_unassigned_meta), key=str.casefold)),
            builder_payload_paths=(dressing.prefab_path,),
            allowed_generated_asset_metas=(dressing.prefab_path + ".meta",),
        )
        self.assertEqual(1, len(calls), "Unity must launch exactly once")
        self.assertIn(dressing.prefab_path, result.builder_paths)
        self.assertIn(dressing.prefab_path + ".meta", result.builder_paths)


if __name__ == "__main__":
    unittest.main()
