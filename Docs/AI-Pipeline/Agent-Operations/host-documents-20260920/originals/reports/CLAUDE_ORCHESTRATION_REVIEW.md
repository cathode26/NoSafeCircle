# Adversarial Review — Concurrent Orchestration Hardening

**Reviewer:** Claude (read-only adversarial review)
**Date:** 2026-09-03
**Checkout:** `C:\NSC\NSC\NoSafeCircle` (branch `main`, HEAD `79dc6a0`)
**Range reviewed:** `eb8fa69` → `79dc6a0`, plus the uncommitted working-tree diff
**Mode:** Read-only. No repository files edited, no commits, no branch changes, no GitHub calls, no Docker/provider jobs. Local deterministic tests only.

---

## 0. Summary

The two commits fix real problems and are directionally right. The uncommitted `pipeline_scope.py` change is a clear improvement and I recommend committing it. However I found **1 Critical, 6 High, 6 Medium and 6 Low** findings. Two of them are new fail-open / exit-code-masking holes introduced by `79dc6a0` itself; one is a pre-existing deterministic CI failure unrelated to this range.

The most important results:

- `79dc6a0` introduces a **silent fail-open** in the exclusive-resource reservation scan (C1). I reproduced it.
- The new scheduler drain **masks a fatal worker failure as exit code 0** when the operator presses Ctrl+C, and the drain loop has **no deadline** (H1, H2). I reproduced both.
- The scheduler's `child_policy` claim that "children were not killed" is **not supported by its test** and is contradicted by the rehearsal logs (H3).
- Scope facts do **not** yet expose "exactly the one relevant C# test" on the production repo: 26 of 60 contracts still receive **all 11** test files, via a matching branch the diff did not touch (H4).
- `codex_supervisor_smoke_test.py::test_docker_provider_envelope` fails deterministically on `main` and is wired into two CI workflows. It is **pre-existing and unrelated** to this range, but it is a genuine composition defect (H6).

---

## 1. Findings

### CRITICAL

#### C1 — Reservation scan silently fails open when the retry loses the Issue from one listing
**Files:** `Pipeline/TaskReviewAgent/issue_workflow_store.py:503-516`, `:766`, `:773`
**Status:** Confirmed defect (reproduced). Trigger frequency is a hypothesis.

`_reservation_snapshot()` returns `None` when the Issue number is absent from a *retry* `list_issues()` response (`issue_workflow_store.py:515`). The caller then does:

```python
snapshot = _reservation_snapshot(self.backend, issue)   # :766
...
if snapshot is None:
    continue                                            # :773
```

`continue` drops the Issue from the scan entirely — **no conflict, no `diagnostics` entry, no event**. Every other unusual condition in `_resource_conflicts_classified` produces either a conflict or a bounded diagnostic; this one produces nothing.

The docstring justifies this as "normally because another worker completed and closed it". That is true for a *genuine* close, because `list_issues()` is open-only (`:1989 → _list_issues_via_api("open")`) and the scan already skips CLOSED Issues. But the helper cannot distinguish a genuine close from a **transient absence**, and it chose the unsafe interpretation silently — inside a retry loop whose entire premise is that GitHub reads are transiently inconsistent.

Reproduction (in-memory backend; Issue stays `OPEN` + `nsc-state:agent-working` throughout):

```
holder Issue: OPEN ['nsc-state:agent-working']
Issue still OPEN at end? OPEN
conflicts: []
diagnostics: []
EXPECTED: conflict (open agent_working Issue reserves Assets/Scenes/Test.unity)
ACTUAL  : *** FAIL-OPEN: reservation silently dropped, no diagnostic ***
```

Consequence: two workers can simultaneously claim the same `unity-scene:` resource. `CLAUDE.md` names Unity scenes as non-merge-safe integration surfaces, so this is the highest-consequence defect class in this subsystem. Before `79dc6a0`, an unreadable/invalid reservation snapshot was always a blocking conflict; the new code adds the first path that treats "I could not see it" as "it reserves nothing".

**Suggested fix direction:** on `current is None`, re-read that one Issue explicitly and require a positive `CLOSED` state before skipping; otherwise emit a conflict. At minimum, always append a diagnostic so the skip is observable.

---

### HIGH

#### H1 — Ctrl+C during drain masks the fatal worker failure as exit code 0
**File:** `Pipeline/TaskReviewAgent/polling_orchestrator.py:2311`, `:2322-2324`, `:2330-2332`
**Status:** Confirmed defect (reproduced).

