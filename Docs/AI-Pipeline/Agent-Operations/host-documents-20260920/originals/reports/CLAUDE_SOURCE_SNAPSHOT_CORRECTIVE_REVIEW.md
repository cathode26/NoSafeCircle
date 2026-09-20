# Corrective review: source-admission snapshot

Review target: `C:\NSC\ClaudeAdmissionSnapshot-20260905\NoSafeCircle`

The current worktree is not ready to integrate. Preserve the existing work, but correct and prove the following before committing:

1. `Pipeline/TaskReviewAgent/polling_orchestrator.py::build_poll_dispatch_plan` still calls `list_committed_task_ids(root)` and constructs two loaders that call `load_committed_task(root, task_id)`. This is the production polling path behind the measured task-count-times-plan cost. Build one `SourceCommitAdmissionSnapshot` immediately after observing `source_commit`; use `snapshot.task_ids`, `snapshot.task_loader()`, and pass the same snapshot to `_LazyTaskcontrolStateProvider`.
2. `PollingOrchestrator._load_candidate` still uses the default `self.task_loader`, which remains a per-task `load_committed_task` call. In the production/default composition, load the admitted contract from the exact plan commit's snapshot. Preserve injected `task_loader` behavior for deterministic tests and compatibility. Revalidate the selected task-contract hash and observe HEAD once after each full portfolio or selected-pair rebuild.
3. Add a non-vacuous production-path regression around the real `build_poll_dispatch_plan`. With 100 committed contracts and repeated planning at one unchanged HEAD, prove contract Git work is bounded and that no per-contract `git show` calls occur. Existing unit coverage of `source_commit_admission_snapshot()` and tests using an injected counting loader do not prove the live production planner uses the snapshot.
4. `source_commit_snapshot.py` currently uses `_TASK_ID = re.compile(r"^NSC-\d{3,}$")`. This reopens the unbounded/Unicode task-ID gap fixed on the starting commit. Use the repository's canonical bounded ASCII task-ID rule (`NSC-000` through `NSC-999`, or non-zero four through nine digits) or validate extracted IDs through the canonical contract. Add aliases such as `NSC-0000`, Unicode digits, and ten-digit IDs to the rejection test.
5. Re-run the focused snapshot/polling tests and the promised production-compatible command-count test. Record red-before evidence against exact base semantics and report the actual `show`, `ls-tree`, `cat-file`, and `rev-parse` counts.

Do not push, touch GitHub, or run a live task. Commit locally only after these corrections and the original task's full gates pass.
