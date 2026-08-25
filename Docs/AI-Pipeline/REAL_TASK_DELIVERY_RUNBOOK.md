# Real Task Delivery Runbook — No Safe Circle

This is the practical end-to-end procedure for advancing one real No Safe Circle implementation task through the current pipeline.

It exists so a new AI assistant or developer can resume from the repository without relying on chat history.

## Authority and source of truth

Read these before changing project state:

1. `AI_PIPELINE.md`
2. `Docs/AI-Pipeline/START_HERE.md`
3. `Docs/AI-Pipeline/CURRENT_STATE.md`
4. this runbook
5. the selected `Tasks/NSC-###.yaml`
6. `Docs/GDD/No_Safe_Circle_GDD.md`
7. `Pipeline/ExecutionCrew/README.md`
8. `Docs/Engineering/UNITY_TESTING_POLICY.md` when Unity tests, scenes, builders, prefabs, or runtime evidence are involved
9. `Pipeline/TaskGraph/CONFORMANCE_RECORDS.md` before packaging delivery/revalidation evidence

The canonical GDD and committed task contract define required behavior. ExecutionCrew performs bounded implementation/review work. Unity/Git tooling establishes deterministic facts. TaskGraph derives current conformance from committed evidence. No worker, test runner, or chat model declares a task complete by itself.

## Game task fast start

For a normal gameplay task, do not front-load this entire runbook before taking the first useful step. Use this short path, then read the detailed section for the stage you are entering:

1. Pull current `main`.
2. Run `python Pipeline/TaskGraph/taskcontrol.py validate`. **Stop if it fails.**
3. Inspect the candidate with `taskcontrol state` and `taskcontrol show`.
4. Confirm manually that its dependencies make sense for the current committed graph; TaskGraph does not currently derive a dependency-ready frontier or authorize dispatch.
5. Read the selected task contract and the canonical GDD requirements governing it.
6. Create a standalone task clone from the GitHub remote and create a feature branch.
7. Audit live contract/resource metadata against current repository reality.
8. Decide the exact production/test write paths; scaffold only genuinely new role-owned files that ExecutionCrew must edit.
9. Run ExecutionCrew and stop at human review — or, if the mandatory pre-Implementer Contract Locality Auditor reports `CONTRACT_REVIEW_REQUIRED`, stop and repair the task contract through the normal human-reviewed TaskGraph workflow instead (see step 3 and step 6).
10. Continue through Unity validation, committed evidence, TaskGraph conformance, and merge using the detailed stages below.

A fresh model should be able to reach a real bounded implementation attempt quickly without reconstructing the whole pipeline architecture first.

## Current gameplay orientation — convenience snapshot

This snapshot is for fast orientation only. The repository and `taskcontrol` remain authoritative; re-check before acting if this file is older than the task work you are about to perform.

As of 2026-08-24:

- canonical playable scene: `Assets/Scenes/DoorPrototype.unity`;
- NSC-003 delivered the current mouse-directed Player Movement / shared pointer projection / movement-restriction foundation;
- NSC-004 delivered Player Health ownership/reset/death/feedback behavior;
- NSC-005 delivered Player Mana ownership/reset/denied-cast feedback behavior;
- the current human-selected next gameplay foundation is `NSC-011 — Active Enemy Registry`;
- `NSC-011` is a concrete `single_agent` implementation with no dependencies;
- `NSC-012 — Enemy Health/Defeat` depends on NSC-011;
- `NSC-007 — Charged Fireball` depends on NSC-003 and NSC-012.

That gives the useful dependency path:

```text
NSC-011 Active Enemy Registry
        ↓
NSC-012 Enemy Health/Defeat
        ↓
NSC-007 Charged Fireball
```

Do not treat this dated snapshot as readiness or execution authorization. Confirm the current graph before each new task.

## Proven workflow

The current production path has been exercised on real gameplay work through NSC-003, NSC-004, and NSC-005. The practical sequence is:

