# No Safe Circle External Reference Projects

**Status:** Active engineering operating policy
**Applies to:** Local source projects mounted for agent inspection
**Authority:** Reference evidence only; never GDD canon, TaskGraph authority, repository truth, completion evidence, or permission to publish source

## 1. Purpose

No Safe Circle agents may sometimes benefit from inspecting earlier projects for concrete implementation experience, especially:

- Addressables organization and platform-specific build tooling;
- pooling, checkout/return validation, and complete reset behavior;
- platform adapters;
- editor automation;
- assembly-definition boundaries;
- runtime-created asset ownership;
- established naming and decomposition preferences.

These projects are supporting evidence. They may help an agent understand a design pattern, but they do not establish what No Safe Circle must build.

## 2. Canonical host layout

Keep reference projects outside the No Safe Circle repository and outside every claimed task checkout:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\
├── NoSafeCircle\
├── NSC-###\
└── ReferenceProjects\
    ├── SpaceInvaders\
    └── SlotEngine-Sanitized\
```

Use these exact folder names unless the manifest is deliberately revised:

```text
SpaceInvaders
SlotEngine-Sanitized
```

Do not place a reference project inside `Assets/`, `Packages/`, `Pipeline/`, or a task checkout. No Safe Circle must never compile against, import from, or depend on a reference project.

## 3. Sanitization and permission boundary

### SpaceInvaders

SpaceInvaders may be exposed when the human operator confirms that the source is theirs to provide to the selected model provider.

### SlotEngine

Use `SlotEngine-Sanitized` by default. Include only files the human operator is authorized to provide to the external model services used by the pipeline.

A read-only mount prevents filesystem modification. It does **not** prevent source text from being transmitted to Claude, Codex, OpenAI, Anthropic, or another configured provider as model context.

Do not mount the full SlotEngine repository merely because it is locally available. Authorization to inspect company work locally is not automatically authorization to transmit or publish it.

## 4. What to include

Prefer a deliberately reduced source tree containing only useful, approved material:

```text
Assets/
Packages/manifest.json
Packages/packages-lock.json
ProjectSettings/
relevant *.asmdef and *.asmref files
relevant tests
approved engineering documentation
```

Exclude generated, cached, personal, secret-bearing, and irrelevant material:

```text
Library/
Temp/
Logs/
obj/
Build/
Builds/
UserSettings/
.vs/
.idea/
*.csproj
*.sln
credentials
API keys
private certificates
company deployment configuration
unapproved art, audio, data, and third-party packages
```

A smaller reference tree improves search quality and reduces accidental disclosure.

## 5. Access is opt-in

Normal No Safe Circle containers do not receive `/reference` access merely because the host folders exist.

Use the optional Compose overlay:

```text
compose.reference.yaml
```

The overlay mounts the operator-managed root as:

```text
host:      C:\UnityProjects\NoSafeCircleAgentCrew\ReferenceProjects
container: /reference
mode:      read-only
```

It enables access only for the interactive, architecture-review, and ExecutionCrew provider services listed in that overlay. Decomposition and supervisor services remain unmounted unless a later reviewed change explicitly adds them.

Example interactive invocation from a No Safe Circle checkout:

```powershell
$env:NSC_REFERENCE_PROJECTS_ROOT = "C:\UnityProjects\NoSafeCircleAgentCrew\ReferenceProjects"; docker compose -f compose.yaml -f compose.reference.yaml run --rm claude
```

Example reference-enabled ExecutionCrew invocation:

```powershell
$env:NSC_REFERENCE_PROJECTS_ROOT = "C:\UnityProjects\NoSafeCircleAgentCrew\ReferenceProjects"; docker compose -f compose.yaml -f compose.reference.yaml -p nosafecircle run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py --task-id NSC-### --provider claude --implementation-path <tracked-production-path> --test-path <tracked-test-path> --host-output-root "C:\UnityProjects\NoSafeCircleAgentCrew\NSC-###\Pipeline\ExecutionCrew\outputs"
```

The ordinary `docker compose ...` command without `-f compose.reference.yaml` remains reference-free.

## 6. Container paths

When present, the expected paths are:

```text
/reference/SpaceInvaders
/reference/SlotEngine-Sanitized
```

The source registry is:

```text
Pipeline/ReferenceSources/reference_sources.json
```

The registry describes expected paths and policy. It does not prove that a host directory exists, that its contents are current, or that permission has been granted.

## 7. Agent-use rules

An agent with reference access must:

1. Read this policy and `Pipeline/ReferenceSources/reference_sources.json` first.
2. Treat the selected task contract, approved GDD, current No Safe Circle checkout, and approved platform documents as the only requirement authorities.
3. Inspect reference code only for a named engineering question.
4. Prefer targeted file/path searches over broad ingestion of the entire project.
5. Record the exact reference project, file path, and source commit SHA when the project is a Git checkout. When no Git history is present, record a deterministic source-tree fingerprint or the human-provided snapshot identifier.
6. Distinguish observed source behavior from a proposed No Safe Circle design.
7. Reimplement the useful idea cleanly unless the human has explicitly confirmed source-level reuse rights.
8. Remove company names, proprietary labels, business-specific paths, APIs, and content assumptions from any clean implementation.
9. Never edit, format, delete, rename, upgrade, or generate files inside `/reference`.
10. Stop and report the issue if the needed path is missing, unexpectedly writable, contains credentials, or appears outside the approved source list.

An agent must not:

- claim a requirement exists because SlotEngine or SpaceInvaders implemented it;
- cite reference code as proof that a No Safe Circle task is complete;
- copy a manager wholesale into No Safe Circle;
- add a compile-time or runtime dependency on a reference project;
- publish proprietary source in a patch, issue, prompt artifact, test fixture, log, or documentation excerpt;
- silently scan all reference content when only one pattern is relevant.

## 8. Source priority

When sources disagree, use this order:

1. Human-approved No Safe Circle GDD and approved design artifacts.
2. The active task contract and current TaskGraph authority.
3. Current No Safe Circle repository state and package/platform truth.
4. No Safe Circle engineering and testing policies.
5. External reference-project observations.

Reference observations cannot override any higher source.

## 9. Pooling and Addressables reuse rule

For SlotEngine and SpaceInvaders, preserve requirements and lessons rather than accidental implementation shape.

Good reuse examples include:

- explicit Addressables handle ownership;
- platform/shared fallback intent;
- pool checkout tracking;
- complete reset contracts;
- leak diagnostics;
- platform-adapter boundaries;
- deterministic editor export behavior.

Bad reuse examples include:

- copying multi-purpose managers;
- retaining company-specific labels and paths;
- reproducing cache-clearing behavior without a No Safe Circle requirement;
- importing obsolete Unity APIs merely because an older project used them;
- treating production sediment as a preferred pattern.

## 10. Operator checklist

Before enabling the overlay:

- confirm the reference root is outside the repository;
- confirm each source folder is intentionally present;
- confirm SlotEngine content is sanitized and authorized for the configured provider;
- remove generated Unity directories;
- check for secrets and private deployment data;
- make sure the No Safe Circle checkout is clean;
- run the reference-enabled provider only for a task that benefits from it.

A missing reference source is not a reason to weaken task validation. The task should continue without it when the standards and current repository are sufficient, or stop with a clear reference-evidence blocker when the human explicitly required a comparison.
