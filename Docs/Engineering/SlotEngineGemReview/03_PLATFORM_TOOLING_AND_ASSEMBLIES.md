## 3.5 Platform differences behind narrow interfaces

`IAudioPlayer` allows `AudioManager` to select a WebGL or desktop implementation at one boundary. The platform-specific code does not leak into every gameplay caller.

The same idea appears in lobby audio and network request strategies.

The implementations have duplication and can be improved, but the boundary is correct:

> Conditional compilation belongs near the platform adapter, not throughout gameplay code.

### Decision

**Adopt.** For No Safe Circle, likely platform boundaries include:

- audio behavior if WebGL requires a distinct path;
- browser bridge or JavaScript interop;
- persistent storage;
- optional content-delivery policy;
- any capture/export feature not supported by WebGL.

---

## 3.6 Explicit ownership of runtime-created assets

The promotional-content subsystem contains a strong small pattern:

- `IPromoCachedAsset : IDisposable`
- `ImagePromoCachedAsset` owns the runtime-created `Texture2D` and `Sprite`.
- `PromoContentCache` owns cached entries and disposes them in one cleanup path.
- `PromoContentKey` provides case-insensitive value equality for URL and MIME type.

This is much better than allowing runtime-created Unity objects to float without a clear destroy owner.

### Decision

**Adopt the ownership pattern.** Use it for:

- Addressables leases/scopes;
- runtime textures and sprites;
- generated meshes or materials;
- temporary render targets;
- pooled prefab ownership;
- any downloaded or generated content.

A resource-owning type should be disposable or have another equally explicit lifetime boundary.

---

## 3.7 Deterministic editor handoff tools

### Files

- `Editor/ArtHandoff/ArtHandoffExtractor.cs`
- `Editor/ArtHandoff/ArtHandoffArtistDeliveryExporter.cs`

The extractor is too large, but its purpose and operational rules are excellent. It creates machine-readable context from selected game assets, walks dependencies, distinguishes game-owned/shared/package content, writes manifests, copies selected source references, and creates an AI/art handoff package.

The artist delivery exporter demonstrates clean operational behavior:

- validate required input first;
- rebuild output from scratch so stale files cannot survive;
- copy only the intended files;
- deterministic sorting;
- display progress;
- catch and surface errors;
- clear the progress bar in `finally`;
- reveal the completed package.

This is directly relevant to the AI-assisted game course:

> Do not repeatedly explain a project to an agent or collaborator by hand when a deterministic export can produce the required context.

### Decision

**Adopt the tooling philosophy and operational safeguards. Split the implementation into smaller services.**

A No Safe Circle context exporter should separate:

- selection and validation;
- dependency discovery;
- manifest model construction;
- serialization;
- file copying;
- editor UI/orchestration.

---

## 3.8 Frame-budgeted heavy work

`ScreenshotAccumulator` uses asynchronous GPU readback, queues encoding/writing work, and yields during expensive row processing after an explicit active-processing threshold.

The particular implementation can be improved, but the valuable idea is clear:

> Noninteractive heavy work should be staged and given an explicit frame budget rather than allowed to create an unbounded hitch.

### Decision

**Adopt the principle, not this exact screenshot implementation.** Use profiling markers and validate the behavior in the browser build.

---

## 3.9 Strategy, catalog, and helper extraction from large systems

Several smaller classes show the direction in which the mature codebase was moving:

- `WildAnimationCatalog` separates loading/lookup from animation consumers.
- `SymbolWinValueHelper` extracts one calculation concern.
- `WaysWinDisplayController` separates queued win presentation from the primary win manager.
- `FadeLifecycleController` owns one lifecycle response.
- `GameNameSpriteSelector` is a narrow data-to-view adapter with guard clauses.
- `IWinState` and concrete win states split behavioral modes from the main coordinator.
- `ISpinRequestor` and `ServerManagerSO` establish strategy boundaries for external services.

Not all of these files are perfect, but together they show the preferred repair strategy for a growing manager:

> Extract a named responsibility into a catalog, policy, state, presenter, calculator, adapter, or service. Do not merely create more regions inside the same manager.

### Decision

**Adopt.**

---

## 3.10 Assembly separation

The package contains separate Runtime, Editor, and Demo assembly definitions. That is an improvement over the older Space Invaders project and settles one previous question: package and compilation boundaries are part of Vincent's current engineering practice.

The single Runtime assembly is too broad for a new game, but one assembly per tiny feature would also be needless fragmentation.

### Decision

**Adopt a small number of meaningful boundaries:**

- `NoSafeCircle.Core`
- `NoSafeCircle.Gameplay`
- `NoSafeCircle.Content`
- `NoSafeCircle.UI`
- `NoSafeCircle.Editor`
- `NoSafeCircle.Tests.EditMode`
- `NoSafeCircle.Tests.PlayMode`

The exact split can remain smaller until dependency pressure justifies another boundary.

---