The drain `while` loop runs **inside** the `try` whose `except KeyboardInterrupt` sets `exit_code = 0` (`:2332`). A fatal cycle sets `exit_code = 2` at `:2311`; a Ctrl+C during the drain overwrites it.

Reproduction (worker A exits 7, worker B never exits, operator interrupts):

```
worker_failed emitted  : True
scheduler_draining     : True
drain sleep iterations : 4 (loop had no deadline; only Ctrl+C stopped it)
still-active children  : ['NSC-102']
scheduler exit code    : 0   <-- fatal worker failure was 2
```

Any wrapper, CI job, or supervising script reading the exit code sees success after a worker failed and while a child is still running. The `scheduler_stopped` event also records `reason: "keyboard_interrupt"`, erasing the original `stop_reason` (`worker_failed`).

#### H2 — The drain loop is unbounded and can never terminate
**File:** `Pipeline/TaskReviewAgent/polling_orchestrator.py:2322-2324`
**Status:** Confirmed defect (reproduced).

```python
while self.active_assignments:
    time.sleep(poll_seconds)
    self._reap_workers()
```

No deadline, no maximum drain duration, no escalation (`terminate()` / `CTRL_BREAK_EVENT`), no periodic progress event. A worker blocked on a hung `docker compose run` (exactly what the rehearsal logs show happening) keeps the scheduler alive indefinitely while holding the scheduler lock. This is a behavioural regression: before this commit a fatal cycle exited promptly with code 2.

In the reproduction above the loop only ended because the test raised `KeyboardInterrupt` — the surviving child never exited.

#### H3 — `child_policy: "children were not killed"` is an unsupported operational claim
**Files:** `polling_orchestrator.py:2340`; test `tests/polling_orchestrator_smoke_test.py:2338-2369`
**Status:** Confirmed (claim vs. evidence mismatch).

`scheduler_stopped` reports to the operator:

> `"children were not killed and durable leases were not released; v1 restart does not adopt prior scheduler processes"`

The only test backing this is `test_ctrl_c_does_not_kill_children_or_release_leases`, which asserts `child.kill_calls == 0 and child.terminate_calls == 0` on a `FakeProcess` (`:385-402`, a plain object with `poll`/`kill`/`terminate` counters). That proves **the Python code never calls `.kill()`** — it says nothing about OS-level signal delivery, which is what an operator will read the sentence as meaning.

The rehearsal logs contradict the operational reading. Exit code `3221225786` = `0xC000013A` = `STATUS_CONTROL_C_EXIT` appears for grandchildren of two different workers:

```
NSC-912 18:20:17Z  error_type=KeyboardInterrupt  (inside worker polling-worker-nsc-912-9039aff80069)
NSC-912 18:20:17Z  GitHub command failed (3221225786): gh api --paginate .../issues?state=all&per_page=100
NSC-912 21:13:00Z  Codex supervisor turn failed (3221225786): Container nosafecircle-codex-supervisor-run-...
```

So a console control event *did* terminate the worker and its `gh` / `docker` grandchildren.

Nuance worth recording, because it changes the fix: I tested the Windows semantics locally in an isolated console. With the inherited "ignore Ctrl+C" flag explicitly cleared in the parent, a child launched **with** `CREATE_NEW_PROCESS_GROUP` survived `GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0)` while an identical child launched **without** it took `KeyboardInterrupt`:

```
grouped (CREATE_NEW_PROCESS_GROUP) -> grouped.survived
plain   (no flag)                  -> plain.interrupted  (KeyboardInterrupt)
```

The scheduler does set `CREATE_NEW_PROCESS_GROUP` on Windows (`polling_orchestrator.py:2193-2194`). So the flag works, and the interrupted rehearsal workers were therefore **either not launched through that scheduler path**, or were stopped by `CTRL_BREAK` / console-close rather than `CTRL_C` (both of which do reach a new process group, and both of which produce `0xC000013A`).

**This is the key point for the fix:** the drain added in `79dc6a0` runs **only** on `cycle.fatal` (`:2312`). It does **not** run on `KeyboardInterrupt`. So the drain does not address the failure mode the rehearsal logs actually show. The claim string is also emitted unconditionally on the Ctrl+C path, where it is least defensible.

**What would settle the residual ambiguity:** the scheduler's own event journal. I found no persisted scheduler event log anywhere under `C:\NSC\Rehearsal` (only per-worker `progress.jsonl`), so the parentage of those workers cannot be proven from the artifacts on disk. See L6.

#### H4 — Scope facts still over-suggest tests: 26 of 60 contracts get *all* test files
**File:** `Pipeline/TaskReviewAgent/pipeline_scope.py:291-302` (uncommitted state)
**Status:** Confirmed defect (measured).

