# Exact worker scope enforcement journal

- Base: `74ed502910d4b82e6f2018d3c1c68577d81686a5`
- Branch: `assistant/fix-exact-worker-scope`
- Read-only graph reference: `c9b3b36417df4f52c8a2af868aeed2f5c3e1f399`

## 2026-09-12

- Read repository, AssistantControl, engineering, testing, and Unity-programmer language guidance before editing.
- Confirmed `RepositoryScopeAuthority._ownership_roots()` broadens every exact DoorPrototype resource to the shared `Assets/NoSafeCircle/DoorPrototype/` root.
- Confirmed test plan paths do not currently receive any exclusive-resource ownership check.
- Added failing regression coverage for the NSC-044/NSC-045 room contract shape, common-file and unrelated-test rejection, common-directory collapse, explicit directory ownership, committed-contract authority, malformed resource paths, and rejection without repository or scope-state mutation.
- Failing-before run reached the new assertions and reported three failures (`..FFF....`): broad DoorPrototype/common-directory acceptance and claimed-root trust remained observable before the implementation.
- Replaced inferred ownership roots with exact committed resource authority. A `repo-file:` path that resolves to a committed Git tree remains an explicit directory resource; exact file, `unity-scene:`, and `unity-prefab:` resources grant only that path.
- Reloaded and hash-verified `Tasks/<TASK-ID>.yaml` from the captured checkout HEAD inside `RepositoryScopeAuthority`; caller-supplied `exclusive_resources` and `contract_path` no longer define write authority.
- Applied the ownership check equally to implementation and test paths, filtered unowned test suggestions, and made malformed, noncanonical, case-mismatched, or unsupported path resources fail closed.
- Preserved read-only directory prefixes such as `Assets/` while rejecting trailing-slash write resources as noncanonical.
- Updated focused synthetic admission and production-pipeline fixtures to declare the exact files they edit.
- Passing-after verification:
  - `python -m unittest Pipeline.AssistantControl.test_scope` — 11 passed.
  - Four focused AssistantControl admission/worktree regressions — 4 passed.
  - `python Pipeline/TaskReviewAgent/tests/production_pipeline_smoke_test.py` — 6 passed, including deterministic Unity `.meta` sidecars and failed/rejected no-commit behavior.
- Read-only graph inspection confirmed c9b3b36 changes only TaskGraph policy/evidence/task files. Its parent `eab9bad9` is an ancestor of the requested base; the two base-only AssistantControl commits and this worker-scope fix do not overlap c9b3b36's changed paths.
