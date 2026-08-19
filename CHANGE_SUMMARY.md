# Progressive Decomposition Pipeline Update

Prepared: 2026-08-18

This package contains proposed replacements for:

- `Docs/AI-Pipeline/START_HERE.md`
- `Docs/AI-Pipeline/CURRENT_STATE.md`
- `Docs/AI-Pipeline/00_MASTER_CONTEXT.md`
- `Docs/AI-Pipeline/DECISIONS.md`
- `Docs/AI-Pipeline/01_MILESTONE_TASK_GRAPH.md`
- `Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md`

## Architectural changes

1. Added progressive, just-in-time task decomposition.
2. Added three work kinds: `feature`, `artifact`, and `implementation`.
3. Kept Milestone 1 deterministic and LLM-free.
4. Moved the Progressive Decomposer into Milestone 2.
5. Added the Artifact Authority Gate before any AI-generated design/content.
6. Added approved artifacts as subordinate, trusted design state under the GDD.
7. Positioned Assignment 7 as a scored Style Evaluator inside Artifact GER.
8. Explicitly separated:
   - deciding that design is missing;
   - authorizing creation of new design;
   - generating it;
   - evaluating its quality;
   - using approved output to decompose implementation work.
9. Added ADR-021 through ADR-024.
10. Preserved Assignment 6 GER as the bounded repair mechanism for both implementation and generated artifacts.

## Important boundary

Milestone 1 does NOT implement Claude-powered decomposition.

Milestone 1 only establishes a truthful persistent work graph.

Milestone 2 introduces RAG/scanner context, progressive decomposition, artifact authority, and artifact generation/evaluation.


---


# Reconciliation Agent — Proposed Files

This package adds a new production-oriented bootstrap agent without modifying Assignment 5.

## Files

- `Pipeline/Reconciliation/reconciliation_agent.py`
- `Pipeline/Reconciliation/prompts/reconcile.md`
- `Pipeline/Reconciliation/README.md`

## Runtime outputs

The agent creates:

- `Pipeline/Reconciliation/outputs/reconciliation.json`
- `Pipeline/Reconciliation/outputs/RECONCILIATION.md`

## Design decisions implemented

- Claude is read-only (`Read,Glob,Grep`).
- Current GDD + current checkout are primary truth.
- Assignment 6 / Assignment 5 outputs are optional historical evidence only.
- The agent creates a coarse hierarchy, not a full backlog.
- `parent_key` and `depends_on` are separate.
- Dependencies cannot target feature nodes.
- Missing design becomes `needs_future_decomposition`; the agent does not invent design or propose artifacts.
- `complete` is conservative and evidence-backed.
- Python validates hierarchy, dependency cycles, evidence, statuses, and repository boundaries.
- Python renders the structured result into a human-reviewable Markdown reconciliation table.
- No `Tasks/*.yaml` are created yet; that happens only after human review.

