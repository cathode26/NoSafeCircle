# Delivery evidence: how a task becomes truly complete

"Complete" in this project means **`conformant`**:

```powershell
python -B Pipeline/TaskGraph/taskcontrol.py state NSC-### --json    # "state": "conformant"
```

Only a **committed delivery record** gets a task there, at `Pipeline/TaskGraph/evidence/NSC-###/records/DEL-*.json`.

These don't count:
- a merge into `main`;
- Vincent saying "done";
- the green `human-complete` viewer overlay;
- a passing Unity run by itself.

Conformance matters because:
- **dependencies unlock only on conformant tasks**;
- a task is archived to `C:\NSC\SuccessfullTasks\<TASK-ID>` only once it is conformant (Vincent's rule, 9/16).

Why this guide exists: on 9/13 the "completion-evidence audit" and the "23 should be completed" repair both died at a quota limit. Since then, tasks Vincent considers done still read `not_delivered` and have been painted green by an overlay instead.

Written 2026-09-16 from:
- `Pipeline/TaskDelivery/`, `Pipeline/TaskGraph/record_delivery.py`, `current_conformance.py`, `conformance_records.py`, `CONFORMANCE_RECORDS.md`;
- `Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md`, `TASK_ITERATION_CLOSEOUT_PLAYBOOK.md`;
- the two real records on `main` (NSC-042, NSC-063).

Who does it:
- the **Task Orchestrator**, for tasks it ran;
- the **Integration Steward**, for tasks that landed by branch merge;
- the **Art Director** (`art-director` agent) prepares art tasks' review evidence, and the Steward packages it.

---

## 1. How the evaluator decides

- **It reads committed Git objects only.** Uncommitted records, contracts or artifacts change nothing. Commit, then query.
- **Three record types:**
  - `DEL-` delivery: base, candidate, integrated commit and tree;
  - `BASE-` baseline: an existing implementation that predates evidence;
  - `REV-` revalidation. **No tooling or example exists yet for revalidation; escalate if you need one.**
- **Every fact is re-verified:**
  - tree matches commit;
  - contract hash and revision at the validated commit;
  - canon hash;
  - each `conformance_surfaces[].blob_sha` at the validated commit **and** at current `HEAD`;
  - each artifact blob.
  - Any mismatch makes the whole task **`invalid_evidence`**; one bad record poisons it.
- **Precedence:** `invalid_evidence`/`ambiguous_evidence`, then `conformant`, then `needs_replan`, then `needs_human`, then `needs_testing`, then `not_delivered`.
  - **`needs_replan`:** the contract changed in `kind`, `type`, `execution_scope`, `acceptance_criteria` or `completion_gates`. A metadata-only revision bump stays conformant; NSC-023 did.
  - **`needs_testing`:** `HEAD` later changed a recorded surface file, or the validated commit is no longer an ancestor of `HEAD`.
  - **`needs_human`:** approval was required and is missing.
- **Gates must be literally `"result": "pass"`.** Records never encode failures, and they must not contain `status`, `complete`, `current`, `ready` or `authorized` fields.
- **Human approval sub-schema:** `required` (bool), `decision` (`approved` or `not_required`), `approved_by`, `notes`.
- **A conformant state authorizes nothing.** `taskcontrol ready`/`authorize` stay disabled.

---

## 2. Where to do it: a clean checkout at the exact commit

Every tool requires a **completely clean tree**, including untracked files. `record_delivery.py` also requires **`HEAD == validated_commit`**. The canonical checkout is almost never clean (36 phantom files, Unity, GitHub Desktop), so:

1. Use the verification worktree `C:\nscrev\branch-verify`, detached at the commit you will validate:
   - usually **current `main`**, so surfaces match `HEAD`;
   - make sure no later commit touched the task's surface files.
2. Keep every spec, review and human-validation file **outside the repo** (`$env:TEMP` or `C:\nscrev\reports\delivery\NSC-###\`).
3. After committing evidence in `branch-verify`, the **Integration Steward** fast-forwards canonical `main` to that commit, using the main-write protocol from the Main Orchestrator guide section 5. Then re-run `taskcontrol state` **on canonical `main`**.
   - If `main` moved in between, merge and re-check; the evidence commit's validated commit must stay an ancestor with unchanged surfaces.

```bash
V=C:/nscrev/branch-verify
git -C "$V" status --porcelain          # must print nothing
git -C "$V" checkout --detach main
git -C "$V" rev-parse HEAD              # this is the validated commit
```

Close interactive Unity on that project first. Only one Unity runs at a time.

---

## 3. Step 1: the authoritative Unity run (one per required platform)

```powershell
cd C:\nscrev\branch-verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\Testing\run_unity_tests_clean.ps1 -TestPlatform EditMode -TestFilter "NoSafeCircle.DoorPrototype.Tests.Editor.SomeTests;NoSafeCircle.DoorPrototype.Tests.Editor.OtherTests"
```

- **Choose the test filter** from the task contract's completion gates. For some tasks it is in `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`, for example NSC-042 and NSC-069.
  - Filters are **semicolon-separated**; commas run zero tests.
  - Confirm class names with `git grep -n "class <Name>" main`.
- **Output.** The runner prints a **bound `validation-manifest.json`** plus `test-results.xml` and `unity.log`. The manifest ties together commit and tree before and after, clean-before and clean-after, Unity version, filter, result counts, artifact hashes, and the runner's own hash. It also strips trailing whitespace from the log.
- **Exit codes:** 10 precondition, 20 Unity, 30 result, 40 repository mutated.
  - Passing tests plus a dirty tree after the run counts as a **failure**.
- **Don't touch the output.** Never rename, move or edit the manifest, XML or log.
- **Never pass `-quit` with `-runTests`** in hand runs; it gives exit 0 with no XML. Use the runner.
- **Run it again** if `HEAD` or the tree changes for any reason after the run. Integrate `main` **before** validating, not after.

---

## 4. Step 2, path A (preferred): draft, review, finalize

```powershell
$TaskId = "NSC-###"
$Out = "C:\nscrev\reports\delivery\$TaskId"; New-Item -ItemType Directory -Force $Out | Out-Null
python -B Pipeline/TaskDelivery/generate_delivery_spec.py draft --task-id $TaskId --base-commit <commit immediately before the implementation history> --validation-manifest <path\validation-manifest.json> --output "$Out\review.json"
```

- `--validation-manifest` is repeatable, once per platform. All manifests must name the same commit and tree.
- Use `--crew-result <crew_result.json>` instead of `--base-commit` for crew-produced work; it infers the base.
- Use `--human-validation <text file>` for a written human check. It is repeatable.
- The draft always starts with `review_status: needs_human` and `human_approval.required: true`.

**Edit `review.json`. Truthful fields only:**
- `review_status` → `"approved"`.
- `surface_candidates[]`: set `selected: true/false`. Each selected surface gets a meaningful `role`.
- `gates[]`: set `evidence` to artifact IDs, and write `notes` explaining why those artifacts prove that gate. "todo", "tbd", "n/a" and blanks are rejected.
- `human_approval.decision` → `"approved"`. `approved_by` → `"Vincent Liguori"`. `notes` → **what Vincent actually checked, quoted and dated**, for example "Vincent walked all four wizards in 8 directions in Unity on 2026-09-17 and said 'looks good'".
- **Don't** edit commits, trees, task identity, hashes, manifests or artifact bindings. `finalize` re-verifies all of them.

```powershell
python -B Pipeline/TaskDelivery/generate_delivery_spec.py finalize --review "$Out\review.json" --output "$Out\delivery-spec.json"
```

`finalize` prints the exact next command. Copy it verbatim; the spec path is a **positional** argument, and there is **no `--spec` flag`**.

## 5. Step 2, path B: hand-authored spec (what NSC-042 and NSC-063 actually used)

Use path B only when path A can't express the truth. Examples:
- evidence from an earlier, byte-identical implementation commit (NSC-042's VAL-001 used historical XML and said so);
- a contract that requires **assistant-only** review, so `human_approval.required: false` with `decision: not_required` (NSC-063). Path A's finalize only accepts `required: false` from the automated validation mechanism.

`delivery-spec.json` uses exactly these keys:

```json
{
  "schema_version": "...",
  "task_id": "NSC-###",
  "validated_commit": "<HEAD sha>",
  "base_commit": "<sha>",
  "candidate_commit": "<sha>",
  "surfaces": [ ... ],
  "artifacts": [ { "id": "...", "type": "unity_test_results|unity_log|human_validation|other", "source_path": "<file outside the repo evidence dir>" } ],
  "gates": [ { "id": "VAL-001", "result": "pass", "evidence": ["<artifact id>"], "notes": "<truthful, specific>" } ],
  "human_approval": { "required": true, "decision": "approved", "approved_by": "Vincent Liguori", "notes": "<what he checked, quoted>" }
}
```

- **Copy the shapes from a real example:**
  - `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\nsc063-delivery-20260914\delivery-spec.json`;
  - `git show main:Pipeline/TaskGraph/evidence/NSC-042/records/DEL-NSC-042-10c614031f38.json`;
  - `git show main:Pipeline/TaskGraph/evidence/NSC-042/prepared/README.md`, which explains which evidence came from which commit.
- **Honesty is on you.** Path B does **not** check that Unity evidence came from the validated commit. If evidence predates it, say exactly which commit it came from and why it still proves the gate.

---

## 6. Step 3: package, stage, validate, commit

```powershell
python -B Pipeline/TaskGraph/record_delivery.py 'C:\nscrev\reports\delivery\NSC-###\delivery-spec.json'
```

- **What it checks:**
  - `HEAD == validated_commit`, the tree is clean, and base and candidate are ancestors;
  - XML shows `result="Passed"`, `failed="0"` and consistent counts;
  - the log is non-empty with no trailing whitespace;
  - human-validation text is valid UTF-8;
  - hashes come from real committed blobs, and artifacts get prospective blob hashes (with `.gitattributes` applied).
- **What it writes:** `Pipeline/TaskGraph/evidence/NSC-###/artifacts/<Name>-<12-char sha>.<ext>` and `records/DEL-NSC-###-<12-char sha>.json`. It never overwrites.
- **What it prints:** the exact STAGE, VALIDATE, CHECK, COMMIT and VERIFY commands. Use them **exactly**:

```powershell
git add -f -- <the exact files it printed>          # never git add . / -A: *.log is gitignored and silently dropped
python -B Pipeline/TaskGraph/validate_draft_evidence.py --record Pipeline/TaskGraph/evidence/NSC-###/records/DEL-NSC-###-<sha>.json   # must say DRAFT EVIDENCE: VALID
git diff --cached --stat
git -c user.name="No Safe Circle TaskReviewAgent" -c user.email="task-review-agent@nosafecircle.invalid" commit -m "Record NSC-### delivery evidence"
python -B Pipeline/TaskGraph/taskcontrol.py state NSC-### --json     # "state": "conformant"
```

- `validate_draft_evidence.py` checks the **index**. It fails if anything else is staged, or if another record is staged for the task.
- `git diff --cached --check` may flag the manifest-bound `.log`. **Don't edit the log.** Scope the check to non-log files: `git diff --cached --check -- <record> <xml> <text>`.
- Art tasks have used `No Safe Circle Art Review <art-review@nosafecircle.invalid>` as the identity.

Then:
1. The Integration Steward fast-forwards canonical `main` to the evidence commit (section 2), and you verify `taskcontrol state NSC-### --json` on canonical `main`.
2. **Remove the stale display overlay**, since real evidence now exists: `python -B C:\NSC\tools\viewer\nsc_viewer.py uncomplete NSC-###`.
3. **Archive the successful task** to `C:\NSC\SuccessfullTasks\NSC-###` (Integration Steward guide, section 6.2; use the record's integrated commit).
4. **Journal:** task, record ID, evidence commit, gates, Vincent's approval quote, archive path.

---

## 7. Pitfalls

| Message or symptom | Fix |
|---|---|
| `Artifact ... source_path refers to the destination evidence directory` | Point `source_path` at the original file outside `Pipeline/TaskGraph/evidence/` |
| `Unity log artifact ... contains trailing whitespace` | Use `run_unity_tests_clean.ps1`, or normalize with `Pipeline/Testing/unity_log_hygiene.py normalize` **before** it is bound to a manifest; never edit a bound log |
| The `.log` missing from the commit | You used `git add .`/`-A`. Use the printed `git add -f -- <files>` and run `validate_draft_evidence.py` |
| `Repository must be completely clean` | A review or spec file is inside the repo, or there is Unity churn. Move files out. Prove churn with `git diff --quiet HEAD -- <path>`, then restore only that path. |
| `already exists; refusing to overwrite` | Use a new output name |
| The task is `needs_testing` after commit | A later commit changed a surface. Validate at current `HEAD` instead. |
| The task is `invalid_evidence` | Read the findings in `state --json`. One bad record poisons the task; fix it with a new record, never by editing a committed one. |
| New task file breaks with `ID map/task count mismatch` | Update `WORK_ID_MAP.json` and resource groups in the same commit; see the playbook |
| `git merge-base --is-ancestor` "looks false" | Success is silent. Check the exit code, not stdout. |

---

## 8. Backlog on 2026-09-16

- **Already conformant:** 003, 004, 005, 011, 012, 019, 023, 024, 028, 037, 038, 039, 041, 042, 063. Only NSC-042 is archived in `SuccessfullTasks`.
- **Look done, but have no delivery record** (the human-complete overlay paints them green):
  - NSC-040, 060, 067, 068, 069;
  - NSC-089 (integrated `4047a4335`, EditMode 2/2 plus builder 57/57);
  - NSC-090 (`c5b40974b`, PlayMode 5/5);
  - NSC-091 (`38904af15`, PlayMode 22/22).
- **NSC-066** has a real open blocker: Vincent's title-screen visual gate, redesign pending. Don't package it.
- **Merged this week, not delivered:** 053, 017, 054, 073 (Vincent approved the hat in Unity on 9/16), 074, 093, and 075 once it lands.
- **Tasks needing a human gate:** check each contract's `completion_gates` for a Vincent gate. Collect his exact words in one batch and record them in the journal first, rather than asking once per task.
