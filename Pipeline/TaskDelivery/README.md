# Human-reviewed delivery-spec generation

`generate_delivery_spec.py` is the narrow, provider-neutral bridge between a committed implementation that passed clean Unity validation and the existing TaskGraph delivery packager. It adds no workflow, staging, commit, conformance, readiness, or execution authority.

The sequence is:

```text
validation-manifest.json -> draft -> human edit -> finalize -> record_delivery.py
```

`draft` verifies a completely clean repository and valid persistent TaskGraph, loads every manifest through the strict manifest loader, binds them to the current HEAD/tree, resolves an ancestral base, and inventories the exact committed diff. It creates deterministic XML/log artifact entries, optional human-validation entries, provenance-bearing surface candidates, and an exact copy of every completion gate. Gate evidence arrays and gate notes begin empty. Suggested surface roles are guidance only.

The review JSON must stay outside the repository. A human must decide which committed files truly are conformance surfaces, write their semantic roles, map specific evidence artifacts to each completion gate, explain each gate in notes, and explicitly approve the review. A Unity result is never automatically mapped to a gate, and unchanged task resources are never silently selected.

## PowerShell example

For manual/non-crew work, provide the base explicitly:

```powershell
python Pipeline/TaskDelivery/generate_delivery_spec.py draft `
  --task-id NSC-038 `
  --base-commit 0123456789abcdef0123456789abcdef01234567 `
  --validation-manifest "C:\Users\Name\AppData\Local\Temp\Run1\validation-manifest.json" `
  --human-validation "C:\Users\Name\AppData\Local\Temp\HumanValidation.txt" `
  --output "C:\Users\Name\AppData\Local\Temp\NSC-038-delivery-review.json"
```

For ExecutionCrew work, `--crew-result` supplies `source_head` as the inferred base. An explicit `--base-commit` may override that inference, but it still must be an ancestor of the validated commit.

```powershell
python Pipeline/TaskDelivery/generate_delivery_spec.py draft `
  --task-id NSC-038 `
  --crew-result "C:\Users\Name\AppData\Local\Temp\crew_result.json" `
  --validation-manifest "C:\Users\Name\AppData\Local\Temp\Edit\validation-manifest.json" `
  --validation-manifest "C:\Users\Name\AppData\Local\Temp\Play\validation-manifest.json" `
  --output "C:\Users\Name\AppData\Local\Temp\NSC-038-delivery-review.json"
```

Multiple manifests are allowed only when all identify the exact same validated commit and tree. Each contributes its own stable Unity XML and log artifact IDs.

After editing and approving the draft:

```powershell
python Pipeline/TaskDelivery/generate_delivery_spec.py finalize `
  --review "C:\Users\Name\AppData\Local\Temp\NSC-038-delivery-review.json" `
  --output "C:\Users\Name\AppData\Local\Temp\NSC-038-delivery-spec.json"
```

Finalization rechecks the clean HEAD/tree, task revision and exact gates, base/candidate ancestry, manifests and external artifacts, selected committed blobs, gate mappings/notes, and human approval. It validates the generated object with `record_delivery.parse_delivery_spec`, writes it atomically without overwrite, and prints the exact next command:

```powershell
python Pipeline/TaskGraph/record_delivery.py 'C:\Users\Name\AppData\Local\Temp\NSC-038-delivery-spec.json'
```

The tool does not run that command. Neither command invokes Unity or an LLM, edits contracts/canon, creates TaskGraph evidence, stages, commits, pushes, merges, or claims completion/conformance. `record_delivery.py`, staged-evidence validation, and committed TaskGraph evidence retain their existing authority.