```text
validate TaskGraph
    ↓
select bounded task
    ↓
inspect task contract and current repository
    ↓
create isolated standalone clone + feature branch
    ↓
correct stale contract/resource metadata if required
    ↓
scaffold any new role-owned files that ExecutionCrew must be allowed to edit
    ↓
run ExecutionCrew
    ↓
human reviews candidate.patch
    ↓
manual patch application
    ↓
interactive Unity validation / manual runtime inspection
    ↓
commit implementation
    ↓
authoritative clean Unity test run(s)
    ↓
package committed evidence
    ↓
validate staged evidence
    ↓
commit evidence
    ↓
TaskGraph must report conformant
    ↓
merge with history preserved
    ↓
TaskGraph must still report conformant after merge
    ↓
push main and clean up branch/clone
```

## 1. Select an actually executable task

Do not choose a task merely because its title looks useful.

First validate the entire committed graph:

```powershell
python Pipeline/TaskGraph/taskcontrol.py validate
```

If this fails, **stop before gameplay implementation**. Repair the graph/metadata inconsistency as its own reviewed change. A `state` query can sometimes inspect one task even when another graph-wide metadata invariant is broken, so `state` alone is not a substitute for `validate`.

Then inspect the selected contract and evidence-derived state:

```powershell
python Pipeline/TaskGraph/taskcontrol.py state NSC-### --json
python Pipeline/TaskGraph/taskcontrol.py show NSC-###
```

For direct ExecutionCrew use, the selected contract must currently be:

- `contract_disposition: active`
- `kind: implementation`
- `execution_scope: single_agent`
- `decomposition_state: concrete`

Also check dependencies manually/currently. ExecutionCrew eligibility is not automatic dependency readiness or execution authorization.

Feature-group/organizational nodes are not dispatchable. `needs_execution_decomposition` work must be decomposed before a one-agent execution run.

## 2. Start from current main and use a standalone clone

For real task execution, use a normal standalone clone rather than a Git worktree.

Why: Docker ExecutionCrew needs a normal Git repository identity. A Windows Git worktree uses a linked `.git` file that can point to a Windows-only worktree gitdir; inside Linux Docker that can produce `source repository identity could not be resolved`. Standalone clones give Docker and Git a normal repository directory and make cleanup simpler.

On this development machine, clone the **GitHub remote**, not the local `NoSafeCircle` checkout. Git for Windows has also rejected local-source clones here because of ownership differences on the primary checkout's `.git` directory. Do not add broad global `safe.directory` exceptions merely to work around task-clone creation.

From the parent directory:

```powershell
cd C:\UnityProjects\NoSafeCircleAgentCrew

git -C .\NoSafeCircle status --short
git -C .\NoSafeCircle switch main
git -C .\NoSafeCircle pull --ff-only origin main

git clone https://github.com/cathode26/NoSafeCircle.git .\NoSafeCircle-NSC###
cd .\NoSafeCircle-NSC###
git switch -c nsc-###-short-description
```

Confirm the task clone is clean and current before doing anything else:

```powershell
git status --short
git log -1 --oneline
git remote -v
python Pipeline/TaskGraph/taskcontrol.py validate
```

The tree should be clean, `origin` should point at GitHub, and TaskGraph validation must pass.

Do not develop directly on `main`.

## 3. Audit the task contract before dispatch

Read the current task contract and compare it to current repository reality.

Pay particular attention to:

- dependency IDs
- `execution_scope`
- `decomposition_state`
- `exclusive_resources`
- scene paths
- acceptance-criterion IDs
- completion-gate IDs
- stale repository observations that are historical evidence versus live authority

The authoritative Door Prototype scene is:

```text
Assets/Scenes/DoorPrototype.unity
```

Several older task contracts were bootstrapped when the scene lived under an obsolete `Assets/NoSafeCircle/DoorPrototype/Scenes/...` path. If a live contract field such as `exclusive_resources` still names the old scene, correct the live field and increment `contract_revision` before implementation. Do not rewrite historical `repository_evidence_at_bootstrap` merely because the old path was historically true.

### Resource-group symmetry is a live invariant

