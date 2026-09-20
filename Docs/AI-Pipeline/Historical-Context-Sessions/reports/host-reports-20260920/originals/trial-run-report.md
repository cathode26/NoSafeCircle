# Disposable 1140 Gauntlet trial — three-role Claude graph management

Run date: 2026-09-13 (UTC). Report author: Claude Opus 5 (1M context), persistent graph lead.
**Verdict: the Gauntlet did NOT fully pass.** 9 of the 12 tasks in scope are complete by
AssistantControl evidence; 3 are blocked (NSC-1143, NSC-1146, NSC-1147). Details below.

## 1. Exact controller and Source identities

| Item | Value |
|---|---|
| Gauntlet Source | `C:\NSC\GauntletFresh1140-20260912-1` |
| Branch | `gauntlet-trial/fresh-e90670d` (unchanged throughout) |
| Source HEAD at trial start | `14776a8f9d3ecc18f4d471974ccda87caf54a84e` |
| Source HEAD at trial end | `273798a94fcdc9c38a946107349bead420aff3ba` |
| Working tree | clean at start and at end (`git status --porcelain` empty both times) |
| Checkout root | `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-5` (verified empty, 0 entries, before start) |
| Viewer | `http://127.0.0.1:8817/` and `/api/state`, pid 8400, `read_only: true`, never restarted |
| Controller implementation | the Source itself; controller ran from the Source directory |

Source provenance was verified independently, not assumed:

- `37899ac` (the abandoned generic three-slot staffing commit) is **absent** —
  `git merge-base --is-ancestor 37899ac HEAD` returned non-zero.
- The four cherry-picked trial commits match their reviewed originals in
  `C:\nscrev\throughput` **by patch-id, exactly**:

| Trial commit | Upstream original | Shared patch-id |
|---|---|---|
| `1d912b0` bounded author correction | `573302b` | `07199459e9aea89ddec28e9fa1162157a63e8b3a` |
| `45e7395` apply corrected review shape | `9521f4e` | `0e8df5bf93776c399b9d2dbbaac011a7ea283081` |
| `28730eed` Source lane held | `bdc9a92` | `24123622247856b79e64002f36bb484c8b7f98fd` |
| `14776a8` tighter corrected-shape binding | `027e787` | `94bc30bb08e57218ca1b739d93f671e678a17b96` |

Focused tests on this exact HEAD: all three sections `exit=0`
(`author_correction_smoke_test: PASS`; `test_decomposition` 14 tests OK in 31.9 s;
`BackgroundJobLoopTests` 28 tests OK in 158.5 s), read from
`C:\Users\VINCEN~1\AppData\Local\Temp\claude\C--NSC\af51bc53-682d-4f43-9610-2f919c37de1b\scratchpad\trial-tests\focused.txt`
before the Sonnet helper was started.

### Controller invocations

| Invocation | Role | PID | Started (UTC) | Released (UTC) | Final status |
|---|---|---|---|---|---|
| `ff4876eda5b64608a0bdc73334ade3d5` | Sonnet delegate-safe setup | 13992 | 00:28:34.911 | 00:29:02.442 | `handoff_required`, `controller_released` |
| `a728e9e7e3074e298f8fee684e120ac1` | Opus normal graph run | 34440 | 00:31:59.730 | 00:55:04.575 | `blocked`, `controller_released` |

Exactly one mutating controller owned the graph at any time. PID 13992 was confirmed exited
before the normal run started; PID 34440 is confirmed exited now. Policy recorded at start:
`capacity 10`, `background_job_limit 4`, `max_actions 240`,
`target_branch gauntlet-trial/fresh-e90670d`, `human_review_tasks ["NSC-042"]`,
`auto_approve_gauntlet true`, `provider_spend_authorized true`,
`policy_sha256 c9f24ce5b68d008ceb5f781266900f8f63864a8d43a4f74d9cd7e55d0ceb1dd1`,
`worker_config_sha256 311230b47f0cb7ff1421734c88860cf7aa5d40f9895b1526cb733511defab9d0`.

## 2. Graph-management roles: model, effort, and what each actually did

