# Context 2 — RAG + Project Scanner + Progressive Decomposer

## Goal

Reduce Claude token usage by making local tools answer factual questions, retrieve only relevant GDD evidence, and let Claude progressively decompose only the bounded work that is close to execution.

This milestone also introduces the Artifact Authority Gate so missing design is never silently invented.

Prerequisite: Context 1's persistent work graph and `taskctl` exist.

## Architecture

```text
Feature / Work Item
        │
        ├── source requirement IDs → Assignment 4 RAG → relevant GDD chunks
        │
        ├── approved artifact dependencies → authorized design extensions
        │
        └── scope/current state → local project scanner → repository evidence
                                      ↓
                                 context pack
                                      ↓
                                   Claude
                                      ↓
                           Progressive Decomposer
                                      ↓
                       Enough information to execute?
                              /              \
                            yes               no
                             ↓                 ↓
                   Concrete child work    Artifact Proposal
                                               ↓
                                      Artifact Authority Gate
                                               ↓
                                           authorized?
                                           /        \
                                         yes         no
                                          ↓           ↓
                                  Artifact Generator   Re-plan /
                                          ↓           Human Review
                                      Artifact GER
                                          ↓
                                  Approved Artifact
                                          ↓
                                  Back to Decomposer
```

## Assignment 4 RAG Role

RAG answers:

> What does the GDD say?

It should not answer whether implementation exists.

Reuse/wrap the Assignment 4 retriever rather than duplicating it when practical.

Possible interface:

```text
python -m gddctl search "mana regeneration"
python -m gddctl requirement GDD-MANA-001
```

## Requirement Records

Work items should eventually reference stable requirement IDs such as:

```yaml
source_requirements:
  - GDD-MANA-001
  - GDD-SPELL-001
```

A requirement record should retain:

- ID
- source location/chunk
- canonical description/text
- optional tags
- GDD version/hash

## Approved Artifact Retrieval

The context builder must also be able to retrieve approved design artifacts that are dependencies or descendants of the current work.

Approved artifacts are subordinate project design state.

They may add authorized detail but may not override contradictory GDD canon.

Unapproved drafts must never be included as trusted context.

## Local Unity/Code Scanner

Start deterministic and simple:

- filesystem enumeration
- ripgrep
- Unity YAML parsing
- `.meta` GUID mapping
- Roslyn later if useful

Questions it should eventually answer include:

- whether a class exists
- where a type is referenced
- whether Grid/Tilemap/NavMesh components exist
- whether a Camera is orthographic
- which scene/prefab references a MonoBehaviour GUID
- whether something is only builder capability versus serialized state
- whether tests exist for a feature
- whether a candidate "complete" task is actually integrated on `main`

## Important State Distinction

Preserve the Assignment 5 lesson:

```text
DEFINED
CREATED_BY_BUILDER
SERIALIZED_IN_SCENE
ATTACHED_TO_PREFAB
```

A builder method that can create something is not proof it currently exists.

## Project State Cache

Store output such as:

```text
.cache/project_state.json
```

Incremental scanning can come later.

## Context Builder

Create something like:

```text
python -m taskctl context NSC-014
```

Output should contain only:

- work contract
- work kind
- parent/feature context
- acceptance criteria
- out-of-scope boundaries
- relevant GDD chunks
- relevant approved artifact content
- targeted current-project findings
- relevant file paths

Do not send the whole GDD/repo.

## Progressive Decomposer

Claude is used for semantic decomposition, not dependency bookkeeping.

Given one bounded feature/work item plus its relevant canon, approved artifacts, and current project evidence, the Decomposer determines whether the work is concrete enough to execute.

If enough information exists, it produces bounded child work.

If information is missing, it identifies the smallest missing design/content artifact needed to continue decomposition.

It must not generate that missing artifact during the same decision.

Detecting missing design and creating missing design are separate actions.

### Decomposer Output

Conceptually:

```json
{
  "work_id": "NSC-130",
  "result": "needs_artifact",
  "reason": "Room 3 cannot be implemented because encounter structure is undefined.",
  "proposed_artifact": {
    "title": "Room 3 Encounter Specification",
    "purpose": "Define enough authorized encounter detail to create implementation tasks.",
    "source_requirements": [
      "GDD-WORLD-001",
      "GDD-ENCOUNTER-001"
    ]
  }
}
```

or:

```json
{
  "work_id": "NSC-130",
  "result": "decomposed",
  "children": [
    {
      "kind": "implementation",
      "title": "Build Room 3 Layout"
    },
    {
      "kind": "implementation",
      "title": "Configure Room 3 Enemies"
    }
  ]
}
```

The final schema should be designed only when implementing this milestone.

## Artifact Authority Gate

Before a proposed artifact may be generated, an evaluator determines whether creating that new information is justified.

The gate answers:

1. Is this artifact actually necessary to progress the parent work?
2. What existing GDD requirements or approved artifacts authorize its creation?
3. What design decisions may the artifact make?
4. What must it not invent, replace, or contradict?

Possible outcomes:

```text
AUTHORIZED
REJECTED
NEEDS_HUMAN_REVIEW
```

A rejected artifact proposal returns to decomposition or human review.

The Authority Gate authorizes generation.

It does not judge the quality of the generated artifact.

## Artifact Generation

Only authorized artifact proposals may be generated.

Generation should use:

- relevant GDD canon from RAG
- parent work context
- relevant approved artifacts
- explicit authority boundaries
- explicit out-of-scope design areas

Artifact generation should be bounded to the smallest missing design needed to continue decomposition.

Do not create unnecessary lore, mechanics, factions, enemies, spells, or other design simply to make an artifact feel complete.

## Artifact GER

Generated artifacts must pass appropriate post-generation evaluation before promotion to trusted project input.

Possible evaluator profiles:

```text
Canon / Design Evaluator
Completeness Evaluator
Style Evaluator
Formatting / Schema Evaluator
```

Not every artifact needs every evaluator.

### Canon / Design Evaluator

Checks whether the artifact:

- stays within its granted authority
- satisfies relevant GDD constraints
- avoids unsupported design expansion
- avoids contradiction with approved canon

### Completeness Evaluator

Checks whether the artifact contains enough concrete information for its intended downstream purpose.

For decomposition artifacts, the key question is:

> Does this artifact now provide enough approved detail to produce bounded child work?

### Style Evaluator — Assignment 7

Assignment 7 supplies the scored style-checking specialization for style-sensitive generated content:

```text
Generator
  ↓
Style Evaluator
  ↓
SCORE + REASON
  ↓
Refiner
  ↓
Style Evaluator
```

This evaluator may check:

- tone/vibe
- No Safe Circle-specific vocabulary/canon
- formatting conventions
- length limits
- other game-specific style constraints

The Style Evaluator does not decide whether the artifact was authorized to exist.

Authority comes first.

## Artifact Promotion

After required evaluators pass, the artifact becomes approved project input.

Conceptually:

```text
Design/
  Approved/
    Encounters/
      Room3.md
```

or another versioned project location.

The final directory/versioning strategy should be chosen during implementation.

Approved artifact metadata should eventually retain:

- artifact ID
- parent work ID
- source requirement IDs
- authority decision
- evaluator results
- approval timestamp/version
- file/hash

Do not over-design this until the first artifact flow works.

## Re-Decomposition

After artifact approval:

1. add/mark the artifact work as complete;
2. rebuild the parent context pack;
3. re-run the Progressive Decomposer;
4. create concrete child work;
5. validate the updated graph deterministically.

This is the core progressive-decomposition loop.

## Token-Saving Goal

Replace repeated full-project Claude crawls with:

1. deterministic graph state;
2. targeted RAG;
3. targeted project scanning;
4. one bounded decomposition call;
5. artifact generation only when missing design actually blocks progress.

The system should not design Room 5 while still building Room 1 unless Room 5 design is truly needed by current work.

## Completion Criteria

1. Assignment 4 RAG can be queried locally.
2. Project scanner produces deterministic state.
3. Context builder combines work + canon + approved artifact + project evidence.
4. Progressive Decomposer can distinguish `decomposed` from `needs_artifact`.
5. Missing design produces an artifact proposal rather than silent invention.
6. Artifact Authority Gate can authorize/reject/escalate proposals.
7. Authorized artifacts can be generated and evaluated through GER.
8. Approved artifacts can re-enter context as trusted design input.
9. Re-running the Decomposer after artifact approval can produce concrete child work.
10. Normal decomposition no longer requires a full GDD/repository crawl.

## Next

Continue with `03_SUPERVISOR_GIT_GITHUB_CONTEXT.md`.

By the end of this milestone, the persistent graph should be able to expand safely near the actionable frontier without allowing implementation agents to invent missing game design.
