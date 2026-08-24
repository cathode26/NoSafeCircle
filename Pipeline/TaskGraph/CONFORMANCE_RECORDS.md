# Delivery/Baseline/Revalidation Evidence Records

Phase 3A derives the current conformance of one schema-v2 task from immutable, committed evidence. Records are historical facts; they never contain mutable readiness or completion authority.

## Locations

```text
Pipeline/TaskGraph/evidence/<TASK-ID>/records/<RECORD-ID>.json
Pipeline/TaskGraph/evidence/<TASK-ID>/artifacts/<files>
```

Only files committed at `HEAD` are read. Uncommitted records, contracts, canon, and artifacts cannot affect the result.

## Common schema 1.0

Every record has exactly these common fields plus exactly one of `delivery`, `baseline`, or `revalidation`:

```json
{
  "schema_version": "1.0",
  "record_type": "delivery",
  "record_id": "DEL-NSC-003-EXAMPLE",
  "task_id": "NSC-003",
  "task_contract": {
    "path": "Tasks/NSC-003.yaml",
    "revision": 1,
    "sha256": "semantic canonical JSON SHA-256"
  },
  "canon": {
    "path": "Docs/GDD/No_Safe_Circle_GDD.md",
    "sha256": "normalized UTF-8 text SHA-256"
  },
  "validated_state": {"commit": "Git commit SHA", "tree": "Git tree SHA"},
  "conformance_surfaces": [
    {"path": "repository/path", "blob_sha": "Git blob SHA", "role": "implementation"}
  ],
  "gate_results": [
    {
      "gate_id": "VAL-001",
      "result": "pass",
      "evidence": [
        {
          "path": "Pipeline/TaskGraph/evidence/NSC-003/artifacts/result.txt",
          "blob_sha": "Git blob SHA"
        }
      ],
      "notes": ""
    }
  ],
  "human_approval": {
    "required": false,
    "decision": "not_required",
    "approved_by": "",
    "notes": ""
  },
  "recorded_at": "2026-08-22T00:00:00Z"
}
```

Task-contract hashes parse the JSON-compatible YAML and hash UTF-8 canonical JSON with sorted keys and compact separators. Canon hashes tolerate a UTF-8 BOM and normalize CRLF and lone CR to LF. Surfaces and gate artifacts use Git blob SHAs.

Delivery records add:

```json
"delivery": {
  "base_commit": "...",
  "candidate_commit": "...",
  "integrated_commit": "...",
  "integrated_tree": "..."
}
```

`validated_state` must exactly equal the integrated commit/tree.

Baseline records establish the first trustworthy evidence state for an implementation that existed before this evidence system. They do not claim when that implementation was authored or delivered. Their IDs use the `BASE-` prefix, and they add:

```json
"baseline": {
  "reason_type": "pre_evidence_existing_implementation",
  "summary": "Why this existing implementation is being baselined"
}
```

The summary must be non-empty. The validated commit/tree is the actual integrated state tested. Baselines contain no `base_commit`, `candidate_commit`, or `integrated_commit` fields. A valid baseline establishes conformant state exactly as a valid delivery does.

Revalidation records add:

```json
"revalidation": {
  "basis_record_id": "DEL-NSC-003-EXAMPLE",
  "reason_type": "code_change",
  "summary": "Why the earlier evidence was revalidated"
}
```

Allowed reasons are `code_change`, `gdd_change`, `contract_change`, `periodic`, and `manual`. The basis may be a delivery, baseline, or prior revalidation record. It must be a same-task committed record, basis chains must be acyclic, and the basis validated commit must be an ancestor of the revalidation commit.

## Validation and selection

The evaluator rejects absolute/non-canonical/traversing paths, unsupported schema fields, mutable authority fields (`status`, `complete`, `current`, `ready`, `authorized`), identity/path disagreement, duplicate IDs, duplicate gate IDs, duplicate surface paths, false trees/hashes/blobs, and incomplete current gate sets.

Every recorded gate must be `pass`. Required human approval establishes conformance only with `decision: approved` and a non-empty `approved_by`; otherwise the derived state is `needs_human`.

When multiple records are current-valid, a record at a strict descendant validated commit supersedes ancestors. Multiple maximal records that cannot be reduced to one by commit ancestry produce `ambiguous_evidence`; timestamps never break ties.

Derived state precedence is:

1. `cancelled` / `superseded`
2. `aggregate`
3. `invalid_evidence` / `ambiguous_evidence`
4. `conformant`
5. `needs_replan`
6. `needs_human`
7. `needs_revalidation`
8. `not_delivered`

## Commands

```text
python3 Pipeline/TaskGraph/taskcontrol.py state NSC-003
python3 Pipeline/TaskGraph/taskcontrol.py state NSC-003 --json
python3 Pipeline/TaskGraph/conformance_evaluator_smoke_test.py
```

