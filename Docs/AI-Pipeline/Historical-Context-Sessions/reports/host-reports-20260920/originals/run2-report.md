# Second disposable Gauntlet run (NSC-1160..NSC-1167) — three-role Claude graph management

Run date 2026-09-13 (UTC). Author: Claude Opus 5 (1M context), persistent graph lead.

**Verdict: the Gauntlet did NOT fully pass.** 12 of the 14 tasks in scope are complete by
AssistantControl evidence. NSC-1164 and NSC-1167 are blocked, for two different reasons,
neither of which is a crew or candidate defect: a Unity licensing failure on a re-validation,
and a stale pinned validation policy caused by a decomposition legitimately rewriting a
dependent's contract. Details in sections 6 and 9.

## 1. Exact controller and Source identities

| Item | Value |
|---|---|
| Gauntlet Source | `C:\NSC\GauntletFresh1140-20260912-1` |
| Branch | `gauntlet-replay/fresh-1160-20260913` (unchanged throughout) |
| Source HEAD at start | `799907e03959626323f74e2662378931e734234a` |
| Source HEAD at end | `62b2af516cdb849942023879e039c3355c6c40c8` (37 commits after base) |
| Working tree | clean at start and at end (`git status --porcelain` empty both times) |
| Checkout root | `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-6` (verified 0 entries before start) |
| Records | `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-6\.assistant-control` |
| Viewer | `http://127.0.0.1:8817/` and `/api/state`, pid 12628, instance `ab9d9e121e9f4f27a23ca7824cf2c9a2`, never restarted |
| Worker config | `C:\NSC\GauntletFresh1140-20260912-1\Pipeline\AssistantControl\worker-haiku.example.json`, sha256 `311230b47f0cb7ff1421734c88860cf7aa5d40f9895b1526cb733511defab9d0` (identical to run 1) |
| Policy sha256 | `9be6bdd50e7c84bccfd75e6841109723d06b892f3fcabcaf8402d17421bd728a` |

Source provenance verified before any provider work:

- `git diff --stat 14776a8 799907e -- Pipeline` names exactly two files,
  `Pipeline/TaskGraph/WORK_ID_MAP.json` (+8) and
  `Pipeline/TaskReviewAgent/authoritative_validation_policy.json` (+152). The whole-tree diff
  adds only `Tasks/NSC-116x.yaml`, eleven EditMode fixtures and their `.meta` files: 32 files,
  964 insertions, 0 deletions. Every controller, decomposition and validation source file is
  byte-identical to run 1's tested head `14776a8`.
- `14776a8` is an ancestor of HEAD; `37899ac` is absent (not a valid object in this clone).
- **Provenance nuance:** `e90670d` exists here only on `remotes/throughput/background-decomposition`
  and is *not* an ancestor of HEAD (`git merge-base e90670d HEAD` = `73e0f06`, trees differ).
  The reviewed lineage rests on `3e5314d`/`2f0d398`, with run 1's report establishing the four
  decomposition-trial commits as patch-id-identical to their upstream originals. The invariant
  that matters — identical controller code to run 1's tested head — holds.
- Family shape confirmed from the contracts: NSC-1160/1165/1166 `needs_execution_decomposition`;
  NSC-1161..1164 `single_agent`, no dependencies; NSC-1165 and NSC-1166 both depend on NSC-1161;
  NSC-1167 depends on NSC-1166. The pristine NSC-1140..1147 contracts were never selected.
- No `nsc-decompose-*` or `assistant-crew-*` containers existed before the run; credential volume
  `nosafecircle_claude-config` present. The unrelated `nosafecircle-codex-exec-run-96803aacce8e`
  was left alone throughout.

### Controller invocations (7 total, journal-derived, exactly one alive at any time)

