# Context 1 — Persistent Work Artifacts + Dependency Graph

## Status

**COMPLETE — 2026-08-21**

Milestone 1 is implemented, validated against the real No Safe Circle graph, merged into `main`, and present on `adversarial-architecture-review`.

Do not treat this file as an instruction to rebuild Milestone 1. It is now the completion record and semantic reference for the persistent work graph.

The next pipeline milestone is:

`Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md`

Current live status is always summarized in:

`Docs/AI-Pipeline/CURRENT_STATE.md`

## Goal That Was Achieved

Milestone 1 replaced repeated full-LLM reconstruction of project work state with a durable deterministic local graph.

The project can now remember:

- what work exists;
- stable work identity;
- parent/feature structure;
- dependencies;
- execution scope;
- exclusive-resource conflicts;
- project-level non-code constraints;
- what is complete/open;
- and which concrete one-agent tasks are executable right now.

No LLM is required to load, validate, inspect, or calculate readiness for the persistent graph.

## Bootstrap Provenance

The initial graph was not seeded directly from an unverified LLM plan.

It passed this trust path:

```text
Current GDD + repository state
        ↓
Immutable reconciliation snapshot
        ↓
Independent multi-model verification
        ↓
Bounded refinement / re-verification
        ↓
0 final material findings
        ↓
Human approval manifest
        ↓
Deterministic Work Graph Seeder
        ↓
Persistent Tasks/*.yaml
```

Approved source reconciliation:

`20260821T193541Z-998ee7b5`

Successful verification:

`20260821T195959Z-43dba5de`

Approval manifest:

`Pipeline/TaskGraph/APPROVED_BOOTSTRAP.json`

Bootstrap completion marker:

`Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json`

The bootstrap marker is published last. Its hashes bind the initial seed state historically; they are not live immutable checksums that prevent legitimate later task-state updates.

## Persistent Graph Produced

The initial approved graph contains:

- 37 work records
- 12 `feature`
- 25 `implementation`
- 0 `artifact` at initial bootstrap
- 36 `open`
- 1 `complete`
- 59 dependency edges
- 36 parent edges
- 7 exclusive-resource groups
- 17 project-level non-code requirements
- one root: `NSC-001` / `no-safe-circle`

The only initially complete implementation is:

`NSC-023 — Fixed Isometric Camera`

Persistent task files:

```text
Tasks/NSC-001.yaml
...
Tasks/NSC-037.yaml
```

Persistent metadata:

```text
Pipeline/TaskGraph/WORK_ID_MAP.json
Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml
Pipeline/TaskGraph/RESOURCE_GROUPS.yaml
Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json
```

The `.yaml` records use a deterministic JSON-compatible YAML 1.2 subset. This intentionally keeps the loader on Python's standard `json` parser and avoids adding a YAML dependency merely for the persistent graph.

## Stable IDs and Traceability

The project root is permanently allocated:

`no-safe-circle → NSC-001`

The remaining initial IDs preserve the approved seed-record order.

Each persistent task keeps a `reconciliation_key` linking the operational work item back to the reconciliation record that proposed it.

Once persisted, IDs are durable work identity. Future reconciliation must not recalculate or renumber them merely because a new snapshot has different ordering.

## Work Kinds

Milestone 1 supports:

```text
feature
artifact
implementation
```

### `feature`

Organizational or high-level work that may require later progressive decomposition.

Feature nodes are not directly handed to implementation workers.

### `artifact`

Work whose output is an approved design/content artifact.

Milestone 1 can represent this kind even though no artifact records were needed in the initial bootstrap. Artifact authority, generation, evaluation, and promotion belong to Milestone 2+.

### `implementation`

Concrete project work that can eventually be executed by an implementation worker when dependencies and execution scope permit it.

## Execution Scope Semantics

Execution scope is separate from design completeness/decomposition state.

Allowed values:

