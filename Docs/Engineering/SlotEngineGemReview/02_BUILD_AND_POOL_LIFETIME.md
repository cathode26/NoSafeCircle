## 3.2 Platform-aware Addressables builds

### Files

- `Editor/Addressables/PlatformAddressableGroupSchema.cs`
- `Editor/Addressables/XpressPlatformBuildScript.cs`

### Why this is one of the strongest reusable pieces

The custom group schema classifies each group as:

- `Shared`
- `WebGL`
- `Desktop`

The custom packed build script then:

- accepts WebGL and supported desktop build targets;
- includes shared groups in both;
- includes only the matching platform-specific groups;
- still respects the user's manual `Include In Build` checkbox;
- treats the default local group as shared;
- excludes unclassified groups instead of silently shipping them everywhere;
- logs the final decision for every bundled group;
- stores original settings before the build;
- restores those settings in `finally`, including when the build fails;
- marks restored schemas dirty and saves them;
- repaints the Addressables UI after restoration.

This is defensive editor tooling. It protects the build from both configuration drift and failed-build residue.

### Decision

**Port this design first.** The source is close to reusable, but it still needs:

- a No Safe Circle namespace;
- validation against Unity 6000.1 and Addressables 2.7.x;
- an EditMode test or editor integration test for each supported build target;
- a validation command that fails if any bundled group lacks the platform schema;
- optional expansion beyond `Desktop` only when another target is actually required.

`SortFirstAddressableGroupSchema.cs` is a useful marker concept, but no sorting consumer exists in the supplied package. Do not carry an unused marker into the new project unless its behavior is implemented and tested.

---

## 3.3 Asset lifetime before pool lifetime

`SlotManager.UnLoadLevelAsync()` returns active symbols, destroys the symbol pools, destroys instantiated content, and only then releases Addressables content.

That ordering captures an essential rule:

> A loaded prefab and its dependencies must remain owned for as long as any live or pooled instance can still use them.

For No Safe Circle, a pooled Addressable prefab should therefore have one owner that controls both:

1. the Addressables load handle; and
2. the pool created from the loaded prefab.

Disposing that owner should:

1. reject new checkouts;
2. require or force return of active instances according to policy;
3. clear inactive instances;
4. release the Addressables handle last.

### Decision

**Adopt as a hard lifecycle invariant.**

---

## 3.4 Pool invariants and semantic reset

### Cleanest reference

`Runtime/AudioManagement/Desktop/AudioSourcePool.cs`

It demonstrates several good pool behaviors:

- an available stack;
- a checked-out set;
- lazy expansion;
- warning on double checkout;
- warning on returning an object that was not checked out;
- resetting `AudioSource` state before reuse;
- pausing only active sources;
- Editor visibility into checked-out clip names;
- leak reporting when the pool is destroyed with active objects.

### Deeper lifecycle knowledge

`SymbolPoolManager` and `SymbolParticlePoolManager` are too large to copy, but they contain hard-earned reset knowledge:

- Spine tracks and state must be cleared;
- transforms, parentage, scale, masks, sorting, materials, and helper state must be restored;
- particle systems must stop and clear;
- pooled particles can be extracted from art templates and centrally rebound by symbol, mode, and animation track;
- a returned object must not merely become inactive—it must become semantically equivalent to a clean instance.

This yields the standard:

> Every pooled type defines its complete checkout and return contract. “SetActive(false)” is not a reset strategy.

### Decision

**Adopt the invariants, observability, and reset discipline. Reimplement on a typed pool abstraction.**

The new pool should provide:

- initial capacity;
- maximum capacity and overflow policy;
- collection checks in development/editor builds;
- O(1) ownership lookup;
- `OnTakenFromPool` / `OnReturnedToPool` hooks;
- active, inactive, peak, expansion, rejection, and leak metrics;
- an Addressables-aware prefab-pool owner;
- tests for double return, foreign return, capacity, reset, and disposal with active instances.

---