| Role | Model / effort as launched | What it actually did |
|---|---|---|
| Lead (Sol-equivalent) | **Claude Opus 5 (1M), xhigh** | Verified every identity (branch, HEAD, clean tree, patch-id provenance, empty root, viewer, Docker, focused tests) before any provider work. Wrote the two helper prompts. Verified the Sonnet handoff from the durable records rather than from its report. Launched and supervised the normal `run-graph` loop. Diagnosed both blockers to root cause. Sole mutation authority; made no code change. |
| Setup (Luna-equivalent) | **Claude Sonnet 5, medium** | Ran `graph-plan` once (exit 0, `status: actionable`) and the identical selection once through `run-graph --delegate-safe` (exit 0, `status: handoff_required`, `handoff_action {kind: decompose, task_id: NSC-1140}`, `allowed_actions [prepare, refresh_prepared, scope]`). Prepared and scoped NSC-1141..NSC-1144, created their `assistant/NSC-114x` branches, then stopped. Launched no provider, touched no Docker, and released the controller. |
| Observer (Spark-equivalent) | **Claude Haiku 4.5, medium** | Two read-only passes over `graph-controller.json`, the owner record, the journal, per-task records, decomposition records, job directories and logs. Reported transitions, worker PIDs, job timings, the `source_lane_held` evidence, and independently confirmed that every repeated `post_crew` followed a `sync_candidate`. Mutated nothing and repaired nothing. |

The implementation crews are separate from these three roles, as required: every crew was
`provider: claude`, `execution_model: claude-haiku-4-5-20251001`, `crew_profile: lean`,
`validation_profile: targeted`, from
`C:\NSC\GauntletFresh1140-20260912-1\Pipeline\AssistantControl\worker-haiku.example.json`.
Decomposition used the configured two-provider path, `providers: ["claude", "codex"]`.

## 3. Tasks, worker run IDs, candidates and integration commits

Every crew ran on Claude Haiku 4.5 (`claude-haiku-4-5-20251001`). No provider or model
fallback occurred anywhere in the run.

| Task | Final status | Worker run ID | Integrated commit |
|---|---|---|---|
| NSC-1140 | complete (decomposed) | — (parent, decomposed) | apply commit `ecf973cbdcd082b8cf9ebd981d34c1a48bd2a612` |
| NSC-1141 | integrated | `assistant-nsc-1141-0881b12bf2dc` | `7c94b74d4d418b3cc1e07bbf6bf56f371d177e73` |
| NSC-1142 | integrated | `assistant-nsc-1142-a3a9cff9d2ed` | `df1e9b5b0e38b16e77298997b286798e2cbbc345` |
| NSC-1143 | **validation_failed (blocked)** | `assistant-nsc-1143-d5979f862ff6` | none; candidate `8ee55cc72e9bbf3ef1b197f0a22bd7c2db9fdd4b` retained |
| NSC-1144 | integrated | `assistant-nsc-1144-67e9e6fc55e9` | `ccc1889e0bb8d9d5967512077761951615792ea2` |
| NSC-1145 | complete (decomposed) | — (parent, decomposed) | apply commit `1289283a58a96bbc38d606300c7197635c8484ed` |
| NSC-1146 | **background_job_failed (blocked)** | none (decompose failed before any crew) | none |
| NSC-1147 | **blocked on dependencies `[NSC-1146]`** | none | none |
| NSC-1148 (generated) | integrated | `assistant-nsc-1148-437de81cae7b` | `c85181be5e204b97f600217f14345a9439d5d025` |
| NSC-1149 (generated) | integrated | `assistant-nsc-1149-480ddc740f14` | `d7ea3865ae5307d8835613c85dc7127a4753bedd` |
| NSC-1150 (generated) | integrated | `assistant-nsc-1150-2b7582b3de8f` | `461e9d1ab806ab4bfb2fc486c1930bf0931d7026` |
| NSC-1151 (generated) | integrated | `assistant-nsc-1151-b760fb9828da` | `273798a94fcdc9c38a946107349bead420aff3ba` |

`complete` per the controller's own final plan:
`['NSC-1140','NSC-1141','NSC-1142','NSC-1144','NSC-1145','NSC-1148','NSC-1149','NSC-1150','NSC-1151']`
— 9 of 12. Totals: 107 completed actions, 25 harvested background jobs, 7 integrations,
9 auto-approvals, 14 candidate synchronizations, 8 crew runs.