The uncommitted diff replaced title-token matching with `test_stem in task_contract_text` and added a `.cs` suffix filter. Both are real improvements. But it left the second branch untouched:

```python
or any(stem in folded for stem in resource_stems)   # :298
```

`stem` is matched against the **whole path**, not against the file stem. The exclusive resource `Assets/Scenes/DoorPrototype.unity` has stem `doorprototype`, which is a substring of the *directory* segment in `Assets/NoSafeCircle/DoorPrototype/Tests/...` — so every test file under `DoorPrototype/` matches.

Measured over all committed contracts in this checkout:

```
contracts=60  tracked .cs test files=11
  matched ALL 11 test files: 26
  matched none: 31
  stem-in-contract only: 2 | resource-stem only: 25 | both: 2

 top by match count (total, via-contract-stem, via-resource-stem):
    11  contract= 1 resource=11  Tasks/NSC-042.yaml
    11  contract= 0 resource=11  Tasks/NSC-052.yaml
 contracts where resource-stem adds files the contract never names: 26 of 60
```

The new precise branch fires for only 4 contracts and matches exactly 1 file each. The imprecise legacy branch dominates. **The stated goal — expose the one relevant C# test — is met on the synthetic gauntlet but not on the production graph.**

**Suggested fix direction:** match `resource_stems` against `PurePosixPath(path).stem` (as the new branch does), not against the full folded path; or require the stem to be a whole-token match.

#### H5 — The consistency retry was applied to only one of three read paths
**File:** `issue_workflow_store.py:766` (fixed) vs `:1744` `list_agent_ready`, `:1765` `list_human_action_required`, `:630` `find`
**Status:** Confirmed defect (reproduced).

Under the *same* body-before-comment skew the commit set out to tolerate:

```
list_agent_ready()          -> []   (silently empty = queue hides the Issue)
list_human_action_required()-> RAISES: managed Issue #1 is invalid: state_version does not match workflow event count
find()                      -> valid = False | reasons = ('state_version does not match workflow event count',)
```

This matters operationally. `AGENTS.md` requires every generic task agent to run `python Pipeline/TaskReviewAgent/issue_queue.py --source .` and to **resume a valid managed Issue before selecting fresh work**. `list_agent_ready()` silently `continue`s past an invalid snapshot, so during the skew window a valid `agent_ready` Issue disappears from the queue and the agent starts fresh work instead — the duplicate-work failure mode the reservation fix exists to prevent, reached by a different door.

#### H6 — `codex_supervisor_smoke_test.py::test_docker_provider_envelope` fails deterministically on `main`
**Files:** `tests/codex_supervisor_smoke_test.py:367`; `downstream_determinism.py:62-73`, `:396-429`, `:906`; `__init__.py:28`
**Status:** Confirmed defect. **Pre-existing and unrelated to this range.** Real composition / test-isolation defect.

Reproduced with the exact CI command:

```
$ python Pipeline/TaskReviewAgent/tests/codex_supervisor_smoke_test.py
  File ".../codex_supervisor_smoke_test.py", line 367, in test_docker_provider_envelope
    require("codex-supervisor" in captured["command"], "wrong Docker service")
KeyError: 'command'
```

**Root cause.** `captured` is empty because the injected `command_runner` is never called. `Pipeline/TaskReviewAgent/__init__.py:28` calls `install_downstream_determinism()` at **package import time**, which replaces the class method process-wide (`downstream_determinism.py:906`):

```python
CodexDockerDecisionProvider.decide = _patched_provider_decide
```

`_patched_provider_decide` (`:396`) short-circuits when exactly one allowed action is a host-deterministic zero-argument action (`:413-416`), synthesising a `SupervisorDecision` and returning **without touching the provider, Docker, or `command_runner`**. `prepare_task_checkout` is in `_HOST_DETERMINISTIC_ZERO_ARGUMENT_ACTIONS` (`:64`), and the test calls `decide(..., allowed_actions=("prepare_task_checkout",))`.

Confirming the chain: `inspect.getsourcefile(CodexDockerDecisionProvider.decide)` resolves to `operator_logging.py:239` (`_patched_decide`), whose captured "original" is already `_patched_provider_decide`.

**Provenance.** The short-circuit landed in `696de7c "Run deterministic closeout actions host-side"` (2026-09-03 06:15), which `git merge-base --is-ancestor 696de7c eb8fa69` confirms is an ancestor of the reviewed range. The test file itself last changed in `9c4bcc9`, *before* `696de7c`. Neither reviewed commit touches `codex_supervisor.py`, `downstream_determinism.py`, `operator_logging.py`, or this test.

