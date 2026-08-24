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
6. `Pipeline/ExecutionCrew/README.md`
7. `Docs/Engineering/UNITY_TESTING_POLICY.md` when Unity tests, scenes, builders, prefabs, or runtime evidence are involved
8. `Pipeline/TaskGraph/CONFORMANCE_RECORDS.md` before packaging delivery/revalidation evidence

The canonical GDD and committed task contract define required behavior. ExecutionCrew performs bounded implementation/review work. Unity/Git tooling establishes deterministic facts. TaskGraph derives current conformance from committed evidence. No worker, test runner, or chat model declares a task complete by itself.

## Proven workflow

The current production path has been exercised on real gameplay work through NSC-003, NSC-004, and NSC-005. The practical sequence is:

```text
select bounded task
    ↓
inspect task contract and current repository
    ↓
create isolated standalone clone + feature branch
    ↓
correct stale contract metadata if required
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

Inspect the current graph and selected contract:

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

For real task execution, prefer a normal standalone clone over a Git worktree.

Why: the Docker execution path previously hit problems with worktrees because a worktree uses a linked `.git` file pointing back into another checkout. Standalone clones give Docker and Git a normal repository directory and make cleanup simpler.

From the parent directory:

```powershell
cd C:\UnityProjects\NoSafeCircleAgentCrew

git -C .\NoSafeCircle status --short
git -C .\NoSafeCircle switch main
git -C .\NoSafeCircle pull --ff-only origin main

git clone .\NoSafeCircle .\NoSafeCircle-NSC###
cd .\NoSafeCircle-NSC###
git switch -c nsc-###-short-description
```

Confirm the task clone is clean before doing anything else:

```powershell
git status --short
git log -1 --oneline
```

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

Contract corrections should be their own reviewed commit before implementation.

After a contract edit:

```powershell
git diff --check
git diff -- Tasks/NSC-###.yaml
git add Tasks/NSC-###.yaml
git commit -m "chore(nsc-###): correct task contract"
```

## 4. Scaffold new ExecutionCrew paths before running the crew

ExecutionCrew requires explicit role paths and currently preflights them as existing tracked files. Implementation and test role paths must be disjoint.

If the task requires a brand-new production or test file, create a minimal valid scaffold and commit it before invoking the crew. The scaffold exists to establish write authority; it is not the implementation itself.

Typical pattern:

```powershell
git add <new-production-file> <new-production-file>.meta <new-test-file> <new-test-file>.meta
git commit -m "test(nsc-###): add implementation scaffold"
```

Do not widen role scopes after the run merely because the model wants another path. If genuinely necessary work falls outside the approved scope, stop and start a new explicitly scoped run after human review.

## 5. Run ExecutionCrew with explicit paths

Read `Pipeline/ExecutionCrew/README.md` before the first run in a new context.

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

`workspace_diagnostic.patch` is diagnostic output from a non-review-ready run and must not be applied as an approved candidate.

## 6. Human-review the candidate before applying

ExecutionCrew never applies its candidate automatically.

Inspect the result and patch. If approved:

```powershell
git apply --check '<exact candidate.patch path>'
git apply '<exact candidate.patch path>'
git status --short
git diff --check
git diff --stat
```

Review the actual implementation diff. Do not assume `REVIEW_READY` means the feature works in Unity.

If the candidate is rejected, use the documented ExecutionCrew human-review retry flow or start a newly scoped run. Human feedback does not expand task or write authority.

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

Run:

```powershell
python Pipeline/TaskGraph/record_delivery.py --spec "$env:TEMP\NSC-###-delivery-spec.json"
```

Use the exact `git add -f -- ...` command printed by the tool. Do not substitute `git add .`, `git add -A`, or a directory-wide force-add.

This matters because `*.log` is ignored by Git; an earlier delivery attempt silently omitted a Unity log until TaskGraph correctly rejected the evidence.

## 11. Validate the actual staged evidence before committing

The Git index, not working-tree intent, is authoritative for the would-be evidence commit.

Run the deterministic draft validator against the staged record:

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

### Stale canonical scene path in a task contract

Symptom: a task's live resource scope references `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity` even though the canonical scene is now `Assets/Scenes/DoorPrototype.unity`.

Response: correct the live contract field, increment `contract_revision`, commit the correction first, and preserve historical bootstrap evidence as historical evidence.

### ExecutionCrew rejects a requested new file path

Symptom: preflight says a role path does not exist or is not tracked.

Response: create a minimal scaffold, add its `.meta` where applicable, commit it, then run ExecutionCrew with that tracked path.

### Unity batch run fails while interactive Unity is open

Symptom: command-line Unity exits before producing a normal test result.

Response: close the interactive editor completely and rerun before changing code.

### Unity leaves stat-only working-tree markers

Symptom: `git status` reports a tracked Unity settings file while `git diff` shows no meaningful content difference.

Response: inspect it. Do not commit unrelated settings churn. The clean runner is designed to distinguish normalized stat-only rewrites from real content mutations.

### Evidence `.log` exists on disk but is missing from the commit

Cause: `*.log` is ignored.

Response: use `record_delivery.py`'s exact printed `git add -f -- ...` command and then `validate_draft_evidence.py` before committing.

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

- task contract changes are committed
- implementation/test changes are committed
- authoritative test artifact paths/results are either captured for closeout or already packaged
- evidence is committed if the task is being claimed complete
- TaskGraph state has been checked
- `main`/feature branch location is clear
- any pipeline behavior learned during the session that changes this procedure is added to this runbook or the relevant authoritative README/ADR
- `Docs/AI-Pipeline/CURRENT_STATE.md` is updated when the infrastructure milestone/slice itself changed

A fresh model should be able to reconstruct the work from Git, task contracts, this runbook, and the routed pipeline documentation without access to the prior chat transcript.
