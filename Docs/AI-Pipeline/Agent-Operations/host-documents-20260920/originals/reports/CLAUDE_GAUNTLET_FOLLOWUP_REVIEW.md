# Gauntlet Follow-Up Review — `review/orchestration-gauntlet-followup`

**Reviewer:** Claude (read-only review + design)
**Date:** 2026-09-03
**Review checkout:** `C:\NSC\ClaudeReview\NoSafeCircle` — isolated clone
**Local branch:** `claude/review-orchestration-gauntlet-followup` @ `11df3aa`
**Base:** `origin/main` @ `983ba6a` (contains `79dc6a0` and `983ba6a`)
**Commits authored by me:** none yet. No fixes committed.

**Constraints honored:** No live rehearsal checkout modified. No GitHub Issue touched. No container stopped, killed, or removed. The two long-lived `nosafecircle-codex-review` containers (up 27h and 29h) were inspected only.

---

## 0. Status and how to read this document

This document has three clearly separated parts.

| Part | Status | Basis |
|---|---|---|
| **Part A — Findings** | VERIFIED | My own reproduction and direct file reads, then an adversarial verification pass (9 investigators, 64 findings, 127 verdicts: 65 CONFIRMED / 9 PLAUSIBLE / 53 REFUTED). Corrections and additions folded in. |
| **Part B — Extended design answers** | DESIGN PROPOSAL | My analysis of the code as it exists at `11df3aa`. Not yet implemented, not yet verified against a Codex implementation. |
| **Part C — Verification and re-fetch** | RE-FETCH PENDING | Verification complete. Re-fetch awaits Codex's next push. |

Nothing in Part B has been implemented. Where Part A and the original brief disagree, I say so explicitly — two of the brief's premises did not survive checking.

**One of my own preliminary conclusions was wrong and has been corrected: see A5.** Findings I personally reproduced are marked **[REPRODUCED]**; findings carried from the verification agents that I did not personally re-derive are marked **[AGENT-CONFIRMED]**.

---

## 0.1 Prioritized action order

Suggested sequence. The first item is a prerequisite for trusting anything about area 1.

| # | Item | Sev | Where | Why this order |
|---|---|---|---|---|
| 1 | **A6** CRLF — unblock the ExecutionCrew suite | High | `execution_crew_smoke_test.py:22,338,341` | Until `:341` passes, `11df3aa`'s own assertions at `:725-726` never execute. Nothing about area 1 is verifiable on Windows until this lands. |
| 2 | **A8.2** register the scheduler suite in CI | High | `.github/workflows/task-review-agent-deterministic.yml` | All 59 scheduler tests are currently unprotected; every fix below needs them running. |
| 3 | **A4 / B4** exit-code contract + result artifact | Critical | `run_pipeline_agent.py:515`, `host_decomposition_launcher.py:243` | A blocked run is reported as success today; corrupts every downstream scheduling decision. |
| 4 | **A8.1** `--exclude-task-id` on the resume path | Critical | `polling_orchestrator.py:786,880` | Operator safety boundary not enforced; small, self-contained fix. |
| 5 | **A1 / B5** boundary normalization | High | `run_crew.py:720,809,813` + 3 consumers | Includes two fail-open defects inside the new function itself. |
| 6 | **A7(b) / B2** shared snapshot per admission | High | `polling_orchestrator.py:1297,624` | Per A5.1 this is the **dominant, compounding latency driver** (901 s, growing 3.4×), not just waste. |
| 7 | **A3 / B3** deterministic resume priority | High | `polling_orchestrator.py:880,1853` | Six consecutive overrides; also fixes A8.3 (only `agent_ready[0]` offered). |
| 8 | **A7(d) / B3** pending-transition state | High | `pass_and_resume_task.py:512` | Reached 2/3 of the fatal threshold in the live run. |
| 9 | **A2 / B1** architect batching | High | `polling_orchestrator.py:2044,2312` | Largest throughput win, but depends on 3, 6 and 7 being correct first. |
| 10 | **A7(c) / B6** consistency-budget fairness | Medium | `issue_workflow_store.py:755` | Re-armed per candidate; fix alongside B2. |

---

# PART A — Findings

Every line number below is exact, from the review checkout at `11df3aa`. Every item marked **REPRODUCED** I executed or read directly.

## A1. `normalized_agent_blockers` — correct, but incomplete

**Severity: High. Status: root cause REPRODUCED; coverage gap CONFIRMED by reading.**

Root cause, from `C:\NSC\Rehearsal\NSC-913\Pipeline\ExecutionCrew\outputs\nsc-913-20260903t223446z\`:

```
role_results/test_author_1.json
  agent_status            = "succeeded"
  failure_classification  = "none"
  structured_output.blockers = ["(none)"]
  structured_output.claimed_changed_paths = ["(none - no changes were made)"]
  summary: "...No edits were required or made."
crew_result.json
  crew_status        = "blocked"
  rejection_reasons  = ["test author blocker: (none)"]
```

The model behaved correctly — the gate test already existed — and serialized its empty answer as a sentinel in **two different fields of the same response**.

`11df3aa` correctly fixes the two `blockers` call sites (`run_crew.py:1244`, `:1273`).

**Confirmed coverage gap — the validator has the identical exposure and is not fixed:**

```
run_crew.py:720   blocking = bool(output.get("blocking_issues"))
run_crew.py:733   if status == "pass" and blocking: reasons.append("validator pass contains blocking issues")
                  -> caller: if scope: reasons+=scope; crew_status="rejected"
```

A provider emitting one sentinel `blocking_issues` object alongside `status="pass"` reproduces the same false-blocker failure in the validator role.

**Sentinel set is too narrow.** `run_crew.py:797` matches by exact casefolded equality after `strip()`. `"none."`, `"N/A"`, `"None identified"`, `"no blockers found"`, `"-"` all still block. Direct evidence the provider does not confine itself to the six listed forms: the same response emitted `"(none - no changes were made)"`.

**Latent, same pathology.** `run_crew.py:1250` and `:1279` take `list(output.get("claimed_changed_paths",[]))` raw into `role_claimed_paths`. It drives no decision today, so it is latent — but it diverged from `agent_runtime_claimed_paths=[]` in the live run and nothing checks the divergence.

**Layering.** Normalization sits at two call sites rather than at a boundary, so every future consumer must remember to call it. See **B5**.

### A1.1 Two fail-open defects *inside* the new function — [AGENT-CONFIRMED]

**Severity: High.** `normalized_agent_blockers` is itself fail-open in two ways:

```
run_crew.py:809   if not isinstance(value, list): return []      # a dict/str payload -> "no blockers"
run_crew.py:813   if not isinstance(item, str): continue          # a structured blocker object is dropped
```

A provider that returns `blockers` as an object, a bare string, or a list of objects now yields "no blockers" instead of failing closed. Given the whole point of the function is to avoid *false* blockers, silently swallowing *real* ones in these shapes is the worse direction. The schema (`schemas.py:58`, `:71`) declares `array of string`, so a non-conforming payload should be a **schema failure**, not an empty list.

### A1.2 Three further uncovered consumers — [AGENT-CONFIRMED]

Beyond the validator (`run_crew.py:720`), the same raw-list pathology exists at:

| File:line | Exposure |
|---|---|
| `Pipeline/Reconciliation/reconciliation_agent.py:989` | forces `seed_assessment.status='blocked'` from a raw model list |
| `Pipeline/TaskReviewAgent/contracts.py:431` | `TaskReviewOutcome` raises a hard contract error on a model-authored blocker list |
| `Pipeline/ExecutionCrew/contract_locality.py:195` | `blocking_findings` gated on raw membership |

This strengthens the case for the single boundary in **B5** over per-call-site patching.

## A2. `--architect-max-invocations-per-poll` is unreachable dead configuration

**Severity: High. Status: CONFIRMED by reading.**

```
polling_orchestrator.py:1710  def poll_once(self) -> PollCycleResult:
                        :1711  self.architect_invocations_this_poll = 0      # reset per poll
                        :1986  if self.architect_invocations_this_poll >= self.max_architect_invocations_per_poll
                        :2007  self.architect_invocations_this_poll += 1     # exactly once
                        :2312  return PollCycleResult("worker_launched", ...) # poll ends after ONE launch
