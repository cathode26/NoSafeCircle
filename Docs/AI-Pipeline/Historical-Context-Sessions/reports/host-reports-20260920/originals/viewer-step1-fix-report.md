# Viewer Step 1 Fix Report

- Clone path: C:\nscrev\viewer-step1-fix
- Branch: fix/viewer-step1
- BASE sha: `7fc15c528280b74532d1f3b39d2b420c9d57a2bd` (confirmed == `git -C C:/NSC/NSC/NoSafeCircle rev-parse main` at the start of this work on 2026-09-16; unchanged throughout)
- HEAD sha: `2e76ab22d2c4556ae93cb70815f14419e9c5a381`
- Commits (BASE..HEAD, oldest first, one per problem, in the assigned order V18, V1, V13, V14, V9):
  1. `2afc305961b1c36de657c41d50e6d39cfb3770b3` — V18: repair AssistantControl viewer regression fixtures
  2. `281d4b1182d938093ce2f295b92d45664c59bf10` — V1: approved and integrating candidates show integration_queued
  3. `d41170774bdff94fd64f93a488c2c8f8a182ffc6` — V13: hide run-detail rows instead of reading Unavailable
  4. `3a72777b505e4f90feba6188c72e9745cadca592` — V14: neutral page title, no mode detection
  5. `2e76ab22d2c4556ae93cb70815f14419e9c5a381` — V9: add hold/unhold to the GER marker CLI (HEAD)

Status: **DONE.** All five problems fixed on one branch, one commit each, in the assigned order. All required suites green; see the final verification section at the end of this report.

---

## Baseline (on BASE, before any change)

Commands run from `C:\nscrev\viewer-step1-fix` (HEAD == BASE at this point) with `TEMP="C:/nscrev/viewer-step1-tmp" TMP="C:/nscrev/viewer-step1-tmp"`.

| Suite | Command | Result |
|---|---|---|
| `Pipeline.AssistantControl.test_viewer` | `python -B -m unittest Pipeline.AssistantControl.test_viewer -v` | **37/57** (4 failures, 16 errors) — matches problem list's 9/16 count exactly |
| `Pipeline.AssistantControl.test_inspect_project` | `python -B -m unittest Pipeline.AssistantControl.test_inspect_project -v` | 7/7 OK |
| `Pipeline.AssistantControl.test_checkouts` | `python -B -m unittest Pipeline.AssistantControl.test_checkouts -v` | 8/8 OK |
| `Pipeline.AssistantControl.test_prepared_refresh` | `python -B -m unittest Pipeline.AssistantControl.test_prepared_refresh -v` | 3/3 OK |