`Tasks/NSC-###.yaml -> exclusive_resources` and `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml` must agree symmetrically.

If a live task contract adds, removes, or renames an exclusive resource:

- update that task's live `exclusive_resources` and increment `contract_revision` when the contract itself changes;
- update `RESOURCE_GROUPS.yaml` so the task appears under exactly the resource keys it currently claims;
- preserve other tasks that still legitimately claim an older resource key;
- preserve each `work_ids` / `reconciliation_keys` positional correspondence;
- do not rewrite historical bootstrap observations merely to make them look current;
- run `taskcontrol.py validate` before proceeding.

This invariant matters because a stale resource group can make the persistent graph invalid even when the selected task itself is otherwise well-formed.

Contract/resource corrections should be their own reviewed commit before implementation.

After a contract/resource edit:

```powershell
git diff --check
git diff -- Tasks/NSC-###.yaml Pipeline/TaskGraph/RESOURCE_GROUPS.yaml
git add Tasks/NSC-###.yaml Pipeline/TaskGraph/RESOURCE_GROUPS.yaml
python Pipeline/TaskGraph/taskcontrol.py validate
git commit -m "chore(nsc-###): correct task contract metadata"
```

Stage only the files that actually changed; do not force a no-op `RESOURCE_GROUPS.yaml` or task-contract edit.

### Locality is also audited automatically inside ExecutionCrew

This manual review is a first pass, not the only safeguard. `python Pipeline/TaskGraph/task_contract_quality_audit.py` is a separate, deterministic, model-free heuristic pattern check against committed contract text; run it as an additional early signal, but it does not replace either this manual audit or the automatic one below.