**Why it is a real defect, not just a stale test.** Importing the package mutates a class globally and silently changes provider semantics. Any test or caller constructing a `CodexDockerDecisionProvider` with an injected runner gets a different object than it asked for, with no opt-out. The behaviour itself is intended and works in production (`NSC-913` logs show `selection=deterministic_host` for `prepare_task_checkout`), but it is untestable in isolation and it silently invalidates an envelope test that two CI workflows depend on: `.github/workflows/task-review-agent-supervisor.yml:94` and `.github/workflows/task-review-agent-deterministic.yml:81`.

**Suggested fix direction:** have the test use an action *not* in `_HOST_DETERMINISTIC_ZERO_ARGUMENT_ACTIONS` (e.g. `acquire_agent_lease`) so the real envelope path is exercised, and add a separate test pinning the short-circuit. Longer term, make the determinism layer opt-in per instance rather than a global class patch.

---

### MEDIUM

#### M1 — Retry amplifies a full paginated Issue listing per skewed Issue
**File:** `issue_workflow_store.py:505-513`
**Status:** Confirmed (measured).

The retry re-lists **every open Issue in the repository** just to re-read one Issue's body:

```python
current = next((item for item in backend.list_issues() if item.get("number") == number), None)
```

Each `list_issues()` is `gh api --paginate repos/{repo}/issues?state=open&per_page=100` (`:1945-1951`). Measured cost of one reservation scan:

| open managed Issues, all skewed | `list_issues()` | `get_comments()` | serial sleep (real delays) |
|---|---|---|---|
| 1 (resolves on first retry) | 2 | 2 | 0 s |
| 80 (resolves on first retry) | 81 | 160 | 0 s |
| 20 (persistent skew) | 81 | 100 | 140 s |
| 80 (persistent skew) | **321** | **400** | **560 s** |

Baseline before the change: 1 listing + N comment reads, no sleeping. `RESERVATION_CONSISTENCY_DELAYS_SECONDS = (0.0, 1.0, 2.0, 4.0)` is 7 s per skewed Issue, applied **serially** inside a scheduler poll. The gauntlet materialises 80 tasks, so this is not a hypothetical scale.

**Suggested fix direction:** re-fetch the single Issue (`gh issue view <n>`) instead of re-listing; and bound the *total* consistency wait per scan, not per Issue.

#### M2 — Transient-skew detection is keyed on human-readable error message text
**Files:** `issue_workflow_store.py:99-104`; producers `issue_workflow.py:1254`, `:1261`, `:1263`
**Status:** Confirmed design fragility.

`_TRANSIENT_RESERVATION_SNAPSHOT_REASONS` matches by exact string equality against `str(exc)` captured in `_snapshot` (`:465-466`). The three strings do currently exist verbatim, so the mechanism works today. But rewording any message silently disables the retry with no test failure — the code would just resume the old fail-closed behaviour. Prefer a typed error code / exception subclass on `WorkflowContractError`.

#### M3 — A benign skew whose hidden event is a contract migration still fails closed
**File:** `issue_workflow.py:1251-1254`
**Status:** Confirmed gap (by inspection).

`validate_event_chain` checks the migrated contract hash **before** `state_version`:

```python
if expected_contract_sha256 != state.task_contract_sha256:
    raise WorkflowContractError("Issue state does not use the final migrated contract hash")   # :1252
if state.state_version != len(ordered):
    raise WorkflowContractError("state_version does not match workflow event count")           # :1254
```

If the newest, not-yet-visible comment is a `TASK_CONTRACT_MIGRATED` event, the body already carries the new hash while the visible chain proves only the old one, so `:1252` fires. That message is **not** in the transient set, so the identical eventual-consistency window fails closed instead of retrying. Narrow, but it is exactly the class of skew the commit targets.

#### M4 — `_reap_workers` treats a `poll()` exception as a dead child and stops supervising it
**File:** `polling_orchestrator.py:1356-1363`
**Status:** Confirmed (by inspection). Pre-existing, but the drain now depends on it.

```python
except Exception as exc:
    returncode = -1
    assignment.observation_error = _bounded_error(exc)
...
del self.active_assignments[task_id]
```

A transient `poll()` failure removes the assignment, so the drain loop can "complete" and the scheduler exit while the OS process is still alive — with its durable GitHub lease intact.

#### M5 — No job object, no orphan adoption, and the lock is released while children live
**File:** `polling_orchestrator.py:2193-2196`, `:2345`
**Status:** Confirmed (by inspection).