All nine approvals were recorded as `authority: assistant_gauntlet_automation` with the
message "Automated Gauntlet approval after exact focused validation." and
`validation_count: 1`. No approval imitated Vincent's human decision, and NSC-042 was never
touched.

## 4. Decomposition rounds and generated children

| Parent | Job ID (prefix) | Started | Completed | Result | Children | Apply commit |
|---|---|---|---|---|---|---|
| NSC-1140 | `65787382637f5055` | 00:32:12.677 | 00:36:51.634 | `review_ready`, exit 0 | **NSC-1148, NSC-1149** | `ecf973cbdcd082b8cf9ebd981d34c1a48bd2a612` at 00:37:05 |
| NSC-1145 | `cc8c696fad81da25` | 00:42:56.911 | 00:46:36.427 | `review_ready`, exit 0 | **NSC-1150, NSC-1151** | `1289283a58a96bbc38d606300c7197635c8484ed` at 00:46:52 |
| NSC-1146 | `f709910da17673de` | 00:54:40.751 | 00:54:48.407 | **failed** (audit) | none | none |

Run IDs `assistant-nsc-1140-decompose-14776a8f9d3e` and
`assistant-nsc-1145-decompose-7c94b74d4d41`. Containers
`nsc-decompose-65787382637f50554ee690b6` and `nsc-decompose-cc8c696fad81da25a77c3371`, each
carrying both ownership labels (`com.nosafecircle.assistant.job`,
`com.nosafecircle.assistant.checkout=61fdd76f6fd148a39ff17d86a66f5a8b5520048b774f25ae4f8e906daf4aa4bd`).

**Author correction: not exercised live.** Both proposals passed deterministic validation on
their first attempt, so the new bounded author-correction round never fired. Neither
decomposition record nor either job log contains any `correction` entry, and both receipts
read `status: succeeded` / `review_ready`. The corrected-shape path (`1d912b0`, `45e7395`,
`14776a8`) is therefore proven for this trial only by the focused tests, not by live
provider behaviour. That gap should be stated plainly rather than credited to the run.

**Source-lane hold: exercised three times, correctly.** All three holds were `integrate`
actions blocked by NSC-1145's in-flight proposal, and all three tasks integrated afterwards:

| At (UTC) | Held action | Held task | Reason | Blocking task |
|---|---|---|---|---|
| 00:44:17.743 | `integrate` | NSC-1144 | `decomposition_proposal_in_flight` | NSC-1145 |
| 00:45:33.372 | `integrate` | NSC-1148 | `decomposition_proposal_in_flight` | NSC-1145 |
| 00:45:35.397 | `integrate` | NSC-1149 | `decomposition_proposal_in_flight` | NSC-1145 |

At most one decomposition was ever in flight: NSC-1140's job completed 00:36:51 before
NSC-1145's launched 00:42:38, which completed before NSC-1146's launched 00:54:40. Meanwhile
crews, settlements, post-crew jobs and candidate syncs continued during the holds — the
independent-work property held.

## 5. Elapsed time by phase

Normal run wall clock: **23 min 04.8 s** (00:31:59.730 → 00:55:04.575). Delegate-safe setup:
**27.5 s** (00:28:34.911 → 00:29:02.442). Aggregated from the journal's `duration_seconds`:

| Action | Count | Total seconds | First | Last |
|---|---:|---:|---|---|
| `wait_job` | 18 | 869.8 | 00:32:37 | 00:54:48 |
| `sync_candidate` | 14 | 154.4 | 00:37:42 | 00:53:28 |
| `integrate` | 7 | 60.7 | 00:39:04 | 00:54:34 |
| `reserve` | 8 | 45.9 | 00:32:04 | 00:47:21 |
| `post_crew` (launches) | 22 | 37.1 | 00:34:59 | 00:54:25 |
| `auto_approve` | 9 | 33.4 | 00:39:00 | 00:54:28 |
| `prepare` | 8 | 32.9 | 00:28:37 | 00:47:07 |
| `scope` | 8 | 17.5 | 00:28:41 | 00:47:09 |
| `apply_decomposition` | 2 | 16.7 | 00:36:53 | 00:46:52 |
| `settle_worker` | 8 | 13.9 | 00:34:56 | 00:49:53 |
| `start_worker` | 8 | 5.0 | 00:32:09 | 00:47:23 |
| `decompose` (launches) | 3 | 2.5 | 00:32:02 | 00:55:04 |