Every ExecutionCrew run also runs its own mandatory, read-only, model-backed Contract Locality Auditor immediately before the Implementer (see `Pipeline/ExecutionCrew/README.md`). It classifies every current `AC-###`/`VAL-###` ID as `local_to_task`, `requires_declared_dependency`, `downstream_integration`, `missing_design`, or `ambiguous`, and stops the run as `CONTRACT_REVIEW_REQUIRED` before the Implementer, Test Author, or Validator ever run when any item is nonlocal. It never edits the task contract, GDD, or graph, and it never grants readiness or dispatch authority — a nonlocal result always routes back through this manual TaskGraph workflow (step 6). Treat it as a mandatory backstop for exactly the class of defect this section exists to catch (for example, a `single_agent`/`concrete` contract whose completion gates actually require another system's pursuit/search/navigation behavior), not as a substitute for reading the contract yourself first.

## 4. Scaffold new ExecutionCrew paths before running the crew

ExecutionCrew requires explicit role paths and currently preflights them as existing tracked files. Implementation and test role paths must be disjoint.

If the task requires a brand-new production or test file, create a minimal valid scaffold and commit it before invoking the crew. The scaffold exists to establish write authority; it is not the implementation itself.

For Unity C# files, also create and commit their `.meta` files so Unity identity is stable. The `.meta` files do not need to be supplied as ExecutionCrew write paths unless the agent genuinely needs authority to edit them.

Typical pattern:

```powershell
git add <new-production-file> <new-production-file>.meta <new-test-file> <new-test-file>.meta
git commit -m "test(nsc-###): add implementation scaffold"
git status --short
```

Do not widen role scopes after the run merely because the model wants another path. If genuinely necessary work falls outside the approved scope, stop and start a new explicitly scoped run after human review.

## 5. Run ExecutionCrew with explicit paths

Read `Pipeline/ExecutionCrew/README.md` before the first run in a new context.

Run Docker Compose from the standalone task clone so `/workspace` is a normal Git repository with a Docker-readable `.git` directory.

Example shape:

```powershell
docker compose -p nosafecircle run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py `
  --task-id NSC-### `
  --provider claude `
  --implementation-path <tracked-production-path-1> `
  --implementation-path <tracked-production-path-2> `
  --test-path <tracked-test-path-1> `
  --host-output-root "C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC###\Pipeline\ExecutionCrew\outputs"
```

Use one human-selected provider for the run. Do not interpret a semantic Validator pass as Unity validation, delivery, readiness, or conformance.

The desired crew result is `REVIEW_READY` with `candidate.patch`.

Every run — including this one — starts with the mandatory, read-only Contract Locality Auditor described in step 3. When it passes, the run continues into the Implementer/Test Author/Validator exactly as before. When it reports the task contract nonlocal, the crew stops immediately as `CONTRACT_REVIEW_REQUIRED` with zero Implementer/Test Author/Validator invocations, zero attempts used, and no patch of any kind; the only artifact is `contract_locality_audit.json`. Do not treat this as a normal blocked/rejected run to retry as-is: repair the task contract first (step 3), then rerun ExecutionCrew.

The Validator itself is a second locality safeguard for exactly the case the audit exists to catch but only becomes apparent once a candidate exists. Every `criteria_results` item carries a `reason_code` alongside its `status`: `pass` requires `proved`; `fail` requires `criterion_failed`; `not_proven` requires exactly one of `runtime_not_executed`, `missing_integration_dependency`, `missing_required_artifact`, `insufficient_evidence`, or `design_ambiguity`. `runtime_not_executed` — required Unity/runtime evidence genuinely was not executed yet, while the rest of the item is otherwise semantically proved — is the only `not_proven` reason that may coexist with an overall Validator `pass`, and doing so still leaves the crew result `REVIEW_READY`. `missing_integration_dependency` and `design_ambiguity` can never coexist with an overall `pass`; they require overall `status=blocked_by_design`, and the crew routes that specific case to `CONTRACT_REVIEW_REQUIRED` rather than a generic `BLOCKED`, since it is the same locality-defect class the mandatory audit exists to catch, just discovered late. `missing_required_artifact` and `insufficient_evidence` also cannot coexist with `pass`. This reason-code taxonomy is deterministically enforced by the crew, not just requested in the Validator prompt; an invalid combination rejects the run rather than silently passing.

The upgraded human footer should give the exact result, artifact path, and copy/paste-ready find/check/apply/verify commands. A preflight block should instead print `RESULT: BLOCKED`, a concrete reason, `ARTIFACT: none` when appropriate, and a next action. `RESULT: CONTRACT_REVIEW_REQUIRED` instead prints find/inspect-only commands for `contract_locality_audit.json` (or, in the rarer case where the audit passed but the Validator later reported the same defect class after writers already ran, the diagnostic-patch footer shape for a non-applyable `workspace_diagnostic.patch`).

`workspace_diagnostic.patch` is diagnostic output from a non-review-ready run and must not be applied as an approved candidate.

## 6. Human-review the candidate before applying

ExecutionCrew never applies its candidate automatically.

If the result is `CONTRACT_REVIEW_REQUIRED`, there is no candidate to review: read `contract_locality_audit.json`, repair the task contract (add the missing declared dependency, move a requirement to `downstream_integration_obligations`, resolve a missing/ambiguous design decision, etc.) through the normal human-reviewed TaskGraph workflow, run `taskcontrol.py validate`, commit the contract correction, and only then rerun ExecutionCrew.

Inspect the result and patch. If approved:

```powershell
git apply --check '<exact candidate.patch path>'
git apply '<exact candidate.patch path>'
git status --short
git diff --check
git diff --stat
```

Review the actual implementation diff. Do not assume `REVIEW_READY` means the feature works in Unity.

If the candidate is rejected, use the documented ExecutionCrew human-review retry flow or start a newly scoped run. A retry is corrective layering, not reconstruction: after the current Contract Locality Auditor passes, ExecutionCrew verifies the prior review-ready `candidate.patch` against the current candidate-owned paths and either seeds it into the disposable clone, recognizes that the exact candidate is already present, or fails closed when those paths have diverged. The task-contract identity must still match the rejected run. Human feedback does not expand task or write authority. Do not manually apply a rejected candidate merely to make retry seeding work.

## 7. Perform interactive Unity validation before freezing the implementation

Open the isolated task clone in Unity, not the primary `main` checkout.

Run the relevant EditMode and PlayMode suites interactively and perform any manual runtime checks required by the task's completion gates.

For scene/builder work, regenerate the canonical scene when the production workflow requires it and inspect the result in Play Mode.

Check for regressions in adjacent behavior, not only the newly added feature.

Important: close the interactive Unity Editor completely before authoritative command-line Unity testing. A second Unity process pointed at the same project can fail before tests run.

After interactive testing, inspect Git carefully:

```powershell
git status --short
git diff --check
git diff --stat
```

Unity may touch tracked `ProjectSettings` files without producing a meaningful normalized diff. Inspect such files rather than blindly committing them. Restore unrelated semantic changes. Preserve intended canonical-scene changes.

Generated Unity YAML can contain trailing whitespace; clean only the offending whitespace without altering serialized semantics.

## 8. Commit the implementation before authoritative clean tests

The committed implementation state must be frozen before the authoritative clean runner, because the runner requires a clean repository and the resulting commit/tree becomes the validation identity used by evidence.

Stage only intended production/test/scene files and commit them:

```powershell
git add <exact intended files>
git commit -m "feat(nsc-###): implement ..."
git status --short
```

`git status --short` must be empty before the clean runner starts.

Do not amend/rebase the validated implementation commit after evidence is produced unless you intend to invalidate and redo that evidence.

## 9. Run authoritative clean Unity validation

Use the committed wrapper:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\Testing\run_unity_tests_clean.ps1 `
  -TestPlatform EditMode `
  -TestFilter "<relevant EditMode filter>"
```

and/or:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\Testing\run_unity_tests_clean.ps1 `
  -TestPlatform PlayMode `
  -TestFilter "<relevant PlayMode filter>"
```

A successful authoritative run must end with:

```text
Unity exit code: 0
Result: Passed (...)
VALIDATION PASSED: assertions passed and the repository remained clean.
```

Record the printed:

- Git HEAD
- Git tree
- XML path
- Unity log path
- test totals

Those exact temporary artifacts are later packaged as evidence.

If Unity exits before tests run, inspect the preserved `unity.log` first. Do not change implementation code just because the Unity process failed to launch.

## 10. Package delivery evidence with the committed deterministic tool

Do not hand-assemble hashes or manually invent a record when the normal delivery tool can package it.

Read:

```text
Pipeline/TaskGraph/CONFORMANCE_RECORDS.md
```

Use:

```text
Pipeline/TaskGraph/record_delivery.py
```

Create the delivery-spec JSON outside the repository (for example under `$env:TEMP`) so the clean-working-tree precondition remains true.

The spec explicitly supplies:

- task ID
- validated commit
- base commit
- candidate commit
- conformance surfaces and roles
- source XML/log/human-validation artifacts
- exact gate-to-evidence mappings
- human approval

The packager verifies the committed contract, GDD, surfaces, ancestry, test XML, log, human-validation text, hashes, and artifact layout. It stages nothing and claims no conformance.

`record_delivery.py` takes the delivery-spec path as a **positional argument**. Run:

```powershell
python Pipeline/TaskGraph/record_delivery.py "$env:TEMP\NSC-###-delivery-spec.json"
```

Do not use a nonexistent `--spec` flag.

Use the exact `STAGE` command printed by the tool. The packager also prints `VALIDATE DRAFT`, `CHECK`, `COMMIT`, and `VERIFY AFTER COMMIT` steps. Do not substitute `git add .`, `git add -A`, or a directory-wide force-add.

This matters because `*.log` is ignored by Git; an earlier delivery attempt silently omitted a Unity log until TaskGraph correctly rejected the evidence.

## 11. Validate the actual staged evidence before committing

The Git index, not working-tree intent, is authoritative for the would-be evidence commit.

Run the deterministic draft validator against the staged record, preferably using the exact command printed by `record_delivery.py`:

```powershell
python Pipeline/TaskGraph/validate_draft_evidence.py `
  --record Pipeline/TaskGraph/evidence/NSC-###/records/DEL-NSC-###-<shortsha>.json
```

Also inspect:

```powershell
git diff --cached --check
git diff --cached --stat
git diff --cached --name-status
```

Only after draft validation succeeds should the human create the evidence commit:

```powershell
git commit -m "chore(nsc-###): record delivery evidence"
git status --short
```

Evidence records are immutable historical facts. Do not edit an existing committed record to make a later state pass.

## 12. Require TaskGraph conformance before merge

Now ask the committed evaluator:

```powershell
python Pipeline/TaskGraph/taskcontrol.py state NSC-### --json
```

The task is not closed unless the derived state is:

```json
"state": "conformant"
```

A clean test run, semantic Validator pass, human approval, or evidence commit is not a substitute for this final derived-state check.

## 13. Push the task branch and merge with evidence history preserved

Do not squash or rebase evidence-backed history after validation. Delivery records bind exact Git identities.

If the standalone clone's upstream is wrong or still points at `main`, explicitly create the same-named remote branch:

```powershell
git push -u origin HEAD:nsc-###-short-description
```

Do **not** use `git push origin HEAD:main` as a shortcut.

Return to the primary repository:

```powershell
cd C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle
git status --short
git switch main
git pull --ff-only origin main
git fetch origin
```

Merge with a real merge commit:

```powershell
git merge --no-ff origin/nsc-###-short-description -m "Merge NSC-### ..."
```

Immediately re-check conformance after the merge:

```powershell
python Pipeline/TaskGraph/taskcontrol.py state NSC-### --json
```

Only if it is still `conformant`:

```powershell
git push origin main
git push origin --delete nsc-###-short-description
```

Then verify one final time:

```powershell
git status --short
python Pipeline/TaskGraph/taskcontrol.py state NSC-### --json
```

## 14. Clean up the standalone clone

After `main` is pushed and post-merge conformance is confirmed:

```powershell
cd C:\UnityProjects\NoSafeCircleAgentCrew
Remove-Item -Recurse -Force .\NoSafeCircle-NSC###
```

If Windows reports an open handle, close Unity, terminals, IDEs, and file explorers pointing into that clone, or remove it after reboot. Git history is already safe once the branch is merged and pushed.

## Existing evidence versus new delivery evidence

Before packaging evidence, inspect:

```powershell
python Pipeline/TaskGraph/taskcontrol.py state NSC-### --json
```

If the task has **no committed delivery/baseline/revalidation record**, a successful first integrated implementation uses a `delivery` record.

If the task already has valid evidence and its conformance surface later changes, do not create a conflicting second delivery record merely to make the new state pass. Use the `revalidation` model described in `Pipeline/TaskGraph/CONFORMANCE_RECORDS.md`, preserving the earlier record as immutable history.

`record_delivery.py` packages delivery records. Check current repository tooling/documentation before assuming revalidation packaging has equivalent automation.

## Common failure modes already encountered

### TaskGraph graph validation fails before the selected task

Symptom: `taskcontrol.py show NSC-###` or `taskcontrol.py validate` reports a resource-group/task-contract inconsistency such as a task being present in a resource group it no longer claims.

Response: stop gameplay work, inspect the live task `exclusive_resources` and `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`, restore symmetric membership, preserve still-valid old resource memberships for other tasks, and rerun `taskcontrol.py validate`. Do not change the selected gameplay task merely to make graph validation pass.

### Stale canonical scene path in a task contract

Symptom: a task's live resource scope references `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` even though the canonical scene is now `Assets/Scenes/DoorPrototype.unity`.

Response: correct the live contract field, increment `contract_revision`, update `RESOURCE_GROUPS.yaml` symmetrically, commit the correction first, and preserve historical bootstrap evidence as historical evidence.

### ExecutionCrew reports `source repository identity could not be resolved`

Common cause on this Windows/Docker setup: ExecutionCrew was launched from a Git worktree whose `.git` file points to a Windows-only worktree gitdir that Linux Docker cannot resolve.

Response: do not patch ExecutionCrew, reconstruct `.git`, or add broad Git trust exceptions. Use a standalone task clone from the GitHub remote and run Docker Compose from that clone.

### ExecutionCrew rejects a requested new file path

Symptom: preflight says a role path does not exist or is not tracked.

Response: create a minimal scaffold, add its `.meta` where applicable, commit it, then run ExecutionCrew with that tracked path.

### ExecutionCrew blocks before any provider runs

A preflight `RESULT: BLOCKED` with `ARTIFACT: none` is not a failed implementation attempt. Read the concrete `WHY` field, fix the environment/scope/precondition, and rerun. Do not search for or apply a candidate patch that was never created.

### ExecutionCrew reports `RESULT: CONTRACT_REVIEW_REQUIRED`

Symptom: the run stops immediately after the mandatory Contract Locality Auditor, before the Implementer, Test Author, or Validator ever run; `ARTIFACT` points at `contract_locality_audit.json` (or, less commonly, at a non-applyable `workspace_diagnostic.patch` when the Validator caught the same defect class later, after writers already ran).

This is not a bug to patch and not a normal `BLOCKED`/`REJECTED` result to retry unchanged: one or more `AC-###`/`VAL-###` items on the selected task are not actually provable under its current scope and declared dependencies. Inspect the audit's `entry_results`/`blocking_findings`, then repair the task contract through the normal human-reviewed TaskGraph workflow described in step 3/step 6 (add the missing declared dependency, relocate the requirement into `downstream_integration_obligations`, resolve the missing/ambiguous design decision), validate the graph, and rerun ExecutionCrew. Do not widen the auditor's authority, and do not hand-edit the contract to make the audit merely stop complaining without actually fixing the underlying locality problem.

### Unity batch run fails while interactive Unity is open

Symptom: command-line Unity exits before producing a normal test result.

Response: close the interactive editor completely and rerun before changing code.

### Unity leaves stat-only working-tree markers

Symptom: `git status` reports a tracked Unity settings file while `git diff` shows no meaningful content difference.

Response: inspect it. Do not commit unrelated settings churn. The clean runner is designed to distinguish normalized stat-only rewrites from real content mutations.

### Evidence `.log` exists on disk but is missing from the commit

Cause: `*.log` is ignored.

Response: use `record_delivery.py`'s exact printed `STAGE` command (which force-adds the exact generated files) and then `validate_draft_evidence.py` before committing.

### TaskGraph reports `not_delivered` even after code/tests pass

Cause: TaskGraph reads committed evidence, not intention or chat history.

Response: package, stage, validate, and commit the appropriate evidence record, then query state again.

### Task becomes non-conformant after a later code change

Cause: a recorded conformance-surface blob no longer matches current `HEAD`.

Response: validate the new implementation state and create appropriate revalidation evidence. Never edit the old immutable record.

### Standalone feature branch `git push` tries to use `main` as upstream

Symptom: Git reports that the upstream branch name does not match the current branch.

Response:

```powershell
git push -u origin HEAD:nsc-###-short-description
```

Then fetch/merge that branch normally in the primary checkout.

## End-of-session handoff checklist

Before allowing a chat/model context to disappear, make sure durable repository state is sufficient to resume:

- TaskGraph validation passes, or a clearly documented graph-repair branch is the active work;
- selected task ID and why it is the current human-selected task are recorded somewhere durable when the choice matters across sessions;
- task contract changes are committed;
- implementation/test changes are committed;
- authoritative test artifact paths/results are either captured for closeout or already packaged;
- evidence is committed if the task is being claimed complete;
- TaskGraph state has been checked;
- `main`/feature branch/standalone clone location is clear;
- any pipeline behavior learned during the session that changes this procedure is added to this runbook or the relevant authoritative README/ADR;
- `Docs/AI-Pipeline/CURRENT_STATE.md` is updated when the infrastructure milestone/slice itself changed.

A fresh model should be able to reconstruct the work from Git, task contracts, the canonical GDD, this runbook, and the routed pipeline documentation without access to the prior chat transcript.