| # | Invocation id | Window (UTC) | Active | Events | Runner |
|---|---|---|---:|---:|---|
| 1 | `dce6aae6d73a4319811d4326600c99d5` (pid 40848) | 02:34:20.927 → 02:37:57.236 | 216.3 s | 57 | v5, PID 37292 |
| 2 | `009ce91c41d34cd9b095e60399db494f` (pid 26980) | 02:46:50.910 → 02:50:47.444 | 236.5 s | 81 | v6 RUN 1, PID 40320 |
| 3 | `6e7a8fa5e91c…` | 02:51:13.278 → 02:51:32.901 | 19.6 s | 14 | v6 RUN 2 |
| 4 | `712bc2350b53…` | 02:51:58.636 → 02:59:41.166 | 462.5 s | 127 | v6 RUN 3 |
| 5 | `ecd9047fa9ed…` | 03:00:08.100 → 03:05:32.624 | 324.5 s | 88 | v6 RUN 4 |
| 6 | `c1d43a3956fc…` | 03:05:59.174 → 03:12:16.493 | 377.3 s | 69 | v6 RUN 5 |
| 7 | `1aea3725eb064f219c7c838b47e66cd1` (pid 14880) | 03:15:17.142 → 03:19:52.768 | 275.6 s | 40 | v7 RUN 1, PID 36716 |

Every invocation ended with a journaled `controller_released`. Total controller-active time
**1912.3 s = 31 m 52 s**; wall clock from first controller start to last release **45 m 31.8 s**.

Runner-to-invocation mapping, for the record: **v5 ran one** invocation (then broke on the non-zero
exit); **v6 ran five** invocations with four `[RECOVER n/5]` lines between them — the journal holds
five distinct invocation ids inside v6's window (`009ce91c`, `6e7a8fa5`, `712bc235`, `ecd9047f`,
`c1d43a39`) and its transcript holds four recovery lines, so five runs and four recoveries is the
correct reading; **v7 ran one** invocation with zero recoveries
(`[DONE] checkouts.lock recoveries used: 0/20`). Runner launch times: v5 PID 37292 at 02:34:19Z,
v6 PID 40320 at 02:46:49Z, v7 PID 36716 at 03:15:15Z; each was launched by the parent session.

## 2. Graph-management roles: model, effort, what each actually did

| Role | Model / effort as launched | What it actually did |
|---|---|---|
| Lead (Sol-equivalent) | **Claude Opus 5 (1M), xhigh** | Verified every identity before provider work (branch, HEAD, clean tree, diff scope, ancestry, empty root, absence of an owner record, viewer, containers, credential volume, worker config, family shape). Wrote both helper prompts. Diagnosed all three failure classes to root cause from durable evidence, including reading the Unity log that overturned the "crew wrote bad code" reading of NSC-1164 and the committed history that proved NSC-1167's policy staleness. Authored the two bounded-recovery runner variants. Ran **no** mutating command — the permission layer refused every attempt from this session — so each mutation was executed by the parent on exact instructions. |
| Setup (Luna-equivalent) | **Claude Sonnet 5, medium** (`gauntlet-setup`) | Ran `graph-plan` successfully (exit 0, `status: actionable`, `mutations_performed: false`). Its `run-graph --delegate-safe` was refused by the auto-mode permission classifier, so it never reached `handoff_required`. It mutated nothing and took no lock. Net contribution: a validated read-only plan. |
| Observer (Spark-equivalent) | **Claude Haiku 4.5, medium** (`gauntlet-observer`) | Read only the first 37 journal lines (02:34:20Z → 02:35:36Z, the first 76 s), and its first-pass answers never reached me. It confirmed one invocation id and `claude` / `claude-haiku-4-5-20251001` for crew work in that window, and escalated one false positive: "duplicate start_worker entries per task" is a misreading of paired `action_started`/`action_completed` records. Net contribution close to zero; I answered its own questions myself from the records. |

## 2a. Final tally, from the controller's own last plan

`C:\NSC\GauntletFresh1140-20260912-1-Checkouts-6\operator-logs\run-graph-20260912-221516.json`
(UTF-16LE) is the authoritative end state:

- `status: blocked`, `next_actions: []` — **no eligible work remained**, so the run ended because
  nothing more could proceed, not because it was stopped.
- `in_scope`: 14 tasks — NSC-1160…NSC-1167 plus the six allocator-generated children
  NSC-1168…NSC-1173. No other task was ever selected.
- `complete` (12): **NSC-1160, NSC-1161, NSC-1162, NSC-1163, NSC-1165, NSC-1166, NSC-1168,
  NSC-1169, NSC-1170, NSC-1171, NSC-1172, NSC-1173**. All three decomposable parents (NSC-1160,
  NSC-1165, NSC-1166) are complete through their children.
- `blocked` (2): **NSC-1164** `validation_failed`, **NSC-1167** `validation_failed`.
- `waiting_human`: empty. NSC-042 was never touched; it stayed in `human_review_tasks` throughout.
- `source_commit`: `62b2af516cdb849942023879e039c3355c6c40c8`.