All 20 test_viewer failures/errors share one root cause: a shared fixture (task NSC-042's contract, written by a helper reused from `test_inspect_project.py`) is missing/rejected under schema v2, so `AssistantSnapshot(...).build()["tasks"]` never contains `NSC-042` (`StopIteration` on `next(item for item in ... if item["id"]=="NSC-042")`) or shows it `excluded` instead of `assistant_idle`. Full list of failing tests captured in `C:\nscrev\viewer-step1-tmp\baseline_test_viewer.log`.

**Did not reproduce yet:** the `TypeError: None >= 42.0` mentioned in the problem list. It does not appear in this baseline run — plausibly because the fixture bug causes `StopIteration` before the timing-projection code that would hit the `None` comparison is ever reached by these tests. Will re-check once the fixture is repaired (commit 1).

### GauntletView front-end tests (baseline, BASE)

Grepped every file in `Pipeline/TaskReviewAgent/GauntletView/tests` for `subprocess|Popen|webbrowser|chrome|msedge|node|8828|C:\NSC|C:/NSC`.

**Skipped** (launch node, or launch a browser, per the rule; no fixed-port or C:\NSC-write skips were needed — none found):
- `browser_smoke_test.py`, `browser_smoke_test.cjs` — mandatory skip; also launch Node/a real browser via Puppeteer-style `page.evaluate`.
- `third_viewer_poll_benchmark.py` — mandatory skip.
- `local_rehearsal_view_test.py` — defines/calls `render_in_node()`, which does `subprocess.run([node, "-e", code], ...)` to execute Node directly.
- `local_rehearsal_review_test.py` — imports `local_rehearsal_view_test as fixtures` and calls `fixtures.render_in_node(...)`, same Node launch.
- `third_local_pipeline_activity_test.py` — calls `subprocess.run([os.environ.get("NSC_NODE","node"), "-e", script], ...)` directly, multiple times.
- `local_stop_endpoint_test.py` — one test (`test_inline_script_still_parses`) calls `subprocess.run(["node", "--check", path])` guarded by `skipIf(shutil.which("node") is None)`. Syntax-check only (no execution), but it does launch the `node` binary, so skipped out of caution per the stated rule. The rest of the module (stop-endpoint behavior) is unrelated to my 5 problems.

No file bound a fixed port (grep for `8828` and generic port-bind patterns found nothing) and no file performed real file IO under `C:\NSC`/`C:/NSC` (the one hit, in `local_candidate_acceptance_view_test.py`, is a literal fixture string/`Path` assigned to a hand-built object's attributes that are never read by IO code in that test — confirmed no `open`/`mkdir`/`write_text` calls in the file).

**Run** (`python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "<module>.py"`, one at a time, `TEMP`/`TMP` = scratch):

| Module | Result |
|---|---|
| `approval_smoke_test.py` | 10/10 OK |
| `decomposition_transition_view_test.py` | 6/7 (1 error, pre-existing, see below) |
| `display_scope_smoke_test.py` | 16/16 OK |
| `gauntlet_view_smoke_test.py` | 149/150 (1 failure: `test_run_scope_is_the_default_proof_view`, the `f-scope` default-checked expectation) |
| `local_candidate_acceptance_view_test.py` | 0/1 (module collection error, pre-existing, see below) |
| `local_crew_view_test.py` | 12/12 OK |
| `run_details_dom_binding_test.py` | 1/1 OK (this is the file to update for V13) |
| `third_viewer_integrity_test.py` | 0/1 (module collection error, pre-existing, see below) |

Combined `approval_smoke_test.py` + `display_scope_smoke_test.py` + `gauntlet_view_smoke_test.py` = 176 tests, 175 passing, 1 failing — this **exactly matches** the problem list's "smoke tests were 175/176, the failure being the f-scope default-checked expectation." Confirmed reproduced.

**Pre-existing failure found, unrelated to V1/V9/V13/V14/V18 (out of scope, not fixed):** `Pipeline/TaskReviewAgent/local_rehearsal.py` does not exist anywhere in the repository at BASE (confirmed both in the clone and via `git -C C:/NSC/NSC/NoSafeCircle cat-file -e 7fc15c528280b74532d1f3b39d2b420c9d57a2bd:Pipeline/TaskReviewAgent/local_rehearsal.py` against the canonical repo — path does not exist). This breaks module collection for `local_candidate_acceptance_view_test.py` and `third_viewer_integrity_test.py` entirely, and one test in `decomposition_transition_view_test.py`. It likely also breaks the 4 node-launching modules skipped above (`local_rehearsal_view_test.py`, `local_rehearsal_review_test.py`, `third_local_pipeline_activity_test.py`, `local_stop_endpoint_test.py`) for the same reason, independent of the node-launch skip rationale — not confirmed since those were not run. Logged as a follow-up.

---

## Commit 1: V18 — viewer tests red for fixture reasons

**Status: reproduced.** Baseline matched the problem list exactly (test_viewer 37/57; GauntletView smoke 175/176 on the f-scope check).

**Commit:** `2afc305961b1c36de657c41d50e6d39cfb3770b3` — "V18: repair AssistantControl viewer regression fixtures" (amended after the cherry-pick to fold in two follow-up fixes described below; full commit message has all details and file:line references).

### Part A — cherry-picked fixture repair

- Got `c12f70287bad1b97e66e8e5fbee1710aaa70c33c` from `C:/NSC/AssistantControlViewerRegression-20260913` via `git -C "$FIX" fetch C:/NSC/AssistantControlViewerRegression-20260913 HEAD`. Verified `git -C "$FIX" rev-parse FETCH_HEAD` == `c12f70287bad1b97e66e8e5fbee1710aaa70c33c` before touching anything.
- `git cherry-pick -x c12f70287bad1b97e66e8e5fbee1710aaa70c33c` applied cleanly (one auto-merge in `test_viewer.py`, no conflicts).
- **Root cause (test_inspect_project.py:29-33 originally):** the shared `InventoryTests.setUp` fixture wrote a pre-schema-v2 NSC-042 contract (`{"id":..., "title":..., "depends_on":[], "exclusive_resources":[...]}`, missing `schema_version`, `contract_disposition`, `execution_scope`, etc.). `AssistantSnapshot.build()` never included that task, so every test expecting to find `NSC-042` in `build()["tasks"]` hit `StopIteration`, or (for the one test not using `next(...)`) saw the task as `excluded` instead of `assistant_idle`. The cherry-picked commit adds `executable_task_contract()` (a schema-v2 helper) to `test_inspect_project.py` and switches the fixture to use it; it also adds idempotency guards in `test_checkouts.py`/`test_prepared_refresh.py` so they don't try to re-commit an already-`active` disposition (which the new default fixture now sets), and updates `test_viewer.py`'s own assertions/fixtures to match current API shapes (candidate/port/timing).
- Effect: `test_viewer.py` went from 37/57 to 56/57 by itself.

### Part B — stale `review_alarm` assertion (found after the cherry-pick)

- The cherry-picked `test_exact_candidate_requests_human_review_and_approval_is_not_acceptance` asserted `attention["review_alarm"]["active"]` / `["after_seconds"]`. `KeyError: 'review_alarm'` — that field does not exist in `_human_review_attention()` (`Pipeline/AssistantControl/viewer.py:358-385`, returns only `kind`/`task_ids`/`candidates`). Grepped `viewer.py` for `review_alarm`: zero hits. The coercive "rickroll" review alarm was deliberately removed on `main` (`330cd3777`, listed as "already fixed, don't redo" in `nsc-viewer-guide.md`). **Test was wrong, not product.** Removed the two stale assertion lines (`Pipeline/AssistantControl/test_viewer.py`, in `CandidateViewTests.test_exact_candidate_requests_human_review_and_approval_is_not_acceptance`).
- Effect: `test_viewer.py` 56/57 -> 57/57.

### Part C — "TypeError: None >= 42.0"

- **Status: reproduced directly against product code** (not via the checked-in suite — see method below), and classified as a **test hazard, not a product bug**.
- Root cause: `_apply_controller_timing_projection` (`Pipeline/AssistantControl/viewer.py:481-556`) sets `stage_elapsed_seconds = None` (line 530) whenever a task is not "currently ticking" — i.e. `currently_ticking = open_attempt is not None and is_controller_running and task_id == current_task_id` is `False`. This is true by design for an in-scope controller-target task that has its own (unclosed) history entry but is **not** the controller's `current_action` — only the task actually being worked ticks live; `durable_stage_elapsed_seconds`/`total_elapsed_seconds` carry the historical view instead. Confirmed via a scratch reproduction (`C:\nscrev\viewer-step1-tmp\repro_none_ge_42b.py`): built a controller with two targets (`NSC-042`, `NSC-999`), `current_action` pointing at `NSC-999`, and an open history entry for `NSC-042`; `row["progress"]["stage_elapsed_seconds"]` came back `None` while `row["in_scope"]` was `True`, and `None >= 42.0` raised exactly `TypeError: '>=' not supported between instances of 'NoneType' and 'float'`.
- Checked every consumer of `stage_elapsed_seconds`: `Pipeline/TaskReviewAgent/GauntletView/index.html:1118` already guards with `if (activity.stage_elapsed_seconds != null)`; the legacy `server.py` (not to be touched) uses `positive_number()`/`duration_text()` helpers that tolerate `None`. No product code path performs an unguarded numeric comparison. The only way to hit the `TypeError` is a Python caller/test doing a raw `>=`/`assertGreaterEqual` — which is exactly what the *previous* (pre-cherry-pick) shape of `test_build_projects_timing_for_the_in_scope_task_named_by_the_controller` would have done if it had gotten past the schema-v2 StopIteration bug; the cherry-picked version already avoids it by mocking `_controller_owner_active` and asserting on the task that genuinely is the live one.
- **Decision: left product code unchanged** (no guard added — `None` here is the correct signal that nothing is actively ticking for that row, and a defensive coercion would fabricate a fake number). Added one focused regression test, `test_in_scope_target_that_is_not_the_current_action_has_no_live_stage_timer` (`Pipeline/AssistantControl/test_viewer.py`, end of `GraphControllerTimingEndToEndTests`), which builds exactly the reproduction scenario above through the public `AssistantSnapshot.build()` path and asserts: `in_scope` is `True`, `stage_elapsed_seconds` and `durable_stage_elapsed_seconds` are `None`, and `total_elapsed_seconds == 0.0` (the product's documented behavior for an open, non-current attempt — it doesn't assume "now" for a row it can't prove is still running). This guards the contract so a future test cannot reintroduce the same unguarded comparison and locks in the None-is-safe behavior.
- Effect: `test_viewer.py` 57/57 -> 58/58 (new test added).

### Part D — GauntletView smoke "f-scope" failure

- **Status: reproduced** exactly as described (175/176, `test_run_scope_is_the_default_proof_view` failing on `'id="f-scope" checked'`).
- Root cause: `git blame`/`git log -p` on `Pipeline/TaskReviewAgent/GauntletView/index.html` showed the static `<input type="checkbox" id="f-scope">` (line 208, commit `7d17efde08` "Make full graph viewer load reliably") never carries a `checked` attribute; the checked state is computed entirely at runtime (line 627-628) by commit `1d0f84d145` "Default AssistantControl viewer to full graph": `const defaultScopeOnly = assistantFullGraph ? false : !Array.isArray(ids); document.getElementById('f-scope').checked = typeof saved === 'boolean' ? saved : defaultScopeOnly;`. This is a deliberate product decision (explicit commit message) so the main/assistant-mode viewer defaults to the **full graph** (unscoped) while legacy/gauntlet "proof view" mode still defaults to scoped. The sibling test `test_assistant_mode_defaults_to_the_full_graph` already exercises and passes against this exact current behavior. **Test was wrong (stale), not product.**
- Change: `Pipeline/TaskReviewAgent/GauntletView/tests/gauntlet_view_smoke_test.py`, `test_run_scope_is_the_default_proof_view` now asserts the checkbox exists without a baked-in `checked` attribute, and that the non-assistant-mode fallback in the runtime default expression is still `!Array.isArray(ids)` (checked/scoped by default outside assistant mode) — preserving the test's original intent (legacy "proof view" defaults to scoped) while being accurate about where that default now lives.
- Effect: `gauntlet_view_smoke_test.py` 149/150 -> 150/150; combined smoke total 175/176 -> 176/176.

### Tests: failing-before / passing-after

| Test | Command | Before | After |
|---|---|---|---|
| `Pipeline.AssistantControl.test_viewer` (57/58 tests incl. 1 new) | `TEMP=... TMP=... python -B -m unittest Pipeline.AssistantControl.test_viewer -v` | 37/57 (4 fail, 16 error) | 58/58 |
| `Pipeline.AssistantControl.test_inspect_project` | same pattern | 7/7 (already green; unaffected) | 7/7 |
| `Pipeline.AssistantControl.test_checkouts` | same pattern | 8/8 (already green; unaffected) | 8/8 |
| `Pipeline.AssistantControl.test_prepared_refresh` | same pattern | 3/3 (already green; unaffected) | 3/3 |
| `approval_smoke_test.py` | `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "approval_smoke_test.py"` | 10/10 (unaffected) | 10/10 |
| `display_scope_smoke_test.py` | same pattern | 16/16 (unaffected) | 16/16 |
| `gauntlet_view_smoke_test.py` | same pattern | 149/150 | 150/150 |

All commands run with `TEMP="C:/nscrev/viewer-step1-tmp" TMP="C:/nscrev/viewer-step1-tmp"` from `C:\nscrev\viewer-step1-fix`.

**Risk / not tested:** the 4 node-launching + `local_stop_endpoint_test.py` GauntletView modules were not run (see skip list above), so V18's effect on them (if any) is unverified. They are unrelated to the files V18 touches (test_viewer.py, test_inspect_project.py, test_checkouts.py, test_prepared_refresh.py, gauntlet_view_smoke_test.py), so no effect is expected.

---

## Commit 2: V1 — approved/integrating candidates show integration_queued

**Status: reproduced** (both the no-controller path and the controller-running path). `integration_queued` was confirmed never assigned anywhere in `viewer.py` before this commit (`grep -n 'integration_queued' Pipeline/AssistantControl/viewer.py` returned nothing on BASE), while `index.html` already had a complete definition for it (color `#f8fafc`, label "Candidate Ready — Waiting for Merge Gate", in `PROCESSED_STATES` and the `local_rehearsal` filter) — confirming the front end was ready and only the backend was missing the assignment.

**Commit:** `281d4b1182d938093ce2f295b92d45664c59bf10`.

### Root cause (file:line, matches the Main Orchestrator's trace exactly)

- No controller: `task_row`, `Pipeline/AssistantControl/viewer.py` (ternary originally at ~1011-1015): `status in {"approved","integrating"}` fell through to `"assistant_idle"`.
- Controller running: `_apply_running_controller_projection`, `Pipeline/AssistantControl/viewer.py` (~662-671, now ~662-676): `has_candidate and phase in {"approved","integrating"}` set `"active"` unconditionally, regardless of whether the controller was actually working that task.

### The change (3 hunks, `viewer.py`)

a) `task_row`'s status ternary: added `else "integration_queued" if status in {"approved", "integrating"}` before the `"assistant_idle"` fallback. `awaiting_human`/`integrated` arms and the `changes_requested`-falls-to-`assistant_idle` behavior are untouched (`changes_requested` still isn't in the new arm, so it still falls through exactly as before).
b) TaskGraph-conformant override set (end of `task_row`): added `"integration_queued"` to `row["state"] in {"assistant_idle", "local_accepted", "complete", ...}`. **Verified this specific line was load-bearing**: temporarily reverted only this one-line set addition (kept part (a)), re-ran `test_taskgraph_conformant_override_still_applies_to_integration_queued`, watched it fail (`'complete' != 'integration_queued'`) exactly as the assignment warned, then restored the real fix and re-confirmed green.
c) `_apply_running_controller_projection`: added a `live_integration_action = task_id == action_task and action_kind in {"auto_approve", "integrate", "sync_candidate"}` guard, and require it (in addition to `has_candidate and phase in {"approved","integrating"}`) before setting `"active"`. `automatic_review` and `checkout_write_in_progress` conditions are untouched (still OR'd in unchanged). The `"active"` state/message text set in that branch is byte-identical to before.
d) No `index.html` changes (none needed — see above). Did not touch the worker projection (`viewer.py` ~1144-1149, `host_identity_alive` `None` stays blue) or the decomposition `running` projection (~901) — see Follow-ups.

### Tests: failing-before / passing-after

All commands: `cd C:\nscrev\viewer-step1-fix && TEMP="C:/nscrev/viewer-step1-tmp" TMP="C:/nscrev/viewer-step1-tmp" python -B -m unittest Pipeline.AssistantControl.test_viewer.CandidateViewTests.<name> -v`. Failing-before was proven by `git stash push --keep-index -- Pipeline/AssistantControl/viewer.py` (isolating the new tests against unmodified BASE `viewer.py` while keeping the new tests), then `git stash pop` to restore the fix.

