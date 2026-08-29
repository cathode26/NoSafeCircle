# External Reference Source Routing

This directory defines the optional, read-only source-project boundary used by No Safe Circle coding agents.

## Files

- `reference_sources.json` records expected source IDs, folder names, container paths, authority, and permission constraints.
- `../../Docs/Engineering/REFERENCE_PROJECTS.md` is the human-readable operating policy.
- `../../compose.reference.yaml` is the opt-in Docker Compose overlay.

## Runtime model

```text
operator-approved host folder
        ↓
optional compose.reference.yaml overlay
        ↓
read-only /reference mount
        ↓
targeted agent inspection
        ↓
clean No Safe Circle implementation
```

Reference access is disabled in the normal Compose configuration. The overlay must be explicitly included for a provider invocation that needs it.

The mounted projects are never:

- GDD canon;
- TaskGraph authority;
- repository completion evidence;
- imported Unity dependencies;
- permission to copy or publish source.

## Expected host and container roots

```text
Host default:      ../ReferenceProjects relative to each checkout
Canonical Windows: C:\UnityProjects\NoSafeCircleAgentCrew\ReferenceProjects
Container:         /reference
```

The overlay uses `bind.create_host_path: false`. A missing host directory therefore fails closed rather than silently creating an empty reference location.

## Orchestrator rule

A task should receive reference access only when its planned approach names a concrete reason, such as reviewing Addressables group filtering or a pool reset contract. Broad exploratory access is not the default.

The task instruction should identify:

- the reference source ID;
- the engineering question;
- the expected relevant paths when known;
- whether source-level reuse is authorized or clean reimplementation is required.

The provider should report exact observed paths and commit/snapshot identity in its review notes. It should not dump reference source into task artifacts.

## Current integration boundary

Interactive, architecture-review, and ExecutionCrew Claude/Codex services are declared in `compose.reference.yaml`.

TaskReviewAgent and decomposition launchers do not automatically add this overlay. Reference-enabled automation must be deliberately routed and reviewed rather than becoming ambient access for every agent run.