```

The counter is only ever `0` or `1` when tested, so with the configured value `10` the guard at `:1986` can never bind.

Journal corroboration: **14 `poll_started`, 11 `architect_started`, 11 `worker_launched`** — strictly 1:1.

**Measured cost** (read from the architect artifacts' `invocation.usage`, not estimated):

| Metric | Value |
|---|---|
| Architect calls | 11 |
| Total input tokens | **1,648,820** |
| Total architect wall time | **803 s = 13.4 min** of a ~30 min session (**45%** of wall clock) |
| Mean input tokens/call | 149,892 |
| First call | 208,150 tokens / 78.9 s |
| Ramp 0 → 6 concurrent workers | 22:22:09 → 22:47:47 (**25.6 min**) |

**This contradicts a premise in the brief.** The cost is *not* driven by resending the portfolio. The **last** call had `portfolio_size=1` and was the **most expensive of the session** (258,005 input tokens, 123.6 s). Portfolio size and cost are uncorrelated across the 11 calls; invariant per-call context dominates. Shrinking or delta-encoding the portfolio will not fix this. See **B1**.

## A3. Approved resume starved by architect selection

**Severity: High. Status: CONFIRMED by journal + code.**

The deterministic priority exists and is then discarded:

```
polling_orchestrator.py:1528-1540  _ordered_candidates() puts the resume FIRST (:1532-1534)
                        :1853       "resume_existing" and "fresh_candidate" handled identically
                        :1869       _mixed_portfolio(plan, candidates)   -> dict by_id, order lost
                        :1994       portfolio_request = whole portfolio -> architect
                        :2044       candidates = ((selected_entry[0], selected_entry[1]),)  # model's pick wins
```

Ordering is advisory; the model's selection is authoritative.

**Journal proof** — deterministic rank 1 versus architect selection, per call:

| Call | Rank 1 | Selected | Portfolio | |
|---|---|---|---|---|
| 1 | NSC-911 | NSC-911 | 10 | |
| 2–4 | NSC-912/913/914 | same | 9→7 | |
| 5 | NSC-911 | NSC-915 | 7 | **overrode** |
| 6 | NSC-911 | NSC-916 | 6 | **overrode** |
| 7 | NSC-911 | NSC-917 | 5 | **overrode** |
| 8 | NSC-911 | NSC-918 | 4 | **overrode** |
| 9 | NSC-911 | NSC-919 | 3 | **overrode** |
| 10 | NSC-911 | NSC-920 | 2 | **overrode** |
| 11 | NSC-911 | NSC-911 | 1 | serviced only when nothing else remained |

Six consecutive overrides. The approved resume was admitted only after the fresh pool was exhausted.

**Policy divergence.** `AGENTS.md` and `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md` both require a validated agent-ready Issue to be resumed *before* fresh work is selected. `Start-GameTaskAgent.ps1` generic resume honors this; the scheduler does not.

## A4. A blocked run exits 0 and is reported as `worker_finished`

**Severity: Critical. Status: CONFIRMED — exact line located.**

```
run_pipeline_agent.py:499  status = _outcome_status(result)
                     :503  if args.mode == "openai" and status == "unknown_outcome":
                     :514      return 2
                     :515  return 0          # EVERY other status, including "blocked"
```

`_outcome_status` (`:232-244`) carries the docstring *"Report the pipeline outcome literally; never default to success."* The caller defeats that intent one level up.

Full chain:

```
run_pipeline_agent.py:515        return 0
  -> Start-GameTaskAgent.ps1:318  if ($AgentExitCode -ne 0) { throw }   -> no throw
  -> host_worker_launcher.py:105  return int(completed.returncode)      -> pure pass-through
  -> polling_orchestrator._reap_workers (:1353)  emits worker_finished for rc 0
```

Journal: **NSC-913 `worker_finished returncode=0` at 22:41:16** while its `crew_status` was `"blocked"`. The scheduler freed capacity and continued as though the task had succeeded. See **B4**.

## A5. Docker serialization — partly REFUTED, do not assert it

**Severity: Medium (performance). Status: mechanism REFUTED; degradation CONFIRMED; cause UNPROVEN.**

Refuted:
- No fixed `container_name` in `compose.yaml`. Concurrent `docker compose run --rm` produce uniquely suffixed containers — observed live: `nosafecircle-claude-exec-run-6ca3cf44b589`. No name-collision serialization.
- Host: **22 logical CPUs, 31 GB**; Docker reports 22 CPUs. Local CPU starvation at 5–6 workers is implausible.

Shared surfaces that *could* contend (not proven):

```
execution_bridge.py:194        compose_project default "nosafecircle"
execution_bridge.py:265-271    docker compose -p nosafecircle run --rm -T <provider>-exec
codex_supervisor.py:317        same project name for every supervisor turn
compose.yaml                   shared named volumes claude-config / codex-config
compose.override.yaml          shared external volume task-supervisor-codex-config
```

Container limits, inspected live: `CpuQuota 0 / NanoCpus 0 / Memory 0` on all three containers against a 22-CPU / 31 GiB host; `docker stats` showed the live exec container at 27.33% of one CPU and 224 MiB. Nothing is resource-capped.

### A5.1 CORRECTION — my preliminary contention conclusion was wrong

My preliminary note reported **Pearson r = 0.733** between concurrent workers and *seconds per 100k input tokens*, and read it as a contention signal. **That was an artifact and is withdrawn.** Normalizing by prompt size divides out the fixed per-call latency floor (container start + provider time-to-first-token), so small-prompt calls inflate the ratio. Decomposing each cycle into its two real phases gives the correct picture:

| Phase | 22:22 → 22:47 | Monotone? | r vs active workers | Session total |
|---|---|---|---|---|
| Host **observation phase** (`poll_started` → `architect_started`) | **40.2 s → 138.5 s** | **yes, strictly** | **0.883** | **901 s** |
| Architect call (`architect_started` → `architect_completed`) | 81.1 s → 126.7 s (min 46.7) | **no** | 0.336 | 832 s |

Raw architect duration is noisy and non-monotone: the 81.1 s call ran with **zero** concurrent workers and was slower than the calls at 3, 4, 5 and 6 workers; the slowest call (126.7 s) had the **smallest** portfolio (1). Neither contention nor prompt growth explains the architect timings — provider-side latency variance is the only hypothesis they support.

**The real finding: the host-side observation phase is the systematically degrading cost, and it is the larger of the two (901 s vs 832 s).** It grows 3.4× across the session. That growth is **A7(b)** — two full Issue sweeps per poll — multiplied by a steadily growing number of open managed Issues as each worker creates and updates its own. A7(b) is therefore promoted from "waste" to **the dominant, compounding latency driver**, and is the highest-value performance fix in this report (see **B2**).

**Verdict on the original question:** Docker is **not** serializing architect and worker calls. Two Docker-level hazards do exist but are blast-radius concerns, not throughput serializers — a single shared read-write CLI credential volume across all concurrent provider containers (`compose.yaml:61`), and one fixed compose project name reused from every checkout.

## A6. CRLF smoke-test failure hides `11df3aa`'s own regression test

**Severity: High. Status: REPRODUCED and root-caused in isolation.**

```
$ python Pipeline/ExecutionCrew/tests/execution_crew_smoke_test.py
AssertionError at execution_crew_smoke_test.py:341
  assert (apply_clone/NEW_IMPL).read_bytes()==b"public class EnemyHealth { public int Health; }\n"
