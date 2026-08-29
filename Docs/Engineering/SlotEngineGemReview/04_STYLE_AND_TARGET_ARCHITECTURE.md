## 4. Style questions resolved by project two

## 4.1 Private fields

The evidence is overwhelming: use **camelCase without an underscore**.

Approximate field scan:

- camelCase: 2,553
- `_camelCase`: 16

The underscore appears in isolated singleton or subsystem code and is not the project-wide convention.

## 4.2 Constants

Use **PascalCase** for project constants.

Recent examples include:

- `MenuPath`
- `FinalDocumentRelativePath`
- `ArtistDeliveryFolderName`
- `DefaultFontLabel`
- `MuteValue`

Uppercase snake case appears mostly in older code, platform interop, or imported conventions.

## 4.3 `var`

Use explicit types by default. Permit `var` when the right-hand side makes the type immediate and repeating it would add noise, or for anonymous types.

This matches the dominant style while avoiding a pointless absolute ban.

## 4.4 Braces and indentation

- Allman braces.
- Four spaces.
- Braces may be omitted for one-line guard clauses only if the statement remains unmistakable and cannot conceal a second statement.

## 4.5 Serialized state

The intended modern standard is private fields with `[SerializeField]`. Public mutable Inspector fields in the legacy engine should not become precedent.

## 4.6 Guard clauses

Guard clauses are strongly supported by the cleaner small classes and tools. Invalid setup should fail early with a specific message rather than continue into a distant null-reference failure.

## 4.7 Namespaces

The archive is inconsistent, but inconsistency in a four-year package is not a reason to preserve the global namespace. New code should always use the `NoSafeCircle` root namespace, with feature-oriented child namespaces.

## 4.8 Async style

The archive mixes coroutines and `Task`. For Unity 6, the standard should be:

- `Awaitable`/`async` for new asynchronous Unity orchestration where it improves readability;
- `Task` for framework/network logic that is genuinely independent of a MonoBehaviour frame coroutine;
- coroutines for existing animation/timeline flows when converting them provides no benefit;
- cancellation passed into any operation that can outlive its caller;
- no `async void` except event/lifecycle entry points that catch and report their own exceptions;
- no public `isInitialized` polling loops.

---

## 5. The clean Addressables architecture for No Safe Circle

The SlotEngine behavior should be decomposed into five responsibilities.

```text
GameBootstrap
└── AddressablesInitialization

ContentResolver
├── address or typed-reference resolution
├── ordered fallbacks
├── platform preference
├── mode/theme preference
└── prioritized override merging

AddressableAssetService
├── typed load operations
├── explicit result/error handling
├── progress
├── cancellation
└── handle creation

AssetScope
├── Application scope
├── Scene/Level scope
├── UI scope
└── temporary operation scope

AddressablePrefabPool<T>
├── owns prefab handle
├── owns pool
├── resets instances
└── releases handle after pool disposal
```

### Proposed core types

The names may change, but the responsibilities should not be recombined into one manager.

- `IContentResolver`
- `ContentQuery`
- `ContentVariant`
- `IAddressableAssetService`
- `AssetLoadResult<T>`
- `AssetLease<T>` or `AddressableLease<T>`
- `AssetScope`
- `AddressablePrefabPool<T>`
- `IPlatformContentPolicy`
- `AddressablesProjectValidator`

### Query model

Gameplay code should not manually concatenate paths such as:

```text
GameName + "/" + ModeName + "/Sounds_WebGL"
```

Instead it should request a logical asset set, for example:

```text
Category: Audio
Game: NoSafeCircle
Mode: Main
Platform preference: WebGL, then Shared
Merge policy: Higher priority replaces lower priority by stable content ID
```

The resolver can translate that model to labels or locations. This preserves SlotEngine's fallback power while removing string construction from consumers.

### Ownership model

Every successful explicit load returns a lease or is registered with a scope. The owner is visible in code.

Examples:

- bootstrap configuration → application scope;
- current level enemies and effects → level scope;
- pause-menu content → UI scope;
- one temporary preview → local `using`/`try-finally` scope;
- pooled enemy prefab → prefab-pool owner.

No “release everything the manager thinks is game content” dictionary should be required.

### Failure model

A missing optional override is not the same as a failed required asset.

Results should distinguish at least:

- success;
- optional variant not found, fallback used;
- required content missing;
- cancelled;
- download/load failure;
- type mismatch or invalid configuration.

This is more useful than returning `null` and relying on a log message.

---