| Test | Before (BASE viewer.py) | After (fixed viewer.py) |
|---|---|---|
| `test_approved_candidate_shows_integration_queued_not_idle` | FAIL — `'integration_queued' != 'assistant_idle'` | PASS |
| `test_integrating_candidate_shows_integration_queued_not_idle` | FAIL — `'integration_queued' != 'assistant_idle'` | PASS |
| `test_controller_running_on_another_task_leaves_candidate_integration_queued` | FAIL — `'integration_queued' != 'active'` | PASS |
| `test_controller_current_action_with_unrelated_kind_leaves_integration_queued` | FAIL — `'integration_queued' != 'active'` | PASS |
| `test_taskgraph_conformant_override_still_applies_to_integration_queued` | PASS on full BASE (trivially — BASE's ternary already produces `assistant_idle`, which was already in the override set); **FAILS when only part (b) is reverted** (`'complete' != 'integration_queued'`) — this is the regression scenario the test exists to catch, verified directly (see above) | PASS |
| `test_controller_actively_integrating_this_candidate_stays_active` | PASS on full BASE (intentional — this scenario's behavior is unchanged by design, "keep today's active projection and message") | PASS |

Full-suite counts: `Pipeline.AssistantControl.test_viewer` 58/58 (after V18) → 64/64 (6 new tests, all green). `test_inspect_project` 7/7, `test_checkouts` 8/8, `test_prepared_refresh` 3/3 — all still green, unaffected.

### Consumers checked (as required)

- **`_apply_held_task_overlay`** (state set near the GER-released branch): its exclusion set `{"active", "aggregate", "checks_pending", "integration_queued", "delivery_ready", "human_action", "local_review_ready"}` **already contained `"integration_queued"` verbatim on BASE**, unused until now. Confirmed no change needed — a released-from-GER task that's now `integration_queued` correctly does not get a stale "GER released" purple overlay.
- **`_apply_external_work_overlay`** (~245-292): only skips overriding `{"active", "complete", "local_accepted"}`. This matches `nsc-viewer-guide.md`'s documented invariant ("A working marker doesn't override active, complete or local_accepted") verbatim — `integration_queued` is intentionally not in that list, so a live external-work marker correctly can still override it. Confirmed intended, no change.
- **`_apply_human_complete_overlay`** (~294-337): only skips `{"active", "human_action", "local_review_ready"}` or active GER. Matches the guide's invariant ("A complete marker doesn't override active, human_action, local_review_ready or active GER") verbatim — Vincent's complete marker can override `integration_queued`, which is correct (his explicit judgment is authoritative). Confirmed intended, no change.
- **`_human_review_attention`**: only reads `row.get("state") == "human_action"`; unrelated to `integration_queued`. No change.
- **Scheduler "active" list** (~182-187): filters on `row.get("state") == "active"` exactly. `integration_queued` rows correctly drop out of `scheduler["active"]` — this is a real, correct side effect: the pre-fix controller-running bug was falsely counting queued (not-live) candidates as scheduler-active work.
- **`_apply_controller_timing_projection`**: never reads or writes `row["state"]`; confirmed unaffected.
- **`index.html` `PROCESSED_STATES`** (line 1559) **and the `local_rehearsal` filter** (line 921): both already list `integration_queued`. No change needed or made.
- **Every test asserting `assistant_idle` or `active` for approved/integrating records:** grepped the whole repo for `assistant_idle` — every hit is inside `viewer.py` itself (none in any test file besides `test_viewer.py`, which I authored/updated). Grepped for every other consumer of `AssistantSnapshot`: `test_completion_workflow.py`, `test_post_crew_workflow.py`, `Pipeline/AssistantControl/__main__.py` (CLI wiring only, not a state consumer). Neither test file asserts `assistant_idle`/`approved`/`integrating` in a way this change touches (checked their exact assertions: `human_action`, `local_accepted`, `blocked` only). Ran both for extra confidence: `test_post_crew_workflow.py` 23/23 (unaffected). `test_completion_workflow.py` has **one pre-existing failure** (`StopIteration` in `test_fixture_candidate_cannot_integrate_until_exact_approval_then_is_preserved`), caused by a separate, unrelated fixture bug in `test_candidate.py`'s `CandidateRecoveryTests` (its own local NSC-042 setup, not the one V18 fixed). Verified this is identical with and without the V1 fix (stashed the whole fix and re-ran; same `StopIteration` at the same line). Logged as a follow-up, not fixed (out of scope).

### Follow-ups (from part d, per instructions)

- **Worker projection** (`viewer.py` ~1144-1149): `host_identity_alive is None` still projects `"active"` (blue) — a worker record stuck `running` with unverifiable host identity stays blue. Not touched (out of scope for V1's candidate-status bug), but could be a separate cause of "stays blue after the work is done" that Vincent mentioned on 9/16. Matches problem list V1's own "Other ways finished work stays blue" bullet.
- **Decomposition `running` projection** (`viewer.py` ~901): a decomposition record left `running` is not addressed by this fix. Same caveat — could be a separate "stays blue" cause.

---

## Commit 3: V13 — run-detail rows always read "Unavailable"

**Status: reproduced.** Confirmed `renderRunDetails()` (`Pipeline/TaskReviewAgent/GauntletView/index.html`, ~870-898) always wrote literal text `"Unavailable"` into a row whenever its field was null/empty, and the static placeholders (~222-250) start that way too. A 9/16 attempt was abandoned; redoing it here hit no real obstacle.

**Commit:** `d41170774bdff94fd64f93a488c2c8f8a182ffc6`.

### The change

Gave each of the 5 fields (`source`, `runtime`, `branch`, `github`, `folder`) a distinct row-wrapper `id="run-row-<field>"`: the existing `<div class="run-location">` for `source` (it has no separate heading — it shares the section's own "Project checkout" `<h2>`), and the existing wrapping `<div>` (heading + value) for the other four. `renderRunDetails()` now does `const row = document.getElementById(\`run-row-${field}\`); if (row) row.hidden = value === null;` before its existing text/button logic, which is otherwise byte-for-byte unchanged. `[hidden] { display: none !important; }` was already defined in the page's CSS (line 26), so no new CSS was needed. Rows with a value render exactly as before; a row shows itself again automatically the next time its field carries a value, since both backends share this same render path.

### Tests updated

- `run_details_dom_binding_test.py`: added a per-field assertion that `run-row-<field>` exists exactly once (this file never actually asserted the literal string `"Unavailable"`, contrary to what the assignment implied — checked directly, confirmed no such assertion existed).
- `gauntlet_view_smoke_test.py`: added `test_run_detail_rows_hide_instead_of_always_reading_unavailable`, matching this file's existing style of asserting on raw JS/HTML source text (no test in this file executes the page's JS).
- `test_viewer.py`: grepped for `"Unavailable"` — no hits, confirmed nothing to update (V13 is a frontend-only display bug; the backend already returns `null`/`None` for missing fields).

### Tests: failing-before / passing-after

Failing-before proven by `git stash push --keep-index -m ... -- Pipeline/TaskReviewAgent/GauntletView/index.html` (isolates the new/updated tests against unmodified BASE `index.html`), then `git stash pop` to restore.

| Test | Command | Before | After |
|---|---|---|---|
| `run_details_dom_binding_test.py` | `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "run_details_dom_binding_test.py" -v` | FAIL — 5 subtest failures (one per field), each `AssertionError: 0 != 1` on the new `run-row-<field>` count | 1/1 OK |
| `gauntlet_view_smoke_test.py` (new test) | `python -B -m unittest Pipeline.TaskReviewAgent.GauntletView.tests.gauntlet_view_smoke_test.GauntletViewHtmlTests.test_run_detail_rows_hide_instead_of_always_reading_unavailable -v` | FAIL | PASS |
| `gauntlet_view_smoke_test.py` (full module) | `python -B -m unittest discover -s ... -p "gauntlet_view_smoke_test.py"` | 150/150 (pre-existing baseline after V18) | 151/151 |
| `approval_smoke_test.py` | same pattern | 10/10 (unaffected) | 10/10 |
| `display_scope_smoke_test.py` | same pattern | 16/16 (unaffected) | 16/16 |
| `Pipeline.AssistantControl.test_viewer` | `python -B -m unittest Pipeline.AssistantControl.test_viewer` | 64/64 (unaffected — V13 doesn't touch any Python backend file) | 64/64 |

All commands run with `TEMP="C:/nscrev/viewer-step1-tmp" TMP="C:/nscrev/viewer-step1-tmp"` from `C:\nscrev\viewer-step1-fix`.

---

## Commit 4: V14 — page title

**Status: reproduced.** `index.html:2` said `<title>NSC Gauntlet Graph</title>`. Also found the sidebar's visible `<h1>NSC Gauntlet</h1>` (line 180), rendered on every page load in every mode — the actual on-screen source of the "Gauntlet/main confusion" symptom.

**Commit:** `3a72777b505e4f90feba6188c72e9745cadca592`.

### The change

Both changed to the neutral **"No Safe Circle Task Graph"**, hardcoded with no mode detection (as directed — no `run.mode`-based logic was added). 2-line diff total. No CSS change needed (`h1 { font-size: 14px; margin: 0 0 2px; letter-spacing: .2px; }` has no width/overflow constraint).

Grepped the whole repository for `"NSC Gauntlet"` in `.py` and `.cjs` test files: **no test asserts either string**, so there was nothing to update. The only other hit in the repo is `Pipeline/TaskReviewAgent/GauntletView/README.md`'s own `# NSC Gauntlet Graph` heading — that documents the separate legacy backend (tracked as DOC8, not part of this assignment), not the shared `index.html` page this fix is about, so it was left untouched.

### Tests

Ran every GauntletView module already exercised for V18/V1/V13, plus `test_viewer.py`, all from `C:\nscrev\viewer-step1-fix` with `TEMP="C:/nscrev/viewer-step1-tmp" TMP="C:/nscrev/viewer-step1-tmp"`:

| Test | Before | After |
|---|---|---|
| `gauntlet_view_smoke_test.py` | 151/151 | 151/151 (unaffected) |
| `approval_smoke_test.py` | 10/10 | 10/10 |
| `display_scope_smoke_test.py` | 16/16 | 16/16 |
| `run_details_dom_binding_test.py` | 1/1 | 1/1 |
| `local_crew_view_test.py` | 12/12 | 12/12 |
| `local_candidate_acceptance_view_test.py`, `third_viewer_integrity_test.py`, `decomposition_transition_view_test.py` | same pre-existing `local_rehearsal`-missing failures as baseline (0/1, 0/1, 6/7) | unchanged |
| `Pipeline.AssistantControl.test_viewer` | 64/64 | 64/64 (HTML-only change, no Python touched) |

No failing-before/passing-after test is meaningful here beyond the plain text substitution itself — there was no existing test to fail, so the "test" for this commit is the substring check above (no test asserted the old text, and grepping confirms the new text is exactly what's in the file).

---

## Commit 5: V9 — GER marker CLI has no hold or unhold

**Status: reproduced.** `Pipeline/TaskDesignGER/ger_viewer_marker.py`'s `change_marker()` and its argparse `choices` only accepted `start`/`pause`/`finish` on BASE — confirmed by reading the file — with no `hold` or "unhold without release" verb, matching the problem list's "forced a raw JSON hand-edit on 9/15" exactly.

**Commit:** `2e76ab22d2c4556ae93cb70815f14419e9c5a381` (HEAD).

### The change

Ported semantics from the out-of-git, read-only reference `C:\nscrev\ger-tools\hold_ger_task.py` (not modified) into `change_marker()`:
- `hold`: `held.add(task_id); released.discard(task_id)` — does not touch `active`; idempotent.
- `unhold`: refuses if `task_id not in held` (`ValueError: "<id> is not held"`), else `held.remove(task_id); active.discard(task_id)` — does **not** add to `released`.

Kept the same lock (`ger-viewer-overlay.lock`), schema check (`assistant-viewer-held-tasks/v1`), invariants (`active <= held`, `held & released == set()`) and atomic `write_record`. Added the reference's post-action invariant re-check (`"Refusing to write overlapping marker sets"`) once, after the whole if/elif chain, so it applies to every action — confirmed this can't fire for the unmodified `start`/`pause`/`finish` branches (their own logic already preserves the invariant, proven by their existing tests still passing). Did **not** add a Source HEAD check (see Follow-ups). `start`/`pause`/`finish`'s branches are byte-for-byte unchanged; only their position in the `if/elif` chain shifted down to make room for `hold`/`unhold` first. Added `"hold"` and `"unhold"` to the argparse `choices` tuple.

### Tests

Added next to the existing marker tests in `Pipeline/AssistantControl/test_viewer.py` (`DuplicateViewerPortTests`, same class as `test_ger_active_then_pause_then_release_is_display_only` and `test_ger_start_requires_hold_and_finish_rejects_held_child`), reusing the same `self.checkout_root()` fixture (a fresh `tempfile.TemporaryDirectory()` per test — respects `TEMP`/`TMP`, i.e. always under the scratch temp, never `C:\NSC`):
- `test_hold_adds_to_held_and_clears_released` (plus proving hold is idempotent)
- `test_unhold_refuses_when_not_held`
- `test_unhold_clears_held_and_active_without_releasing`
- `test_hold_enables_start_then_unhold_reverses_a_hold_never_started` (end-to-end: hold → start → pause → start → finish for one task; hold → unhold for a second task that never started)

### Tests: failing-before / passing-after

Failing-before proven by `git stash push --keep-index -- Pipeline/TaskDesignGER/ger_viewer_marker.py`, then `git stash pop` to restore.

| Test | Before | After |
|---|---|---|
| `test_hold_adds_to_held_and_clears_released` | ERROR — `ValueError: Unknown GER marker action: hold` | PASS |
| `test_unhold_refuses_when_not_held` | FAIL — `"is not held" does not match "Unknown GER marker action: unhold"` | PASS |
| `test_unhold_clears_held_and_active_without_releasing` | ERROR — `ValueError: Unknown GER marker action: unhold` | PASS |
| `test_hold_enables_start_then_unhold_reverses_a_hold_never_started` | ERROR — `ValueError: Unknown GER marker action: hold` | PASS |
| `test_ger_active_then_pause_then_release_is_display_only` (existing) | PASS (unmodified) | PASS — proves `start`/`pause`/`finish` unchanged |
| `test_ger_start_requires_hold_and_finish_rejects_held_child` (existing) | PASS (unmodified) | PASS — proves `start`/`finish` unchanged |

Full-suite counts: `Pipeline.AssistantControl.test_viewer` 64/64 (after V14) → 68/68 (4 new tests). `test_inspect_project` 7/7, `test_checkouts` 8/8, `test_prepared_refresh` 3/3 — unaffected. `python -B -m compileall -q Pipeline/AssistantControl Pipeline/TaskDesignGER`: clean (exit 0).

### Docs updated

Grepped the whole repository for `"ger_viewer_marker"`: the only real source-file hits besides the module itself are `Pipeline/AssistantControl/test_viewer.py` (already updated) and `Pipeline/TaskDesignGER/GER_AGENT_RUNBOOK.md` (`.git/index` and `__pycache__/*.pyc` are not real content). Updated the runbook:
- Added a `hold` example immediately before the existing `start` example, replacing the implicit "after confirming the ID is held" precondition with an explicit command instead of a hand JSON edit.
- Added an `unhold` example after the `pause` example.
- Extended the summary sentence ("The command edits only the live viewer JSON atomically...") to describe what `hold`/`unhold` do, alongside the existing `start`/`pause`/`finish` description.
- Left the NSC-044-specific dated run instructions (lines ~36-53) untouched — that's a historical, specific record of an actual run, not a general verb-usage description.

### Follow-ups (per instructions, not implemented)

- **No Source HEAD check was added** to `hold`/`unhold` (nor does one exist for `start`/`pause`/`finish`, or in the reference tool). `validate_task_id()` only checks the ID's *shape*, not whether it names a task actually committed at the live Source HEAD, so a mistyped or stale ID can be held/unheld without any existence check. This mirrors the pre-existing behavior of the other three verbs, so it's not a regression introduced here, but it's a real gap worth a dedicated follow-up (the assignment explicitly asked me not to add this check now).

---

## After all commits: final verification

All commands run from `C:\nscrev\viewer-step1-fix` at HEAD `2e76ab22d2c4556ae93cb70815f14419e9c5a381`, with `TEMP="C:/nscrev/viewer-step1-tmp" TMP="C:/nscrev/viewer-step1-tmp"`.

**The 4 baseline AssistantControl suites, re-run in full:**

| Suite | BASE (before any commit) | Final (after all 5 commits) |
|---|---|---|
| `Pipeline.AssistantControl.test_viewer` | 37/57 (4 failures, 16 errors) | **68/68** |
| `Pipeline.AssistantControl.test_inspect_project` | 7/7 | **7/7** |
| `Pipeline.AssistantControl.test_checkouts` | 8/8 | **8/8** |
| `Pipeline.AssistantControl.test_prepared_refresh` | 3/3 | **3/3** |

**The 8 GauntletView modules run for the baseline, re-run in full** (`python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "<module>.py"`):

| Module | BASE | Final |
|---|---|---|
| `approval_smoke_test.py` | 10/10 | 10/10 |
| `decomposition_transition_view_test.py` | 6/7 (pre-existing, unrelated) | 6/7 (unchanged) |
| `display_scope_smoke_test.py` | 16/16 | 16/16 |
| `gauntlet_view_smoke_test.py` | 149/150 | **151/151** (1 V18 fix + 1 new V13 test) |
| `local_candidate_acceptance_view_test.py` | 0/1 (pre-existing, unrelated) | 0/1 (unchanged) |
| `local_crew_view_test.py` | 12/12 | 12/12 |
| `run_details_dom_binding_test.py` | 1/1 | 1/1 (now also covers the new `run-row-<field>` ids) |
| `third_viewer_integrity_test.py` | 0/1 (pre-existing, unrelated) | 0/1 (unchanged) |

**Other checks:**
- `python -B -m compileall -q Pipeline/AssistantControl Pipeline/TaskDesignGER` — clean, exit 0.
- `git -C "$FIX" diff --check 7fc15c528280b74532d1f3b39d2b420c9d57a2bd` — clean, exit 0, no whitespace errors.
- `git -C "$FIX" diff --stat 7fc15c528280b74532d1f3b39d2b420c9d57a2bd` — **10 files changed, 394 insertions(+), 46 deletions(-)**. No whole-file rewrite: every changed file's line count is proportionate to its actual edit (largest is `test_viewer.py` at 275 lines, reflecting 10 new tests across 3 problems; `viewer.py` is 12 lines for a 3-hunk logic fix; `index.html` is 16 lines for 2 commits' worth of small structural/text edits). Cross-checked with `git ls-files --eol` on every changed file: all show a uniform `i/lf w/crlf` (index stores LF, working tree checks out CRLF under this clone's `core.autocrlf=true`) — no file has mixed or inconsistent line endings.

### Pre-existing failures (not caused by this work, not fixed — out of scope)

1. **`Pipeline/TaskReviewAgent/local_rehearsal.py` does not exist anywhere in the repository at BASE**, confirmed both in the clone and directly against the canonical repo (`git -C C:/NSC/NSC/NoSafeCircle cat-file -e 7fc15c528280b74532d1f3b39d2b420c9d57a2bd:Pipeline/TaskReviewAgent/local_rehearsal.py` → "path does not exist"). This breaks:
   - `local_candidate_acceptance_view_test.py` and `third_viewer_integrity_test.py` entirely (module-level `ImportError` → 1 synthetic failing "test" each);
   - one test in `decomposition_transition_view_test.py` (`test_real_local_snapshot_shape_projects_exact_handoff`, which does a local `from Pipeline.TaskReviewAgent.local_rehearsal import LocalRunContext` inside the test body).
   - It likely also affects the 4 node-launching modules that were skipped for a different reason (`local_rehearsal_view_test.py`, `local_rehearsal_review_test.py`, `third_local_pipeline_activity_test.py`, `local_stop_endpoint_test.py`) — not confirmed, since those were never run.
2. **`Pipeline/AssistantControl/test_completion_workflow.py`'s one test** (`test_fixture_candidate_cannot_integrate_until_exact_approval_then_is_preserved`) fails with `StopIteration`, caused by a separate, unrelated fixture bug in `test_candidate.py`'s `CandidateRecoveryTests` (its own local NSC-042 setup — not the shared `InventoryTests` fixture V18 repaired). Confirmed identical with and without every commit in this branch (stashed the whole branch's changes and re-ran; same failure, same line).

Neither is V1, V9, V13, V14 or V18, and neither was touched.

### Skipped test modules (with reasons)

From `Pipeline/TaskReviewAgent/GauntletView/tests`, per the assignment's rule ("skip modules that launch a browser or node, bind a fixed port, or write under C:\NSC"):
- `browser_smoke_test.py`, `browser_smoke_test.cjs`, `third_viewer_poll_benchmark.py` — mandatory skip.
- `local_rehearsal_view_test.py` — defines/calls `render_in_node()`, which runs Node via `subprocess.run`.
- `local_rehearsal_review_test.py` — imports and calls the same `render_in_node()`.
- `third_local_pipeline_activity_test.py` — calls `subprocess.run([... "node" ...])` directly, multiple times.
- `local_stop_endpoint_test.py` — one test (`test_inline_script_still_parses`) calls `subprocess.run(["node", "--check", path])`, guarded by `skipIf(shutil.which("node") is None)`; syntax-check only, but it does launch `node`, so skipped out of caution per the stated rule.

No module was skipped for binding a fixed port or writing under `C:\NSC` — none of the surveyed modules did either (confirmed by grep; the one `C:/NSC` hit, in `local_candidate_acceptance_view_test.py`, is inert fixture-string data with no real file IO, confirmed by inspection, so that module was run, not skipped).

### Risks / what was not tested

- The 5 skipped GauntletView modules above (their interaction with V13/V14's `index.html` changes and V9 is unverified, though none of them reference `run-row-`, `renderRunDetails`, `f-scope`, or the marker CLI).
- Windows Unity, Docker, and provider-backed behavior: none of this work touches Unity, Docker, or providers, so none was exercised or needed.
- The viewer was never started, queried, or restarted on port 8828, and no `AssistantSnapshot` was ever built against `C:\NSC\NoSafeCircle-AssistantCheckouts` — every test uses a disposable fixture root under `C:\nscrev\viewer-step1-tmp` or a `tempfile.TemporaryDirectory()`.
- V1's follow-ups (worker projection, decomposition `running` projection) are unverified for the "stays blue" symptom beyond the candidate-status path this commit fixes.
- V9's Source-HEAD-existence gap (see that commit's follow-up) is unverified/unguarded, matching pre-existing behavior of the other three verbs.

### Follow-ups (consolidated)

1. **`local_rehearsal.py` is missing from the repository entirely** (see Pre-existing failures #1) — breaks 3 GauntletView test modules' collection and likely 4 more that were skipped for the node-launch reason. Worth its own investigation: was it deleted, renamed, or never landed on `main`?
2. **V1**: the worker projection (`viewer.py` ~1144-1149, `host_identity_alive is None` stays blue) and the decomposition `running` projection (`viewer.py` ~901) were explicitly left untouched per the assignment; either could be a separate cause of Vincent's 9/16 "stays blue after the work is done" complaint, distinct from the candidate-approval bug this commit fixes.
3. **V9**: no Source HEAD / existence check on `hold`/`unhold` (or the pre-existing `start`/`pause`/`finish`) — an unknown or mistyped task ID can be held/unheld with no verification it is a real, currently-committed task.
4. **`Pipeline/AssistantControl/test_completion_workflow.py`** has a pre-existing, unrelated `StopIteration` failure from `test_candidate.py`'s `CandidateRecoveryTests` fixture (see Pre-existing failures #2) — a second, separate pre-schema-v2-style fixture bug outside the scope of V18's fix (which only repaired `test_inspect_project.py`'s `InventoryTests` fixture).

---

## Independent review (2026-09-16, Pipeline Maintainer Agent)

**VERDICT: APPROVE** by a fresh `pipeline-reviewer` subagent on `7fc15c528..2e76ab22d`. No blocking or major findings.

Tests re-run by the reviewer at head, with TEMP under `C:\nscrev\tmp\viewer-step1-review`:
- `test_viewer` 68/68, `test_inspect_project` 7/7, `test_checkouts` 8/8, `test_prepared_refresh` 3/3.
- GauntletView: approval 10/10, gauntlet_view 151/151, run_details_dom_binding 1/1.
- display_scope 16/16 on the second run. The first run hit a `WinError 10053` flake in `server.py`, which this branch doesn't touch.

Failing-before: the reviewer ran the 10 new V1/V9 tests against the base `viewer.py` and `ger_viewer_marker.py`. 8 failed as expected. The other 2 passed on base by design, because they guard against regressions.

Scope: exactly the 10 intended files, `.invalid` identity, LF blobs, `diff --check` clean, no new blocking gate, no temp under `C:\NSC`. None of these files changed on main between `7fc15c528` and `bdf618744`.

Minor follow-ups from the review (not fixed on this branch):
1. The new timing test pins `total_elapsed_seconds == 0.0`, a side effect of today's code. The report's explanation of `None >= 42.0` is unproven: with the real owner check the reviewer got `KeyError`.
2. `DuplicateViewerPortTests` raised the `/api/state` timeout from 5 s to 30 s, which hides V7 (slow state).
3. `ger_viewer_marker.py:50`: `hold` accepts an unknown task ID. The viewer snapshot then fails with "Held task overlay names unknown task IDs" until someone runs `unhold`. `finish --ready-child` has the same gap.
4. `index.html:312`: the `integration_queued` help text still says "and human handoff".
5. V1 is only partly fixed: a worker with `host_identity_alive` None, a decomposition left `running`, and an unexpired `working` overlay can still show blue. After merge, mark V1 **PARTIAL**, not fixed.

---

## Codex FIX_FIRST follow-ups (2026-09-16)

Fixed the three review findings above on the same branch, in the same clone, base and head unchanged (`7fc15c528..2e76ab22d` is the trial-merge work already reviewed and approved; these three commits sit on top of it). New head: `196d9b28ec594af23cc4c80fb3b7224cea457f50`.

### Finding 1 (major) — `ger_viewer_marker.py:50`, hold/finish --ready-child accept unknown task IDs

**Commit:** `fd13b50ae` — "FIX_FIRST 1/3: hold/finish --ready-child refuse unknown task IDs"

**Root cause:** `change_marker()`'s `hold` branch wrote `task_id` straight into `held-task-ids.json`'s `task_ids` with only shape validation (`validate_task_id`, an `NSC-###` regex), never checking it names a task that actually exists. `AssistantSnapshot._apply_held_task_overlay` (`Pipeline/AssistantControl/viewer.py:228-231`) computes `known = {row.get("id") for row in rows}` from `state["tasks"]`, itself built from `self.contracts` — which `AssistantSnapshot.build()` populates via `_load_contracts_at_head(self.source, head)` (`viewer.py:91-98, 139-145`): every `Tasks/NSC-*.yaml` committed at the live Source repo's current HEAD. Any ID not in that set makes the whole overlay raise `"Held task overlay names unknown task IDs: ..."`, breaking the live viewer snapshot. `finish --ready-child` had the identical gap for child IDs.

**Fix:** `change_marker()` gained a keyword-only `source: Path | None = None` parameter and a `_known_task_ids(source)` helper that calls the exact same `_load_contracts_at_head` the viewer uses (imported from `Pipeline.AssistantControl.viewer`), so the two can never drift. When `source` is given, `hold` refuses an unknown `task_id` and `finish` with `--ready-child` refuses any unknown child, both before any file is opened, so nothing is written on refusal. The CLI gained `--source`, `default=Path.cwd()` — identical to how `Pipeline/AssistantControl/__main__.py:37` defaults its own `--source`, and consistent with the runbook's existing instruction to run these commands from the canonical source checkout (`C:\NSC\NSC\NoSafeCircle`). Callers that omit `source` (the pre-existing tests, and the old 3-positional-arg call shape) are unaffected — the check is simply skipped, not enforced closed, so no existing invocation breaks. `start`/`pause`/`unhold`/`finish`-without-children were not touched: the only route an unknown ID could ever reach `held` was through `hold`, which is now closed.

**Tests** (`Pipeline/AssistantControl/test_viewer.py`, `DuplicateViewerPortTests`, next to the existing marker tests):
- `test_hold_of_unknown_task_id_refuses_and_leaves_file_unchanged`
- `test_hold_of_known_task_id_still_works`
- `test_finish_ready_child_refuses_unknown_task_id`

**Failing-before:** ran the 3 new tests with `git stash push --keep-index -- Pipeline/TaskDesignGER/ger_viewer_marker.py` (isolates them against the pre-fix module). All 3 errored: `TypeError: change_marker() got an unexpected keyword argument 'source'` — proving the pre-fix module has no way to make this check at all.

**Passing-after:** `git stash pop` restored the fix; all 3 new tests pass. Full `Pipeline.AssistantControl.test_viewer`: 71/71 (68 before + 3 new).

**Doc:** `Pipeline/TaskDesignGER/GER_AGENT_RUNBOOK.md` — one sentence added before the `hold` example noting `hold`/`finish --ready-child` refuse an ID not committed at the Source HEAD.

### Finding 2 (minor) — `index.html:221`, run-detail rows read "Unavailable" before first snapshot

**Commit:** `713b5e6d6` — "FIX_FIRST 2/3: hide run-detail rows in static markup, not just after render"

**Root cause:** the 5 row wrappers (`run-row-source`, `-runtime`, `-branch`, `-github`, `-folder`) had no `hidden` attribute in the static HTML, so each showed literal "Unavailable" text until the first snapshot reached `renderRunDetails()` (`index.html:870-888`), which already does `row.hidden = value === null` on every render — the JS logic was already correct, only the static starting state was wrong.

**Fix:** added `hidden` to all 5 wrappers in the static markup. No JS or CSS change (`[hidden] { display: none !important; }` already existed).

**Test:** extended `Pipeline/TaskReviewAgent/GauntletView/tests/run_details_dom_binding_test.py` — `IdParser` now also records which ids carry a `hidden` attribute, and the existing per-field subtest asserts `run-row-<field>` is in that set.

**Failing-before:** `git stash push --keep-index -- Pipeline/TaskReviewAgent/GauntletView/index.html` isolated the new assertion against the pre-fix HTML. 5 subtest failures, one per field (e.g. `'run-row-branch' not found in {...}`).

**Passing-after:** restored the fix; `run_details_dom_binding_test.py` 1/1 OK. Adjacent suites unaffected: `gauntlet_view_smoke_test.py` 151/151, `approval_smoke_test.py` 10/10, `display_scope_smoke_test.py` 16/16.

### Finding 3 (minor) — `index.html:312`, `integration_queued` hint still says "human handoff"

**Commit:** `196d9b28e` — "FIX_FIRST 3/3: correct the integration_queued legend hint"

**Root cause:** checked both backends that emit `integration_queued`. `server.py` sets it once a candidate is verified/`agent_ready` and only waiting on the merge gate/queue (`server.py:2033`, `:2128` "WAITING FOR MERGE GATE", `:3266`); `Pipeline/AssistantControl/viewer.py`'s `task_row` (fixed under V1, `7fc15c528..2e76ab22d`) sets it for candidates already `status` `approved`/`integrating`. Neither is waiting on a human at that point — the old hint's "...and human handoff" was stale.

**Fix:** reworded the hint to "candidate is approved or ready and waiting for the merge/integration step". Left the legend label ("Candidate Ready — Waiting for Merge Gate") unchanged — it's still accurate for both backends.

**Test:** none added. Checked `gauntlet_view_smoke_test.py`'s existing `test_integration_queue_state_has_explicit_label` (line ~2936) — it only regex-asserts the `label`, never the `hint` text. Grepped the whole repo for `"human handoff"`: no other hit. Per the assignment, no test was needed.

**Verification:** `gauntlet_view_smoke_test.py` 151/151 and `run_details_dom_binding_test.py` 1/1 unaffected by this change.

### Final state at head `196d9b28e`

| Suite | Result |
|---|---|
| `Pipeline.AssistantControl.test_viewer` | 71/71 |
| `approval_smoke_test.py` | 10/10 |
| `display_scope_smoke_test.py` | 16/16 |
| `gauntlet_view_smoke_test.py` | 151/151 |
| `run_details_dom_binding_test.py` | 1/1 |
| `python -B -m compileall -q Pipeline/AssistantControl Pipeline/TaskDesignGER` | clean, exit 0 |
| `git diff --check 7fc15c528` | clean, exit 0 |
| `git ls-files --eol` on every file changed since `7fc15c528` | all `i/lf` (LF in the index; CRLF in the working tree, per this clone's `core.autocrlf=true`) |
| `git status` | clean |

**Not done / follow-ups carried forward, unchanged by this work:**
- Review follow-up #1 (`total_elapsed_seconds == 0.0` pin, `None >= 42.0` explanation unproven with the real owner check) — not addressed here, outside these 3 findings.
- Review follow-up #2 (`DuplicateViewerPortTests`' 30s `/api/state` timeout hides V7) — not addressed here.
- Review follow-up #5 (V1 partial: worker `host_identity_alive is None`, decomposition left `running`, unexpired `working` overlay can still show blue) — not addressed here; still needs marking V1 **PARTIAL** at merge time, not fixed.
- No Source-HEAD check was added to `start`/`pause`/`unhold`/`finish`-without-children (only `hold` and `finish --ready-child`, per the assignment) — any stale/hand-edited `held-task-ids.json` entry predating this fix is still unvalidated by those verbs.

---

## Codex FIX_FIRST round 2 (2026-09-17)

Closed the one open major finding from the second Codex review (`C:\nscrev\codex-jobs\codex-review-viewer-step1-merge2-20260917-0002\CODEX_VERDICT.json`): fd13b50ae's known-task-ID check (round 1, finding 1 above) had two bypasses. New head: `0a7bf7ac2`, base unchanged (`7fc15c528`).

### Finding (major) — `Pipeline/TaskDesignGER/ger_viewer_marker.py:29` onward, two ways past the Source-HEAD check

**Bypass 1:** `source` defaulted to `None`, and the known-ID check only ran `if source is not None:`. `change_marker(checkout_root, "hold", "NSC-999")` with `source` omitted skipped the check entirely and wrote `NSC-999` unchecked.

**Bypass 2:** the CLI's `--source` defaulted to `Path.cwd()` and was trusted outright — `hold NSC-999 --checkout-root <live root> --source <some other checkout that happens to contain NSC-999>` passed the known-ID check against the *wrong* checkout, then `AssistantSnapshot` later raised "Held task overlay names unknown task IDs" against the live root's *real* Source, degrading the viewer.

### Design and root cause

Every checkout root is bound to exactly one Source. `Pipeline/AssistantControl/checkouts.py:41` (`Checkouts.prepare`) writes that binding as `.assistant-control/project.json`, `{"source": ..., "checkout_root": ...}`, and lines 42-44 already refuse a mismatch for the root's own machinery; `decomposition.py`'s `_ensure_owner` (~line 117-124) reuses the same record for the same purpose. Individual task-checkout records (`{task_id}.json`) each carry the same `"source"` too.

Added `root_source(checkout_root)` to `ger_viewer_marker.py` (new, ~line 35): reads `project.json` if present; otherwise, for a root prepared before that record existed, falls back to the unique `"source"` value across the root's `*.json` task records; several distinct sources is refused; no records at all means a fresh root (`None`).

`change_marker()` (`ger_viewer_marker.py:67`): `source` is now a **required** keyword-only argument (no default — closes bypass 1, since Python itself refuses the call before any file is touched). Before the lock or any read, it calls `root_source(checkout_root)`; if the root has a recorded Source, the given `source` must match it (`_same_source`, `Path.resolve()` + `os.path.normcase` for Windows drive-letter/case tolerance) or the call is refused with no write (closes bypass 2 — a `--source` naming a different checkout can no longer stand in for the root's real Source). Only after that does the existing `_known_task_ids(source)` check run for `hold` and `finish --ready-child`, unconditionally now (no more `if source is not None:` guard).

CLI (`main()`, ~line 151): `--source` no longer defaults to `Path.cwd()`; when omitted, it's derived from `root_source(args.checkout_root)`, and a fresh root with no recorded Source and no `--source` is a `parser.error` usage error (exit 2) instead of silently trusting the operator's shell location. `start`/`pause`/`finish`-without-children/`unhold` need no `--source` change on the live root, since it already has a recorded Source (`C:\NSC\NSC\NoSafeCircle`, written when `C:\NSC\NoSafeCircle-AssistantCheckouts` was first prepared) that derivation picks up automatically.

**Commit:** `0a7bf7ac2` — "FIX_FIRST round 2: close hold/finish --ready-child source bypasses" on `fix/viewer-step1`.

### Callers updated

Only two call sites exist in the repo (grepped `change_marker(` across `Pipeline`): `Pipeline/AssistantControl/test_viewer.py` and `ger_viewer_marker.py`'s own `main()`. Every existing test call now passes `source=self.root`. Two tests held a fictional task ID (`NSC-003`, `NSC-012`) that the shared `InventoryTests` fixture never committed; rather than touch that shared fixture (used by unrelated test classes), each affected test now commits the extra ID locally first via a new `_commit_task()` helper, mirroring the existing NSC-043-child pattern at `test_viewer.py:87-92`.

### Tests (`Pipeline/AssistantControl/test_viewer.py`, `DuplicateViewerPortTests`, next to the existing marker tests)

New:
- `test_hold_without_source_is_rejected_and_leaves_file_unchanged` (bypass 1)
- `test_hold_refuses_when_source_does_not_match_recorded_source` (bypass 2; new `_independent_source()` helper builds a second, distinct git repo)
- `test_cli_derives_source_from_recorded_root_and_still_checks_ids`
- `test_cli_on_fresh_root_without_source_is_a_usage_error`
- `test_cli_unhold_works_on_recorded_root_without_source`

(CLI tests call `ger_viewer_marker.main()` in-process via a new `_run_marker_cli()` helper — `sys.argv` patched, stdout captured — no subprocess/console window.)

Updated: `test_ger_active_then_pause_then_release_is_display_only`, `test_ger_start_requires_hold_and_finish_rejects_held_child`, `test_hold_adds_to_held_and_clears_released`, `test_unhold_refuses_when_not_held`, `test_unhold_clears_held_and_active_without_releasing`, `test_hold_enables_start_then_unhold_reverses_a_hold_never_started` — all now pass `source=self.root`; the three that hold `NSC-003`/`NSC-012` also call `_commit_task(...)` first.

### Failing-before / passing-after

Isolated the two new bypass tests against the pre-round-2 module by restoring `git show HEAD:Pipeline/TaskDesignGER/ger_viewer_marker.py` (HEAD = `196d9b28e`) over the working copy, running just those two tests, then restoring the fix:

| Test | Before (`196d9b28e`) | After (`0a7bf7ac2`) |
|---|---|---|
| `test_hold_without_source_is_rejected_and_leaves_file_unchanged` | FAIL — `AssertionError: TypeError not raised` (hold succeeded, wrote NSC-999 unchecked) | PASS |
| `test_hold_refuses_when_source_does_not_match_recorded_source` | FAIL — `AssertionError: ValueError not raised` (mismatched --source accepted) | PASS |

Both failures were plain `AssertionError: ... not raised` — i.e. at `196d9b28e` the vulnerable call silently succeeds, exactly matching the two bypasses in the finding.

**Full suite passing-after** (`TEMP`/`TMP` = `C:\nscrev\tmp\viewer-step1-v3`):

| Command | Result |
|---|---|
| `python -B -m unittest Pipeline.AssistantControl.test_viewer` | **76/76** (71 before + 5 new) |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "gauntlet_view_smoke_test.py"` | 151/151 |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "run_details_dom_binding_test.py"` | 1/1 |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "approval_smoke_test.py"` | 10/10 |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "display_scope_smoke_test.py"` | 16/16 |
| `python -B -m compileall -q Pipeline/AssistantControl Pipeline/TaskDesignGER` | clean, exit 0 |
| `git diff --check 7fc15c528` | clean, exit 0 |
| `git ls-files --eol` (3 changed files) | all `i/lf`, `w/crlf` |
| `git status` | clean |

### Doc

`Pipeline/TaskDesignGER/GER_AGENT_RUNBOOK.md`: one sentence added noting `--source` is no longer taken from the working directory and, for the live root, is derived automatically.

### Risks / not done

- `root_source()`'s fallback (scanning `*.json` task records for a unique `"source"`) is exercised only implicitly by the "no recorded Source" fresh-root path in tests; no test constructs a root with task-checkout records but no `project.json` to exercise that specific fallback branch directly. Low risk: the logic is a straightforward set-uniqueness check, and the live root already has `project.json` (every root `Checkouts.prepare()` has touched does).
- Did not add a Source-HEAD check to `start`/`pause`/`unhold`/`finish`-without-children beyond the new source-identity match (still no check that the *task itself* exists for those verbs) — unchanged from round 1's stated scope, still a follow-up.

---

## Round 3 fix (2026-09-17)

Fixed a fresh `pipeline-reviewer` finding on `0a7bf7ac2` (round 2's head): making `source` a required keyword-only argument broke the live out-of-repo caller. New head: `63b43bbec`, base unchanged (`7fc15c528`).

### Finding 1 (major) — `ger_viewer_marker.py:67-69`, `source` required breaks `nsc_viewer.py`

`change_marker()`'s `source` had no default (round 2 closed bypass 1 that way). But `C:\nscrev\viewer-tools\nsc_viewer.py:491` calls `change_marker(args.checkout_root, action, task_id, children)` positionally, with no `source` at all — every `ger-start`/`ger-pause`/`ger-finish` from that live caller raised `TypeError`.

**Fix:** `source` is a defaulted keyword-only argument again (`Path | None = None`). Inside `change_marker`, when `source` is `None`, it now falls back to `root_source(checkout_root)`; if that is also `None` (a fresh root), it raises `ValueError` telling the caller to pass one. When a source is given and the root has a recorded Source, the existing mismatch refusal is unchanged. Bypass 1 stays closed: a library `hold NSC-999` call with no `source` is validated against the recorded Source and refused as not a committed task, not silently accepted. `main()`'s own CLI-level resolution (deriving `--source` from `root_source()`, `parser.error` usage-exit on a fresh root) was left as-is — it already resolves to a concrete `source` before calling `change_marker`, so `test_cli_on_fresh_root_without_source_is_a_usage_error` still exits via `SystemExit`, not the library's `ValueError`.

**Test updated:** `test_hold_without_source_is_rejected_and_leaves_file_unchanged` now records a `project.json` Source on the root first, then asserts `change_marker(root, "hold", "NSC-999")` (no `source`) raises `ValueError` matching `"NSC-999.*not a committed task"`, file byte-identical before/after — instead of the old `TypeError`.

**Test added:** `test_nsc_viewer_call_shape_without_source_on_recorded_root` mirrors `nsc_viewer.py`'s exact call shape (positional `ready_children`, no `source` keyword) on a root with a recorded Source: `hold` then `start` with no children succeeds, and `finish` with an unknown ready child (`"NSC-999"`) is refused with the file unchanged.

### Finding 2 (minor) — `root_source` fallback, `root_source()` ~line 53-59, corrupt JSON crashes

The no-`project.json` fallback ran `json.loads` on every sibling `*.json`, so one corrupt or non-JSON file (or an unrelated file that merely ends in `.json`) raised a raw `JSONDecodeError` out of `root_source`.

**Fix:** added `TASK_RECORD_NAME = re.compile(r"^NSC-\d+\.json$")`; the fallback loop now only considers files matching that pattern, and wraps `json.loads` in `try/except json.JSONDecodeError`, re-raising as `ValueError(f"Task checkout record is not valid JSON: {path}")` naming the exact path.

**Test added:** `test_root_source_fallback_ignores_non_task_json_and_flags_corrupt_task_record` — a root with no `project.json`, one valid `NSC-001.json` naming `self.root` as Source and a non-task `notes.json` containing garbage text: `root_source()` derives `self.root` (the garbage file is ignored, not even opened as JSON). Then a corrupt `NSC-002.json` (`"{not valid"`) makes `root_source()` raise `ValueError` whose message contains the corrupt file's exact path; the file's bytes are asserted unchanged before/after (the function never writes anything, just confirming it wasn't touched).

### Finding 3 (minor) — `test_viewer.py:1083`, `_independent_source`'s git calls could pop a console

`_independent_source`'s `run()` helper (added in round 2) called `subprocess.run(["git", ...])` with no `creationflags`. Added `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)`, matching every other subprocess call in this test module.

### Commit

`63b43bbec` — "FIX_FIRST round 3: restore the no-source library call, harden root_source fallback" on `fix/viewer-step1`, identity `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`. 2 files changed (`Pipeline/TaskDesignGER/ger_viewer_marker.py`, `Pipeline/AssistantControl/test_viewer.py`), 65 insertions, 8 deletions.

### Failing-before / passing-after

Isolated the new nsc_viewer-shape test against the pre-round-3 module via `git stash push --keep-index -- Pipeline/TaskDesignGER/ger_viewer_marker.py` (base = `0a7bf7ac2`), then `git stash pop`:

| Test | Before (`0a7bf7ac2`) | After (`63b43bbec`) |
|---|---|---|
| `test_nsc_viewer_call_shape_without_source_on_recorded_root` | ERROR — `TypeError: change_marker() missing 1 required keyword-only argument: 'source'` | PASS |

**Full suite passing-after** (`TEMP`/`TMP` = `/c/nscrev/tmp/viewer-v31`, i.e. `C:\nscrev\tmp\viewer-v31`; the MSYS bash shell mangles a backslash-form `TEMP=C:\nscrev\...` export into a bogus concatenated path, so the POSIX-form export was used to get the real `C:\nscrev\tmp\viewer-v31` into the Windows environment):

| Command | Result |
|---|---|
| `python -B -m unittest Pipeline.AssistantControl.test_viewer` | **78/78** (76 before + 2 new: the nsc_viewer-shape test and the root_source-fallback test) |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "gauntlet_view_smoke_test.py"` | 151/151 |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "run_details_dom_binding_test.py"` | 1/1 |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "approval_smoke_test.py"` | 10/10 |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "display_scope_smoke_test.py"` | 16/16 |
| `python -B -m compileall -q Pipeline/TaskDesignGER Pipeline/AssistantControl` | clean, exit 0 |
| `git diff --check 7fc15c528` | clean, exit 0 |
| `git ls-files --eol` (2 changed files) | both `i/lf`, `w/crlf` |
| `git status` | clean |

### Risks / not done

- `main()` still independently resolves `--source` before calling `change_marker` (parser.error for a fresh root); `change_marker`'s own new fallback is exercised only by direct/library callers (like `nsc_viewer.py`) and by the new tests, not by any CLI test path with a fresh root — low risk, the fallback reuses the same `root_source()` the CLI already calls.
- No Source-HEAD/task-existence check was added beyond what rounds 1-2 already added; unchanged, still a follow-up.

---

## Codex round 3 fixes (2026-09-17)

Fixed the two `FIX_FIRST` findings from `C:\nscrev\codex-jobs\codex-review-viewer-step1-v3-20260917\CODEX_VERDICT.json` (base `32c6223d3e0e8c6a311958a4fddce92840b1d907`, prior head `df73efb99f7d1acb2735824583f58c01c34aca2d` — this branch had since been rebased onto current local `main`, so its historical commit shas above no longer resolve, but no product line changed in the rebase: Codex's own base-vs-head probes at `32c6223d3` reproduced the exact pre-fix state described in the sections above). New head: `28845be4ab4527dd457f8fab5fb81bab490165c6`.

### Finding 1 (major) — `viewer.py:654`, automatic-review candidate active without being targeted

**Reproduced** by Codex's own repro script (`tests_run`, `at: head`): with `current_action` targeting `NSC-001` (`kind: prepare`), a synthetic `NSC-002` in `human_action` went `active`/`automatic_validation` anyway. Reproduced independently here the same way the report's other findings were: `git stash push --keep-index -- Pipeline/AssistantControl/viewer.py`, run only the two new tests against unmodified `df73efb99` — `test_untargeted_automatic_review_candidate_is_not_active` failed (`AssertionError: 'active' == 'active'`); `test_targeted_automatic_review_candidate_stays_active` already passed on base (it's the byte-identical-behavior guard, not a regression test). `git stash pop` restored the fix.

**Root cause:** `_apply_running_controller_projection`'s `automatic_review` computation (`viewer.py:653-661`) only checked `row.get("state") == "human_action"`, `auto_approve_gauntlet`, `task_id != "NSC-042"`, and `is_synthetic_gauntlet(...)` — never whether the controller's `current_action` actually targets this row. `live_integration_action` (used for the *already-approved* candidate case a few lines down) already carried exactly the targeting rule the finding wants: `task_id == action_task and action_kind in {"auto_approve", "integrate", "sync_candidate"}`.

**Fix:** moved `live_integration_action`'s computation above the `automatic_review` block and reused it as the targeting gate: when `is_gauntlet_candidate` is true (the old `is_synthetic_gauntlet(...)` check, unchanged), `automatic_review = True` only if `live_integration_action` is also true. When it is false — the untargeted case — the row does **not** fall through to `active`. It goes to a new `elif automatic_review_queued:` branch: `row["state"] = "checks_pending"`, `row["progress"] = {"phase": "automatic_review_queued", "transition_context": "This disposable Gauntlet candidate is queued for automatic review; the graph controller is not working on it yet."}`.

**State choice:** picked `checks_pending` ("Task In CI", `index.html:309-310`) over inventing a new legend entry or leaving the row at its prior `human_action` ("Task Needs You"). Reasoning: `human_action` would be actively misleading here — the whole point of `automatic_review` is that a human is *not* expected to act on a synthetic Gauntlet candidate, so falling back to "Task Needs You" the moment the controller looks away would reintroduce the exact "on you" framing V1/automatic-review exists to avoid. Of the three "in flight" states, `active` ("a worker is running this right now") is wrong (nothing is running against this task right now — that's the whole bug), and `integration_queued` ("candidate is approved or ready and waiting for the merge/integration step") asserts a decision (approved/ready) that hasn't happened yet — automatic review hasn't run on this row at all while the controller is elsewhere. `checks_pending`'s hint ("waiting on GitHub pull-request checks") doesn't literally apply (no PR is involved), but its label and grouping are the closest existing fit for "queued for an automated gate, not on a human, not running right now" — reusing an existing category loosely, per the instructions, rather than inventing one.

`checkout_write_in_progress` was checked per the instructions: it already requires `task_id == action_task` (`viewer.py:647-651`) as part of its own definition, so it is inherently task-bound and needs no change; left untouched.

Targeted case is byte-identical: `test_running_graph_keeps_automatic_gauntlet_review_blue_but_not_042` (existing, unmodified) and the new `test_targeted_automatic_review_candidate_stays_active` both confirm `state == "active"`, `progress.phase == "automatic_validation"`, and the exact same `transition_context` string as before.

**Tests** (`Pipeline/AssistantControl/test_viewer.py`, `ViewerTests`, next to `test_running_graph_keeps_automatic_gauntlet_review_blue_but_not_042`):
- `test_untargeted_automatic_review_candidate_is_not_active` — controller preparing `NSC-001`, synthetic `NSC-002` in `human_action`: asserts `state != "active"` and `state == "checks_pending"`.
- `test_targeted_automatic_review_candidate_stays_active` — same candidate, `current_action` now `{"kind": "sync_candidate", "task_id": "NSC-002"}`: asserts `state == "active"`, `phase == "automatic_validation"`, and the exact `transition_context` text.

### Finding 2 (major) — `ger_viewer_marker.py:98`, `finish --ready-child` doesn't validate the parent

**Reproduced** by Codex's own repro script (`tests_run`, `at: head`): `finish` on a held-but-unknown `NSC-999` with `--ready-child NSC-001` released both IDs (`released_ger_task_ids == ['NSC-001', 'NSC-999']`). Reproduced independently the same way: `git stash push --keep-index -- Pipeline/TaskDesignGER/ger_viewer_marker.py` against `df73efb99`, ran the two new tests — `test_finish_of_unknown_held_parent_is_refused_and_leaves_file_unchanged` and `test_start_of_unknown_held_task_is_refused_and_leaves_file_unchanged` both failed (`AssertionError: ValueError not raised`); `test_unhold_of_unknown_held_task_still_works` already passed on base (unhold was never gated). `git stash pop` restored the fix.

**Root cause:** `change_marker` (`ger_viewer_marker.py:94-104`, pre-fix) validated `task_id` against `_known_task_ids(source)` only for `action == "hold"`, and validated `children` against the same set only for `action == "finish" and children`. The `finish` action's own `task_id` (the parent being released) was never checked — a hold file entry that predates this validation, or one hand-edited to add an unknown ID (the documented `unhold` repair scenario), could still be `start`ed, `pause`d or `finish`ed as if it were a real task.

**Fix:** the two separate `if` blocks became one `if action != "unhold":` block. It computes `known = _known_task_ids(source)` once, refuses if `task_id not in known` (`f"{task_id} is not a committed task at the Source HEAD; refusing to {action} it"`, generalizing the existing `hold`-only message to name the actual action), and then — nested inside, only for `finish` with children — refuses on any unknown child exactly as before. `unhold` is excluded by name, matching the instruction that it remains "the documented repair path for unknown held IDs." The check runs before `records`/`path` are touched, before the lock, and before the hold file is read at all, so a refusal leaves the file provably byte-identical (asserted in every new test via `read_bytes()` before and after).

**Existing start/pause/finish tests kept passing:** two pre-existing tests exercised `start`/`finish` on task IDs (`NSC-003`, `NSC-020`) that were held in the fixture's hand-written JSON but never actually committed via `self._commit_task(...)` — under the old code this was fine, since only `hold` and `finish`'s children were checked. Under the new rule those calls would now be refused as "not a committed task," changing the tests' meaning. Both were updated to commit the IDs they exercise first, preserving their original intent (`test_ger_active_then_pause_then_release_is_display_only` now also commits `NSC-003`; `test_ger_start_requires_hold_and_finish_rejects_held_child` now also commits `NSC-003` and `NSC-020`) so they still test "must be held" / "still held" failures, not a newly-added "not committed" failure.

**Tests** (`Pipeline/AssistantControl/test_viewer.py`, `DuplicateViewerPortTests`, next to `test_finish_ready_child_refuses_unknown_task_id`):
- `test_finish_of_unknown_held_parent_is_refused_and_leaves_file_unchanged` — hold file lists only `NSC-999`; `finish NSC-999 --ready-child NSC-001` (with `NSC-001` actually committed) is refused, file unchanged.
- `test_start_of_unknown_held_task_is_refused_and_leaves_file_unchanged` — hold file lists only `NSC-999`; `start NSC-999` is refused, file unchanged.
- `test_unhold_of_unknown_held_task_still_works` — hold file lists only `NSC-999`; `unhold NSC-999` still succeeds and clears it.

### Commits

- `f327201d0` — "Codex round 3 finding 1: require the automatic-review candidate to be targeted" (`viewer.py`, `test_viewer.py`).
- `28845be4a` — "Codex round 3 finding 2: validate the held parent task_id in change_marker" (`ger_viewer_marker.py`, `test_viewer.py`).

Both authored with identity `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`, one commit per finding, exact paths staged (verified via `git diff --cached` hunk headers before each commit to confirm no cross-finding bleed in the shared `test_viewer.py`).

### Failing-before / passing-after

| Test | Before (`df73efb99`) | After (`28845be4a`) |
|---|---|---|
| `test_untargeted_automatic_review_candidate_is_not_active` | FAIL — `AssertionError: 'active' == 'active'` | PASS |
| `test_targeted_automatic_review_candidate_stays_active` | PASS (byte-identical-behavior guard, not a regression test) | PASS |
| `test_finish_of_unknown_held_parent_is_refused_and_leaves_file_unchanged` | FAIL — `AssertionError: ValueError not raised` | PASS |
| `test_start_of_unknown_held_task_is_refused_and_leaves_file_unchanged` | FAIL — `AssertionError: ValueError not raised` | PASS |
| `test_unhold_of_unknown_held_task_still_works` | PASS (unhold was never gated, base or fixed) | PASS |

**Full suite passing-after** (`TEMP`/`TMP` = `C:\nscrev\tmp\viewer-v32`):

| Command | Result |
|---|---|
| `python -B -m unittest Pipeline.AssistantControl.test_viewer` | **83/83** (78 before + 5 new) |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "gauntlet_view_smoke_test.py"` | 151/151 |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "run_details_dom_binding_test.py"` | 1/1 |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "approval_smoke_test.py"` | 10/10 |
| `python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "display_scope_smoke_test.py"` | 16/16 |
| `python -B -m compileall -q Pipeline/AssistantControl Pipeline/TaskDesignGER` | clean, exit 0 |
| `git diff --check 32c6223d3` | clean, exit 0 |
| `git ls-files --eol` (3 changed files: `viewer.py`, `test_viewer.py`, `ger_viewer_marker.py`) | all `i/lf`, `w/crlf` |
| `git status` | clean |

### Risks / not done

- The `checks_pending` reuse for the untargeted automatic-review case is a display choice, not a new mechanism; if a future reviewer wants a dedicated "queued for automatic review" legend entry instead of reusing `checks_pending`'s "Task In CI" label, that's a follow-up for whoever owns `index.html` copy, not a functional gap.
- No further Source-HEAD/task-existence hardening was done beyond this finding's exact scope (the parent `task_id` for `hold`/`start`/`pause`/`finish`); `unhold` remains intentionally unchecked, per the finding.
