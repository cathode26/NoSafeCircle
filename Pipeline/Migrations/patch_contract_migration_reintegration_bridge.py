#!/usr/bin/env python3
"""One-shot patch for carrying verified migrations into later mainline integration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def patch_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"{label}: expected block not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def patch_module() -> None:
    module = ROOT / "Pipeline" / "TaskReviewAgent" / "downstream_resilience.py"
    patch_once(
        module,
        "    WorkflowEventType,\n    WorkflowState,\n",
        "    WorkflowEventType,\n    WorkflowPhase,\n    WorkflowState,\n",
        "WorkflowPhase import",
    )

    helper = '''def _integrated_main_for_migration(
    controller: Any,
    human_commit: str,
    head: str,
) -> str:
    """Resolve the main parent that the clerical migration merged into the task.

    The current origin/main may have advanced after the migration. The receipt must
    therefore prove the historical migration first, then let integrate_current_main
    handle later automation-only progress as a separate transition.
    """

    candidates = _git_text(
        controller.command_runner,
        controller.checkout,
        "rev-list",
        "--merges",
        "--ancestry-path",
        f"{human_commit}..{head}",
        check=False,
    ).splitlines()
    for merge_commit in candidates:
        values = _git_text(
            controller.command_runner,
            controller.checkout,
            "rev-list",
            "--parents",
            "-n",
            "1",
            merge_commit,
            check=False,
        ).split()
        if len(values) != 3:
            continue
        parents = values[1:]
        contains_human = [
            _git(
                controller.command_runner,
                controller.checkout,
                "merge-base",
                "--is-ancestor",
                human_commit,
                parent,
                check=False,
            ).returncode
            == 0
            for parent in parents
        ]
        if contains_human.count(True) != 1:
            continue
        main_parent = parents[contains_human.index(False)]
        if (
            _git(
                controller.command_runner,
                controller.checkout,
                "merge-base",
                "--is-ancestor",
                main_parent,
                head,
                check=False,
            ).returncode
            == 0
        ):
            return main_parent
    raise DownstreamPipelineError(
        "clerical migration head does not contain one unambiguous mainline merge parent"
    )


'''
    patch_once(
        module,
        "def _build_contract_migration_receipt(\n",
        helper + "def _build_contract_migration_receipt(\n",
        "historical integrated main helper",
    )

    old_main = '''    _git(
        controller.command_runner,
        controller.checkout,
        "fetch",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        timeout_seconds=900.0,
    )
    current_main = _git_text(
        controller.command_runner,
        controller.checkout,
        "rev-parse",
        "origin/main",
    )
    if not _SHA40.fullmatch(current_main):
        raise DownstreamPipelineError("origin/main did not resolve to a commit")
    if (
        _git(
            controller.command_runner,
            controller.checkout,
            "merge-base",
            "--is-ancestor",
            current_main,
            head,
            check=False,
        ).returncode
        != 0
    ):
        raise DownstreamPipelineError(
            "origin/main advanced beyond the clerical migration integration"
        )
'''
    new_main = '''    current_main = _integrated_main_for_migration(
        controller,
        human_commit,
        head,
    )
'''
    patch_once(module, old_main, new_main, "historical migration main identity")

    bridge = '''def _prepare_contract_migration_mainline_bridge(
    self: Any,
    state: Mapping[str, Any],
    human: Mapping[str, Any],
    head: str,
) -> dict[str, Any]:
    from .mainline_reintegration import _automation_receipt_for

    existing = _automation_receipt_for(self, head)
    if existing is not None:
        return existing
    carry_forward = _contract_migration_receipt_for(
        self,
        state,
        human,
        head,
    )
    payload = {
        "schema_version": "1.0",
        "task_id": self.task_id,
        "branch": state.get("branch"),
        "prior_task_head": carry_forward["human_tested_commit"],
        "human_tested_commit": carry_forward["human_tested_commit"],
        "main_head": carry_forward["integrated_main_commit"],
        "merge_base": carry_forward["merge_base"],
        "integrated_commit": head,
        "classification": "automation_only",
        "human_revalidation_required": False,
        "main_changed_paths": carry_forward["main_changed_paths"],
        "task_changed_paths": carry_forward["task_changed_paths"],
        "overlap_paths": [],
        "exclusive_overlap_paths": [],
        "non_automation_paths": [],
        "task_blob_changes_after_merge": [],
        "created_at_utc": utc_now(),
        "authority": "verified_contract_migration_mainline_bridge",
        "carry_forward_receipt_sha256": carry_forward["receipt_sha256"],
    }
    bridge_receipt = {
        **payload,
        "receipt_sha256": semantic_sha256(payload),
    }
    self.state["mainline_reintegration"] = bridge_receipt
    self._persist()
    return bridge_receipt


def _patched_integrate_current_main(self: Any) -> dict[str, Any]:
    _observation, state = self._require_lease(
        WorkflowPhase.DELIVERY_EVIDENCE
    )
    head = _git_text(
        self.command_runner,
        self.checkout,
        "rev-parse",
        "HEAD",
    )
    human = self._latest_human_validation()
    if (
        isinstance(human, Mapping)
        and human.get("result") == "pass"
        and human.get("tested_commit") != head
    ):
        _prepare_contract_migration_mainline_bridge(
            self,
            state,
            human,
            head,
        )
    return _ORIGINALS["integrate_current_main"](self)


'''
    patch_once(
        module,
        "def _patched_assert_human_tested_head(\n",
        bridge + "def _patched_assert_human_tested_head(\n",
        "contract migration integration bridge",
    )
    patch_once(
        module,
        '            "human_validation_artifact": controller._human_validation_artifact,\n',
        '            "human_validation_artifact": controller._human_validation_artifact,\n'
        '            "integrate_current_main": controller.integrate_current_main,\n',
        "original integration action",
    )
    patch_once(
        module,
        "    controller.run_authoritative_unity_test = _patched_run_authoritative_unity_test\n",
        "    controller.run_authoritative_unity_test = _patched_run_authoritative_unity_test\n"
        "    controller.integrate_current_main = _patched_integrate_current_main\n",
        "patched integration action",
    )


def patch_test() -> None:
    test = (
        ROOT
        / "Pipeline"
        / "TaskReviewAgent"
        / "tests"
        / "downstream_resilience_smoke_test.py"
    )
    patch_once(
        test,
        "    _build_contract_migration_receipt,\n    validation_plan_for,\n",
        "    _build_contract_migration_receipt,\n"
        "    _prepare_contract_migration_mainline_bridge,\n"
        "    validation_plan_for,\n",
        "bridge test import",
    )
    patch_once(
        test,
        "from Pipeline.TaskReviewAgent.goal_loop_guard import GuardedTaskController  # noqa: E402\n",
        "from Pipeline.TaskReviewAgent.goal_loop_guard import GuardedTaskController  # noqa: E402\n"
        "from Pipeline.TaskReviewAgent.mainline_reintegration import (  # noqa: E402\n"
        "    _automation_receipt_for,\n"
        ")\n",
        "automation receipt test import",
    )

    new_test = '''def test_verified_migration_bridges_later_mainline_integration() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-carry-forward-later-main-") as temporary:
        repo, state, human, human_commit, operational_commit = create_migration_fixture(
            Path(temporary)
        )
        git(repo, "switch", "main")
        later = repo / "Pipeline/TaskReviewAgent/later_automation.py"
        later.write_text("# later automation-only change\\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "Advance automation after migration")
        later_main = git(repo, "rev-parse", "HEAD")
        git(repo, "push", "origin", "main")
        git(repo, "switch", BRANCH)
        git(repo, "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")
        require(
            run(
                "git",
                "-C",
                str(repo),
                "merge-base",
                "--is-ancestor",
                later_main,
                operational_commit,
                cwd=repo,
                check=False,
            ).returncode
            != 0,
            "fixture did not advance main beyond the migration head",
        )

        old_hash = hashlib.sha256(
            subprocess.check_output(
                ["git", "-C", str(repo), "show", f"{human_commit}:{CONTRACT_PATH}"]
            )
        ).hexdigest()
        event = migration_event(
            old_hash=old_hash,
            new_hash=state["task_contract_sha256"],
            human_commit=human_commit,
            operational_commit=operational_commit,
        )
        tested = object.__new__(ResumableDownstreamTaskController)
        tested.task_id = TASK_ID
        tested.checkout = repo
        tested.command_runner = _default_runner
        tested.workflow = FakeWorkflow(FakeService(event))
        tested.state = {}
        tested.last_observation = {
            "task": {
                "task_id": TASK_ID,
                "contract_path": CONTRACT_PATH,
                "task_contract_sha256": state["task_contract_sha256"],
            }
        }
        tested._persist = lambda: None
        tested._latest_human_validation = lambda: human

        bridge = _prepare_contract_migration_mainline_bridge(
            tested,
            state,
            human,
            operational_commit,
        )
        require(
            bridge["human_tested_commit"] == human_commit,
            "bridge changed the original human commit",
        )
        require(
            bridge["main_head"] != later_main,
            "bridge incorrectly treated later main as the historical migration base",
        )
        recognized = _automation_receipt_for(tested, operational_commit)
        require(recognized is not None, "mainline integration did not recognize the bridge")
        require(
            recognized["human_tested_commit"] == human_commit,
            "recognized bridge lost the original PASS identity",
        )


'''
    patch_once(
        test,
        "def test_behavioral_contract_change_is_rejected() -> None:\n",
        new_test + "def test_behavioral_contract_change_is_rejected() -> None:\n",
        "later-main bridge regression",
    )
    patch_once(
        test,
        "        test_verified_contract_migration_carries_original_pass,\n"
        "        test_behavioral_contract_change_is_rejected,\n",
        "        test_verified_contract_migration_carries_original_pass,\n"
        "        test_verified_migration_bridges_later_mainline_integration,\n"
        "        test_behavioral_contract_change_is_rejected,\n",
        "bridge regression registration",
    )


def main() -> int:
    patch_module()
    patch_test()
    print("Contract migration reintegration bridge patch applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