Children are placed in their own process group but not in a Windows **Job Object** with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. If the scheduler is killed (`taskkill`, crash, console close) the workers are orphaned and keep running with live leases. `lock.release()` runs in `finally`, so a restarted scheduler acquires the lock immediately while orphans are still writing — and `child_policy` itself states "v1 restart does not adopt prior scheduler processes". The drain does not close this gap because it only runs on the fatal-cycle path.

#### M6 — Test-stem / contract-text matching: residual false positives and false negatives
**File:** `pipeline_scope.py:294-300`
**Status:** Confirmed mechanism; no false negative found in committed data.

*False positives.* `test_stem in task_contract_text` is an unanchored substring test over the **entire serialized contract**, including `notes`, `decomposition_reason` and `provenance`. Two consequences: (a) a mention anywhere — not just in a completion gate — pulls a test into scope; (b) a shorter stem that is a prefix of a longer one matches when only the longer is named (e.g. a file `FooTest.cs` matches a contract naming `FooTests`).

*False negatives.* The match requires the **file stem** to appear. A gate naming only the test *method*, the *assembly*, or a class whose name differs from its filename would not match. I checked every committed contract and found **0** such cases:

```
Contracts naming a COMMITTED test class in gates but getting ZERO suggestions: total: 0
```

So this is a latent risk, not a current failure. Anchoring on the completion-gate / acceptance-criteria text rather than the whole document would remove (a) without cost.

---

### LOW

- **L1 — `failed_child` is written but never read.** `polling_orchestrator.py:1293` declares it, `:1375` assigns it, nothing consumes it. Repeated failures overwrite it. The `worker_failed` events do record every failure, so no audit data is lost — but the field is dead state that reads like a safeguard.
- **L2 — The drain sleeps before reaping** (`:2323-2324`), so it always waits at least one `poll_seconds` even when every child has already exited.
- **L3 — The new drain test's strongest assertion is satisfied by the wrong event.** `tests/polling_orchestrator_smoke_test.py` asserts `'"active_children": []' in events`; at drain time `scheduler_draining` reports a **non-empty** list, so that string can only come from `scheduler_stopped` (`:2339`). The test therefore never pins that `scheduler_draining` actually named the surviving worker.
- **L4 — `eb8fa69` overwrites `acceptance_criteria` wholesale** from the canonical builders (`prepare_synthetic_gauntlet.py:446-451`). Correct here — the wave/concrete selector matches the materialiser exactly (`:447-449` vs `:503-507`), and the repository guard (`test_public_or_production_repository_is_refused_before_mutation`) keeps it off production — but it would silently revert human edits if the helper were ever reused.
- **L5 — `C:\NSC\Rehearsal\.task-review-agent\outputs\NSC-911` does not exist.** Only `.task-review-agent\NSC-911.json` (a `durable_checkout_identity` record, `checkout_purpose: "decomposition"`) is present. One of the four requested log paths has no logs.
- **L6 — No scheduler event journal is persisted.** `C:\NSC\Rehearsal` contains only per-worker `progress.jsonl` / `progress.log`. There is no `scheduler_started` / `worker_launched` / `scheduler_stopped` stream, so neither the drain path nor worker parentage can be verified from the rehearsal artifacts. This is why H3 retains a residual ambiguity.

---

## 2. Answers to the specific questions

**Does the reservation retry correctly handle GitHub exposing an updated Issue body before its matching event comment?**
Yes for the common case, and the new test proves it. Both skew directions (body ahead of comments, comments ahead of body) produce `state_version does not match workflow event count`, which is in the transient set, so both are retried. Two gaps: the migration-event ordering in M3, and the string-coupling in M2.

**Is the retry narrowly bounded so genuine malformed or tampered workflow history still fails closed?**
Yes. Only three exact reasons are retried; every other reason returns immediately; after exhausting the delays the last (invalid) snapshot is returned and becomes a blocking conflict. `test_resource_conflict_and_tampered_history_fail_closed` still passes. Tampering that happens to produce one of the three messages costs 7 s and then still fails closed. The bound is correct — **but see C1**: exhaustion is not the only exit, and the `None` exit is not fail-closed.

**Could repeated `list_issues` / `get_comments` calls introduce races, false negatives, excessive API usage, or accidentally ignore an Issue that still reserves resources?**

- *Accidentally ignore an Issue that still reserves resources:* **yes — C1, reproduced.**
- *Excessive API usage:* **yes — M1**, measured at 321 full paginated listings and 560 s of serial blocking for 80 skewed Issues.
- *False negatives:* yes, in the narrow M3 case.
- *Races:* the retry re-reads a fresh Issue object each pass but never re-checks that it still names the same task, so a lease released and re-acquired mid-window is evaluated against whichever snapshot happens to be valid. Low impact given the short window, but the loop makes no consistency claim across iterations.

