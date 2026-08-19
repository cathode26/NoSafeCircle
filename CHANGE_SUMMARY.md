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