**The Gauntlet did not fully pass.** Twelve of fourteen tasks are complete by AssistantControl
evidence; the two that are not are blocked by a Unity licensing fault and a stale fixture pin
(section 6), neither of which is a crew, candidate or controller-scheduling defect, and neither of
which has a supported recovery path that I could take without a code or fixture change.

## 3. Tasks, worker run IDs, candidates, integrations

11 crews ran, one per task, each with exactly one `start_worker` and one `settle_worker`:

| Task | Crew run id | start_worker | settle_worker | Final state |
|---|---|---|---|---|
| NSC-1161 | `assistant-nsc-1161-288bf9247a6e` | 02:35:05.453 | 02:37:15.481 | integrated |
| NSC-1162 | `assistant-nsc-1162-27d3a8777c35` | 02:35:15.021 | 02:37:45.049 | integrated |
| NSC-1163 | `assistant-nsc-1163-8dcd61ca18df` | 02:35:25.952 | 02:37:39.935 | integrated |
| NSC-1164 | `assistant-nsc-1164-46f742ae7497` | 02:35:35.603 | 02:37:42.595 | **validation_failed** |
| NSC-1167 | (crew in v7) | 03:17:23.342 | 03:19:40.606 | **validation_failed** |
| NSC-1168 | `assistant-nsc-1168-afaf33b8d401` | 02:47:43.249 | 02:50:24.028 | integrated |
| NSC-1169 | `assistant-nsc-1169-2295e069cf04` | 02:48:06.872 | 02:51:19.707 | integrated |
| NSC-1170 | `assistant-nsc-1170-dc2e88235c29` | 02:55:53.711 | 02:58:52.550 | integrated |
| NSC-1171 | `assistant-nsc-1171-acca55837466` | 02:56:05.068 | 02:59:28.179 | integrated |
| NSC-1172 | `assistant-nsc-1172-65c854c0a707` | 03:01:31.140 | 03:04:34.475 | integrated |
| NSC-1173 | `assistant-nsc-1173-f79d63de221c` | 03:01:44.125 | 03:05:15.745 | integrated |

