# AssistantControl background-throughput integration journal

Date: 2026-09-12

## Integration identity

- Canonical repository: `C:\NSC\NSC\NoSafeCircle`
- Isolated worktree: `C:\NSC\NoSafeCircle-AssistantControl-SpeedIntegration`
- Branch: `assistant/integrate-background-throughput`
- Exact base and commit parent: `eab9bad9325a3e28894a64b6bbde92ee58e75476`
- Upstream repository: `C:\nscrev\throughput`
- Upstream pre-stack parent: `b1a325b1c598bae7b2b18077078b04c75a4c9c28`
- Upstream endpoint: `e90670da5b5fc19567e1efe1cb655c43de292f4e`
- Integration shape: one local commit; no push or merge performed

## Included provenance

The following contiguous upstream commits were semantically applied in order and
folded into one integration commit:

1. `6f32664108b4578c0d0580f1275fba5f4e58cf19`
2. `c70a2d937633eb7fb4e1554cc24f9083ecda8dcb`
3. `24273b6127a9f999b4dbce57cf1c56960d1c9d8f`
4. `0c42f0d94880cb008640795db96ccb9ba4e505e1`
5. `67614e7d7d407196ee8b2984ee418bd94d3ac578`
6. `14cd051bb95eb6203e5cb56113741b22216c37de`
7. `62245a1d9bc0c2c34196f8641cf03aa84a0402fd`
8. `91a0b0dfd9ad605d39e565b014ea95c099e8d42b`
9. `ca56dc7f075f1b2fa064b34751cb9878787bc849`
10. `e90670da5b5fc19567e1efe1cb655c43de292f4e`

One additional semantic extraction was authorized from
`6e5f9cfd1f1fb616d2f1542eafb098f75584ee69`: only
`parse_committed_task_bytes()` and the refactor of `load_committed_task()` to
call it. The helper validates the task ID, decodes UTF-8-sig JSON, requires a
mapping with the exact ID, validates `exclusive_resources` as a list of
non-empty strings, hashes the exact raw bytes, enforces an optional expected
SHA-256, and returns the contract with `task_contract_sha256`. No other file or
behavior from `6e5f9cf` was included.

## Explicit exclusions

- `37899ac36423a0049df8232b3d9ca2e200d12630` persistent three-worker staffing
  slots.
- Trial decomposition commits `573302bcbf02597ee5fd3db3729c9ed5d2b72e8a`,
  `9521f4e0e90c338e1d277879c23845ffec8bd51b`,
  `bdc9a9236db4690cbc13506a0f2824a089a498f1`, and
  `027e7879715633119cfc1b65179882d91843a361`.
- All speculative D1, D2a, D2b, D3, D4, and D5 optimization designs.
- No repository task, asset, scene, contract, graph-state, run-state, or provider
  state artifact was imported or modified.
- Every other file and behavior from `6e5f9cf`.

Static review found no `STAFFING_SCHEMA`, `worker_slots`, `staffing_width`,
`staffing_slot_*`, `--worker-slots`, persistent slot state, or staffing viewer
projection. The existing admission-capacity action ordering remains, but no
generic persistent worker slots or additional graph controllers were added.

## Conflict and semantic resolution

`c70a2d9` conflicted in
`Pipeline/TaskReviewAgent/committed_tasks.py` because its branch already carried
the parser extraction while `eab9bad` retained inline parsing. The resolution:

- preserved current main's `load_committed_task()` subprocess behavior;
- added only the authorized byte-parser extraction;
- refactored the single loader to call that parser without changing validation
  or hash behavior;
- retained `c70a2d9`'s batch loader and its parity/fail-closed tests;
- did not import the unrelated `CREATE_NO_WINDOW` change on the existing single
  loader or any other `6e5f9cf` behavior.

All later selected commits applied without conflicts. Git's three-way application
preserved newer main behavior. The new `background_jobs.py` and
`test_background_jobs.py` blobs match `e90670d` exactly; the remaining differences
from `e90670d` are newer main behavior plus the authorized conflict resolution.

## Review and tests

The complete diff from `eab9bad` was reviewed. Before this journal it contained
13 expected files, 7,210 insertions, and 159 deletions. No task, asset, scene,
contract, TaskGraph, ExecutionCrew, AgentRuntime, or provider file changed.

Focused command executed:

```powershell
python -m unittest Pipeline.AssistantControl.test_background_jobs Pipeline.AssistantControl.test_graph_controller Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_decomposition_transport Pipeline.AssistantControl.test_cli_worker Pipeline.AssistantControl.test_worker_control Pipeline.AssistantControl.test_admission Pipeline.AssistantControl.test_admission_worktree
```

- Initial sandboxed run: environment failure before test behavior. It reported
  121 tests in 0.477 seconds with 225 setup/cleanup errors, all `WinError 5`
  permission failures while creating nested temporary repositories. No assertion
  failure was reported. Artifacts remain under
  `.test-work\speed-integration\temp`.
- Authorized rerun outside the filesystem sandbox, with `TEMP` and `TMP` rooted
  at `.test-work\speed-integration-escalated\temp`: 121 tests passed in
  656.908 seconds, `OK`.
- `python Pipeline\TaskReviewAgent\tests\git_identity_guard_smoke_test.py`:
  `PASS`.
- `git diff --check eab9bad9325a3e28894a64b6bbde92ee58e75476 HEAD`:
  passed with no output before and after the journal was staged.

Tests used disposable Git repositories, fixture workers, and local Windows child
processes. No provider, Docker, or Unity process was launched. Full repository CI
was intentionally not run.

## Residuals

- The focused tests prove the fixture and local process lifecycle paths; they do
  not constitute a live provider, Docker, or Unity demonstration.
- The failed sandbox-run artifacts are retained inside this isolated worktree and
  can emit access warnings during an unprivileged recursive status scan. A
  privileged post-test scan found no tracked or untracked repository changes.
- No product test failure was observed, so no untouched-base reproduction was
  necessary.

## Proposed merge command

After Codex review and only when the canonical checkout is still clean on exact
base `eab9bad9325a3e28894a64b6bbde92ee58e75476`, the proposed merge command is:

```powershell
git -C C:\NSC\NSC\NoSafeCircle merge --ff-only assistant/integrate-background-throughput
```

This command has not been run.