- `single_agent` — safe bounded one-agent handoff.
- `needs_execution_decomposition` — approved design is concrete enough, but implementation responsibilities are still too broad for one safe handoff.
- `human_integration_required` — the next meaningful action fundamentally requires human integration/editor judgment.
- `not_applicable` — feature/organizational or already-complete work.
- `unknown` — insufficiently reviewed/legacy state; not safe for autonomous selection.

The initial graph contains:

- 16 `single_agent`
- 8 `needs_execution_decomposition`
- 13 `not_applicable`

Progressive Decomposition remains a later semantic step:

1. **design decomposition** when approved information is missing/too coarse;
2. **execution decomposition** when design is already approved but one implementation record is too broad.

Execution decomposition may split known responsibilities. It may not invent new mechanics or content.

## Status Semantics

Milestone 1 persistent work uses:

- `open`
- `complete`

Operational transient states such as Claimed/In Progress/Validating belong later in the supervisor/GitHub layer rather than being committed constantly into every task branch.

Production completion semantics remain:

- implementation work is complete only when integrated repository evidence supports the claim, eventually requiring merge to `main`;
- artifact work is complete only after required authority/evaluation and promotion to trusted project input;
- feature nodes are organizational and are not direct execution tickets.

## Reconciliation Boundary

Reconciliation is an immutable observation snapshot, not the mutable task database.

A new reconciliation run:

1. observes current GDD/repository state;
2. creates a new immutable snapshot;
3. may propose graph additions/changes/conflicts;
4. never directly rewrites the persistent graph.

The living operational state is `Tasks/*.yaml`.

Future graph changes must cross an explicit deterministic diff/review/apply boundary. Safe cascading readiness changes are computed from the graph, not written by an LLM.

## Core Implementation

Milestone 1 implementation lives under:

`Pipeline/TaskGraph/`

Important files include:

- `bootstrap_inputs.py` — loads the human-approved immutable verification artifacts and rechecks bound hashes/invariants.
- `work_graph_transform.py` — deterministic stable-ID allocation and in-memory transformation.
- `work_graph_validate.py` — structural, dependency, hierarchy, execution-scope, resource-group, provenance, and project-requirement validation.
- `work_graph_persist.py` — staged persistence, reload/revalidation, publication, and final completion marker.
- `seed_work_graph.py` — dry-run/apply entry point for the one-time initial bootstrap.
- `persistent_work_graph.py` — live persisted-graph loader.
- `taskcontrol.py` — deterministic graph CLI.
- associated smoke tests.

The initial bootstrap is one-shot. Do not rerun `seed_work_graph.py --apply` after `BOOTSTRAP_PERSISTED.json` exists.

## `taskcontrol`

Implemented commands:

```text
python Pipeline/TaskGraph/taskcontrol.py validate
python Pipeline/TaskGraph/taskcontrol.py list
python Pipeline/TaskGraph/taskcontrol.py show NSC-003
python Pipeline/TaskGraph/taskcontrol.py ready
python Pipeline/TaskGraph/taskcontrol.py graph
```

### `validate`

The live loader and graph validator check the current persistent state rather than blindly trusting that the initial seed was valid forever.

Validation covers, among other things:

- duplicate IDs/reconciliation keys;
- filename/ID consistency;
- valid ID format;
- ID-map/task consistency;
- valid kind/status/execution-scope enums;
- malformed required fields;
- one correct project root;
- valid parent references;
- connected/acyclic parent hierarchy;
- valid dependencies;
- dependency acyclicity;
- bootstrap provenance consistency;
- exclusive-resource group consistency;
- project-requirement structure;
- open executable work incorrectly marked `not_applicable`.

### `ready`

A work item is executable-ready when:

1. `status == open`;
2. `kind` is `artifact` or `implementation`;
3. `execution_scope == single_agent`;
4. every `depends_on` item is complete.