## Run

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/reconciliation_agent.py
```


---


# Immutable Reconciliation Snapshot Update

## Why

The Reconciliation Agent is reusable, not a one-time bootstrap script.
Therefore its output must not become a mutable project database.

This update separates:

- design truth: GDD;
- implementation truth: current repository;
- operational work truth: `Tasks/*.yaml`;
- reconciliation evidence: immutable point-in-time snapshots.

## Code changes

`Pipeline/Reconciliation/reconciliation_agent.py`

- creates a unique append-only directory for every run;
- preserves raw and validated output per run;
- never overwrites an earlier snapshot;
- writes `PROPOSED_GRAPH_DELTA.json` and `.md`;
- does not mutate `Tasks/*.yaml`;
- emits bootstrap seed proposals before the task graph exists;
- emits `taskctl_diff_required` after a persistent task graph exists;
- updates only `outputs/LATEST.json` as a mutable convenience pointer;
- preserves a failed run directory for inspection.

## Output layout

```text
Pipeline/Reconciliation/outputs/
├── LATEST.json
└── runs/
    └── <timestamp>-<run-id>/
        ├── reconciliation.raw.json
        ├── reconciliation.json
        ├── RECONCILIATION.md
        ├── PROPOSED_GRAPH_DELTA.json
        └── PROPOSED_GRAPH_DELTA.md
```

## Architecture changes

- Added ADR-025: reconciliation results are immutable snapshots.
- Added ADR-026: reconciliation proposes graph deltas and never directly
  mutates the persistent graph.
- Added `reconciliation_key` traceability to the Milestone 1 task schema.
- Clarified that safe cascades such as dependency completion changing
  `taskctl ready` are deterministic graph behavior.
- Clarified that full reconciliation reruns must not cause uncontrolled LLM
  rewrites of task files.

## Still intentionally deferred

Milestone 1 still needs to implement the deterministic task graph, seeder, and
reconciliation diff/apply behavior. The Reconciliation Agent now emits the
correct boundary and proposed-delta artifacts but does not invent that
unfinished `taskctl` functionality inside the LLM agent.


---


# Multi-Model Reconciliation Verification Update

## Why

The successful Reconciliation Agent run proved that deterministic schema and
graph validation can produce a coherent immutable snapshot, but human review
found semantic issues that those validators cannot detect reliably: required
shared capabilities can be buried inside a consumer, reusable runtime systems
can remain only in notes, and required deliverables can be classified in a way
that risks disappearing from the persistent graph.

This update adds an independent, model-diverse verification layer before the
first persistent graph is seeded.

## New verification crew

Added:

- `Pipeline/Reconciliation/verification_crew.py`
- `Pipeline/Reconciliation/prompts/verification/coverage_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/structure_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/evidence_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/refiner.md`
- `Pipeline/Reconciliation/verification_smoke_test.py`

The crew runs four independent read-only audits:

1. GDD Coverage Auditor A
2. GDD Coverage Auditor B
3. Dependency and Decomposition Auditor
4. Repository Evidence Auditor

The two coverage auditors use different requested models when at least two
models are configured. Structure/evidence models are also varied when possible.

## Model diversity

Default model pool:

```text
opus,sonnet
```

Assignments are randomized for every verification run. The random seed, model
pool, and exact requested model for every role/pass are saved in
`MODEL_ASSIGNMENTS.json`.

Override with:

```text
RECONCILIATION_VERIFIER_MODELS=opus,sonnet
```

Full supported Claude model names may also be placed in the pool.

The main Reconciliation Agent's targeted dangling-dependency structural repair
now defaults to `opus` through `RECONCILIATION_REPAIR_MODEL`, instead of
silently reusing the generator's default `sonnet` model.

## No majority voting

Verifier findings are merged by union.

A material finding is not discarded because the other agents did not report
it. Every blocker/error must be resolved by evidence, preserved as unresolved,
or escalated for human review.

## Deterministic coverage guard

Each coverage auditor emits a structured GDD requirement map.

Python automatically creates an error finding whenever that auditor marks a
required requirement as `unrepresented` or `ambiguous`.

Two independent coverage agents are used because deterministic validation can
enforce an auditor's map but cannot guarantee that a single semantic auditor
noticed every requirement.

## Bounded refinement and second pass

If pass 1 has a blocker/error:

```text
immutable reconciliation snapshot
        ↓
independent multi-model pass 1
        ↓
union findings
        ↓
bounded Refiner
        ↓
new refined candidate
        ↓
independent multi-model pass 2
        ↓
human approval
```

The source reconciliation snapshot is never edited.

## Verification outputs

Verification has its own append-only output tree:

```text
Pipeline/Reconciliation/outputs/verifications/
└── <source-reconciliation-run-id>/
    └── <verification-run-id>/
        ├── MODEL_ASSIGNMENTS.json
        ├── pass1/
        ├── MERGED_FINDINGS_PASS1.json
        ├── refined_candidate.raw.json
        ├── refined_candidate.json
        ├── REFINED_RECONCILIATION.md
        ├── PROPOSED_REFINED_GRAPH_DELTA.json
        ├── PROPOSED_REFINED_GRAPH_DELTA.md
        ├── pass2/
        ├── MERGED_FINDINGS_PASS2.json
        ├── VERIFICATION_SUMMARY.json
        └── VERIFICATION.md
```

Refined-candidate files only exist when refinement is needed.

`LATEST_VERIFICATION.json` is a mutable convenience pointer; verification run
directories remain append-only.

## Safety boundaries

- All verification agents are read-only (`Read,Glob,Grep`).
- `AgentCrew/` and `DynamicContentPipeline/` remain explicitly forbidden.
- Verification never writes `Tasks/*.yaml`.
- `verified` means ready for human approval, not automatic graph seeding.
- Original reconciliation snapshots remain immutable.

## Naming cleanup

Renamed the planned deterministic task CLI from `taskctl` to `taskcontrol`
throughout the included pipeline code/docs to avoid collision with the existing
third-party `taskctl` project.

Planned commands are now:

```text
python -m taskcontrol list
python -m taskcontrol show <id>
python -m taskcontrol validate
python -m taskcontrol graph
python -m taskcontrol ready
```

## Architecture decision

Added ADR-027: reconciliation bootstrap requires independent multi-model
verification.

## Run command

After a successful reconciliation run:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/verification_crew.py
```

By default it verifies the snapshot referenced by
`Pipeline/Reconciliation/outputs/LATEST.json`.

## Validation performed on this export

- `reconciliation_agent.py` compiles with Python.
- `verification_crew.py` compiles with Python.
- deterministic model-assignment smoke check passed;
- two configured models produce different coverage-auditor assignments;
- deterministic required-coverage failure generation smoke check passed.

No live Claude verifier run was executed in the export environment. The first
real run should be performed in the user's existing Docker/Claude environment.


## Post-refiner validation recovery

- normalize verification input paths out of `sources.files_reviewed` without weakening repository evidence validation;
- clarify in the Refiner prompt that generated verification artifacts are inputs, not project evidence;
- add `recover_verification.py` so a preserved run can resume after the completed Refiner and run only the missing second-pass audit;
- preserve expensive pass-1 and Refiner outputs instead of repeating them.


---


# Change Summary — Execution Scope + Reconciliation Output Cleanup

## Why this change exists

The latest multi-model verification exposed two architecture problems that are separate from GDD coverage correctness:

1. a work item can be fully specified by the GDD and still be too large/cross-system for one implementation agent;
2. reconciliation and verification history had become hard to navigate because current candidate files and immutable audit files were mixed across parallel directory trees.

This change addresses both without mutating `Tasks/*.yaml`.

## 1. Add execution-scope semantics

Every new reconciliation work item now records:

- `execution_scope`
- `execution_reason`

Supported scopes:

- `single_agent`
- `needs_execution_decomposition`
- `human_integration_required`
- `not_applicable`
- `unknown`

`decomposition_state` still answers whether approved design is sufficiently concrete.

`execution_scope` now independently answers whether the known implementation work is a safe bounded one-agent handoff.

Legacy candidates that predate this field are normalized conservatively:

- feature/already-complete work → `not_applicable`
- open implementation/artifact work → `unknown`

This keeps old immutable snapshots usable without pretending their execution size was already reviewed.

## 2. Add an Execution Scope Auditor

The multi-model verification crew now runs five independent roles:

1. GDD Coverage Auditor A
2. GDD Coverage Auditor B
3. Dependency and Decomposition Auditor
4. Repository Evidence Auditor
5. Execution Scope Auditor

The new auditor specifically hunts for concrete-but-oversized tasks, hidden multi-system implementation bundles, human/editor integration work presented as autonomous work, and missing/incorrect execution-scope classifications.

Model assignment remains randomized and findings remain unioned rather than majority-voted.

## 3. Make `taskcontrol ready` execution-aware in the architecture

Milestone 1 documentation now requires autonomous-ready work to satisfy all of these:

- open;
- kind `artifact` or `implementation`;
- all dependencies complete;
- `execution_scope: single_agent`.

`needs_execution_decomposition`, `human_integration_required`, and `unknown` must not be handed to an implementation agent as ordinary ready work.

The Progressive Decomposer will therefore support two distinct future modes:

- design decomposition when approved design is missing/too coarse;
- execution decomposition when design is concrete but the implementation handoff is too broad.

Execution decomposition may split known implementation responsibilities but cannot invent new game design.

## 4. Add a simple current-output view

`Pipeline/Reconciliation/outputs/current/` is now the mutable human-facing place to look for the latest state:

```text
current/
├── STATUS.md
├── CURRENT.json
├── CANDIDATE.json
├── CANDIDATE.md
├── PROPOSED_GRAPH_DELTA.json
├── PROPOSED_GRAPH_DELTA.md
├── VERIFICATION_SUMMARY.json   # when available
└── VERIFICATION.md             # when available
```

`STATUS.md` explicitly says whether the candidate is unverified, needs human review, or completed automated verification. It also reports how many open executable records still have `execution_scope: unknown`.

These files are convenience copies only. They are never historical evidence.

## 5. Nest future verification history under its source reconciliation run

New verification runs now use:

```text
outputs/
└── runs/
    └── <reconciliation-run-id>/
        ├── reconciliation.json
        ├── RECONCILIATION.md
        └── verifications/
            └── <verification-run-id>/
                ├── pass1/
                ├── pass2/
                ├── refined_candidate.json
                ├── VERIFICATION_SUMMARY.json
                └── ...
```

This makes the provenance relationship obvious: the verification belongs to that reconciliation snapshot.

## 6. Add deterministic output maintenance utilities

No model calls are needed for these utilities.

Refresh the latest human-facing current view:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/refresh_current_output.py
```

Move legacy top-level `outputs/verifications/` runs under their source reconciliation run and then refresh `current/`:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/migrate_output_layout.py
```

The migration moves directories for organization only and records `LAYOUT_MIGRATION.json`; semantic reconciliation/verification artifacts are not rewritten.

Recovery code can resolve both the new nested layout and the old legacy verification layout.

## 7. Validation / smoke coverage

The deterministic smoke test now checks:

- model assignment includes the execution-scope role;
- coverage auditors remain model-diverse when possible;
- required coverage gaps still become material findings;
- verification bookkeeping paths are stripped from repository source tracking;
- legacy candidates receive conservative execution-scope defaults.

## No graph mutation

This change still does not create or modify `Tasks/*.yaml`.

The current verified/refined candidate remains a candidate until human review and approval.


---


# Package Manifest Evidence Boundary Fix

## Problem

The multi-model verification Refiner correctly used `Packages/manifest.json` as
current Unity configuration evidence while refining the world/tilemap work item,
but deterministic reconciliation validation did not permit that path.

The result was rejected after the expensive pass-1 auditors and Refiner had
already completed.

## Fix

- permit exactly `Packages/manifest.json` as current-project configuration evidence;
- do **not** permit the rest of `Packages/`;
- keep current exact paths and historical evidence paths in separate sets so the
  package manifest cannot accidentally be classified as historical evidence;
- update generator, evidence-auditor, and Refiner prompts to match the validator;
- add regression tests for the exact package boundary.

## Recovery

The failed verification run is reusable. After applying this patch and passing
the smoke test, resume:

docker compose run --rm claude python3 Pipeline/Reconciliation/recover_verification.py --source-run-id 20260819T072941Z-1a10b837 --verification-run-id 20260819T080021Z-460045d5

This reuses completed pass 1 and the completed Refiner output and proceeds to the
missing pass-2 verification.