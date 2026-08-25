---
artifact_id: "ART-WEBGL-DESKTOP-001"
artifact_type: "platform-publication-target"
status: "approved"
authority: "human"
approved_by: "Vincent Liguori"
approved_date: "2026-08-25"
canonical_relationship: "additive_to_gdd"
---

# Desktop WebGL Publishing Target

## Purpose

No Safe Circle must be publishable as a Unity WebGL build intended for play in a desktop web browser.

This is an additional human-approved publication target. It does **not** replace the existing canonical GDD requirement for a Windows Standalone build. The two targets coexist unless the GDD is explicitly revised later.

## Approved Decisions

- A desktop-browser Unity WebGL build is a required publication target for the finished capstone.
- The WebGL target is for desktop-browser play. Mobile, tablet, and touch controls are not required by this artifact.
- Existing mouse-directed gameplay and the project's Unity Input System/Input Actions architecture must remain usable in the WebGL build; this artifact does not authorize a separate WebGL-only control scheme.
- The WebGL build must include the current human-approved canonical gameplay scene, or a later human-approved replacement canonical gameplay scene.
- Authoritative WebGL validation must run the built game through a web server in a desktop browser; opening build files directly from `file://` is not sufficient publication validation.
- Runtime gameplay intended for publication must not depend solely on Windows-only APIs, native Windows-only plugins, or assumptions that require unrestricted local filesystem access. If such a dependency is introduced, affected work must provide a WebGL-compatible path or explicitly escalate the incompatibility for human review.
- The final published WebGL build must not require development-time AI services, API keys, or agent infrastructure at runtime.

## Minimum Publication Validation

Before the WebGL publication target can be considered satisfied, a human-reviewed validation pass must establish at minimum that:

1. Unity can produce a WebGL build containing the canonical gameplay scene.
2. The build loads successfully when served over HTTP(S) in a desktop browser without a fatal startup error.
3. Core mouse/pointer input is accepted in the browser and the game can enter normal gameplay.
4. The delivered build does not depend on development-time AI services or credentials.
5. Any WebGL-specific errors that block normal gameplay are resolved or explicitly accepted by the human project owner before publication.

This artifact does not claim those conditions are satisfied today. It defines the publication target and the evidence that future build/deployment work must eventually provide.

## Explicitly Undecided / Out of Scope

This artifact intentionally does **not** choose or authorize:

- a hosting provider, storefront, domain, or CDN;
- a specific supported-browser matrix beyond the desktop-browser target;
- mobile/tablet/touch support;
- exact browser-window resolution, aspect ratio, fullscreen behavior, or responsive-page layout;
- WebGL template branding or page chrome;
- compression, caching, CDN headers, or server configuration beyond the need to serve the build correctly;
- memory-budget, loading-time, or frame-rate targets beyond the requirement that the published build be usable;
- analytics, telemetry, cloud saves, accounts, or persistent online services;
- CI/CD or automatic deployment;
- replacement or removal of the existing Windows Standalone delivery requirement.

Those decisions require separate human approval if they become necessary.

## Downstream Use

Treat this artifact as approved subordinate project design state when work touches:

- Unity build configuration;
- platform-dependent APIs or plugins;
- input behavior that may differ in a browser;
- local filesystem or persistence assumptions;
- networking required solely for hosting/runtime delivery;
- shaders, audio, memory, loading, or other behavior with WebGL compatibility implications;
- release packaging, browser validation, or deployment.

A future implementation task may be created near the actionable frontier to configure, build, validate, and publish the WebGL target. This artifact does not itself create TaskGraph work, grant readiness, authorize execution, or prove delivery/conformance.

## Authority Boundary

This artifact records a direct human product decision. It may add the WebGL publication target because the current GDD does not exclude additional delivery targets. It may not silently rewrite gameplay canon, remove the Windows Standalone requirement, invent hosting/product requirements, or grant implementation authority outside approved task contracts.

Any future conflict between this artifact and an explicit GDD revision is resolved in favor of the current human-approved canonical GDD unless this artifact is also revised or superseded.