**When one scheduler worker fails, does the new drain behavior reliably keep other workers alive and supervised until they exit?**
Alive: yes — nothing kills them, and the new test confirms no `kill` / `terminate`. Supervised until they exit: **only if they exit and only if nobody presses Ctrl+C.** See H1 and H2.

**Could draining wait forever, mishandle Ctrl+C, lose another worker failure, or behave incorrectly under Windows process/job semantics?**

- *Wait forever:* **yes — H2, reproduced.**
- *Mishandle Ctrl+C:* **yes — H1, reproduced** (exit code 2 → 0, and `stop_reason` overwritten).
- *Lose another worker failure:* the `worker_failed` **events** are all emitted, so the journal is complete. Only the unused `failed_child` field is clobbered (L1). Effectively no — but M4 can lose a *live* child from supervision.
- *Windows semantics:* **yes — M5** (no job object, orphans survive, lock released while children live).

**Does the scheduler's previous claim that children were not killed match the actual process behavior? Explain whether the fix addresses the real cause.**
The claim is **not supported by its test** and is contradicted by the rehearsal evidence (H3). The test only proves the Python code calls no `kill()`; the logs show workers and their `gh` / `docker` grandchildren dying with `STATUS_CONTROL_C_EXIT`.

**The fix does not address the real cause.** The drain runs only on `cycle.fatal` (`:2312`). The rehearsal failures were console control events, which take the `except KeyboardInterrupt` path (`:2330`) — where there is no drain at all, and where the unchanged `child_policy` sentence is emitted anyway. My local experiment further shows `CREATE_NEW_PROCESS_GROUP` *does* shield a Python child from `CTRL_C_EVENT`, so the real cause is more likely `CTRL_BREAK` / console-close, or workers not launched through the scheduler path — neither of which the drain touches.

**Do repository scope facts now expose exactly the two policy documents, the intended implementation paths, and the one relevant C# test without suggesting `.meta` or unrelated "gauntlet" files?**
Partly — a real improvement, but not "exactly", and not on the production repo.

*Policy documents:* yes. Both `_REQUIRED_POLICY_PATHS` entries are tracked in both the production and rehearsal repos, so `required_policy_paths` exposes exactly those two.

*The one C# test, on the synthetic gauntlet:* yes, and the improvement is large. Replaying both algorithms against the real rehearsal repo and the real `Tasks/NSC-912.yaml`:

```
OLD (committed 79dc6a0):
    Assets/NoSafeCircle/DoorPrototype/Tests/Editor/MuffcabbageGauntletTests.cs
    Assets/NoSafeCircle/DoorPrototype/Tests/Editor/MuffcabbageGauntletTests.cs.meta        <- .meta
    Assets/NoSafeCircle/DoorPrototype/Tests/Editor/MuffcabbageRehearsalSettingsTests.cs    <- unrelated
    Assets/NoSafeCircle/DoorPrototype/Tests/Editor/MuffcabbageRehearsalSettingsTests.cs.meta
    Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py                <- pipeline Python!
    Pipeline/TaskReviewAgent/tests/synthetic_gauntlet_approver_smoke_test.py
NEW (uncommitted):
    Assets/NoSafeCircle/DoorPrototype/Tests/Editor/MuffcabbageGauntletTests.cs
```

Note the committed state also leaked **pipeline Python test files** into `suggested_test_paths` (because `_is_test_path` matches any `tests` path segment, `pipeline_scope.py:150-151`). The `.cs` filter fixes that too. This alone justifies committing the working-tree change.

*On the production repo:* **no — H4.** 26 of 60 contracts still receive all 11 test files through the untouched `resource_stems` branch.

**Could matching a test-file stem against serialized task-contract text produce false positives or false negatives?**
Yes to both in principle — see M6 — but the new branch is by far the more precise of the two, and I found **no false negative** among the 60 committed contracts. The practical precision problem today is the *old* branch it sits next to, not the new one.

**Are the new tests realistic reproductions of the production failures?**
Partly. Honest assessment per test:

