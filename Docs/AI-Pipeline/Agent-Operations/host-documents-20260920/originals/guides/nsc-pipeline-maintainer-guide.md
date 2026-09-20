# Pipeline Maintainer and Reviewer: operating guide

The **Pipeline Maintainer** fixes the pipeline itself: AssistantControl, ExecutionCrew, TaskGraph, TaskDecomposition, the viewer, and the GER and viewer tools. Its work queue is `C:\NSC\nsc-pipeline-problems.md`.

The **Reviewer** is always a *different, fresh* agent. It checks each fix adversarially before the Integration Steward merges it with Vincent's go. This is the "Astra" role from 9/13-9/14.

**How it runs (2026-09-16).**
- The Maintainer is a standing desktop session titled **Pipeline Maintainer Agent**. Its rules are in `C:\Users\VincentLiguori\.claude\agents\pipeline-maintainer.md`, and its launch prompt is in `C:\NSC\nsc-agent-launch-prompts.md`.
- Each review is a fresh `pipeline-reviewer` (`C:\Users\VincentLiguori\.claude\agents\pipeline-reviewer.md`), run on the host `claude` CLI on the Gmail account by default - **not** as an Agent-tool subagent, which spends the scarce desktop account. Section 2.6 has the three ways and when each applies.
- The Game Agent is the Integration Steward and merges.
- Other agents hand pipeline bugs to this session by title (`C:\NSC\nsc-agent-directory.md`).

Why this role exists:
- Good fixes were built on 9/13 and proven live, but **never reached `main`**: worker recovery, decomposition `needs_human`, container timeout, Docker mount paths, the viewer test fixture.
- Meanwhile orchestrators re-diagnosed the same failures.
- Vincent's complaint about over-engineering ("I need 20 audits before you can run a task") means fixes must remove friction, not add gates.

Read first: `C:\NSC\nsc-pipeline-runbook.md`, `AGENTS.md`, and `C:\NSC\nsc-pipeline-problems.md`.

---

## 1. Authority

