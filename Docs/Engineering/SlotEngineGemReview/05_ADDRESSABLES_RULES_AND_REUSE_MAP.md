## 6. Addressables rules that should become standards

1. Addressables operations remain asynchronous. Never use `WaitForCompletion` in game code targeting WebGL.
2. Mirror every explicit load with a release of the matching handle or lease.
3. Keep the operation handle for as long as the result is in use.
4. Releasing runtime ownership and deleting browser/download cache are separate operations.
5. Do not call `ClearDependencyCacheAsync` during ordinary level unload.
6. Prefer typed `AssetReference` fields for inspector-assigned singular assets.
7. Use labels or pre-resolved locations for logical sets of assets.
8. Centralize label names and content IDs; do not scatter string literals through gameplay systems.
9. Addressables groups reflect load/unload lifetime and dependency behavior—not merely the folder tree.
10. A pool cannot outlive the Addressables handle for its prefab and dependencies.
11. Platform-specific content is selected by the content/build layer, not by gameplay callers.
12. Missing platform classification is a build validation failure.
13. Run Addressables Analyze rules and a custom validation suite before release builds.
14. Profile bundle count, duplicated dependencies, peak memory, and load/unload behavior in an actual WebGL player.
15. Boot-critical content can remain direct/local when independent unloading provides no value.

---

## 7. What should be ignored as legacy sediment

The following patterns occur in the archive but should not be adopted:

- multi-thousand-line managers;
- global singletons as the default dependency mechanism;
- public mutable fields for runtime state;
- global namespace code;
- dozens of signal registrations in one class;
- Resources and Addressables paths maintained in parallel throughout production code;
- stringly typed paths and labels constructed at every call site;
- existence-check operations immediately followed by a load lookup for the same key;
- coroutine callback overload matrices;
- initialization exposed as a bool that callers poll every frame;
- `async void Start` without a contained failure boundary;
- cache eviction on every content unload;
- reflection into private TextMeshPro internals as a general solution;
- manual `GC.Collect` as ordinary gameplay memory management;
- forced `Resources.UnloadUnusedAssets` loops without profiling evidence;
- `DestroyImmediate` in normal runtime flow;
- copied comments that explain textbook design-pattern terminology rather than project intent;
- giant helper classes that are only smaller managers under another name.

These are not moral failures. They are the exact sort of compromises a long-lived production engine accumulates. The point of this review is to prevent them from becoming deliberate design choices in a new game.

---

## 8. Exact reuse map

| Source | Decision | No Safe Circle treatment |
|---|---|---|
| `PlatformAddressableGroupSchema.cs` | Port | Namespace, validate, test |
| `XpressPlatformBuildScript.cs` | Port design; likely close source port | Update for Addressables 2.7.x and add automated validation |
| `SortFirstAddressableGroupSchema.cs` | Do not port yet | Only add with an implemented sorting consumer |
| `AddressablesManager.cs` | Do not copy | Rebuild as resolver + loader + scope + lease services |
| `AudioSourcePool.cs` | Reimplement | Preserve checkout set, reset, leak diagnostics, metrics |
| `SymbolPoolManager.cs` | Mine reset requirements only | Typed pools; split static/animated/particle concerns |
| `SymbolParticlePoolManager.cs` | Reimplement concept | Keep template handoff/binding; simplify ownership and lookup |
| `IAudioPlayer.cs` | Reuse boundary concept | Smaller interface(s), platform adapter selected at composition root |
| `PromoContentCache` and `IPromoCachedAsset` | Reuse ownership concept | Disposable runtime assets and value-object cache keys |
| `WildAnimationCatalog.cs` | Reuse catalog concept | Inject content service; no singleton or Resources branch |
| `ArtHandoffExtractor.cs` | Rebuild in modules | Deterministic agent/project context exporter |
| `ArtHandoffArtistDeliveryExporter.cs` | Reuse operational pattern | Rebuild output, deterministic copy, validation, `finally` cleanup |
| `ScreenshotAccumulator.cs` | Reuse frame-budget concept | Profile-first staged work; avoid copying implementation blindly |
| Runtime/Editor/Demo asmdefs | Reuse separation concept | Add Core/Gameplay/Content/UI/Test boundaries as needed |

---