Feature nodes, decomposition-needed work, human-integration work, and unknown-scope work are not returned as executable-ready.

The first real ready frontier contained seven tasks:

```text
NSC-003  Mouse-Directed Player Movement, Shared Pointer Projection, and Movement Restriction
NSC-004  Player Health Ownership, Restore, Death Transition, and Feedback
NSC-005  Player Mana Ownership, Restart Reset, and Denied-Cast Feedback
NSC-011  Active Enemy Registry
NSC-020  Shared Doorway-Crossing State (Forward-Side Crossing Detection)
NSC-024  Tilemap and AI Navigation Package Configuration
NSC-037  Windows Build Scene Registration
```

This was the key Milestone 1 proof: the repository can now answer **what can safely execute now** without rebuilding a roadmap in an LLM context.

### `list`, `show`, and `graph`

`list` provides the compact full backlog with status/kind/execution scope.

`show <ID>` exposes the bounded task contract including dependencies, exclusive resources, acceptance criteria, validation requirements, notes, and bootstrap repository state.

`graph` reconstructs the feature hierarchy and dependency edges in human-readable text.

## Real First-Task Example

`NSC-003` is a concrete `single_agent` task with no dependencies and is a strong anchor for the next pipeline slice.

Its contract includes:

- mouse-directed click/hold movement through Unity Input System/Input Actions;
- shared cursor-to-gameplay-plane projection;
- owner-controlled movement restriction for Charged Fireball;
- owner-controlled reset entry point;
- owner-controlled gameplay suspend/re-enable behavior;
- Unity integration through the relevant Input Actions, builder, and canonical scene resources.

Milestone 2 should use real near-term gameplay work like this when testing compact context generation rather than building generic infrastructure in isolation.

## Resource-Conflict Semantics

Exclusive resource claims describe integration/conflict surfaces; they do not automatically imply dependency edges.

Initial shared resource groups include logical ownership surfaces plus concrete Unity assets such as:

- `Assets/InputSystem_Actions.inputactions`
- `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`
- `Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs`
- `Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity`

These become especially important later when the supervisor introduces claims/worktrees and eventually parallel workers.

## Lessons Preserved from Milestone 1

1. **Repository state beats conversation memory.**
2. **Reconciliation is observation, not mutable project state.**
3. **Human approval is a real authority boundary.**
4. **The graph should be coarse and truthful rather than exhaustively speculative.**
5. **Execution size and design completeness are different questions.**
6. **A resource collision is not automatically a dependency.**
7. **Deterministic code owns IDs, dependency bookkeeping, validation, and readiness.**
8. **LLMs should be reserved for semantic judgment/decomposition/implementation where they add value.**
9. **Infrastructure must quickly feed real game implementation.**
10. **Do not fully decompose distant features just to make the graph look complete.**

## Completion Criteria — Satisfied

Milestone 1 satisfies its intended completion criteria:

- work files are parseable;
- stable persistent IDs exist;
- `feature`, `artifact`, and `implementation` are supported;
- graph validation catches malformed/unsafe graph state;
- parent and dependency graphs are connected/acyclic as required;
- readiness is deterministic;
- feature nodes are not returned as executable work;
- `single_agent` execution scope is enforced by readiness;
- the initial graph was reconciled against current GDD/repository state rather than copied from old assignment output;
- seeded records preserve `reconciliation_key` traceability;
- reconciliation history is immutable and cannot directly rewrite `Tasks/*.yaml`;
- dependency/status changes cascade through deterministic computation;
- the graph distinguishes ordinary blocking from execution-decomposition and human-integration states;
- the real graph identifies a truthful executable frontier.

## Next

Milestone 1 is closed.

Continue with:

`Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md`

Before substantial Milestone 2 infrastructure, review the M1-complete architecture through:

`Pipeline/ArchitectureReview/README.md`

Then build the smallest Milestone 2 context/decomposition slice that directly advances real No Safe Circle gameplay.
