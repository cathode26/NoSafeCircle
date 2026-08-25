# Human-reviewed delivery-spec generation

## What this does / does not do

`generate_delivery_spec.py` is the narrow, provider-neutral bridge from strict `validation-manifest.json` facts to a human-approved, `record_delivery.py`-compatible delivery spec:

```text
validation manifest(s) -> draft -> human review -> finalize -> record_delivery.py
```

It performs clerical derivation and fail-closed verification. It does not decide truthful conformance surfaces, semantic roles, evidence-to-gate mappings, gate notes, whether a human validation occurred, approval, readiness, dispatch, delivery, or conformance. It never runs Unity or an LLM, stages, commits, pushes, merges, or creates TaskGraph evidence. A Unity pass does not automatically prove every gate.

## Preconditions

- Commit the implementation and complete authoritative clean Unity validation.
- Keep the repository completely clean for both `draft` and `finalize`, at exactly the validated HEAD/tree.
- Keep every manifest and its exact XML/log files present and unchanged through finalization and evidence packaging.
- Put review/spec outputs and optional human-validation inputs outside the repository.
- Choose a new output path: draft and finalize refuse to overwrite an existing file.
- Supply at least one validation manifest. Multiple manifests must identify exactly the same commit/tree.

## Produce validation manifest(s)

Run the committed clean wrapper for each required EditMode or PlayMode filter:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\Testing\run_unity_tests_clean.ps1 `
  -TestPlatform EditMode `
  -TestFilter "<exact filter>"
```

A successful run prints `Validation manifest: C:\...\validation-manifest.json` and preserves that manifest beside `test-results.xml` and `unity.log`. The manifest binds exact Git, Unity, result-count, path, hash, and size facts. It supplies no gate mapping or conformance claim.

## Create a draft

ExecutionCrew path, using the run's authoritative `crew_result.json` artifact:

```powershell
$TaskId = "NSC-###"
$ManifestPath = "C:\...\validation-manifest.json"
$CrewResultPath = "C:\...\crew_result.json"
$ReviewPath = Join-Path $env:TEMP "$TaskId-delivery-review.json"

python Pipeline/TaskDelivery/generate_delivery_spec.py draft `
  --task-id $TaskId `
  --crew-result $CrewResultPath `
  --validation-manifest $ManifestPath `
  --output $ReviewPath
```

Manual/non-crew path:

```powershell
$BaseCommit = "<commit-immediately-before-delivered-implementation-history>"
python Pipeline/TaskDelivery/generate_delivery_spec.py draft `
  --task-id $TaskId `
  --base-commit $BaseCommit `
  --validation-manifest $ManifestPath `
  --output $ReviewPath
```

`--base-commit` means the commit immediately before the delivered implementation history whose diff is being packaged, not an arbitrary old ancestor. With a crew result, its `source_head` is the inferred base; an explicit base overrides that inference but must still be ancestral.

## Human review checklist

The generated draft intentionally begins with `"review_status": "needs_human"` and is not finalizable. Humans edit only these truth-bearing fields:

- change `review_status` to `approved`;
- set each surface candidate's `selected` value to `true` or `false`;
- provide an explicit nonblank semantic `role` for every selected surface;
- map specific artifact IDs in every completion gate's `evidence` array;
- write meaningful gate-specific `notes` explaining why those artifacts prove that gate;
- set `human_approval.decision` to `approved`, with nonblank `approved_by` and `notes`.

Do not select every changed file or map every Unity artifact to every gate by reflex. Review the contract and make each claim truthfully.

Do not edit integrity/provenance fields: validated commit/tree; base/candidate commit; task identity/revision/hash; manifest inventory; artifact source paths/hashes/sizes/manifest bindings; or gate identity/reference/requirement. They are revalidated, and tampering or staleness fails closed.

## Finalize

```powershell
$DeliverySpecPath = Join-Path $env:TEMP "$TaskId-delivery-spec.json"

python Pipeline/TaskDelivery/generate_delivery_spec.py finalize `
  --review $ReviewPath `
  --output $DeliverySpecPath