Phase landmarks: first dispatch 00:32:02 (3 s after controller start); four crews running by
00:32:37; first decomposition applied 00:37:05; first integration 00:39:13; second
decomposition applied 00:46:52; last integration 00:54:34; stop 00:55:04.
`sync_candidate` at 154 s across 14 actions is the largest avoidable cost: every integration
invalidates the other in-flight candidates, so each must re-merge and re-validate. It
converges, but it is quadratic in the number of concurrently ready candidates.

## 6. Blocked tasks, with exact evidence paths

### NSC-1143 — transient Unity licensing failure, not a code defect

Record: `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-5\.assistant-control\NSC-1143.json`
(`status: validation_failed`, `candidate_validation_failure.failed_at`
`2026-09-13T00:35:52.380601+00:00`, `validation_error` first line
`candidate EditMode Unity test failed (20)`).
Job: `...\.assistant-control\background-jobs\NSC-1143\1e13888c6880fed8...` (`result_status: validation_failed`).
Unity log: `C:\Users\VincentLiguori\AppData\Local\Temp\NoSafeCircle-UnityTests-16c2901ae8694cc2a14bc1bceb56b254\unity.log`.

The crew itself **succeeded** (`worker.status: succeeded`, `crew_status: review_ready`,
`returncode 0`, crew run `nsc-1143-20260913t003254z`, candidate
`8ee55cc72e9bbf3ef1b197f0a22bd7c2db9fdd4b`). Unity then failed to start at all. The log ends:

```
[Licensing::Module] Error: Access token is unavailable; failed to update
[Licensing::Client] Error: Code 404 while processing request (status: Found 0 entitlement groups and 0 free entitlements matching requested entitlement ids)
[Licensing::Module] Error: 'com.unity.editor.headless' was not found.
No valid Unity Editor license found. Please activate your license.
Exiting without the bug reporter. Application will terminate with return code 1
```

No `test-results.xml` was produced, because no test ever ran. This is environmental and
one-off: of **439** preserved `NoSafeCircle-UnityTests-*` runs on this host, exactly **one**
— this task's — hit the licensing error, and four other Unity validations succeeded within
the same three minutes. The controller recorded it fail-closed and correctly did not retry;
`post_crew` never calls `revise` itself. NSC-1143 is a leaf, so nothing downstream was
affected. The documented remedy is `revise`, which is outside the command set authorized for
this run, so I left the candidate and its evidence intact rather than improvising.

### NSC-1146 — stale pinned decomposition template (a Gauntlet fixture defect)

Record: `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-5\.assistant-control\NSC-1146.background-job.json`.
Run root: `...\.assistant-control\background-jobs\NSC-1146\f709910da17673de3347007a15a3e21b528bc8ea5a58ae9cda3da7aefb538eea`.
Exact error:

```
ValidationPolicyAuditError: decomposition template for NSC-1146 is stale: it names parent
contract '555810312bd6f5dd094dd3ca6e0ddba6a74a230d6329ba6b94d6cd8df113468f'; the committed
contract is '529eeffa5377db6da2c6bcfb30942e9d2fb93e220c2067b61f61c40d90c4e38f'
```

Root cause, established from committed history rather than inferred:

1. `Pipeline/TaskReviewAgent/authoritative_validation_policy.json` pins, under key
   `"NSC-1146"`, `"parent_task_contract_sha256": "555810312bd6f5dd..."`.
2. NSC-1146's own contract says it must "Rewrite NSC-1147's dependency on this parent to the
   generated concrete children" — NSC-1146 is itself decomposable, and it depends on NSC-1145,
   which is also decomposable.
3. Applying NSC-1145's decomposition (commit `1289283a58a96bbc38d606300c7197635c8484ed`,
   "taskgraph: apply NSC-1145 decomposition GDP-e2e274359e21…") rewrote `Tasks/NSC-1146.yaml`,
   bumping `contract_revision` 1 → 2 (4027 → 4043 bytes) — `git log -- Tasks/NSC-1146.yaml`
   shows exactly two commits: the gauntlet generator `bdaaa2d` and this apply commit.
