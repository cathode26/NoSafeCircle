# SlotEngine Gem Review

**Source reviewed:** `SlotEngine.zip`
**Review date:** August 29, 2026
**Purpose:** Extract Vincent Liguori's strongest reusable engineering patterns without treating four years of production debt as a coding standard.
**Repository role:** Supporting engineering evidence; not game-design canon and not authorization to copy proprietary source code.

---

## 1. Bottom line

This project does not weaken the conclusions from Space Invaders. It strengthens them.

The large legacy managers are not the clearest evidence of how Vincent wants to build No Safe Circle. The clearest evidence is found in the infrastructure and in the newer extractions around the legacy core:

- platform-specific behavior hidden behind interfaces;
- Addressables used as a real content-resolution system, not merely a prefab loader;
- content fallback and override rules expressed once and reused;
- pooled objects returned to a known semantic state;
- resource ownership made explicit for runtime-created assets;
- editor tools that turn manual handoff work into deterministic exports;
- large systems gradually split into catalogs, helpers, states, and presenters;
- deliberate WebGL-specific loading, memory, and performance decisions.

The right conclusion is not “copy SlotEngine.” It is:

> Preserve the hard-earned architectural ideas, then reimplement them as smaller, typed, testable services for No Safe Circle.

The strongest Addressables code to carry forward is the **platform-aware build tooling**. The runtime `AddressablesManager` contains valuable product knowledge, but it should be replaced rather than copied wholesale.

---

## 2. Review method

This was an archaeological review, not a defect count.

The archive contains 551 C# files. After excluding obvious generated or third-party-heavy files, the working sample contained approximately:

| Measure | Result |
|---|---:|
| Reviewed C# files | 532 |
| Reviewed lines | 87,345 |
| Median file size | 89 lines |
| Files at or below 80 lines | 244 |
| Files above 500 lines | 36 |
| Files declaring a namespace | 169 |
| `[SerializeField]` occurrences | 1,502 |
| Approximate camelCase field declarations | 2,553 |
| Approximate `_camelCase` field declarations | 16 |

The review deliberately prioritized:

1. reusable infrastructure;
2. recent responsibility extractions;
3. explicit lifecycle and cleanup behavior;
4. systems used from several call sites;
5. editor automation;
6. patterns repeated independently in different subsystems.

The review deliberately did **not** infer a preferred standard from giant classes merely because they contain the most lines.

---

## 3. The highest-value gems

## 3.1 Addressables as a content-resolution layer

### What the project gets right

`Runtime/AssetManagers/AddressablesManager.cs` supports substantially more than “load this address.” It encodes several useful content rules:

- load by typed address;
- try a preferred address, then a default address;
- try an ordered list of possible addresses;
- load the intersection of multiple labels;
- try mode-specific labels, then `main` labels;
- load platform-specific content, then generic content;
- merge prioritized label layers so higher-priority assets override lower-priority assets by filename;
- preload dependencies with progress reporting;
- keep game content and lobby content in different lifetime buckets.

Those capabilities are used in real systems:

- `AudioManager` prefers `Sounds_WebGL` or `Sounds_Desktop`, then falls back to `Sounds`.
- `TmpFontManager` prefers platform-specific font/material content, then generic content.
- `SymbolPoolManager` loads platform variants of symbol sprites and animated symbol prefabs.
- `WildAnimationCatalog` asks for mode-specific wild animations and falls back to `main`.
- `SlotManager` tries a platform HUD before the shared HUD.
- `LobbyGameStateManager` loads platform-classified lobby prefabs and icons.

This yields a valuable design principle:

> Gameplay systems ask for logical content. A content-resolution service decides which physical asset satisfies the request for the current game, mode, platform, and fallback policy.

That principle should become canonical.

### What should not be copied

The current manager combines too many concerns:

- Addressables initialization;
- existence checks;
- key and label resolution;
- fallback policy;
- priority merging;
- loading;
- profiling;
- ownership classification;
- release;
- browser cache eviction;
- global singleton access;
- Resources fallback.

It also has an overload-heavy coroutine/callback API, scattered string keys, initialization polling, no request cancellation, weak error results, and broad game/lobby cleanup rather than precise ownership.

A particularly important correction: normal asset unload should release the matching Addressables handles. `ClearDependencyCacheAsync` is for removing cached bundles and their dependencies; it should not be coupled automatically to every game unload. Cache eviction needs its own explicit maintenance or content-version policy.

### Decision

**Adopt the content-resolution model. Replace the runtime implementation.**

---
