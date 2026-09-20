# Brief: `new_task.py`, create a brand-new task contract (2026-09-17)

**From:** Documentation Agent. **To:** Pipeline Maintainer Agent. **Board:** H-20260917-25. **Vincent:** "Lets create the tool new_task.py. Queue Pipeline Maintainer with it."

## Why

There is **no way to create a task** today:
- `Pipeline/TaskGraph/taskcontrol.py` only inspects: `validate, list, show, ready, authorize, state, states, graph`.
- The `ger-tools` committers (`apply_contract.py`, `contract_commit.py`, `apply_followup_revision.py`) only **revise** a contract that already exists.
- NSC-093 and NSC-094 were hand-written and committed together as `c17b5b5ec` by `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`.

Vincent wants adding a task to be routine: the Viewer Agent takes the request, the GER Agent turns it into a contract, and this tool writes and commits it.

## What a contract looks like (from `Tasks/NSC-094.yaml` on main, schema_version 2.0)

Top-level keys, in this order:

```text
schema_version, id, contract_revision, contract_disposition, superseded_by, title, reconciliation_key, kind, type,
execution_scope, execution_reason, decomposition_state, decomposition_reason, parent, depends_on, exclusive_resources,
acceptance_criteria, completion_gates, downstream_integration_obligations, gdd_evidence, basis, source_scope,
confidence, notes, repository_state_at_bootstrap, repository_evidence_at_bootstrap, provenance
```

- `acceptance_criteria[]`: `criterion_id`, `reference`, `requirement`.
- `completion_gates[]`: `gate_id`, `reference`, `requirement`.
- `provenance`: `origin`, `created_by_human_request`, and task-specific keys; `contract_followups` is appended later by the revision tools.
- Highest ID on main today is `NSC-094`.

## Build

`C:\nscrev\ger-tools\new_task.py`, outside git like the other ger-tools, with a README section.

```text
python -B new_task.py --brief <brief.json> [--id NSC-### | --id auto] [--draft] [--commit]
```

1. **Brief** (JSON, written by the GER Agent): `title`, `reconciliation_key`, `kind`, `type`, `parent`, `depends_on`, `exclusive_resources`, `execution_scope`, `decomposition_state`, `acceptance_criteria`, `completion_gates`, `downstream_integration_obligations`, `gdd_evidence`, `basis`, `source_scope`, `confidence`, `notes`, `provenance`. Anything missing that the schema needs is a usage error naming the field.
2. **ID:** `--id auto` takes the lowest free `NSC-###` above the current highest at HEAD. Refuse an ID that exists in `Tasks/` at HEAD, or appears in `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`.
3. **Write** the full key set, in the order above, with the file's usual formatting and line endings: `schema_version` copied from main's current contracts, `contract_revision: 1`, `contract_disposition: active`, `superseded_by: null`.
4. **Fail closed** before writing anything:
   - the canonical checkout is on `main`, and `Tasks/` and `RESOURCE_GROUPS.yaml` are clean;
   - HEAD hasn't moved since the run started;
   - `parent` and every `depends_on` ID exists;
   - `reconciliation_key` is unique across `Tasks/` and kebab-case;
   - no acceptance criterion or gate has an empty `requirement`.
5. **Reconcile** `RESOURCE_GROUPS.yaml` with `apply_contract.py`'s helpers, exactly as `contract_commit.py` does.
6. **Validate:** `taskcontrol.py validate` and `git diff --check`. On any failure, restore both files and exit nonzero.
7. **Commit** (only with `--commit`; dry run otherwise, printing the contract and the validate result):
   - stage exactly `Tasks/<ID>.yaml` and `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`;
   - identity `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`;
   - message `Add task <ID>: <title>`;
   - never push. Journaling stays with the caller, as it is for `contract_commit.py`.
8. **`--draft`:** create the task so **no crew can start it** until the GER Agent completes it. Find what actually blocks selection (`taskcontrol ready` and the selection code), use that, and document it. Vincent may let the Viewer Agent create draft tasks itself.

## Tests

- Unit tests in a scratch clone, never the canonical checkout: auto-ID, duplicate ID and duplicate `reconciliation_key` refusals, the full key set and key order, `taskcontrol validate` passing, resource-group reconciliation, dirty-tree refusal, restore-on-failure, and `--draft` not being selectable.
- One dry run against real main, with no `--commit`.

## Notes

- Your usual flow: fix in a clone, an independent review (a Docker or host Claude review job, since Codex is out until the 19th), then hand it over.
- When it lands, tell the Documentation Agent. It will write the "add a task" procedure into the GER guide and the Viewer Agent guide.