- `test_resource_scan_retries_body_before_comment_visibility_skew` — good. It models the real skew (truncating the newest comment) and pins the exact re-read count. It does **not** cover the `None` path (C1), the migration-ordering gap (M3), or multi-Issue amplification (M1).
- `test_fatal_child_exit_drains_other_workers_before_scheduler_stops` — models the happy path only: the survivor exits on its second `poll()`. No hung worker, no Ctrl+C, no second failure. Its `active_children: []` assertion is satisfied by the wrong event (L3). H1 and H2 both live in the space this test does not enter.
- `production_pipeline_smoke_test` scope assertion — correctly upgraded from title-substring to contract reference, but it asserts only *presence* of `DOOR_TEST`. It never asserts **absence** of `.meta`, of unrelated tests, or of pipeline Python files — which is where the actual bug was.

**Missing test coverage, by category:**

*Concurrency / GitHub eventual consistency*

1. Reservation scan where the skewed Issue vanishes from one retry listing and remains `OPEN` → must conflict, not skip. **(C1)**
2. Reservation scan where the Issue is genuinely `CLOSED` during the window → must skip, and the two cases must be distinguishable.
3. `list_agent_ready()` / `list_human_action_required()` / `find()` under the same skew. **(H5)**
4. Skew whose hidden newest event is `TASK_CONTRACT_MIGRATED`. **(M3)**
5. Bound on total `list_issues()` calls and total sleep for a scan over N skewed Issues. **(M1)**
6. A test pinning that each string in `_TRANSIENT_RESERVATION_SNAPSHOT_REASONS` is still produced verbatim by `validate_event_chain`. **(M2)**

*Windows process semantics*

7. Drain with a worker that never exits + an injected deadline → must terminate and must return 2.
8. `KeyboardInterrupt` **during** drain → exit code must stay 2 and `stop_reason` must stay `worker_failed`. **(H1)**
9. Second worker failing during drain → both `worker_failed` events emitted, both recorded.
10. `poll()` raising during drain → child must not be silently dropped. **(M4)**
11. An integration-level check that a real child process in a new process group survives a console `CTRL_C_EVENT`, so the `child_policy` sentence is backed by process behaviour rather than by `FakeProcess` counters. **(H3)**

*Persistence / scope*

12. Negative scope assertions: `facts()["suggested_test_paths"]` contains **no** `.meta`, **no** `Pipeline/**` path, and no test the contract does not name.
13. A production-shaped contract owning `Assets/Scenes/DoorPrototype.unity` must not pull in all 11 test files. **(H4)**
14. `required_policy_paths` is empty (not an error) when a policy document is absent from the checkout.
15. `test_docker_provider_envelope` rewritten against a non-short-circuited action, plus a test pinning the short-circuit. **(H6)**

---

## 3. Rehearsal log diagnosis (NSC-911 / 912 / 913 / 914)

**Requested paths.** `NSC-912`, `NSC-913`, `NSC-914` exist. **`NSC-911` does not** — only `.task-review-agent\NSC-911.json`, a `durable_checkout_identity` record with `checkout_purpose: "decomposition"` (L5).

**Diagnosis: these are two unrelated phenomena, not one interruption.**

### (a) Console-control-event terminations — NSC-912, and almost certainly NSC-913's final run

`3221225786` = `0xC000013A` = `STATUS_CONTROL_C_EXIT`. It appears across three separate NSC-912 runs, in *different* child programs:

| when | what died | recorded as |
|---|---|---|
| 18:20:17Z | worker itself, then `gh api ... issues?state=all` | `error_type=KeyboardInterrupt`, then `GitHub command failed (3221225786)` |
| 19:19:12Z | worker during `search_repository` | `error_type=OSError [Errno 22] Invalid argument` |
| 21:13:00Z | `docker` / codex supervisor container | `Codex supervisor turn failed (3221225786)` |

NSC-913's latest run (`20260903-210955Z`) simply stops mid-turn at 21:12:58 with no `[END]` record — consistent with the same event that hit NSC-912 at 21:13:00, two seconds later.

The `[Errno 22] Invalid argument` at 19:19:12 is the same story in a different costume: an interrupted native call / broken console handle during a subprocess read, not a logic error.

**This confirms the diagnosis in the sense that matters:** the runs were killed from the console, and the kill reached the workers' grandchildren (`gh`, `docker`), not just the top-level process. It does **not** confirm that the scheduler's `CREATE_NEW_PROCESS_GROUP` was bypassed — my isolated-console experiment shows that flag does hold against `CTRL_C_EVENT`. The better-supported reading is `CTRL_BREAK_EVENT` or a console-close, both of which reach a new process group and both of which yield `0xC000013A`. Without a scheduler event journal (L6) I cannot close that gap from the artifacts on disk.

### (b) A better diagnosis for NSC-913's 19:53 run, and the real motivation for `required_policy_paths`

NSC-913's `20260903-195321Z` run did **not** crash. It reached `blocked` after burning turns hunting for a policy document whose path was never exposed to it:

```
20:03:34Z Turn 15 read_repository_file -> Docs/Engineering/ProgrammerLanguagePolicy.md   (rejected: not a committed file)
20:04:49Z Turn 17 read_repository_file -> Docs/Engineering/programmer-language-policy.md (rejected: not a committed file)
20:09:18Z Turn 23 list_repository_files -> prefix Docs/                                   (rejected: outside approved read roots)
20:09:38Z [END] blocked
```

NSC-912 shows the same pattern at 19:18-19:19 and again at 21:12 (`search_repository` for `EditMode` under `Docs/Engineering/`, rationale: *"Its exact committed path is still not exposed in the deterministic observation"*). NSC-913 at 21:12:58 searched `Assets/` for `MuffcabbageGauntletTests`.

This is direct production evidence for **both** halves of the scope change: `required_policy_paths` (`pipeline_scope.py:317-319`) removes the policy-path guessing loop, and the `suggested_test_paths` precision fix removes the test-path search. Both are well-motivated by these logs. It is also evidence that the operator-visible symptom — runs stalling before `validate_execution_scope` — had a deterministic cause independent of the Ctrl+C terminations.

### (c) NSC-914 is not an interruption at all

`20260903-195524Z` ran to a clean terminal state: `record_pipeline_blocker` at 20:03:31 → `[END] blocked` at 20:03:56, because *"ExecutionCrew run nsc-914-20260903t200039z is blocked and produced no review-ready candidate."* That is the workflow behaving correctly. It should not be counted as part of the interrupted-rehearsal population.

---

## 4. What I validated

**Tests run (all local, deterministic, read-only):**

| suite | result |
|---|---|
| `issue_workflow_smoke_test` | **PASS** (30 tests) |
| `polling_orchestrator_smoke_test` | **PASS** (59 tests) |
| `production_pipeline_smoke_test` | **PASS** (5 tests) |
| `prepare_synthetic_gauntlet_smoke_test` | **PASS** (8 tests) |
| `codex_supervisor_smoke_test` | **FAIL** — `KeyError: 'command'` (H6, pre-existing) |

**Behaviour I reproduced directly:** C1 (reservation fail-open), H1 (exit-code masking), H2 (unbounded drain), H5 (skew on the other read paths), H6 (CI test failure, via the exact CI command).

**Measurements I took:** M1 amplification table (1/20/80 Issues, transient and persistent skew); H4 match statistics across all 60 committed contracts; the old-vs-new `suggested_test_paths` replay on the real rehearsal `NSC-912` contract; a false-negative sweep over all committed contracts (0 found).

**Windows semantics experiment:** in an isolated console with the inherited ignore-flag explicitly cleared, `GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0)` interrupted a child launched without `CREATE_NEW_PROCESS_GROUP` and did **not** interrupt one launched with it. Two earlier variants were confounded (parent-level ignore inherited by the same-group child; harness console with Ctrl+C already disabled) and are discarded.

**What I verified as correct and did not flag:**

- `eb8fa69`'s wave/concrete selector matches the materialiser exactly (`prepare_synthetic_gauntlet.py:447-449` vs `:503-507`); the added acceptance-criteria repair and its GUID assertion are sound.
- `required_policy_paths` exposes exactly the two documents; both are tracked in both repos; both are inside `_READ_PREFIXES`.
- The `.meta` exclusion works: `.cs.meta` has suffix `.meta`, so the `== ".cs"` test rejects it.
- The retry's fail-closed-on-exhaustion path is correct, and tampered-history tests still pass.
- `worker_failed` events are emitted for every failing child, including during drain.
- The `openai_pipeline.py` prompt addition is consistent with the new `repository_scope_facts` fields.

**Confirmed defects:** C1, H1, H2, H3, H4, H5, H6, M1, M6 (mechanism), L1, L2, L3, L5, L6.
**Hypotheses / by-inspection only:** M2 (fragility, not yet broken), M3 (ordering gap, not reproduced end-to-end), M4, M5, and the *frequency* of C1's trigger — the defect is demonstrated, but how often GitHub transiently omits an open Issue from a paginated listing is not established by anything I can measure read-only.

---

## 5. Recommendation

Commit the working-tree `pipeline_scope.py` change — it is a strict improvement and the evidence above supports it. Before relying on `79dc6a0` for unattended multi-worker runs, address **C1** (silent fail-open) and **H1** / **H2** (exit-code masking and the unbounded drain); those three are small, local changes with clear regression tests. **H6** should be fixed independently since it is red in CI today for reasons unrelated to this work.