```

Finalization rechecks the clean exact HEAD/tree, current task identity/revision/gates, base ancestry/candidate, a nonempty unique/current manifest inventory, exact manifest-bound XML/log inventory, external artifact hashes/sizes, selected committed blobs and roles, complete gate mappings/notes, and explicit human approval. It validates compatibility with `record_delivery.py` before publishing.

## Run record_delivery

Finalize prints the exact PowerShell-safe next command:

```powershell
python Pipeline/TaskGraph/record_delivery.py 'C:\...\NSC-###-delivery-spec.json'
```

Copy that printed command instead of reconstructing quoting. Then follow `record_delivery.py`'s exact `STAGE`, `VALIDATE DRAFT`, `CHECK`, `COMMIT`, and `VERIFY AFTER COMMIT` instructions. Do not use `git add .` or `git add -A`. TaskDelivery itself performs none of those actions and does not claim conformance.

## Closeout ordering learned from NSC-039

Before authoritative validation, fetch and integrate current `origin/main`. A validation manifest binds the exact tested commit and tree; if the implementation is rebased after validation, the manifest is stale even when the source diff looks identical. The reliable order is:

```text
commit implementation -> fetch/integrate current main -> verify TaskGraph loads -> authoritative clean Unity validation -> TaskDelivery draft/finalize -> record_delivery -> evidence commit
```

If a new task contract was added while the implementation branch was in progress, verify the persistent TaskGraph before drafting delivery evidence. NSC-039 was temporarily blocked because a concurrently-created task file existed without matching TaskGraph ID-map/resource metadata. A useful check is:

```powershell
python Pipeline/TaskGraph/taskcontrol.py state NSC-039 --json
```

`not_delivered` is acceptable before evidence exists; graph/schema/ID-map validation failure is not.

A successful authoritative runner can still leave a Windows/Unity file-stat marker that `git status` later reports, especially the code-coverage settings path. Do not rerun Unity immediately. First determine whether the exact path has a real normalized content change:

```powershell
$Path = "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json"
git diff --quiet HEAD -- $Path
if ($LASTEXITCODE -eq 0) {
    git restore --source=HEAD --worktree -- $Path
}
```

Only exact, proven stat-only churn should be restored. Any real content difference requires diagnosis.

## Immutable Unity logs and staged whitespace checking

Manifest-bound XML/log files are evidence bytes. Do not edit a copied Unity log to make `git diff --cached --check` happy; changing it invalidates the hash recorded in the delivery package.

NSC-039 produced a valid staged package whose raw Unity log contained Unity-generated trailing spaces. The safe handling pattern was:

1. stage exactly the files printed by `record_delivery.py`;
2. run `validate_draft_evidence.py` and require `DRAFT EVIDENCE: VALID`;
3. if full `git diff --cached --check` fails **only** on the exact manifest-bound `.log`, preserve the log unchanged;
4. run a scoped whitespace check on the structured/human-authored evidence, for example `git diff --cached --check -- <record> <xml> <human-validation>`;
5. inspect the staged stat and commit only the exact task evidence paths.

This exception applies only to immutable machine evidence already validated by `validate_draft_evidence.py`. It is not permission to ignore whitespace failures in source files, delivery records, XML, human-authored evidence, or unrelated staged paths.

For the broader PowerShell and retry postmortem, see:

```text
Docs/AI-Pipeline/TASK_ITERATION_CLOSEOUT_PLAYBOOK.md
```

## Multiple manifests

Repeat `--validation-manifest`, for example:

```powershell
  --validation-manifest "C:\...\EditMode\validation-manifest.json" `
  --validation-manifest "C:\...\PlayMode\validation-manifest.json"
```

All manifests must identify exactly the same commit/tree. Each contributes its own exact manifest-bound Unity XML and log artifact IDs.

## Optional human-validation artifact

Repeat `--human-validation "C:\...\human-validation.txt"` during draft creation when a real human check occurred. Each input must be an existing nonempty UTF-8 regular file outside the repository that truthfully documents the action. TaskDelivery hashes and inventories the file; it cannot establish that the action happened or that it proves a gate.

## Failure / redo rules

- Missing, stale, removed, duplicated, tampered, or unbound manifest evidence fails closed.
- A changed manifest/XML/log, HEAD/tree, task contract, gate set, selected blob, or external artifact requires correction and usually a fresh authoritative validation/draft.
- Keep the manifest/XML/log trio unchanged until TaskDelivery finalization and `record_delivery.py` finish.
- Draft/finalize never overwrite. Use a new filename, or deliberately remove an obsolete external temporary output after human review.
- Finalization requires at least one strict manifest; human validation alone is insufficient.
- No TaskDelivery result automatically stages, commits, creates evidence, grants conformance, authorizes dispatch, or completes a task. Committed TaskGraph evidence remains authoritative.
