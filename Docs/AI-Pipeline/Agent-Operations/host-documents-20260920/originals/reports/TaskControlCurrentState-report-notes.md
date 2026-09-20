# TaskControl current-state migration

The implementation makes committed TaskControl selection, contract applicability, and additive lifecycle events authoritative for delivery and eligibility. Old task names and unrelated delivery artifacts no longer select a current implementation. Selected evidence still has to prove its exact Git objects, contract, validation policy, epoch, artifact hashes, and required approval.

The isolated checkout is `C:\NSC\TaskControlCurrentState-20260907`, on `taskcontrol-current-state`, created from the fetched `origin/main` commit `73fae3818ded52eec10e12230de7403cafda4081`. The active operator checkout was only inspected to locate the remote and guidance. No live Issues, claims, containers, workers, or gauntlet runs were operated. Nothing was pushed or merged.

## Audit and replacement rules

| Original rule / assumption | Canonical replacement |
| --- | --- |
| `current_conformance.py` loaded every task delivery record and `_maximal` inferred the current one from validated-commit ancestry. Old records could make a new revision delivered/stale/ambiguous without an explicit current selection. | `taskcontrol_state.current_selection` resolves the committed selection first. No selection means `not_delivered`; only the selected record and its required revalidation basis chain are evaluated. Ancestry validates an explicit reference rather than choosing one. |
| The history-identity CI workflow required NSC-020 to remain conformant with `DEL-NSC-020-5827effabf60`. A deliberate reset/revision could violate that permanent historical expectation. | All three affected workflows run `taskcontrol.py validate-current --source .` against the exact checked-out PR head. Existing history-identity object/tree audit remains in place. |
| The synthetic-gauntlet test fixture used the checkout's real Tasks and reconstructed fixtures by deleting the entire 911–990 range. It depended on a particular historic/current installation, including assumptions about partial existing contracts. | The test fixture owns a complete, deterministic, small input graph. A regression poisons the unrelated checkout with historical synthetic IDs and verifies unchanged fixture output. The production installer still refuses to overwrite existing contracts. |
| Acceptance-harness prose described NSC-900–999 as a permanently reserved range outside production. | IDs are local fixture-manifest identities. History does not reserve them. |
| Thirteen admission/execution/decomposition/accounting/launcher regexes admitted exactly three digits although TaskGraph already admitted three or more. | These boundaries preserve full IDs of at least three digits. NSC-1000 now passes the same admission path without aliasing or truncation. Invalid or command-shaped IDs remain rejected. |
| The dispatch policy's known-state list could not represent newly canonical `retired`/`excluded` states. The bulk reader would reject the entire snapshot. | Both states are recognized but remain absent from fresh-eligible and dependency-satisfied sets. CLI filters also expose them. |

The audit did **not** find a general CI rule that reserves every task ID found in commit messages. The actual historical inferences above were repaired. Other Git history scans were classified rather than removed: immutable record/event path checks; exact commit/tree translation; decomposition replay/undo ancestry; operational branch/claim inventories; Git author audits; and publication boundaries remain safety or audit checks. Reusing an immutable evidence **path** is still forbidden; reusing a task through a new epoch and evidence path is supported.

## Schema, commands, and publication

`TASKCONTROL_CURRENT.json` is a one-time generated activation marker with schema, fixed authority name, exact migration base commit, and 14 frozen legacy selections. It was produced by `taskcontrol.py migrate-current`, not manually authored. Its edits or deletion fail validation after activation.

`taskcontrol.py transition` is the single host-owned lifecycle writer. `reset`, `retired`, `cancelled`, and `excluded` append an event and advance the epoch; `select --record-id` appends an exact selection in the current epoch. Every event has a contiguous revision, predecessor semantic hash, base commit, contract binding, operation, disposition, and reason. Publication exclusively creates the next file. The command requires a clean checkout and rechecks HEAD and cleanliness before publication. It does not invoke Git mutations or execute task-provided commands.

Selection binds record ID/hash, task ID, contract revision/hash/path, tested and delivered 40-character commits, lifecycle epoch, and a fixed validation-policy identity with a hash of the task's completion gates and authoritative policy entry. New selected evidence must match the tested contract and policy, and the tested commit must contain the exact epoch-start event. Reset/revision does not delete old commits or records. A contract revision is committed before the canonical transition can bind it; an old selection with a mismatched contract fails closed until reset/selection is committed.

The delivery packager calls the same planner. Its exact path list includes the selection event; draft validation compares the staged event to the canonical plan alongside the record/artifacts. Existing authorization, resource, dependency, decomposition and publication checks remain additional gates. A lifecycle reset grants no execution authority and performs none of the separate operational reset helper's cleanup.

`validate-current` reconstructs the complete TaskGraph from committed Git objects, validates graph invariants, and evaluates every task in numeric ID order using one captured HEAD. It rejects malformed current records and orphan selections. It ignores uncommitted content. Unstarted tasks are valid repository state. Schedulers retain the existing bulk TaskControl JSON reader. No visualizer implementation or visualizer-state suite exists at the captured baseline; no separate lifecycle model was added.

## Compatibility and limits

Repositories that predate the activation marker retain the original evidence semantics for historical inspection. Once a marker exists, it cannot be removed to fall back. The migration freezes valid legacy selections, including `needs_replan`/`needs_testing`; it does not manufacture passing results. Existing approved, tree-preserving history-identity translations remain supported without editing old record bytes.

Git objects and artifact hashes prove exact committed provenance under the existing review trust model. This change does not add signed test attestations or rerun Unity from task data. A new selection is not an arbitrary `complete` flag. Existing record-schema, gate, artifact, historical contract, canon, surface, topology and human-approval checks still determine whether it is conformant. Revalidation basis records remain subject to their historical provenance checks even though only the explicit selection controls current applicability.

All execution in this work used temporary Git fixtures and local validation snapshots. No Unity editor/test runner, external provider, live scheduler launch, or acceptance gauntlet run was invoked. The missing baseline quick/width/thousand suites were covered by new deterministic width and repository tests; existing scheduler, dispatch, decomposition, identity, reset/rehearsal and acceptance-harness suites were exercised.
