# Context 2 — RAG Canon Service + Unity/Code Scanner + Context Builder

## Goal

Reduce Claude token usage by making local tools answer factual questions and retrieve only relevant GDD evidence.

Prerequisite: Context 1's persistent tasks and `taskctl` exist.

## Architecture

```text
Task Artifact
   │
   ├── source requirement IDs → Assignment 4 RAG → relevant GDD chunks
   │
   └── task scope → local project scanner → relevant code/state
                           ↓
                      context pack
                           ↓
                        Claude
```

## Assignment 4 RAG Role

RAG answers: **What does the GDD say?**

It should not answer whether implementation exists. Reuse/wrap the Assignment 4 retriever rather than duplicating it when practical.

Possible interface:

```text
python -m gddctl search "mana regeneration"
python -m gddctl requirement GDD-MANA-001
```

## Requirement Records

Tasks should eventually reference stable requirement IDs such as:

```yaml
source_requirements:
  - GDD-MANA-001
  - GDD-SPELL-001
```

A requirement record should retain ID, source location/chunk, canonical description/text, optional tags, and GDD version/hash.

## Local Unity/Code Scanner

Start deterministic and simple:

- filesystem enumeration
- ripgrep
- Unity YAML parsing
- `.meta` GUID mapping
- Roslyn later if useful

Questions it should eventually answer include whether a class exists, where a type is referenced, whether Grid/Tilemap/NavMesh components exist, whether a Camera is orthographic, which scene/prefab references a MonoBehaviour GUID, and whether something is only builder capability versus serialized state.

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

- task contract
- acceptance criteria
- out-of-scope boundaries
- relevant GDD chunks
- targeted current-project findings
- relevant file paths

Do not send the whole GDD/repo.

## Token-Saving Goal

Replace a long Claude crawl with one local context-package operation, then let Claude inspect only truly relevant files.

## Completion Criteria

1. Assignment 4 RAG can be queried locally.
2. Project scanner produces deterministic state.
3. Context builder combines task + canon + project evidence.
4. Normal tickets no longer require a full GDD/repository crawl.
5. Factual computation and semantic LLM judgment are clearly separated.

## Next

Continue with `03_SUPERVISOR_GIT_GITHUB_CONTEXT.md`.