4. NSC-1146's committed contract hash therefore became `529eeffa5377…`, the pinned value no
   longer matched, and the audit refused to apply a stale template. Nothing was mutated.

**This is a defect in the disposable Gauntlet's fixture data, not in the AssistantControl
controller.** The fresh-gauntlet generator pins each decomposable parent's contract hash, but
applying an *upstream* parent's decomposition necessarily bumps a *downstream* decomposable
parent's `contract_revision`. Any gauntlet with a chain of two decomposable parents where the
later depends on the earlier will hit this. NSC-1140 and NSC-1145 were unaffected because
nothing decomposable sat upstream of either. The controller's audit behaved exactly as
designed by failing closed.

**No bounded recovery exists within my authority.** The audit is deterministic over committed
state, so `clear-background-job` plus a fresh `run-graph` would reproduce the identical
failure — a loop, not recovery. The only real fix is re-pinning the hash in
`authoritative_validation_policy.json`, which would be a code/data change after the trial
began and would amount to editing fixtures to manufacture a pass. I did neither.

### NSC-1147 — blocked on dependencies

Blocked with `reason: dependencies`, `dependencies: ['NSC-1146']`. It never reached a crew.
Once NSC-1146 blocked, nothing eligible remained anywhere in the graph.

### The stop was correct, not premature

An independent read-only `graph-plan` after the run returned `status: blocked`,
`next_actions: []`, `held: []`, `waiting_human: []`, with the same 9 complete and the same 3
blocked. No eligible independent work was abandoned.

## 7. Clean shutdown verified

- Controller released itself at 00:55:04.575 (`outcome: returned`); PID 34440 exited. No
  `stop-graph` was needed.
- The failed NSC-1146 decompose job's container cleanup is recorded
  `provider_container_cleanup.status: verified_absent`, generation 1, with 23 consecutive
  absent observations across a 15.4 s window, `verified_at_utc 2026-09-13T00:55:04.039836`.
  No cleanup is pending anywhere, so `stop-background-jobs` was not needed and was not run.
- All 25 job run directories contain a `receipt.json`; no receipt-less dead job exists.
- No `nsc-decompose-*` or `assistant-crew-*` container remains. Source is clean.
- Runner transcript: `C:\nscrev\reports\trial-runner\transcript-20260912-193158.log`
  (`[DONE] Operator loop ended with status: blocked`); its stderr log and the
  `run-graph-20260912-193159.stderr.log` are both **empty**. Exactly one `run-graph`
  invocation was needed — the runner's continue-statuses never triggered.
- Operator log: `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-5\operator-logs\run-graph-20260912-193159.json`
  (note: written UTF-16LE by PowerShell redirection, which trips a naive UTF-8 read).

## 8. Viewer: real transitions, and one projection gap

Viewer at 01:01:01Z reports `read_only: true`, `state_root` the -5 root, `source_commit`
`273798a94fcdc9c38a946107349bead420aff3ba`, `task_total: 12`, `hidden_count: 92`,
`generated: ['NSC-1148','NSC-1149','NSC-1150','NSC-1151']`, and
`state_counts: {local_accepted: 9, blocked: 1, ready: 2}`. The four allocator-generated
children joined the visible graph automatically and the 92 unrelated contracts stayed hidden.

**Projection gap worth fixing upstream:** the viewer shows NSC-1146 and NSC-1147 as `ready`,
while the controller's durable plan has NSC-1146 `background_job_failed` and NSC-1147
dependency-blocked. NSC-1146 has no task record — its failure lives only in
`NSC-1146.background-job.json` — so the viewer projects node state from the committed
contract and shows it as available work. NSC-1143 shows `blocked` correctly because it does
have a task record. This is a concrete instance of why a viewer colour is not evidence: the
viewer's `ready` here is wrong, and the controller's `blocked` is right. No conclusion in
this report rests on a viewer colour.

## 9. Did the three-role procedure reduce the lead's work?

**Modestly, and less than the setup role's cost suggests.** Honest accounting:

- The **Sonnet setup helper** did not reduce my work. Its whole job took 27.5 s of wall clock
  and two commands, and the authority boundary was enforced by `--delegate-safe` in the CLI,
  not by the helper's judgement. I still had to write a long exact-value prompt, then re-verify
  its entire handoff from the durable records (owner status, controller status, per-task
  statuses, lock state, Source identity) because a helper's self-report is not evidence. The
  verification cost roughly matched the delegation saving. Its real value is structural, not
  economic: it demonstrates that a cheaper agent can perform portable setup without ever
  holding graph authority, and that the delegate-safe boundary stops it at exactly the right
  action (`decompose NSC-1140`).
- The **Haiku observer** did reduce my work, genuinely. Its second pass independently
  cross-checked the `source_lane_held` events, confirmed no two decompositions overlapped, and
  established that every repeated `post_crew` followed a `sync_candidate` rather than being a
  loop — the one question I most wanted checked, answered without me re-reading 25 job
  directories. It also correctly escalated rather than repaired: it flagged NSC-1145/1146/1147
  having no records, which I then resolved as by-design dependency chaining. Its one weakness
  is staleness — it reported one `source_lane_held` event when three eventually existed, and
  reported NSC-1144/NSC-1148 as "approved" moments before they integrated. An observer's
  snapshot must be read as of its timestamp, never as final state.
- The **decisive diagnostic work was not delegable**: reading the Unity log to overturn the
  "crew wrote bad code" reading of NSC-1143, and tracing NSC-1146's staleness through
  `authoritative_validation_policy.json` and `git log -- Tasks/NSC-1146.yaml`. Both required
  forming and testing a hypothesis against committed history, and both changed the report's
  conclusions.

Net: the observer earns its place; the setup helper earns its place as an authority-boundary
demonstration rather than as a labour saving. Neither helper was given, or took, any
mutation authority.

## 10. Code changes made after the trial began

**None.** The Source tree was clean at start and is clean now, and every commit between
`14776a8` and `273798a` was machine-generated by AssistantControl itself (two
`taskgraph: apply … decomposition` commits, the `Implement NSC-…` crew candidates, and the
`assistant-sync/…` merge commits from `sync_candidate`). I edited no repository file, no task
contract, no durable record, and no fixture. Files I created live outside the repository:
this report, and two read-only helper scripts in my scratchpad
(`digest.py`, `report_data.py`).

## 11. Unrelated activity on the host, deliberately left alone

Two containers on this host were not part of the trial and were not touched:

- `nosafecircle-codex-exec-run-96803aacce8e` — Vincent's interactive login-shell container.
- `nosafecircle-round-robin-decompose-run-8b7dc9d06217` — created 00:27:54.889Z, before my
  helper ran any command. Command:
  `run_round_robin_decomposition.py --task-id NSC-025 --providers claude,codex --max-calls 2
  --run-id assistant-nsc-025-decompose-eab9bad9325a`. It binds
  `C:\NSC\NSC\NoSafeCircle` **read-only** and writes to
  `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\decomposition-runs`. It carries
  no `com.nosafecircle.assistant.job`/`.checkout` labels, so it did not come from the trial's
  ticketed path.

I confirmed it could never collide with my controller's identity: this controller names its
containers explicitly as `nsc-decompose-<job-id[:24]>`
(`Pipeline/AssistantControl/background_jobs.py:210`, applied at
`Pipeline/AssistantControl/decomposition.py:407`), whereas that container carries a
Compose-generated one-off name. My cleanup path could never inspect or remove it, and did
not. I touched no real-game checkout and nothing under `C:\NSC\NSC\NoSafeCircle`.

## 12. What would be needed to finish the Gauntlet

1. **NSC-1143**: re-validate the retained candidate `8ee55cc…` now that Unity licensing is
   healthy, or `revise` it. The blocker was infrastructure, so this will most likely clear.
2. **NSC-1146**: fix the Gauntlet fixture so a decomposable parent's pinned
   `parent_task_contract_sha256` is not invalidated by an upstream parent's
   `apply_decomposition` — either re-pin after each apply, or stop pinning the parent contract
   hash for parents that have decomposable ancestors. This is a fixture/generator change and
   belongs to the throughput lane, not to a live Gauntlet run.
3. **NSC-1147** needs nothing of its own; it unblocks when NSC-1146 does.

No push, publication, or GitHub mutation was performed, and nothing was posted to Issue #36.