**Maintainer may:**
- make standalone clones under `C:\nscrev\`;
- create `fix/<topic>` branches there;
- write code and tests;
- run tests in the clone;
- commit there with the automation identity;
- write reports;
- hand implementation to Codex (`nsc-codex-jobs-guide.md`) and review its output.

**Ask first (the Main Orchestrator, who asks Vincent):**
- which problem to take when priorities are unclear;
- any change that **adds** a blocking gate, audit, required field or refusal. Vincent wants fewer hard gates; propose advisory signals instead;
- any test run that needs Unity, Docker containers or provider calls.

**Never:**
- edit the canonical checkout `C:\NSC\NSC\NoSafeCircle`, a live task checkout, `C:\nscrev\branch-verify`, or live `.assistant-control` records;
- merge into `main`. The Integration Steward does that after review and Vincent's go;
- push;
- restart live viewers or workers;
- write test temp files under `C:\NSC`.

---

## 2. Workflow per problem

### 2.1 Set up

```bash
TOPIC=viewer-integration-queued
FIX=C:/nscrev/$TOPIC-fix
BASE=$(git -C C:/NSC/NSC/NoSafeCircle rev-parse main)
git clone -q -c core.autocrlf=true -c core.longpaths=true C:/NSC/NSC/NoSafeCircle "$FIX"
git -C "$FIX" switch -c fix/$TOPIC "$BASE"
```

- Commit identity: get it from `Pipeline.TaskReviewAgent.git_identity_guard.validated_agent_git_identity()` (default `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`). Never invent one, and never use a GitHub noreply address.
- Clone paths get long; `core.longpaths` avoids "Filename too long".

### 2.2 Reproduce first

- Write or run a **failing-before** test on the unmodified base: it must fail, or prove the bug, on `main`'s code.
- Classify the problem as **reproduced** (you saw it fail) or **theoretical** (reasoned from code). Reviews treat these differently.
- If it doesn't reproduce, stop and report; don't fix a theory as if proven.

### 2.3 Fix

- Smallest change that fixes the cause. Match surrounding code style.
- **Propagate every change, then re-grep.**
  - A new noun (state, field, command) needs a schema entry, its readers and writers, a test, and docs.
  - Grep for every place the old behaviour or string appears.
- **Keep existing behaviour and CLI** unless the problem is the behaviour. Add, don't break.

### 2.4 Test (in the clone only)

```bash
cd "$FIX"
python -B Pipeline/TaskGraph/taskcontrol.py validate
python -B -m compileall -q Pipeline/AssistantControl Pipeline/ExecutionCrew Pipeline/TaskDecomposition Pipeline/TaskGraph Pipeline/TaskReviewAgent
python -B -m unittest Pipeline.AssistantControl.test_<module>            # focused suite(s)
PYTHONPATH="$FIX" python -B -m Pipeline.TaskReviewAgent.tests.<name>      # TaskReviewAgent tests run as modules
python -B -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "*_smoke_test.py"   # viewer front end
git diff --check "$BASE"
```

- **Temp directories.**
  - Set `TEMP`/`TMP` to a scratch folder.
  - Some TaskReviewAgent suites write under `C:\NSC`. Set `NSC_DECOMP_PENDING_TEMP`, `NSC_REVISION_RACE_TEMP` and `NSC_DECOMP_WAKE_TEMP` to a scratch folder.
  - **Skip** `local_candidate_source_integration_test`, `local_source_wait_completion_test` and `immutable_crew_manifest_test` unless Vincent allows them (they hard-code `C:\NSC`).
- **Pre-existing failures.** Run the same suite on the base clone commit. On 9/16 `test_viewer` was **37/57** because of a pre-schema-v2 fixture (V18). Report only what your change affected: failing-before and passing-after per test.
- **Unity-dependent fixes.** Say what needs a Windows Unity run. The Task Orchestrator or Steward runs it with `run_unity_tests_clean.ps1` after review. Don't claim it passed.

### 2.5 Report

Write `C:\nscrev\reports\<topic>-fix-report.md`:
- problem ID, reproduced or theoretical;
- the root cause, with file:line;
- the change (files, commits on `fix/<topic>`, base sha);
- tests: each one failing-before and passing-after, with exact commands and counts; pre-existing failures listed separately;
- risks, what was not tested, and follow-ups.

### 2.6 Review (a fresh Reviewer)

Start a **new** reviewer; don't reuse the author. **Pick the reviewer by which account it spends, not by which tool is nearest** - the Agent tool spends the desktop (Outlook) account that `CLAUDE.md` lists as use-last, and this guide defaulted to it until 2026-09-18 because it predated the account split.

- **Default: the host `claude` CLI on the Gmail account.** `claude -p --agent pipeline-reviewer --model claude-fable-5-1 ...` (recipe and flags: `nsc-codex-jobs-guide.md`, host `claude -p` jobs). **Check the account first with `claude auth status --text`; it must print `cathode26@gmail.com`**, and do that check yourself rather than trusting a tool to do it.
- **A Docker review job** (`nsc-codex-jobs-guide.md` 4.3, `review-job-prompt.md` on `claude-exec`) when the review's evidence sits inside one job clone. Also Gmail, and it pops no console windows.
- **The Agent tool** (`subagent_type: "pipeline-reviewer"`, Opus 5 at xhigh, `model: "fable"` for identity, locking or provider-spend code) **only when the review needs Unity, PixelLab, Windows-only tools or this session's own context.** It is the scarce account; use it last.
- **A Codex reviewer** is also acceptable once Codex has quota.

For a FIX FIRST re-check, reuse that same reviewer - message the Agent-tool one by its agentId, or give a fresh CLI reviewer its own prior report. Give it:
- the report;
- the clone path;
- base..head;
- the problem entry;
- "read-only: do not edit, commit, run providers, Docker or Unity, or write under `C:\NSC`".

The Reviewer returns:

```text
VERDICT: APPROVE | FIX FIRST | REJECT
Findings (most severe first):
- [blocking|major|minor] file:line: what is wrong; failure scenario; reproduced or theoretical
Tests re-run by reviewer: <commands + results>
Scope check: only intended files changed? new blocking gates added? temp under C:\NSC? identity ok?
```

- **FIX FIRST:** fix, then the **same** Reviewer re-checks only the new commits.
- **REJECT:** back to the Main Orchestrator.
- Never let the author mark its own work approved.

### 2.7 Hand off

- Message the **Game Agent** (Integration Steward) by title with: branch `fix/<topic>` in `C:\nscrev\<topic>-fix`, head sha, report path, verdict. Tell Vincent in two lines.
- The Steward fetches it into the canonical repo (`git fetch C:/nscrev/<topic>-fix fix/<topic>:fix/<topic>`), trial-merges it in `branch-verify`, and shows Vincent. After merge:
  - **viewer code** changes need a viewer restart (`nsc_viewer.py restart`);
  - **crew or worker** changes only affect newly prepared checkouts, because older checkouts keep their pinned code.
- Mark the problem in `nsc-pipeline-problems.md` as fixed, with the commit.

---

## 3. Porting queue (built before, not on `main`)

Verify that each location still exists before starting. Some branches were renamed or lost.

| Problem | What exists | Where (last known) | Note |
|---|---|---|---|
| P3 lost final worker write | bounded retry of the final write + `recover-worker-result` CLI, proven live 9/13 | commits `aac2555c` and descendants on `throughput/worker-and-decomposition-fixes` and later combined branches under `C:\nscrev\` (for example `C:\nscrev\ac-fixes`, `C:\nscrev\final-integration`) | Highest priority; wedges runs forever |
| D3 decomposition `needs_human` shown as failed | `_authenticated_run_result`, `_needs_human_proof`, `decomposition_needs_human` viewer phase | `eb3beb75` (`C:\nscrev\decomp-needs-human-fix`) | |
| D4 fixed 3600 s decomposition timeout | derived budgets, env forwarding, `decomposition_slow` event | `008d1df` | |
| D2 real-task decomposition guidance | coverage mapping, candidate-wide rules, production-path test rule, `.asmdef` authority | `616ca980`..`c6f7981a` on `codex/coverage-mapping-guidance-20260913` (`C:\nscrev\coverage-mapping-guidance-fix`) | Astra-approved for research only; needs a real review |
| D1 exact-partition rule | Fable's 9/12 real-task rule (design only) | `C:\NSC\AssistantControlEvidence\FABLE_RUN2_RESPONSE.md` item 4 | Implement with tests |
| D6 recursive decomposition | children may be `needs_execution_decomposition` | `codex/recursive-decomposition-20260914` (`C:\nscrev\recursive-decomposition-fix`, repo `C:\nscrev\revision-review-integration`) | Not on `main` (`policy.py:117`) |
| D7 revision-review third call | bounded third review call | head `4fd54b8c` on `throughput/decomposition-final-integration` (`C:\nscrev\final-integration`) | Large; review carefully |
| E4 Docker Desktop mount-path check | Windows mount-format normalization | `8d8ae6cd0` in `C:\NSC\NoSafeCircle-AssistantControl-SpeedIntegration` | |
| V18 viewer test fixture | schema-v2 fixture repair | `c12f702` in `C:\NSC\AssistantControlViewerRegression-20260913` (branch gone; check the folder) | Do this **before** other viewer work |

## 4. New work, in suggested order

**The current queue (2026-09-16)** is in the session launch prompt, `C:\nscrev\reports\handoffs\pipeline-maintainer-agent-launch-prompt.md`:
1. take over `fix/viewer-step1` (V18, V1, V13, V14, V9), built by a subagent of the Documentation Agent, when the Documentation Agent hands it over: review, fix first, hand to the Game Agent;
2. P34 stub metas, from the Game Agent's brief `C:\nscrev\reports\handoffs\pipeline-maintainer-brief-20260916.md`.

The list below is the longer-term order.

1. **V18:** fix the viewer tests to 57/57, as the base for all viewer work. *(Built on `fix/viewer-step1` @ `2e76ab22d`; approved by review on 2026-09-16; with the Game Agent for merge.)*
2. **V1:** approved and integrating candidates should show `integration_queued`, not blue. *(Same branch and status. Only partly fixed: other blue sources remain; see the problem list.)*
3. **P3 port**, then **D3/D4/D5** (`archive-decomposition` command).
4. **P34:** write full importer metas for staged art, so no cubemap imports.
5. **P2:** `adopt-existing` for tasks whose behaviour already exists.
6. **P18:** renormalize line endings (only with Vincent) and extend safe-churn to hash-identical generated assets.
7. **P35:** `archive-successful NSC-###`, as in Integration Steward guide section 6.2.
8. **Move the tools into the repo:**
   - `C:\NSC\tools\viewer\nsc_viewer.py` → `Pipeline/AssistantControl/viewer_control.py`;
   - `nsc_watch.py`;
   - `C:\NSC\tools\ger\*.py` → `Pipeline/TaskDesignGER/` (G1), each with smoke tests;
   - add `hold`/`unhold` to `ger_viewer_marker.py` (V9).
9. **Docs:** retire stale docs (DOC1-DOC9) with banners pointing to the current guides, and port the `C:\NSC\nsc-*-guide.md` set into `Docs/AI-Pipeline/agents/` once Vincent agrees.

**Windows rules for any script you write:**
- Every console subprocess gets `CREATE_NO_WINDOW` (`0x08000000`).
- Long-lived children use a hidden console, never `DETACHED_PROCESS`. On 9/16 a detached viewer popped 100+ windows.
- Write files as UTF-8 without a BOM, and use atomic replace.
- Use PowerShell 5.1-compatible syntax in `.ps1` files.