Nine integrations landed, each as an `assistant-sync/<task>-<id>` merge commit; the final HEAD is
`62b2af516cdb849942023879e039c3355c6c40c8` (NSC-1173's). Representative candidate commits:
NSC-1161 `2205c89a32134dd9dda68d42d4c1ba09366c7eb6` (integrated as `242be48439c3b87ce1c9884cfa1e022c754ce230`),
NSC-1162 `49d5448fa8ec1ed47057c6f3eba59888a1cd7931`, NSC-1163 `8ce0a789d592…`, NSC-1168 `d95ce48add1a…`,
NSC-1173 `62b2af516cdb…`. Every repeated `post_crew` in all 14 task sequences is preceded by a
`sync_candidate` for the same task: the repeats are the designed revalidation after an intervening
integration, not a loop. No task received two `start_worker` actions.

## 4. Decomposition rounds and generated children

Three decompositions, all `review_ready` then `applied`, author `claude-sonnet-5`, independent
reviewer `codex` / `gpt-5.6-sol`, each bound to the Source head it started from
(`reviewed_source_is_ancestor: true`):

| Parent | Run id | Window | Rounds | Children | Applied as |
|---|---|---|---|---|---|
| NSC-1160 | `assistant-nsc-1160-decompose-799907e03959` | 02:34:35.269 → 02:38:49.392 (251.1 s) | author 62.5 s, reviewer 104.5 s, **corrections 0** | NSC-1168, NSC-1169 | `d2fd194eb81282e7d74664a3d0ffe8c81feb3c81` |
| NSC-1165 | `assistant-nsc-1165-decompose-242be48439c3` | 02:50:06.144 → 02:54:27.128 (257.6 s) | author 74.3 s, **author correction 49.9 s**, reviewer 31.6 s, **corrections 1** | NSC-1170, NSC-1171 | `b41a31e05d97701e671eee2dff1b87b062f6521b` |
| NSC-1166 | `assistant-nsc-1166-decompose-b41a31e05d97` | 02:55:37.377 → 02:59:25.274 (224.4 s) | author 72.3 s, reviewer 61.6 s, **corrections 0** | NSC-1172, NSC-1173 | `1175937…` (`11759376848a9d9a4e890d69c0b10f15bb795ee3`) |

**The bounded author-correction path was exercised for the first time.** NSC-1165's round 1
proposal was initially invalid, the deterministic validator's findings drove exactly one
correction round (`round_provider_started … "correction_of_round": 1`), and the corrected
proposal then passed the independent reviewer and applied cleanly. Evidence:
`…\.assistant-control\decomposition-runs\assistant-nsc-1165-decompose-242be48439c3\progress.jsonl`
(`run_completed … "author_corrections_used": 1`) and its `rounds\` directory. Run 1 never
reached this path. The bound held: one correction, never two.

All six generated children joined the graph and were crewed, validated, approved and integrated.

## 5. Elapsed time by phase

| Phase | Window (UTC) | Duration |
|---|---|---|
| Lead verification of every identity | ~02:10 → 02:17 | ~7 min |
| Sonnet attempt 1 (failed on my prompt's unquoted paths) | 02:17:00.210 → 02:17:00.847 | 0.6 s |
| Sonnet attempt 2 `graph-plan` (exit 0, actionable) | 02:18:05.013 → 02:18:08.209 | 3.2 s |
| Sonnet `run-graph --delegate-safe` | — | refused by the permission classifier |
| My two refused launch attempts, then parent hand-off | ~02:28 → 02:34:19 | ~6 min |
| v5 invocation 1 | 02:34:20.927 → 02:37:57.236 | 3 m 36 s |
| **Gap: lock failure to v6 relaunch (operator round trips)** | 02:37:57 → 02:46:49 | **8 m 52 s** |
| v6, 5 invocations, 4 lock recoveries | 02:46:49 → 03:12:17 | 25 m 28 s |
| **Gap: two `clear-background-job` calls plus v7 launch** | 03:12:17 → 03:15:15 | **2 m 58 s** |
| v7, 1 invocation, 0 lock recoveries | 03:15:15 → 03:19:53 | 4 m 38 s |
| First dispatch after a controller start | 02:34:20.927 → 02:34:25.579 | 4.7 s |

Aggregated from the journal's `duration_seconds` (476 lines, 12 action kinds):

| Action | Count | Total s | First | Last |
|---|---:|---:|---|---|
| `wait_job` | 21 | 636.3 | 02:37:12 | 03:19:52 |
| `sync_candidate` | 29 | 399.6 | 02:48:23 | 03:15:48 |
| `wait_worker` | 1 | 134.8 | 03:19:38 | 03:19:38 |
| `integrate` | 9 | 119.1 | 02:49:46 | 03:16:59 |
| `reserve` | 11 | 91.6 | 02:35:03 | 03:17:21 |
| `prepare` | 11 | 59.8 | 02:34:31 | 03:17:11 |
| `auto_approve` | 12 | 55.6 | 02:49:37 | 03:16:52 |
| `scope` | 11 | 34.2 | 02:34:33 | 03:17:15 |
| `post_crew` (launches) | 40 | 28.6 | 02:37:16 | 03:19:41 |
| `settle_worker` | 11 | 25.7 | 02:37:15 | 03:19:40 |
| `apply_decomposition` | 3 | 23.3 | 02:47:10 | 03:00:52 |
| `start_worker` | 11 | 7.6 | 02:35:05 | 03:17:23 |
| `decompose` (launches) | 3 | 2.8 | 02:34:25 | 02:55:23 |

Peak concurrency: **4 crew workers** (02:35:35, NSC-1161..1164) and **4 background jobs**
observed in the controller's own `background_jobs` running list. A naive journal count reaches 5
because `job_completed` is journaled at harvest, later than the child actually exited; the
configured bound of 4 was never exceeded in controller state.

`sync_candidate` is again the dominant avoidable cost: 29 actions / 399.6 s here versus
14 / 154.4 s in run 1. Every integration invalidates the other in-flight candidates, so each must
re-merge and re-validate; the cost grows with the number of concurrently ready candidates.

## 6. Blocked tasks, with exact evidence paths

### NSC-1164 — Unity licensing failure on a re-validation, not a crew defect

Final record `validation_failed` in
`C:\NSC\GauntletFresh1140-20260912-1-Checkouts-6\.assistant-control\NSC-1164.json`.

The candidate **passed real focused EditMode validation three times** before this:

| Job | Completed | Candidate | Focused test manifest |
|---|---|---|---|
| `829916c66773…` | 02:49:09.442 | `75696ff44eb0e7dd3a2caaeec896b5c1da99cd06` | `outputs/NSC-1164/candidate-75696ff44eb0/post-candidate-validation/EditMode-55ad0bdc149e/validation-manifest.json` |
| `d8d2844bd8b8…` | 02:50:35.074 | `3b8314838eca5df361822421ab54f5a343b1cb97` | `…/candidate-3b8314838eca/…` |
| `4b62e5f19f72…` | 02:54:53.362 | `56f236b962609c1b82ac4596cacec623495291bf` | `…/candidate-56f236b96260/…` |

The final re-validation of the re-synced candidate `f2e00ebb76ec54b3a89f65dadd6645e1c81a90c7`
(job `6c5fb5d56d0723e7f5f12812dde155216665b7790003e1b9c8074008ce064710`, 03:15:38.005 →
03:16:21.637) returned `status: validation_failed` with
`validation_error: "candidate EditMode Unity test failed (20) … UNITY FAILURE: Unity exited with code 1."`

`C:\Users\VincentLiguori\AppData\Local\Temp\NoSafeCircle-UnityTests-96eb6fd14e2f40c192b12ae4ec832991\unity.log`
contains, verbatim:

- `[Licensing::Client] Error: Code 404 while processing request (status: Found 0 entitlement groups and 0 free entitlements matching requested entitlement ids)` (three times)
- `[Licensing::Module] Error: Access token is unavailable; failed to update`
- `[Licensing::Module] Error: 'com.unity.editor.headless' was not found.`
- `No valid Unity Editor license found. Please activate your license.`

**No `test-results.xml` was produced** in that directory, so no test ever ran and the candidate was
never evaluated. This is the same failure class as run 1's NSC-1143.

The failure is **intermittent, not a broken host licence**, on two independent pieces of evidence:

- another post-crew child validated NSC-1173 successfully in the overlapping window
  (03:15:50.221 → 03:16:48.988, real manifest
  `outputs/NSC-1173/candidate-62b2af516cdb/post-candidate-validation/EditMode-4e5b75c12a19/validation-manifest.json`);
- a headless licensing probe run by the parent immediately after the failure **succeeded** (serial
  assigned, license updated, exit 0) while still emitting the recurring
  `Access token is unavailable; failed to update` line.

Whether the trigger is a licence-token refresh or contention for a single headless entitlement
(the operator's Unity Editor GUI is normally open on the checkout) is **not established** by this
evidence; both remain open.

**There is no re-validation path for this state in this stack.** The parent tried the receipt's own
suggested command, `revise NSC-1164 --candidate-commit f2e00ebb…`, and it refused with
`candidate is not the clean owned reviewed candidate`: `begin_revision` accepts only a
`unity_materialization_failed` candidate or a human `changes_requested` rejection, and a focused
**validation** failure is neither. So a candidate whose three prior validations passed is now
parked with no supported way to re-run the validation that only failed for want of a licence.

### NSC-1167 — stale pinned validation policy after its contract was rewritten (fixture defect)

Record `validation_failed`; job `ae43e4ec4e28…` (03:19:41.701 → 03:19:52.078), candidate
`bd615a0d42caf56b542712bb613b023b5172721d`, and the receipt's
`validation_error: "authoritative validation policy for NSC-1167 is stale"`.

Proof from committed history, not inference:

- `Pipeline/TaskReviewAgent/authoritative_validation_policy.json` pins, for NSC-1167,
  `task_contract_sha256: 76e17a2b045d937ef5835e739858a97551d0298b14f200d4aedea117e26c2812`.
- The current `Tasks/NSC-1167.yaml` hashes to
  `8f7a5bfd43c4742c0893382453e44e0c79668f5b9af37e40db7f29858538ac7c`.
- `git log --follow -- Tasks/NSC-1167.yaml` shows the change came from `1175937`, the
  **NSC-1166 decomposition apply**, which rewrote `Tasks/NSC-1166.yaml`, `Tasks/NSC-1167.yaml`,
  added `Tasks/NSC-1172.yaml` and `Tasks/NSC-1173.yaml` and updated `WORK_ID_MAP.json`. NSC-1167's
  `depends_on` moved from `NSC-1166` to the concrete child `NSC-1173`, exactly as NSC-1166's own
  `decomposition_reason` mandates ("rewrite every inbound dependent to the concrete child
  capabilities it uses").
- No commit after the base touched `authoritative_validation_policy.json`, so the pin was never
  refreshed.

The parent independently confirmed that the pinned `76e17a2b…` equals the NSC-1167 contract bytes
**as of `799907e`**, so the pin was correct when written and was invalidated purely by the apply.
A `sync_candidate` cannot help: the contract, not the candidate, is what moved.

This is the same class as run 1's NSC-1146 blocker — its **second face**: run 1 hit the stale
*decomposition child template*, run 2 hit a stale *task entry* in the same policy file. It reaches
the run through a path the fresh fixture did not close. The fixture avoided having a *decomposable
parent's* contract rewritten by an upstream apply, but **a dependent of a decomposable parent is
rewritten by that parent's own apply**, which invalidates the dependent's pinned policy hash. It is
deterministic: any future family with an edge into a decomposable parent will hit it. Fixing it
means regenerating the pinned hash, which is a Source fixture change and out of scope for this run,
so I did not touch it; the parent reports it is being folded into the authenticated re-pin migration
already under review.

### Not blockers

`post_crew` jobs `8b97d834…` (NSC-1164, 02:56:21.933) and `4ac95f73…` (NSC-1173, 03:07:27.319)
failed on the checkouts lock (section 9) and blocked their tasks by design until their indexes were
archived. Their archives are
`…\.assistant-control\NSC-1164.background-job.8b97d834d3aaa42737ddca36ba6ada81ed51ea2eb58eebeb72cd6cf746b192aa.cleared.json`
and
`…\.assistant-control\NSC-1173.background-job.4ac95f738c10688fb66f4b209fc0ed440cc06f464638b4d5c589e64b787a1c87.cleared.json`.
Both stderr logs are empty; both receipts carry the lock error verbatim. After the archives, fresh
tickets ran and NSC-1173 integrated at 03:16:59.928.

## 7. Procedure deviations

1. **No delegate-safe setup pass ran.** Attempt 1 (02:17:00) failed on my own prompt defect:
   unquoted Windows paths are de-slashed by Git Bash, so the CLI received
   `C:NSCGauntletFresh1140-20260912-1` and returned
   `{"status": "command_failed", "error": "fatal: cannot change to 'C:NSCGauntletFresh1140-20260912-1': No such file or directory"}`.
   Nothing was mutated and no lock taken. I corrected the quoting and resumed the same helper;
   its `graph-plan` succeeded (02:18:05.013 → 02:18:08.209, exit 0, `status: actionable`,
   first action `decompose NSC-1160`, `mutations_performed: false`), and its
   `run-graph --delegate-safe` was then refused by the Claude Code auto-mode classifier. It stopped
   and mutated nothing. Artifacts: `…\scratchpad\run2-1160\a_stdout.json`, `a2_stdout.json`,
   `a2_exit.txt`, `ts_a*_start/end.txt`. Consequence: the prepare/scope setup happened inside the
   normal loop instead, which is what first exposed the lock race (section 9).
2. **Every mutating command was run by the parent, not by me.** The permission layer refused, from
   this session, the detached runner launch (both via PowerShell `Start-Process` and via a
   background Bash launch), and also refused writing any file under `C:\nscrev\reports`. I supplied
   exact commands and the parent executed them. This added the 8 m 52 s and 2 m 58 s gaps in
   section 5.
3. **Two operator-script variants were authored mid-run** (section 11) — no Gauntlet Source file
   was changed.
4. **Two background-job indexes were archived** with `clear-background-job` (paths in section 6),
   after I verified both jobs were `post_crew` with `provider_container: null`, no pending cleanup,
   and no live controller.

The procedure change this run was meant to test — Sonnet's release to runner launch in under 60 s,
against run 1's 177 s — **could not be measured, because no delegate-safe pass ever released a
controller.** The equivalent figure for this run is the 8 m 52 s and 2 m 58 s recovery gaps, both
caused by permission round trips rather than by verification work. On the evidence available, the
lead's verification was not the bottleneck; the mutation-permission boundary was.

## 8. Viewer

Viewer pid 12628 served `read_only` state throughout on `http://127.0.0.1:8817/`, correctly scoped
(`state_root` the -6 root, `source` the Gauntlet Source, the eight targets visible, the six
generated children joining automatically, the pristine 1140s hidden). It was never restarted and
no conclusion in this report rests on a viewer colour. Run 1's projection gap reproduced: at
03:03Z the viewer showed NSC-1160/1161/1162 as `human_action` and NSC-1163/1164 as `assistant_idle`
while the durable records had NSC-1161 and NSC-1162 already integrated. The records were right.

## 9. Findings for the FIX AFTER list

### F1 (new, high value) — a 10 s `checkouts.lock` wait fails a whole invocation instead of deferring a cycle

Seven timeouts, all
`TimeoutError: [Errno 10060] timed out after 10s waiting for exclusive file lock: 'C:\NSC\GauntletFresh1140-20260912-1-Checkouts-6\.assistant-control\checkouts.lock'`:

| # | UTC | Action | Task | Effect |
|---|---|---|---|---|
| 1 | 02:37:57.228 | `post_crew` | NSC-1163 | fatal — invocation 1 ended, `controller_released` 02:37:57.236 |
| 2 | 02:50:47.425 | `sync_candidate` | NSC-1163 | fatal — v6 RUN 1 |
| 3 | 02:51:32.893 | `auto_approve` | NSC-1162 | fatal — v6 RUN 2 |
| 4 | 02:56:22.094 | `post_crew` | NSC-1164 | **not** fatal to the invocation; the job was recorded `failed`, blocking NSC-1164 |
| 5 | 02:59:41.142 | `integrate` | NSC-1163 | fatal — v6 RUN 3 |
| 6 | 03:05:32.591 | `auto_approve` | NSC-1170 | fatal — v6 RUN 4 |
| 7 | 03:07:34.169 | `post_crew` | NSC-1173 | **not** fatal to the invocation; the job was recorded `failed`, blocking NSC-1173 |

The trigger, precisely: at 02:37:46.581 the controller launched `post_crew` for NSC-1162 and at
02:37:47.225, **1.1 s later**, it began `post_crew` for NSC-1163 while that fresh child still held
`checkouts.lock` for candidate registration. All four crews had settled inside 8 s
(02:37:37–02:37:45), so the launches bunched. Run 1 never hit this because its delegate-safe pass
had pre-prepared the checkouts and spread `post_crew` launches over 20 minutes.

Two distinct defects are visible:

- **F1a**: four Source-lane action kinds (`post_crew` launch, `sync_candidate`, `auto_approve`,
  `integrate`) each turned a 10 s lock wait into `status: command_failed`, exit 1, killing an
  invocation that had done real work. The natural fix is the mechanism this controller already
  has: defer the action with a `held` record and retry next cycle, as it does for
  `source_lane_held`, rather than propagating the timeout.
- **F1b**: the same error class was fatal in entries 1, 2, 3, 5, 6 and survivable in 4 and 7, and
  entries 4 and 7 occurred in the same action kind as entry 1. The inconsistency is **not
  explained** by this evidence and should be understood before the fix, because the survivable
  path silently converts a lock race into a failed job that blocks a task.

Operator-level mitigation measured here: with `--background-jobs 4`, v6 needed 4 recoveries across
5 invocations in 25 m 28 s. With `--background-jobs 2`, v7 completed its remaining work in **one
invocation, 4 m 38 s, zero recoveries**. That is suggestive, not conclusive — v7 also had far less
work left.

### F2 (recurrence, and a dead end) — a licensing-class validation failure is recorded as `validation_failed`, with no way back

NSC-1164 (section 6). A Unity run that never obtained an entitlement, produced no
`test-results.xml` and ran no test is recorded identically to a candidate whose tests failed. Two
consequences, both verified:

- the receipt's own `next_action_command` proposes `revise NSC-1164 --candidate-commit f2e00ebb…`,
  which would spend provider budget asking a crew to fix code that three prior validations proved
  correct;
- and that command **refuses anyway** — `candidate is not the clean owned reviewed candidate`,
  because `begin_revision` accepts only a `unity_materialization_failed` candidate or a human
  `changes_requested` rejection. A focused-validation failure has no revalidation path at all.

**FIX AFTER**: classify infrastructure failures (no entitlement, Unity exited before running tests,
no results XML) as retryable rather than as a candidate verdict, and give a `validation_failed`
candidate a supported revalidation path so a transient host fault cannot permanently park work that
has already passed.

### F3 (recurrence, new path) — a decomposition apply staleness-invalidates its dependents' pinned policy

NSC-1167 (section 6). Either regenerate the pinned `task_contract_sha256` for every dependent an
apply rewrites, or pin the policy on something the apply does not rewrite.

## 10. Comparison with run 1

| | Run 1 | Run 2 |
|---|---|---|
| Tasks in scope | 12 (8 targets + 4 children) | 14 (8 targets + 6 children) |
| Complete | 9 | **12** |
| Blocked | 3 (NSC-1143 Unity licensing, NSC-1146 stale template, NSC-1147 dependencies) | 2 (NSC-1164 Unity licensing, NSC-1167 stale policy) |
| Controller invocations | 2 (1 delegate-safe + 1 normal) | 7 (0 delegate-safe + 7 normal) |
| Normal-loop wall clock | 23 m 05 s, single invocation | 45 m 32 s across 7 invocations, including 11 m 50 s of operator gaps |
| Controller-active time | ~23 m | 31 m 52 s |
| Decompositions | 2 applied, 0 author corrections | **3 applied, 1 author correction (first time)** |
| `sync_candidate` cost | 14 actions / 154.4 s | 29 actions / 399.6 s |
| `checkouts.lock` failures | 0 | 7 |
| Peak crews / jobs | 4 / 4 | 4 / 4 |

Run 2 completed a larger graph and a deeper decomposition tree, exercised the author-correction
path run 1 never reached, and reproduced both of run 1's non-controller failure classes. It also
surfaced one wholly new controller defect (F1) that run 1's delegate-safe pass had masked.

## 11. Code changes made after the run began

**No file in the Gauntlet Source was changed.** The Source tree was clean at start and end, and all
37 commits between `799907e` and `62b2af5` were machine-generated by AssistantControl itself
(three `taskgraph: apply … decomposition` commits, the `Implement NSC-…` crew candidates, and the
`assistant-sync/…` merges from `sync_candidate`). I edited no repository file, no task contract, no
durable record and no fixture.

Two **operator scripts outside the repository** were authored, both parse-checked before use:

- `C:\nscrev\reports\gauntlet-run-1160-runner-v6.ps1` (sha256
  `54A6254E95877BDDDE1399588C5F4272E779A11556D46C45EAC9F29ABB6EF92E`): v5 plus a bounded recovery
  that resumes after 25 s when a result is `command_failed` with a `waiting for exclusive file lock`
  error, at most 5 times.
- `C:\nscrev\reports\gauntlet-run-1160-runner-v7.ps1` (sha256
  `4FCF89F2F870EFFF258EE8C79A4F90913A66EEC731F8B0E26F70170D16E89437`): v6 with `--background-jobs 2`,
  20 recoveries, and a guard that stops after three consecutive recoveries which add no journal
  event.

Both keep v5's identity gate, the eight targets, capacity 10, max-actions 240, the target branch,
the worker config and the NSC-042 human-review boundary unchanged. My read-only helper scripts
(`digest2.py`, `poll2.py`, `report_data2.py`) live in my scratchpad.

## 12. What would be needed to finish

- **NSC-1164**: needs a controller change, not an operator action. `revise` is refused by design
  (F2), so the only paths available today are a code change that makes a licensing-class failure
  retryable, or an untested attempt at
  `post-crew NSC-1164 --run-id assistant-nsc-1164-46f742ae7497 --config <worker-haiku.example.json>`
  to re-register and re-validate the finished crew run. Do **not** use the receipt's suggested
  `revise`: it refuses, and nothing is wrong with the candidate — three focused validations passed.
- **NSC-1167**: regenerate its pinned `task_contract_sha256` in
  `Pipeline/TaskReviewAgent/authoritative_validation_policy.json` to match the post-apply contract,
  then re-validate. That is a Source fixture change and needs Vincent's decision.
- **NSC-1160/1165/1166** are already complete through their children; **NSC-1166** would clear once
  NSC-1173's sibling set is complete, and it already is — its only outstanding dependent state was
  NSC-1167.

Stop discipline: the run was never stopped by force. Every invocation released its own lock, the
final owner record reads `controller_released` (`1aea3725eb064f219c7c838b47e66cd1`), the controller
state reads `blocked` with `last_error: null`, no background job is running, and no
`nsc-decompose-*` or `assistant-crew-*` container remains.