## `record_delivery.py` — packaging delivery evidence

Closing NSC-005 exposed excessive manual clerical work after implementation and validation
were already complete: creating evidence directories by hand, copying the Unity XML and
log, writing a human-validation text file, computing every hash and Git object identity by
hand, hand-assembling the delivery record JSON, remembering that `*.log` is gitignored and
therefore needs `git add -f`, and discovering only after committing that the `.log`
artifact had silently not been staged. TaskGraph correctly rejected that incomplete
evidence as `invalid_evidence` — the safety behavior was correct, but producing valid
evidence was needlessly manual and error-prone.

`Pipeline/TaskGraph/record_delivery.py` is deterministic clerical automation for that one
packaging step. It is **not** another agent and it has **no completion authority**:

- It consumes one explicit JSON delivery-spec file (see below) — never an LLM, never Unity.
- It validates every precondition (clean working tree, `HEAD == validated_commit`, ancestor
  relationships, committed task contract and canon, committed conformance-surface blobs,
  exact completion-gate-set match, artifact existence) before writing anything.
- It copies artifact bytes byte-for-byte and validates them by type: Unity test-results XML
  must parse, have a `<test-run>` root, `result="Passed"`, `failed="0"`, and consistent
  integer counts; a Unity log must be a non-empty file; human-validation text must be valid
  UTF-8 non-blank text. It never turns a failing or malformed Unity result into passing
  evidence.
- It computes the task-contract semantic SHA-256, the canon canonical-text SHA-256, every
  conformance-surface Git blob SHA (read from the validated commit, and confirmed via `git
  cat-file -t` to actually be a `blob`, not a tree/directory), and every generated evidence
  artifact's *prospective* Git blob SHA itself, without staging or writing to the object
  database. The artifact hash uses `git hash-object --stdin --path=<final-repository-path>
  --filters`, i.e. the same clean-filter/`.gitattributes` normalization that `git add -f`
  will apply once the printed staging command below is run — not a raw hash of the copied
  bytes, which could disagree with what Git eventually commits (for example CRLF-normalizing
  `text=auto`/`eol=lf` attributes). The artifact file written to the working tree is still an
  exact byte-for-byte copy of the source; only the recorded `blob_sha` accounts for the
  filter Git will apply at commit time. Nothing is asked of, or trusted from, the human.
- It generates the delivery record and validates it with the existing, unmodified
  `conformance_records.validate_record_shape()` — the authoritative schema is reused, not
  duplicated or re-implemented.
- It stages nothing, commits nothing, pushes nothing, merges nothing, and never edits a
  `Tasks/*.yaml` contract.
- It never claims the task is conformant. Its output explicitly says TaskGraph determines
  conformance only after the evidence is committed.

### Delivery-spec input

One explicit JSON file, schema `1.0`, with unknown top-level or nested fields rejected
outright (no silently-ignored typos).

The delivery spec is input to the tool, not repository evidence, and this tool requires a
completely clean working tree before packaging. Keep the spec file outside the Git working
tree — the recommended Windows workflow is an external path such as
`$env:TEMP\NSC-005-delivery-spec.json` — or somewhere already covered by `.gitignore`. Do
not place an untracked spec file inside the repository, since that would fail the
clean-working-tree precondition, which is never weakened to permit an untracked spec:

```json
{
  "schema_version": "1.0",
  "task_id": "NSC-005",
  "validated_commit": "12fad9358f637e7e066376357247752db8b51c50",
  "base_commit": "<commit before this task delivery began>",
  "candidate_commit": "12fad9358f637e7e066376357247752db8b51c50",
  "surfaces": [
    {"path": "Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMana.cs", "role": "mana_owner"},
    {"path": "Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerManaUI.cs", "role": "mana_indicator_feedback"}
  ],
  "artifacts": [
    {"id": "playmode_results", "type": "unity_test_results", "source_path": "C:\\...\\test-results.xml", "name": "PlayerManaPlayModeTests"},
    {"id": "unity_log", "type": "unity_log", "source_path": "C:\\...\\unity.log", "name": "PlayerManaPlayModeTests"},
    {"id": "human_validation", "type": "human_validation", "source_path": "C:\\...\\human-validation.txt", "name": "HumanValidation"}
  ],
  "gates": [
    {"gate_id": "VAL-001", "evidence": ["playmode_results", "unity_log"], "notes": "..."},
    {"gate_id": "VAL-002", "evidence": ["playmode_results", "human_validation"], "notes": "..."}
  ],
  "human_approval": {"required": true, "decision": "approved", "approved_by": "", "notes": "..."}
}
```

Notes:

- `surfaces`/`gates`/`artifacts` are exactly what the human/spec declares. The tool never
  infers a semantic conformance surface or a completion gate that was not explicitly listed.
- `gates` must contain exactly the task contract's current completion-gate ID set (no
  unknown, missing, or duplicate gate IDs); every gate result is implicitly `pass`, because
  this tool only packages a *successful* delivery.
- If `human_approval.required` is `true` and `approved_by` is blank, the repository's
  configured `git config user.name` is used; if that is also unavailable, packaging fails.

### Generated layout

```text
Pipeline/TaskGraph/evidence/<TASK-ID>/artifacts/<Name>-<validated-commit-short-sha>.<ext>
Pipeline/TaskGraph/evidence/<TASK-ID>/records/DEL-<TASK-ID>-<validated-commit-short-sha>.json
```

For example, `DEL-NSC-005-12fad9358f63.json` referencing
`PlayerManaPlayModeTests-12fad9358f63.xml`, `PlayerManaPlayModeTests-12fad9358f63.log`, and
`HumanValidation-12fad9358f63.txt`. Extensions are `.xml`/`.log`/`.txt` for the three known
artifact types, or derived from the source file's own extension for `type: "other"`.

Every generated path is checked for a pre-existing file immediately before publication;
the tool refuses to overwrite an existing artifact, an existing delivery record, or any
other prior immutable evidence. Artifacts are published before the record.

### The `.log`-is-gitignored regression, addressed directly

The NSC-005 defect was that a `.log` evidence file existed on disk but `*.log` was
gitignored, so a plain `git add`/`git commit` silently omitted it, and TaskGraph correctly
derived `invalid_evidence` from the resulting incomplete record. `record_delivery.py` never
runs `git add` itself. Instead, after successful packaging, it prints an exact staging
command that force-adds only the exact files it just generated:

```text
git add -f -- 'Pipeline/TaskGraph/evidence/NSC-005/artifacts/PlayerManaPlayModeTests-12fad9358f63.xml' 'Pipeline/TaskGraph/evidence/NSC-005/artifacts/PlayerManaPlayModeTests-12fad9358f63.log' 'Pipeline/TaskGraph/evidence/NSC-005/artifacts/HumanValidation-12fad9358f63.txt' 'Pipeline/TaskGraph/evidence/NSC-005/records/DEL-NSC-005-12fad9358f63.json'
```

It never prints or runs `git add -A`, `git add .`, or `git add -f <directory>`; the printed
command always enumerates the exact generated files by name, so an ignored artifact cannot
be silently dropped again. The tool itself never executes that command — the human runs it,
then runs `validate_draft_evidence.py` (below) against the exact staged index before
committing, inspects `git diff --cached --check`/`--stat`, commits, and only then queries
TaskGraph:

```text
python Pipeline/TaskGraph/taskcontrol.py state NSC-005 --json
```

Committing is the human's decision; TaskGraph's evidence-derived evaluator remains the only
authority for `conformant`, exactly as before. Run
`python3 Pipeline/TaskGraph/record_delivery_smoke_test.py` for the deterministic regression
suite, which proves (against synthetic repositories, never the real repository) that a
package this tool produces is actually consumable by `current_conformance.py` once
committed, and that a gitignored `.log` artifact is still enumerated in the printed stage
command.

## `validate_draft_evidence.py` — validating the actual staged would-be commit

Postmortem improvement #4. `record_delivery.py` (above) guarantees that the *bytes it
generates* are correct and prints the exact `git add -f` command needed to stage them. It
does **not** guarantee that the human actually ran that command correctly, ran it for every
file, or didn't also unintentionally sweep unrelated work into the same commit with a
follow-up `git add -A`. NSC-005 was exactly this gap: the packaging step (predecessor manual
process) was fine, the `.log` file existed on disk, but it was never actually staged because
`*.log` is gitignored, and nothing checked the *actual index* before commit. TaskGraph's
evidence-derived evaluator correctly rejected the resulting commit as `invalid_evidence` /
`artifact_blob_mismatch` — that was the correct safety behavior — but the failure was only
discovered after committing.

`Pipeline/TaskGraph/validate_draft_evidence.py` closes that specific gap. It answers exactly
one question, deterministically, with no agents, no LLM, no Unity, and no mutation of any
kind: **if the human commits the currently staged Git index on top of committed HEAD right
now, does the draft evidence record actually contain the record and evidence objects it
claims to contain?**

`validate_draft_evidence.py` currently validates one new delivery record per evidence
closeout commit; baseline/revalidation draft validation is not supported.

