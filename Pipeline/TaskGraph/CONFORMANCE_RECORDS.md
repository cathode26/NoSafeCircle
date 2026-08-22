# Delivery/Revalidation Evidence Records

Phase 3A derives the current conformance of one schema-v2 task from immutable, committed evidence. Records are historical facts; they never contain mutable readiness or completion authority.

## Locations

```text
Pipeline/TaskGraph/evidence/<TASK-ID>/records/<RECORD-ID>.json
Pipeline/TaskGraph/evidence/<TASK-ID>/artifacts/<files>
```

Only files committed at `HEAD` are read. Uncommitted records, contracts, canon, and artifacts cannot affect the result.

## Common schema 1.0

Every record has exactly these common fields plus either `delivery` or `revalidation`:

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

Revalidation records add:

```json
"revalidation": {
  "basis_record_id": "DEL-NSC-003-EXAMPLE",
  "reason_type": "code_change",
  "summary": "Why the earlier evidence was revalidated"
}
```

Allowed reasons are `code_change`, `gdd_change`, `contract_change`, `periodic`, and `manual`. The basis must be a same-task committed record, basis chains must be acyclic, and the basis validated commit must be an ancestor of the revalidation commit.

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

Phase 3A enables evidence-derived current-state inspection through `taskcontrol state`. No production delivery/revalidation evidence has yet been proven on a real task. Dependency-readiness and dispatch authorization policy are not enabled: `taskcontrol ready` remains unavailable, `taskcontrol authorize` remains denied with exit code `2`, and zero tasks may be autonomously dispatched. State inspection alone, including a `conformant` result, never authorizes execution.