```

Root cause, proven in an isolated scratch repo: the repository **has** a `.gitattributes`, but it contains only

```
Pipeline/TaskGraph/evidence/**/artifacts/*.log -whitespace
```

— **no `text` or `eol` rule at all**. Global `core.autocrlf=true` therefore governs, and `git clone` writes CRLF into the working tree. Isolated reproduction: committed blob is LF, cloned working tree is `\r\n`.

**The most important consequence:** line 341 executes *before* lines 725–726, which are the `normalized_agent_blockers` assertions that `11df3aa` added. **The commit's own regression test never runs on Windows.** The fix it ships is currently unverified on the platform where the bug occurred.

**Do not fix with a repo-wide `* text=auto eol=lf`.** `compose.yaml` deliberately sets `core.autocrlf=true` in *every* container (`GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0`) so a clean Windows host tree is also clean inside Linux containers, and `unity_meta_bytes()` is GUID/hash-bound.

**Verified surgical fix:** make the test's own throwaway repos EOL-deterministic using the mechanism the repo already uses in compose — `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=core.autocrlf`, `GIT_CONFIG_VALUE_0=false`. I confirmed in isolation that the clone then yields LF and satisfies the assertion. This is test-local and cannot affect the real repository or container semantics.

### A6.1 REFINEMENT — the root cause is deeper, and production already solves it

Verification found two earlier causes than the `.gitattributes` gap, and a better fix framing:

| File:line | Defect |
|---|---|
| `execution_crew_smoke_test.py:22` | the `write()` helper omits `newline=""`, so Windows text mode writes **CRLF into every synthetic fixture at creation** |
| `execution_crew_smoke_test.py:338` | the verification clone omits the `core.autocrlf=false` hardening that **production `clone_exact` already applies** |
| `execution_crew_smoke_test.py:1350` | thirteen further raw `Path.write_text()` calls share the same defect |

**Preferred fix, revised:** rather than introducing a new environment mechanism, **align the test with the hardening production already performs** — apply the same `core.autocrlf=false` that `clone_exact` uses, and pass `newline=""` in `write()`. My `GIT_CONFIG_COUNT` approach works and is verified, but matching the existing production path is the smaller, more consistent change and removes the whole class rather than one assertion.

## A7. Other waste and correctness

**A7(a) — Do NOT "fix" the pagination; it is already cached.**
`dispatch_plan.py:751-789` `_PlanScopedIssueBackend` caches `list_issues` once per plan and `get_comments` per Issue, and `get_issue` correctly invalidates **and re-appends** a still-open Issue (`:775-784`). I checked this specifically because I suspected a fail-open; it is correct. **This candidate finding is refuted.**

**A7(b) — Real waste: the reservation scan bypasses that cache. Severity: Medium.**

```
polling_orchestrator.py:1297-1301  reservation_observer = lambda: observe_durable_integration_reservations(
                                       source=..., checkout_root=..., worker_id=...)   # no backend=
                            :624   selected_backend = backend or GhIssueBackend(...)   # FRESH backend
                            :629   for issue in selected_backend.list_issues():        # second full sweep
```

Per poll: **two independent full paginated listings and two `get_comments` sweeps**, and — worse — **two different GitHub snapshots observed within one poll** (reservations at `:1769`, plan at `:1821`). The reservation scan and the dispatch plan can disagree about the world. See **B2**.

**A7(c) — Consistency-retry budget starvation. Severity: Medium.**

```
issue_workflow_store.py:485-486  def _consistency_deadline(): return time.monotonic() + sum(RESERVATION_CONSISTENCY_DELAYS_SECONDS)   # 7.0 s
                         :755    consistency_deadline = _consistency_deadline()   # ONCE, before the loop
                         :511-516 sleeps min(delay, remaining) inside a PER-ISSUE loop
```

One 7-second budget is shared across every Issue in the scan, and the first skewed Issue can consume all of it. Issues later in the listing get little or no retry. This is a side effect of the fix for the earlier per-Issue amplification problem. See **B6**.

**REFINEMENT — worse than stated.** `_resource_conflicts_classified` is invoked **once per candidate**, so the 7 s deadline is **re-armed per candidate**, not once per poll. Across a 60-candidate plan the worst-case consistency stall is ~14× what a single-scan reading suggests. Both facts hold together: the budget is shared *within* a scan (starving late Issues) and *re-armed across* scans (multiplying total stall). B6 addresses both — the scan-scoped budget object must be threaded across candidates, not re-minted.

**A7(d) — Near-miss fatal scheduler shutdown. Severity: High.**

```
22:29:54  scheduler_wait_observation_failure  consecutive=1/3
          "managed Issue #42 is invalid: workflow state label mismatch:
           expected 'nsc-state:human-action', found ['nsc-state:agent-ready']"
22:30:03  scheduler_wait_observation_failure  consecutive=2/3
          "managed Issue #42 is invalid: state_version does not match workflow event count"
22:30:14  scheduler_observation_recovered     previous_consecutive_failures=2
```

One more failed poll would have produced `reservation_observation_failed fatal=True` — all admissions stop plus a 30-minute drain.

Root cause of the label mismatch: `pass_and_resume_task.py:509-512` writes **labels only**:

```python
desired_labels = [l for l in snapshot.labels if l not in ALL_STATE_LABELS] + ["nsc-state:agent-ready"]
backend.update_issue(snapshot.issue_number, labels=desired_labels)
```

Every normal transition writes body **and** labels in one call (`issue_workflow_store.py:986-989`). See **B3**.

**A7(e) — ExecutionCrew prompt cost. Severity: Medium.**
NSC-913 used **508,343 input tokens over 3 invocations** to create one C# file containing one constant. The `test_author` alone used **219,442 input tokens and made zero changes**.

## A8. Additional findings from adversarial verification

Findings the verification pass surfaced that my preliminary sweep missed. The first two I re-verified personally.

### A8.1 `--exclude-task-id` does not bind on the resume path — Severity: Critical — [REPRODUCED]

```
polling_orchestrator.py:786   agent_ready = issue_workflow.list_agent_ready()      # NO exclusion filter
                       :815   plan_dispatch(..., excluded_task_ids=excluded_task_ids)  # FRESH POOL ONLY
                       :880   selected = agent_ready[0]                            # no exclusion check
```

An operator-excluded task that happens to be `agent_ready` is still admitted through the resume slot. `--exclude-task-id NSC-042` therefore does **not** protect NSC-042.

This is a direct operator-boundary violation: `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md` documents this exact flag as the mechanism for *"a bounded rehearsal that must leave a legitimate task untouched"*. The live session passed `NSC-042` plus `NSC-921`…`NSC-990` on every poll.

**Fix:** filter `agent_ready` by `excluded_task_ids` at `:786` before `agent_ready[0]` is chosen, and assert the resume task is not excluded at the admission point.
**Test:** `test_excluded_task_id_is_not_admitted_via_resume_slot` — an excluded task that is valid `agent_ready` must yield `no_safe_work`, not a launch.

### A8.2 The scheduler's entire test suite runs in no CI workflow — Severity: High — [REPRODUCED]

`grep -rn "polling_orchestrator_smoke_test" .github/workflows/` returns **nothing**, while `task-review-agent-deterministic.yml` alone registers 41 other smoke tests. All 59 scheduler tests — including the fatal-drain behavior added in `983ba6a` — are unprotected by CI.

**Fix:** register `Pipeline/TaskReviewAgent/tests/polling_orchestrator_smoke_test.py` in `task-review-agent-deterministic.yml`.
**Test:** extend `ci_workflow_split_smoke_test.py`, which already pins the registered-test list, to require the scheduler suite.

### A8.3 Only `agent_ready[0]` is ever offered — Severity: High — [AGENT-CONFIRMED]

`polling_orchestrator.py:880` takes the first agent-ready Issue only. Every other human-approved agent-ready Issue is invisible to the scheduler for that poll, compounding **A3**: not only can the architect override the resume, but a backlog of approved work is never even presented. B3's deterministic pre-architect admission should iterate the full agent-ready set.

### A8.4 Concrete composition of the oversized prompts — Severity: High — [AGENT-CONFIRMED]

The measured token costs in A2 and A7(e) decompose as:

| File:line | Payload |
|---|---|
| `Pipeline/ExecutionCrew/prompts.py:138` | full GDD inlined verbatim — **81,699 bytes** into *every* role prompt |
| `Pipeline/ExecutionCrew/prompts.py:108` | auditor prompt carries the entire committed task catalog — **55,961 bytes = 37%** of the prompt |
| `Pipeline/TaskDecomposition/context_builder.py:343` | decomposition ships 90 full sibling contracts — **245,744 bytes = 60%** of a 418,966-char context |
| `Pipeline/TaskReviewAgent/architect_preflight.py:888` | architect re-sends full task contracts every poll — **175,358 of 208,610 input tokens** |

This is the actionable answer to "what is in the 208k/219k tokens", and it confirms A2's conclusion from the opposite direction: the payload is dominated by *invariant* context re-sent per call, not by portfolio size.

### A8.5 Deterministic short-circuit unreachable from the implementation loop — Severity: High — [AGENT-CONFIRMED]

`downstream_determinism.py:919` — the zero-argument provider short-circuit never fires from the implementation supervisor loop; **13 of 68 supervisor provider calls decided an action that was already forced, at 231,308 input tokens.** Related: no no-progress circuit breaker exists (`openai_pipeline.py:311`) — 21 consecutive provider calls occurred without state progress.

### A8.6 Exit-code problem is broader than one line — Severity: High — [AGENT-CONFIRMED]

`host_decomposition_launcher.py:243` has **eight distinct `return 0` outcomes, five of which are not success**. Any exit-code contract (B4) must cover the decomposition launcher, not only `run_pipeline_agent.py:515`.

### A8.7 Existing tests cannot detect the reported failures — Severity: Medium — [AGENT-CONFIRMED]

| File:line | Problem |
|---|---|
| `tests/polling_orchestrator_smoke_test.py:710` | the resume-priority test cannot detect starvation — `FakeArchitect` always selects rank 1, so **A3 was structurally untestable** |
| `tests/host_decomposition_launcher_smoke_test.py:93` | `test_stale_authorized_plan_releases_to_fresh_decomposition` asserts nothing — its body was emptied |
| `tests/downstream_determinism_smoke_test.py:66` | passes a pre-narrowed action menu no production caller ever produces, so it passes vacuously |

Every Part B regression test must be checked against this pattern: a test that cannot fail before the fix proves nothing.

### A8.8 Further scheduler waste — Severity: Medium — [AGENT-CONFIRMED]

- `issue_workflow_store.py:779` — `resource_conflicts` re-parses every open Issue's full event chain **once per candidate**.
- `committed_tasks.py:43` — `load_committed_task` has no memoization; ≥60 `git show HEAD:Tasks/*.yaml` subprocesses per plan.
- `polling_orchestrator.py:1637` — the architect cooldown key omits the integration fingerprint, so freed capacity cannot trigger re-analysis.
- `polling_orchestrator.py:1466` — the deterministic prologue re-observes every active checkout with `git` on every poll.
- `polling_orchestrator.py:637` — the reservation observer uses the non-retrying `_snapshot`, discarding the codebase's own consistency retry and burning the fatal-failure budget (this is the mechanism behind **A7(d)**).

---

# PART B — Extended design answers

Design proposals. Not implemented. Each names the exact insertion points in `11df3aa`.

## B1. Architect batching: one call, an ordered batch of admissions

### B1.1 What is actually single-item today

The multi-candidate machinery **already exists**. Only two things collapse it to one:

```
polling_orchestrator.py:2010-2015  portfolio_analysis = self.architect_runner(...)
                        :2016      selected_advisory = portfolio_analysis.advisory      # ONE advisory
                        :2044      candidates = ((selected_entry[0], selected_entry[1]),)  # 1-tuple
                        :2047      for candidate, resume_phase in candidates[:MAX_CANDIDATES_PER_POLL]:
                        :2312          return PollCycleResult("worker_launched", ...)   # returns inside the loop
```

`MAX_CANDIDATES_PER_POLL = 1000` (`:128`) is a second dead bound — the list is always length 1. The loop already has per-item `considered` dedup, conflict `continue`, and identity revalidation. **The batching change is therefore small: widen `:2044` and turn the `return` at `:2312` into a `continue`.**

### B1.2 Smallest safe contract

Reuse `ARCHITECT_ADVISORY_SCHEMA` (`architect_preflight.py:180-207`) **unchanged**. Its `parallel_recommendation` enum is already `["start","wait","human_review"]` — a per-item disposition. Wrap it:

```python
ARCHITECT_BATCH_SCHEMA = _strict_object({
    "schema_version": _STRING,                 # "1.0"
    "source_head": _STRING,                    # MUST equal plan.source_commit
    "batch_rationale": _STRING,
    "considered": _array(_strict_object({      # EVERY portfolio pair, exactly once
        "task_id": _STRING,
        "work_type": {"type":"string","enum":["implementation","decomposition"]},
        "disposition": {"type":"string","enum":["admit","wait","human_review","ineligible"]},
        "rationale": _STRING,
    })),
    "admissions": _array(ARCHITECT_ADVISORY_SCHEMA),   # ordered; subset of considered[disposition=admit]
})
```

`admissions` is the ordered launch list. `considered` gives the explicit disposition for **every** item the brief asks for, so nothing is silently dropped.

### B1.3 Host-side validation (fail closed, before any launch)

1. `source_head == plan.source_commit`, else discard the whole batch.
2. Every `(task_id, work_type)` in the revalidated `mixed_portfolio` appears in `considered` **exactly once**; any missing or extra pair → discard batch (`ArchitectPreflightError`).
3. Every `admissions[i]` has a matching `considered` entry with `disposition == "admit"`.
4. No duplicate `task_id` in `admissions`.
5. `len(admissions) <= max_workers - len(active_assignments)`; truncate with an explicit `batch_truncated` event (no silent caps).
6. Pairwise disjointness: for each ordered pair, run the existing `detect_deterministic_conflict` on their `predicted_change_surface`. On the first conflicting item, **truncate at that item** — never reorder, because order is the architect's ranking.

### B1.4 The launch loop — revalidate before every launch

This is the safety-critical part. Replace the single-shot return with:

```
batch_id = analysis_id
for index, advisory in enumerate(admissions):
    # (1) capacity
    if len(self.active_assignments) >= self.max_workers:            -> break  ("capacity_full")
    # (2) global reality check -- DISCARD the rest if the world moved
    if _git_head(self.source) != plan.source_commit:                -> break  ("source_moved")
    # (3) fresh per-admission GitHub snapshot (see B2)
    cache = _PlanScopedIssueBackend(GhIssueBackend(source_root))
    reservations = self._integration_reservations(backend=cache)     # may raise -> break
    subplan     = self.plan_builder(..., backend=cache)
    # (4) is this task STILL admissible?
    if advisory.task_id not in eligible(subplan):                    -> continue ("stage2_withdrew")
    if advisory.task_id in self.excluded_task_ids | set(active):     -> continue
    # (5) contract identity unchanged
    if task_contract_sha256 != advisory.task_contract_sha256:        -> continue ("contract_changed")
    # (6) conflict against CURRENT reservations, not batch-time ones
    if detect_deterministic_conflict(...) is not None:               -> continue ("conflict")
    # (7) launch
    launch(advisory); emit worker_launched(batch_id=batch_id, batch_index=index)
    # (8) the child WILL mutate its Issue -> the snapshot is now stale
    cache = None
emit("architect_batch_completed", batch_id, launched, skipped, discarded, reasons)
```

**Distinction the brief asks for:** a *per-item* failure (steps 4–6) `continue`s to the next admission; a *global* reality change (steps 1–2, or a reservation observation failure) `break`s and **discards the remaining batch**. Discarded items are simply re-planned next poll — the batch is advisory, never authority.

### B1.5 Why this beats shrinking the portfolio

Measured (A2): cost is invariant-context-dominated, not portfolio-dominated — the `portfolio_size=1` call cost 258k tokens, the most of the session. Batching amortizes that one fixed cost across N launches instead of paying it per launch.

| | Today | Batched (N≈5) |
|---|---|---|
| Architect calls for 11 launches | 11 | ~2–3 |
| Input tokens | 1,648,820 | ~300–450k |
| Architect wall time | 803 s | ~150–250 s |
| Ramp 0→6 workers | 25.6 min | ~3–5 min |

Only after batching does `--architect-max-invocations-per-poll` become meaningful: a poll may legitimately call the architect again if the batch is exhausted while capacity remains, and the cap then genuinely binds.

### B1.6 Regression tests (deterministic; fake architect runner, fake processes)

1. `test_batch_fills_available_capacity_in_one_architect_call` — `max_workers=5`, batch of 5 → 5 `worker_launched`, exactly **1** `architect_started`.
2. `test_batch_revalidates_reservations_between_launches` — a fake observer that returns a conflicting reservation after launch #2 → launches 1–2 succeed, #3 skipped with `conflict`, batch continues to #4.
3. `test_source_head_move_discards_remaining_batch` — HEAD changes after launch #1 → exactly 1 launch, `architect_batch_completed.discarded > 0`.
4. `test_batch_missing_disposition_is_rejected_before_any_launch` — a `considered` list omitting one portfolio pair → zero launches, fatal, no process spawned.
5. `test_batch_admission_outside_portfolio_is_rejected` — existing `:2030` invariant, extended to every element.
6. `test_batch_truncated_at_capacity_emits_explicit_event` — no silent truncation.
7. `test_conflicting_pair_truncates_and_does_not_reorder`.
8. `test_per_poll_architect_cap_now_binds` — cap 1, batch exhausted with capacity left → second call refused with `architect_budget_exhausted`.

## B2. One coherent GitHub snapshot per admission

### B2.1 Exact object flow today

```
poll_once:1769  reservations = self._integration_reservations()
                  -> self.reservation_observer()                       [set :1297-1301, NO backend arg]
                     -> observe_durable_integration_reservations:624   selected_backend = GhIssueBackend(...)   # FRESH #1
                     -> :629  list_issues()  + _snapshot -> get_comments per Issue
poll_once:1821  plan = self.plan_builder(source=, worker_id=, excluded_task_ids=)
                  -> plan_poll_dispatch:778  cached_backend = _PlanScopedIssueBackend(GhIssueBackend(...))  # FRESH #2
                     -> list_agent_ready() + plan_dispatch(...)  all through the cache
```

Two backends, two sweeps, two snapshots taken at different instants inside one poll.

### B2.2 Narrowest patch

The seam already exists — `observe_durable_integration_reservations` **already accepts `backend=`** (`polling_orchestrator.py:611`). Three small changes:

1. `plan_poll_dispatch` gains one optional parameter `backend: IssueBackend | None = None`; line `:778` becomes
   `cached_backend = backend or _PlanScopedIssueBackend(GhIssueBackend(source_root=root))`.
2. `PollingOrchestrator._integration_reservations` gains `backend=None` and forwards it to `self.reservation_observer`; the lambda at `:1297-1301` gains a `backend` parameter.
3. `poll_once` (and the B1 batch loop) constructs **one** `_PlanScopedIssueBackend` and passes the same object to both.

Net effect per admission: **one** `list_issues()` and **one** `get_comments` per Issue instead of two, and both stages reason over an identical snapshot.

### B2.3 Staleness safety — the part that must not be got wrong

- **Scope the cache to one admission attempt, not one poll.** With B1 launching several workers per poll, a poll-scoped cache would be stale for admissions 2..N.
- **Discard the cache immediately after each launch** (B1 step 8). The child calls `acquire_agent_lease` and mutates its Issue; any snapshot predating that is invalid.
- **Mutation is already impossible through the cache.** `_PlanScopedIssueBackend.create_issue` / `update_issue` / `add_comment` / `ensure_labels` all raise (`dispatch_plan.py:791-810`), so sharing it cannot let the scheduler mutate an Issue. This preserves the existing `test_scheduler_source_has_no_issue_or_claim_mutation_calls` guarantee.
- **Consistency re-reads still bypass the cache correctly.** `get_issue` (`:775-784`) performs a live read, drops the stale entry, and re-appends the fresh one when still open — so the B6 retry sees live data even through a shared cache.

### B2.4 Regression tests

1. `test_one_admission_performs_exactly_one_issue_listing` — counting backend; assert `list_issues` calls == 1 and `get_comments` calls == N, not 2N.
2. `test_reservation_scan_and_plan_observe_the_same_snapshot` — backend whose second `list_issues()` would differ; assert both stages see snapshot #1.
3. `test_cache_is_discarded_after_each_launch` — assert a fresh `list_issues` occurs before admission #2.
4. `test_shared_cache_still_rejects_mutation` — assert `update_issue` through the shared cache raises.
5. `test_consistency_reread_bypasses_cache` — assert `get_issue` hits the live backend even when the listing is cached.

## B3. The PASS/label transition window

### B3.1 Why the mismatch is guaranteed, not rare

```
pass_and_resume_task.py:509-512   writes ONLY the label nsc-state:agent-ready
        |
        v  GitHub `labeled` webhook
.github/workflows/nsc-issue-workflow.yml
        on: issues: types: [labeled]
        if: github.event.label.name == 'nsc-state:agent-ready'
        steps: checkout@v4 -> setup-python@v5 -> python issue_state_action.py   # writes body + hashed event
```

The divergence window is **the entire GitHub Actions dispatch + checkout + Python setup time** — typically 30–90 s, minutes under runner contention. It is architecturally guaranteed by using a label write as an RPC trigger to an asynchronous Action.

Meanwhile `_snapshot` marks the Issue invalid (`expected 'nsc-state:human-action', found ['nsc-state:agent-ready']`), the reservation scan raises, and the scheduler burns a poll. With real polls taking 1–2 minutes and `max_consecutive_observation_failures=3`, that window can plausibly span three polls. The journal reached **2/3**.

### B3.2 Recommendation — both halves are needed

**(A) Make the helper path atomic.** `pass_and_resume_task.py:512` should perform the canonical transition instead of a label-only write, using the same path every other transition uses:

```
issue_workflow_store.py:977-989   backend.add_comment(issue, event_comment)
                                  backend.update_issue(issue, body=update_issue_body(...),
                                                       labels=labels_for_state(next_state.state, labels))
```

This **preserves the hashed event contract** precisely because it goes through the existing `transition()` API that computes `state_version`, `last_event_id`, and the event hash chain — it does not hand-write a body. Body and labels then land in one `gh` API call, so the label-mismatch class disappears for this path. The Action must become **idempotent**: on trigger, if the body already sits at the target state with a matching final event, exit 0 without writing.

**(B) The human path is irreducible — define a pending-transition state.** A human applying `nsc-state:agent-ready` in the GitHub UI supplies only a label; GitHub offers no transactional label+body+comment write. So recognize the state narrowly.

`_snapshot` classifies a mismatch as `PENDING_TRANSITION` only if **all** hold:

1. The body parses to a valid state `S` **and the event chain is otherwise fully coherent** (`state_version == len(events)`, `last_event_id` matches, hashes verify) — the *only* defect is the label set.
2. The label set is exactly one state label `L`, and `L != labels_for_state(S)`.
3. `(S.state -> L.state)` is a **legal transition** in the committed state machine.
4. **No event comment exists yet for `L.state`** — proving the Action has not run.
5. The divergence is **younger than a bounded age** (e.g. `PENDING_TRANSITION_MAX_AGE_SECONDS = 600`), from the Issue's `updated_at` or the `labeled` timeline event.

Semantics of `PENDING_TRANSITION` — this is the precise answer to "don't count it toward fatal":

| Question | Answer |
|---|---|
| Valid for lease/selection/resume? | **No** — still fail-closed. Do not resume it. |
| Does it still reserve its exclusive resources? | **Yes** — fail-closed for conflicts. |
| Does it increment `consecutive_observation_failures`? | **No.** Emit `issue_pending_transition` instead of `scheduler_wait_observation_failure`. |
| Past `MAX_AGE`? | Degrades to a genuine invalid state, counts toward fatal, fails closed. |

The age bound is what keeps this from becoming a hole: a genuinely stuck, forked, or tampered Issue still fails closed once the legitimate window expires.

Note the second journal failure (`state_version does not match workflow event count`, 22:30:03) is a *different* class — that one is the retryable skew, and it still surfaced because of the budget starvation in **B6**.

### B3.3 Regression tests

1. `test_pass_and_resume_writes_body_labels_and_event_atomically` — assert exactly one `update_issue` carrying both body and labels, plus one `add_comment`; assert the event chain still validates.
2. `test_issue_state_action_is_idempotent_when_body_already_advanced` — Action re-run makes no second event.
3. `test_label_ahead_of_body_is_pending_not_invalid` — assert `PENDING_TRANSITION`, `issue_pending_transition` emitted, and `consecutive_observation_failures` **unchanged**.
4. `test_pending_transition_still_reserves_resources` — an overlapping candidate is still blocked.
5. `test_pending_transition_past_max_age_fails_closed_and_counts` — advance the injected clock past `MAX_AGE`.
6. `test_illegal_label_pair_is_invalid_not_pending` — e.g. body `complete`, label `agent-working` → invalid, counts.
7. `test_pending_transition_with_existing_target_event_is_invalid` — condition 4 violated.

## B4. Child completion authority — exit code **and** artifact

### B4.1 A strict exit-code allowlist alone is NOT sufficient

Four concrete reasons, all grounded in this codebase:

1. **No identity.** An exit code cannot prove *which run* produced it. A recycled PID, an orphan from a prior scheduler session (the runbook states v1 does not adopt prior processes), or an unrelated process cannot be distinguished from the intended child.
2. **The chain is a pure pass-through.** `run_pipeline_agent.py:515` → `Start-GameTaskAgent.ps1:318` → `host_worker_launcher.py:105`. Any layer can produce `0` for reasons unrelated to the workflow outcome.
3. **Codes collide with OS-supplied codes.** `Start-GameTaskAgent.ps1`'s `throw` yields PowerShell exit 1; a console control event yields `0xC000013A` (`3221225786`, observed repeatedly in the NSC-912 logs); `taskkill` yields 1. Hand-assigned semantic codes cannot be told apart from these.
4. **8 bits is lossy** — no room for status plus reason plus identity.

**Therefore: exit code is the fast path; the artifact is the authority.** The scheduler treats a worker as successful only when **both** agree. Any disagreement, or a missing artifact, is a failure. Fail closed.

### B4.2 Exit-code allowlist

| Code | Meaning | Scheduler action |
|---|---|---|
| `0` | Success terminal — `human_action_required` **or** `completed` | `worker_finished` (artifact disambiguates which) |
| `3` | `blocked` — deterministic, needs human/repair | `worker_blocked` (new event; frees capacity, **not** counted as completed work, **not** fatal) |
| `4` | `no_safe_work` / idle | `worker_idle`; no work claimed |
| `2` | contract/operational error (existing convention) | `worker_failed`, fatal |
| anything else | unknown, including OS-supplied codes | `worker_failed`, fatal |

Change required: `run_pipeline_agent.py:503-515` must map `status` through an explicit table rather than falling through to `return 0`.

### B4.3 Minimum artifact

The worker **already writes** `run.json` carrying `schema_version`, `run_id`, `task_id`, `worker_id`, `started_at_utc`, and log paths. Add a sibling `run_result.json`, written **last**, atomically (`tmp` + `os.replace`):

| Field | Purpose |
|---|---|
| `schema_version` | contract versioning |
| `run_id` | must equal `run.json`'s |
| `worker_id` | **the anti-stale key** — must equal the scheduler's generated `polling-worker-<task>-<uuid4 hex[:12]>`, which is unguessable and unique per admission |
| `task_id` | must equal the admitted task |
| `source_head` | commit the run was admitted at |
| `task_contract_sha256` | binds to the exact contract revision |
| `terminal_status` | enum: `human_action_required` \| `completed` \| `blocked` \| `no_safe_work` \| `error` |
| `outcome_authority` | existing concept, e.g. `committed_branch_to_human_unity_handoff` |
| `issue_number` | cross-check |
| `exit_code` | what the child is about to return |
| `pid` | `os.getpid()` — must equal the pid the scheduler recorded |
| `finished_at_utc` | must fall inside the child's observed lifetime |

### B4.4 Scheduler validation — all must pass

1. Path is **derived by the scheduler** from `(output_root, task_id, run_id)` — never read from child-supplied text.
2. `worker_id == assignment.worker_id`.
3. `task_id == assignment.task_id`; `pid == assignment.pid`.
4. `run_id` matches the `run.json` in the same directory.
5. File mtime **>** `assignment.start_time_utc` — rejects a leftover artifact from a prior run of the same task.
6. `exit_code == observed returncode`.
7. `terminal_status` in the success set → `worker_finished`; in `{blocked, error}` → `worker_blocked` / `worker_failed`.
8. **Missing, unparseable, or mismatched artifact with exit 0 → `worker_failed`.** This is exactly the NSC-913 hole closed.

**Why not re-read the Issue after exit:** GitHub is eventually consistent (the whole premise of `983ba6a`), so a post-exit read can lag the child's final write; and the Issue is mutated *by the child*, so reading it reintroduces precisely the stale-data dependency the brief asks to avoid. A locally-written, identity-bound artifact has neither problem.

### B4.5 Regression tests

1. `test_blocked_run_exits_nonzero_and_is_not_worker_finished` — the NSC-913 reproduction.
2. `test_exit_zero_without_result_artifact_is_failure`.
3. `test_stale_artifact_from_prior_run_is_rejected` — same `task_id`, different `worker_id`.
4. `test_artifact_pid_mismatch_is_rejected`.
5. `test_artifact_mtime_before_launch_is_rejected`.
6. `test_human_action_required_and_completed_both_succeed_via_artifact`.
7. `test_exit_code_and_artifact_disagreement_fails_closed`.
8. `test_scheduler_never_reads_child_supplied_artifact_path`.

## B5. One boundary-level structured-output normalization

### B5.1 Where the boundary goes

Two candidates:

- **(a) AgentRuntime** — `agent_runner.py:248-250`, right after `validate_instance`. A single choke point for every role, but it is provider-generic and would apply to non-crew consumers (the architect advisory, decomposition) that must **not** be normalized.
- **(b) ExecutionCrew** — one function applied at the four `thaw_json` sites: auditor `:1202`, implementer `:1244`, test_author `:1273`, validator `:1293`.

**Recommend (b),** with the spec declared beside the schemas in `Pipeline/ExecutionCrew/schemas.py`. Sentinel tolerance is a crew-role semantic, not a runtime semantic; keeping it out of AgentRuntime avoids silently altering architect/decomposition outputs. A later `request.output_normalization` field could push it into AgentRuntime if other crews need it.

### B5.2 Declarative spec

```python
ROLE_OUTPUT_NORMALIZATION = {
  "implementer":  (("blockers", STRING_LIST), ("claimed_changed_paths", PATH_LIST)),
  "test_author":  (("blockers", STRING_LIST), ("claimed_changed_paths", PATH_LIST)),
  "validator":    (("blocking_issues", OBJECT_LIST(("path","issue","required_fix"))),),
  "contract_locality_auditor": (...),
}

def normalize_role_structured_output(role, output) -> tuple[dict, dict]:
    """Return (normalized_output, discarded) -- never mutates input, never reorders."""
```

### B5.3 Conservative sentinel recognition

```python
def _is_empty_sentinel(text: str) -> bool:
    t = unicodedata.normalize("NFKC", text).replace("\u00a0", " ").strip()
    if len(t) > 64:            # a real blocker is never this short-form
        return False
    while t[:1] in "([{\"'" and t[-1:] in ")]}\"'":
        t = t[1:-1].strip()
    t = t.strip(" \t-–—•").rstrip(".!;,:…").strip()
    t = " ".join(t.split()).casefold()
    return t == "" or t in _SENTINELS
```

`_SENTINELS` (**whole-string only, never substring**): `none`, `no`, `n/a`, `na`, `nil`, `null`, `nothing`, `empty`, `no blocker`, `no blockers`, `none identified`, `none found`, `no blockers found`, `no blockers identified`, `not applicable`, `no issues`, `no issues found`, `nothing to report`, `no changes`, `no changes were made`, `none - no changes were made`.

**Conservatism guarantees — how a real blocker is never discarded:**

1. **Whole-string equality only.** `"None of the approved implementation paths permit the required change"` never matches — this is the single most important property.
2. **Length guard** (64 chars) as belt-and-braces.
3. **Mixed lists keep every non-sentinel entry** (the existing `11df3aa` behavior).
4. **Nothing is dropped silently.** Every discarded entry is recorded in the role record as `normalized_discarded_<field>`, so `crew_result.json` remains a complete audit trail.
5. **Deterministic scope reasons are untouched.** Normalization removes only a *self-reported* sentinel; `scope_check_reasons` from `incremental_check` / `source_revalidation` still stand on their own.
6. **`OBJECT_LIST` rule:** an entry is a sentinel iff **every** string leaf normalizes empty. `{"path":"(none)","issue":"Cannot compile X","required_fix":"(none)"}` is **kept**.
7. **`PATH_LIST` rule:** drop whole-string sentinels only. A remaining entry that is not a valid repo-relative path is **not** dropped — it is surfaced as a diagnostic, because it may indicate a genuine scope problem.
8. **Structural invariant:** `normalized(L)` is always a subsequence of `L` — never adds, reorders, or rewrites an element.

### B5.4 Regression cases

Exact NSC-913 reproduction:

1. `blockers=["(none)"]` → `[]`, discarded `["(none)"]`; crew reaches `review_ready`, not `blocked`.
2. Same response's `claimed_changed_paths=["(none - no changes were made)"]` → `[]` with a diagnostic recorded.

Punctuation / N-A variants — all → `[]`:

3. `["(none)"]`, `["None."]`, `["none"]`, `["NONE"]`, `["N/A"]`, `["n/a."]`, `["NA"]`, `["- none -"]`, `["  (No Blockers)  "]`, `["nil"]`, `["Nothing to report."]`, `["not applicable"]`, `["—"]`, `["\u00a0none\u00a0"]`

Anti-false-negative (must remain **UNCHANGED**):

4. `["None of the approved paths allow the required change"]`
5. `["none identified in the approved scope, but the meta guid is wrong"]`
6. `["N/A because the contract omits the target assembly"]`
7. `["Cannot compile", "(none)"]` → `["Cannot compile"]`, discarded `["(none)"]`

Validator objects:

8. `blocking_issues=[{"path":"(none)","issue":"(none)","required_fix":"(none)"}]` with `status="pass"` → `[]`, crew **not** rejected.
9. `blocking_issues=[{"path":"(none)","issue":"Missing meta","required_fix":"add meta"}]` → **kept**, crew rejected (fail-closed preserved).

Robustness:

10. Non-string / nested / `None` members → ignored, never raises.
11. Property test: for every list `L`, `normalized(L)` is a subsequence of `L`.
12. End-to-end crew replay of the exact NSC-913 `test_author` response → `crew_status == "review_ready"`.

## B6. The shared 7-second consistency deadline

**Problem.** `_consistency_deadline()` (`issue_workflow_store.py:485-486`) returns `monotonic() + 7.0`. It is computed **once** per scan (`:755`, and again for `list_human_action_required` at `:1758`) and shared across the whole loop, while `_consistent_snapshot` sleeps `min(delay, remaining)` inside a **per-Issue** loop (`:511-516`). The first skewed Issue can consume the entire budget; every later Issue gets none. That is unfair, and it is why the retryable skew at 22:30:03 still surfaced as a hard failure.

**Proposed: two-phase scan with a deferred retry queue.**

```
Phase 0 — sweep, NO sleeping:
    for issue in listing:
        snap = _snapshot(issue)
        if coherent: accept
        elif retryable_reason: snap = exact get_issue(n)      # delay 0, cheap
             if still incoherent: pending.append(n)
        else: fail closed now (unchanged)

Phase 1..K — shared backoff ladder (1s, 2s, 4s):
    for delay in RESERVATION_CONSISTENCY_DELAYS_SECONDS[1:]:
        if not pending or monotonic() > scan_deadline: break
        sleep(min(delay, scan_deadline - monotonic()))        # ONE sleep for the whole pending set
        for n in list(pending):                               # exact reads only
            if coherent_now(n): pending.remove(n)

After the ladder: remaining pending Issues take the existing fail-closed path.
```

**Properties:**

| Property | Today | Proposed |
|---|---|---|
| Total sleep per scan | ≤ 7 s | ≤ 7 s (unchanged) |
| Retry rounds for the *last* Issue in the listing | often 0 | 1 immediate + up to 3 backoff — same as the first |
| Sleep multiplied per Issue? | no, but budget is consumed serially | no — one sleep serves the entire pending set |
| Exact reads, worst case | unbounded-first-wins | `N + 3·min(|pending|, PENDING_RETRY_CAP)` |

Add `PENDING_RETRY_CAP` (e.g. 32) with an **explicit** `consistency_retry_truncated` event — no silent caps.

**Two interactions worth calling out:**

- **Exclude `PENDING_TRANSITION` (B3) from the retryable set.** It is not a skew; retrying it burns budget on a state that cannot converge until the Action runs, and it must not count toward fatal either.
- **When B2 lands, pass one scan-scoped budget object** (not a bare float) alongside the shared cache, so the reservation scan and `list_human_action_required` share **one** budget rather than each minting a fresh 7 s.

**Regression tests:**

1. `test_late_issue_gets_retry_budget` — 50 Issues, only the last skewed → it converges (today it does not).
2. `test_total_sleep_bounded_regardless_of_issue_count` — injected clock; assert ≤ 7 s for N=1 and N=200.
3. `test_no_per_issue_amplification` — counting backend; assert exact reads ≤ `N + 3·min(|pending|,cap)`.
4. `test_pending_retry_cap_emits_explicit_truncation_event`.
5. `test_pending_transition_is_not_retried_and_does_not_consume_budget`.
6. `test_persistent_incoherence_still_fails_closed_after_ladder`.

---

# PART C — Verification status and re-fetch procedure

## C1. Adversarial verification — COMPLETE

9 investigators across the seven areas raised **64 findings**; each was independently challenged by two refutation lenses (correctness; evidence-and-impact), producing **127 verdicts: 65 CONFIRMED, 9 PLAUSIBLE, 53 REFUTED**.

The high refutation count is the point of the exercise — roughly 40% of raised findings did not survive challenge and are not in this report.

**Negative results, recorded so they are not re-investigated:**

1. **`_PlanScopedIssueBackend` is correct.** I suspected `dispatch_plan.py:775-784` of dropping Issues on consistency re-read; it correctly re-appends a still-open Issue. Do not "fix" it.
2. **Docker is not serializing.** Every Docker-level mechanism in the original brief was disproved: no `container_name`, no `cpus`/`mem_limit`/`deploy` keys, `CpuQuota 0 / NanoCpus 0 / Memory 0` on all live containers, distinct one-off container slugs per `compose run`.
3. **My own `r = 0.733` contention signal was an artifact** and is withdrawn — see A5.1.
4. **Repeated GitHub pagination is largely already solved** by the plan-scoped cache; the defect is the reservation scan bypassing it, not the pagination itself.

**Provenance markers used in Part A:** **[REPRODUCED]** = I executed or derived it myself. **[AGENT-CONFIRMED]** = carried from a verification agent with a CONFIRMED verdict but not personally re-derived by me. A8.1 and A8.2 were re-verified by me directly.

## C2. Re-fetch and verify after Codex pushes

Not yet performed — `origin/review/orchestration-gauntlet-followup` is still at `11df3aa`, one commit ahead of `origin/main` @ `983ba6a`.

When Codex pushes, from `C:\NSC\ClaudeReview\NoSafeCircle` (never a rehearsal checkout):

```bash
git fetch origin review/orchestration-gauntlet-followup
git log --oneline 11df3aa..origin/review/orchestration-gauntlet-followup
git diff --stat 11df3aa origin/review/orchestration-gauntlet-followup
git diff 11df3aa origin/review/orchestration-gauntlet-followup
```

Verification checklist for the new diff:

1. **Does the ExecutionCrew suite now run to completion on Windows?** Until `execution_crew_smoke_test.py:341` passes, the `normalized_agent_blockers` assertions at `:725-726` never execute (A6). This gates the credibility of every claim about area 1.
2. Run the four suites I used as a baseline: `execution_crew_smoke_test`, `issue_workflow_smoke_test`, `polling_orchestrator_smoke_test`, `production_pipeline_smoke_test`. Baseline at `11df3aa`: the last three pass; the first fails at `:341`.
3. Confirm `codex_supervisor_smoke_test.py::test_docker_provider_envelope` — failing on `main` for a pre-existing, unrelated reason (global class patch from `696de7c`).
4. For each Part B area actually implemented, check the named regression tests exist and genuinely fail before / pass after.
5. Re-run the journal correlation against any new live run: architect calls vs worker launches (expect ≪ 1:1 if B1 landed), rank-1 vs selection (expect no override of an approved resume if B3/A3 landed), and `worker_finished` vs `crew_status` (expect no blocked-as-finished if B4 landed).

## C3. Summary of the two premises that did not survive checking

1. **"Merely shrinking the portfolio is not the fix"** — correct, and the measurement is stronger than the brief assumed: portfolio size and cost are *uncorrelated*; the `portfolio_size=1` call was the most expensive of the session (258,005 tokens). Batching, not trimming, is the fix (B1).
2. **"Repeated full GitHub pagination"** — largely already solved by `_PlanScopedIssueBackend`. The real defect is that the reservation scan constructs its own backend and bypasses that cache (A7b), producing two sweeps *and* two divergent snapshots per poll (B2).
