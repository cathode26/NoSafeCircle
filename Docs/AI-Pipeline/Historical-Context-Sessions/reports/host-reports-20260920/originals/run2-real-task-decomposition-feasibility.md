# Run 2: decomposing the real game tasks, feasibility report (developer R)

Received 2026-09-13 at about 23:15 UTC and recorded in summary by the coordinating session. No providers and no Docker were used.

## Verdict

**GO** for a proposals-only run of all five tasks: `decompose` for each, with no apply. The run uses combined commit `80a7537befae9cdfbb689bbb526ea7d5c30ead5d`, which is our code at `9dee4a6` plus the game at `886bb81`. It lives in the standalone clone `C:\nscrev\realdecomp-run2-src`, branch `realdecomp/combined-9dee4a6bd308`.

**Now BLOCKED:** Codex hit its usage limit (retry Sep 19, 2026 08:10), and every decomposition needs Codex as the round-2 reviewer.

## Path split

**Taken verbatim from game `886bb81`:**
- `Tasks/`, `Assets/`, `Docs/Art/`
- `Pipeline/TaskGraph/evidence/` and `migrations/`
- `WORK_ID_MAP.json`, `RESOURCE_GROUPS.yaml`, `PROJECT_REQUIREMENTS.yaml`
- `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`

**Identical in both trees:** `Docs/GDD`, `BOOTSTRAP_PERSISTED`, `APPROVED_BOOTSTRAP`, V2 migration.

**Removed:** `Pipeline/TaskGraph/TASKCONTROL_CURRENT.json`, because the game has none.

**Everything else** is our code, verified by diff.

## Rebuilding

Command: `C:\Python313\python.exe C:\nscrev\realdecomp-tools\rebuild_combined.py --code <sha>`. It:
- builds the tree with a temporary index;
- verifies the path split;
- makes a standalone clone (a git worktree cannot be the Source, because its `.git` file points outside the container);
- runs `offline_preflight.py`;
- prints the commands;
- refuses if any decomposition record already exists.

## Offline results on 80a7537, all five tasks

| Task | Context size | Classification | Decompose gate | Preflight |
|---|---|---|---|---|
| NSC-014 | 269 KB | real_task | ok | ok, no templates needed |
| NSC-015 | 256 KB | real_task | ok | ok |
| NSC-025 | 236 KB | real_task | ok | ok |
| NSC-033 | 280 KB | real_task | ok | ok |
| NSC-035 | 205 KB | real_task | ok | ok |

- The graph loads with 84 tasks.
- Running `decompose` without the spend flag refuses first and writes nothing.
- `inspect-decomposition` reaches the record reader.
- Removing TaskControl does not affect `decompose` or `inspect`. Only the controller's conformance view is affected (every task shows `invalid_evidence`), so the controller must not be used.

## Findings

- **Dependencies:** the `decompose` CLI has no dependency gate. The graph controller only offers decompose once a task's dependencies are complete.
- **Partition rule (`policy.py:143`), confirmed:** a hand-made NSC-025 split where two children share the scene builder and the scene is refused. The error: "Child exclusive_resources must exactly partition ... extra=['repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs', 'unity-scene:Assets/Scenes/DoorPrototype.unity']". A split where one child owns both passes. The rule was kept unchanged.
- **What `apply-decomposition` would do (not run):**
  - write child task files starting at NSC-086;
  - turn the parent into an aggregate and bump its revision;
  - rewrite each dependent's `depends_on` and bump its revision;
  - update `WORK_ID_MAP` and `RESOURCE_GROUPS`, and possibly re-pin the policy;
  - make one local commit, with no push.
- **Deliverable to Codex, per task:**
  - the folder `decomposition-runs\<run-id>\`, containing `decomposition_run_result.json`, `decomposition_result.json`, `graph_delta.json` and the per-round artifacts;
  - the record `<TASK>.decomposition.json`.

## Commands

Run each in its own PowerShell terminal. **These spend money.** Start NSC-025 first, then the rest 1-2 minutes apart.

```
Set-Location 'C:\nscrev\realdecomp-run2-src'; & 'C:\Python313\python.exe' -m Pipeline.AssistantControl --source 'C:\nscrev\realdecomp-run2-src' --checkout-root 'C:\nscrev\realdecomp-Checkouts' decompose NSC-025 --run-id run2-nsc-025-80a7537befae --providers claude,codex --compose-project nosafecircle --authorize-provider-spend
```

For the other tasks, change only the task and run id:
- NSC-035 / run2-nsc-035-80a7537befae
- NSC-014 / run2-nsc-014-80a7537befae
- NSC-015 / run2-nsc-015-80a7537befae
- NSC-033 / run2-nsc-033-80a7537befae

## Operating constraints

- **Records:** one record per task per checkout root, so a retry needs a new `--checkout-root`.
- **CLI exit code:** the CLI exits 1 unless the result is `review_ready`. `needs_human` is still a valid, recorded result.
- **Container limit:** 78 minutes each.
- **Concurrency:** nothing in the code prevents five runs at once. They do share the image and the writable `claude-config` and `codex-config` volumes, so stagger the starts. Do not move the Source while runs are active.

## Chaining caveat for Codex

- Every plan numbers its children from NSC-086 against the same graph.
- Applying one plan bumps its dependents' revisions.
- The chain is 025 → 014 → 015 → 033. Once 025 is applied, the 014 proposal no longer matches its parent.
- 035 is independent, but its child numbers need re-planning after any apply.

Suggested order: run 025 and 035 first; run 014, 015 and 033 after their upstream lands on the game's main, or run them now purely as design input.
