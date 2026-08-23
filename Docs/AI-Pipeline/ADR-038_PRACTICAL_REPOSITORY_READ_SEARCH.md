# ADR-038 — Practical Repository Read/Search

## Status

Accepted — 2026-08-23.

## Context

No Safe Circle is developed in a trusted, single-user local environment. The developer, checked-out repository, Docker environment, and Claude account are trusted. The immediate priority is useful repository-aware agents that can help build the game, not a hostile multi-tenant filesystem-security platform.

## Decision

Stage 4B.2 accepts Claude Code's native `Read`, `Glob`, and `Grep` tools for inspecting the actual No Safe Circle working tree. `/workspace` is the intended repository working area in Docker.

`repository_read` exposes `Read`. `repository_search` exposes `Glob` and `Grep`. Requests with both expose all three. Empty-capability requests retain the fresh temporary workspace and no-tool behavior from Stage 4B.

Repository-relative `context_paths` and the generated instruction to inspect only No Safe Circle files under `/workspace` are task guidance, not hardened sandbox enforcement. The project explicitly accepts the limited risk that native read/search tools may technically read elsewhere in the container. Claude is instructed not to inspect `/home`, credentials, environment secrets, or unrelated filesystem locations.

Repository writing remains unsupported. Shell and approved command execution remain unsupported. Web access remains unsupported. `Bash`, `Edit`, `Write`, `NotebookEdit`, `WebSearch`, and `WebFetch` remain explicitly disabled.

## Consequences

Agents can inspect current code, documentation, Tasks, tests, Unity assets, pipeline files, and uncommitted development changes without repository copying, snapshots, brokers, MCP, or custom search infrastructure.

Stronger containment may be revisited if this pipeline is later used in an untrusted, shared, or production environment. For the current trusted project, work should proceed toward useful Execution Crew and game-development capability rather than further repository-security research.