```powershell
python Pipeline/TaskGraph/validate_draft_evidence.py --record Pipeline/TaskGraph/evidence/NSC-005/records/DEL-NSC-005-12fad9358f63.json
python Pipeline/TaskGraph/validate_draft_evidence.py --record Pipeline/TaskGraph/evidence/NSC-005/records/DEL-NSC-005-12fad9358f63.json --json
python3 Pipeline/TaskGraph/validate_draft_evidence_smoke_test.py
```

The **Git index is authoritative**. It never substitutes working-tree bytes for staged
bytes:

- The draft record itself must be staged, must be a genuinely new path relative to HEAD
  (never a staged modification, replacement, or deletion of an already-committed record or
  artifact), and is parsed from the **index** (`git show :<path>`), never from the working
  tree.
- It is validated with the existing, unmodified `conformance_records.validate_record_shape()`
  — the schema is reused, not duplicated or weakened — and then cross-checked against the
  repository: the validated commit/tree resolve and the validated commit is HEAD or an
  ancestor of it; the recorded task contract and canon exist and hash-match at the validated
  commit *and* are still the current ones at HEAD (otherwise this is stale evidence or would
  require replan, not a delivery commit); every conformance surface's blob matches at both
  the validated commit and HEAD; the completion-gate ID set exactly matches the current task
  contract; human approval is internally consistent; and, for delivery records, `base_commit`
  and `candidate_commit` resolve and stand in the correct ancestor relationship to the
  validated commit.
- For every gate-evidence artifact reference, it resolves what would actually be committed:
  a staged (index) blob if one exists, otherwise the already-committed HEAD blob, otherwise
  the reference fails outright. A file that merely exists in the working tree is never
  treated as evidence.
- Any staged change outside the one task's `Pipeline/TaskGraph/evidence/<TASK-ID>/` is
  reported and fails validation, so an accidental `git add -A`/`git add .` cannot sweep
  unrelated work into an evidence closeout commit.
- Any other newly staged file under that task's `records/` directory besides the one
  supplied via `--record` also fails validation: TaskGraph's `load_committed_records()`
  loads and validates every file in that directory after commit, so an extra staged
  record — malformed or otherwise valid — would be committed and derived from without
  ever having been checked by this validator.

On the NSC-005 regression specifically — a record staged, its XML and human-validation
staged, but its `.log` gitignored and never staged — the validator fails with the exact
missing path, states plainly that the file exists in the working tree but is neither staged
nor already committed, notes that it is ignored by `.gitignore`, and prints the one safe fix:

```text
git add -f -- 'Pipeline/TaskGraph/evidence/NSC-005/artifacts/PlayerManaPlayModeTests-12fad9358f63.log'
```

It never suggests `git add -A`, `git add .`, or `git add -f <directory>`, and if a referenced
path is genuinely missing (absent from the index, HEAD, *and* the working tree) it says so
plainly instead of inventing a staging command. Running that exact fix and rerunning the
validator passes.

`record_delivery.py` prints the exact `validate_draft_evidence.py --record <path>` command
as the step immediately after `STAGE` and before `CHECK`/`COMMIT` in its own human and JSON
output, so the normal workflow always includes it.

The packager (`record_delivery.py`) validates the bytes it generates before they are staged;
this validator validates the actual staged would-be commit before it is committed. They
solve different problems, and neither claims the task conformant: this tool never stages,
commits, pushes, or merges anything, and its own regression suite proves it (`git status`
and `HEAD` are asserted unchanged across both passing and failing runs). Committed
TaskGraph evaluation (`current_conformance.py` / `taskcontrol.py state`) remains the sole
authority for `conformant`, exactly as before, and only after the human actually commits.

Phase 3A enables evidence-derived current-state inspection through `taskcontrol state`. Baseline evidence is immutable history, never mutable current/completion/readiness authority.

NSC-023 is the first real production baseline example. At committed HEAD, `BASE-NSC-023-86af98f41ab5` proves the current state of the Fixed Isometric Camera as `conformant`. Its validated implementation is commit `86af98f41ab53016ef55eca9516cc339a1e4f5d1`, tree `3e89c4a4879d1bf4179ae48f95b85dee1abc0d4d`, and its evidence was committed in `8933e67c7767abf45634f7bade79c734f334eea5`. Uncommitted evidence was correctly ignored before that evidence commit.

No real production revalidation record exists yet. Do not fabricate a gameplay, contract, GDD, or implementation change merely to produce one; the first legitimate relevant change will exercise production revalidation.

A conformant result does not establish dependency readiness. Dependency-readiness policy and dispatch authorization policy have not been implemented or approved: `taskcontrol ready` remains unavailable, `taskcontrol authorize` remains denied with exit code `2` and reason code `evidence_derived_dispatch_policy_not_enabled`, and zero tasks may be autonomously dispatched. State inspection and a conformant result never authorize autonomous execution.
