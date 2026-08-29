# No Safe Circle Engineering Standards

**Status:** Active working standard 0.3 — derived from Space Invaders and SlotEngine evidence
**Date:** August 29, 2026
**Applies to:** Runtime code, editor tools, tests, content-loading infrastructure, and agent-authored changes
**Supporting evidence:** [`SLOTENGINE_GEM_REVIEW.md`](./SLOTENGINE_GEM_REVIEW.md)

---

## 1. Purpose

This document is engineering operating guidance, not game-design canon.

These standards are intended to preserve Vincent Liguori's demonstrated strengths:

- small, understandable objects;
- explicit system boundaries;
- reusable infrastructure;
- intentional object and asset lifetime;
- data-driven content;
- WebGL-aware performance;
- editor tooling that removes repetitive setup;
- code that can be safely extended by people and coding agents.

They are not an attempt to make every file look identical or to impose arbitrary line-count theater. The goal is to make responsibility, ownership, and failure visible.

---

## 2. Core principles

### 2.1 One primary responsibility

Each component, service, or asset type has one primary reason to change.

A coordinator may sequence several collaborators, but it should not absorb their implementation.

When a class grows, extract a named responsibility such as:

- policy;
- resolver;
- catalog;
- state;
- presenter;
- calculator;
- validator;
- adapter;
- repository;
- pool;
- lifetime scope.

Do not use regions as a substitute for decomposition.

### 2.2 Composition first

Prefer composition and interfaces. Use inheritance only for a small, stable behavioral contract where substitutability is real.

Do not create inheritance solely to share fields or avoid a few duplicated lines.

### 2.3 Explicit ownership

Every object or resource with a nontrivial lifetime has an identifiable owner.

This includes:

- Addressables handles;
- pooled instances;
- runtime-created textures, sprites, materials, and meshes;
- event subscriptions;
- coroutines and asynchronous operations;
- temporary files and render textures;
- generated editor output.

Ownership must be visible in the API and cleanup path.

### 2.4 Data drives content

Content configuration belongs in ScriptableObjects, structured data, or purpose-built catalogs. Runtime behaviors consume data; they do not become content databases.

### 2.5 Automate repeated fragile work

Repeated manual scene, prefab, asset, build, validation, or handoff work should trigger consideration of an editor tool or validator.

---

## 3. Naming and formatting

### 3.1 Naming

| Element | Convention |
|---|---|
| Namespace | `PascalCase`, rooted at `NoSafeCircle` |
| Type | `PascalCase` |
| Method | `PascalCase` |
| Property | `PascalCase` |
| Event | `PascalCase` |
| Enum type/member | `PascalCase` |
| Constant | `PascalCase` |
| Private field | `camelCase`, no underscore prefix |
| Parameter | `camelCase` |
| Local variable | `camelCase` |
| Boolean | A predicate: `is`, `has`, `can`, `should`, or an equally clear state phrase |
| Event/signal handler | `On...` |
| File | Matches the primary type exactly |

Avoid abbreviations unless they are established domain terms. Prefer `cancellationToken` to `ct` in public or nontrivial code; short names are acceptable in very small local scopes.

### 3.2 Formatting

- Four spaces; no tabs.
- Allman braces.
- One primary type per file, except tiny private/nested data types that exist only for that owner.
- `using` directives at the top of the file.
- No trailing whitespace.
- End files with a newline.
- Keep related fields together, but do not create arbitrary field-order rituals that obscure meaning.

One-line guard clauses may omit braces when unmistakable. Use braces whenever another statement could be added accidentally or the branch is not immediately obvious.

### 3.3 Types and `var`

Use explicit types by default.

`var` is permitted when:

- the right-hand side makes the type immediately obvious;
- the type is anonymous;
- repeating a long generic type would reduce readability.

Do not use `var` to hide an important abstraction or return type.

### 3.4 Comments

Comments explain constraints, rationale, ownership, platform behavior, or non-obvious tradeoffs.

Do not narrate an obvious line of code. Do not preserve tutorial commentary in production files. Delete stale comments when behavior changes.

Public APIs with non-obvious contracts should use XML documentation.

---

## 4. Class and method design

### 4.1 Size is a warning, not a law

- Aim for short methods that perform one level of abstraction.
- A method around 20–30 lines deserves a responsibility check.
- A MonoBehaviour approaching 150–200 lines deserves a responsibility review.
- Large data models, generated code, and deliberate tables are exceptions.
- A short class can still be badly coupled; a long class can occasionally be coherent. Review responsibility rather than worshiping a number.

### 4.2 Guard clauses

Validate required state early and return or throw with a specific message.

Do not allow a missing required reference to become a null-reference exception many calls later.

Use:

- editor validation for authoring errors;
- assertions for programmer invariants in development;
- structured error results for expected runtime failures;
- exceptions for unrecoverable contract violations at controlled boundaries.

### 4.3 Public API

Runtime state is private.

Expose behavior through:

- methods;
- read-only properties;
- events/signals;
- narrow interfaces;
- immutable result/data types.

Avoid public mutable fields.

### 4.4 Inspector fields

Use private serialized fields:

```csharp
[SerializeField]
private Transform target;
```

Use `Min`, `Range`, tooltips, custom drawers, or validation when they materially prevent bad authoring.

Do not serialize transient runtime state merely to observe it. Use dedicated debug views or read-only inspector tooling.

---

## 5. Dependencies and communication

### 5.1 Direct references

Use a direct reference when:

- one object clearly owns another;
- the dependency is required and one-to-one;
- the caller needs an immediate result;
- obscuring the call behind a global event would make control flow harder to follow.

### 5.2 Interfaces

Use an interface at a meaningful substitution boundary, especially for:

- platform adapters;
- content loading;
- save/storage providers;
- external/network services;
- time/random sources used in deterministic tests;
- pools or factories consumed by several systems.

Do not create an interface for every class without a real alternate implementation or testing boundary.

### 5.3 Signals and events

Strongly typed signals/events are appropriate for cross-feature or one-to-many notifications.

Rules:

- group contracts by feature;
- use descriptive payload types instead of long primitive parameter lists;
- pair every registration with unregistration in the matching lifetime;
- avoid anonymous callbacks when reliable removal is required;
- do not emit a global signal merely to avoid a direct call to an object already owned by the sender;
- do not place dozens of unrelated subscriptions in one manager—split the responsibility.

### 5.4 Reuse and tool selection

Before creating a new event bus, tween coroutine, fader, loader, pool, or similar infrastructure, search the current repository for an established implementation and inspect the current dependency/assembly configuration. Prefer reuse or a narrow extension when it fits. Do not force a tool into a problem merely because the tool exists.

Project-preferred tools and patterns:

- **Direct references:** default for clear, local, one-to-one ownership.
- **deVoid Signals:** preferred for typed cross-system, one-to-many, fire-and-observe notifications when the library is installed and the event is truly decoupled. Search for an existing signal before declaring a new one. Subscription and unsubscription must be lifecycle-symmetric.
- **DOTween:** preferred timing/interpolation engine for ordinary presentation tweening and sequencing when installed. Gameplay state must not depend on a tween as its authoritative source of truth.
- **Hierarchy fader:** before creating a new fade coroutine or utility, use or extend the project fader. New visual types should normally be integrated through a narrow fade-target adapter rather than another parallel fade system. The fader owns what participates; DOTween may own how normalized values change over time.
- **Addressables/content service:** consider for nontrivial dynamic loading, variants, preload, platform selection, or explicit release lifetimes. Do not use Addressables merely to replace a simple inspector-owned reference.
- **Pools:** consider for objects with meaningful repeated spawn/despawn cost. Prefer an existing pool and define semantic reset rather than creating another pool implementation.

Dependency availability is a hard precondition. Before writing against deVoid, DOTween, Addressables, or another package, verify it in `Packages/manifest.json`, plugin source/binaries, `.asmdef` references, or existing compiling code. An agent must not silently add or upgrade a third-party dependency unless the selected task explicitly authorizes package/dependency changes. If the best tool is absent and adding it is out of scope, report the recommendation instead of smuggling the dependency into the task.

Reference examples under an approved `/reference` mount are supporting evidence only. They may suggest an approach but are not proof that a class/package exists in No Safe Circle and are never authority to copy private source.

### 5.5 Singletons and service location

Global access is not the default dependency strategy.

A true application-wide service may have one validated instance, but creation and lifetime belong to a composition root/bootstrap. Consumers should receive interfaces or scoped references where practical.

Never silently create a missing production service from a random property getter.

---

## 6. Unity lifecycle

- Cache stable component references during initialization.
- Do not repeatedly call `GetComponent`, `FindObjectOfType`, or hierarchy searches in hot paths.
- Make `Awake`, `OnEnable`, `Start`, `OnDisable`, and `OnDestroy` responsibilities deliberate.
- Subscribe and unsubscribe in symmetric lifecycle methods.
- Stop or cancel owned operations when the owning object is disabled/destroyed if their results are no longer valid.
- Avoid `DestroyImmediate` in runtime gameplay code.
- Do not depend on script execution order when an explicit bootstrap or initialization contract is clearer.
- Use `OnValidate` or editor validation for authoring checks, but do not mutate large asset graphs unexpectedly.

---

## 7. Async and cancellation

### 7.1 Preferred tools

For Unity 6 code:

- use `Awaitable` and `async` for new Unity-oriented asynchronous orchestration when it improves control flow;
- use `Task` for framework/network logic that is independent of MonoBehaviour coroutine scheduling;
- retain coroutines for animation/timeline flows where they remain clearer or already form a stable subsystem.

Do not mix all three styles inside one operation without a clear adapter boundary.

### 7.2 Rules

- Any operation that can outlive its caller accepts or owns cancellation.
- Do not expose initialization as a bool that every consumer polls.
- Await initialization once through a bootstrap/readiness operation.
- Avoid `async void`; it is permitted only for event/lifecycle entry points with internal exception handling.
- Report failure through a typed result or exception boundary; do not return an empty string or null for every failure category.
- Do not block the main thread waiting for asynchronous content.
- Do not use Addressables `WaitForCompletion` in WebGL-targeted game code.

---

## 8. Addressables standard

### 8.1 Why we are using Addressables

WebGL does not require Addressables, but No Safe Circle benefits from them because we need deliberate control over:

- what content is part of the initial player;
- what loads together;
- when large content becomes resident;
- when content ownership ends;
- platform variants;
- future remote/local delivery choices.

### 8.2 Architecture

Addressables responsibilities remain split:

- `AddressablesInitialization`: initialize once and expose an awaitable readiness boundary.
- `IContentResolver`: convert a logical content request into addresses/labels/locations using fallback and platform policy.
- `IAddressableAssetService`: perform typed loads and return leases/results.
- `AssetScope`: own a group of leases with a shared lifetime.
- `AddressablePrefabPool<T>`: own both the prefab lease and its pool.
- `AddressablesProjectValidator`: validate editor configuration and build assumptions.

Do not recreate a single global manager that owns all of these concerns.

### 8.3 Keys and labels

- Prefer typed `AssetReference` fields for singular inspector-assigned assets.
- Use labels or resource locations for logical sets.
- Centralize content IDs and label definitions.
- Do not hand-build path strings throughout gameplay code.
- Normalize IDs in one place only.
- Use stable logical IDs for override merging; filenames are acceptable only when uniqueness is explicitly guaranteed.

### 8.4 Fallback and variants

The standard resolver supports ordered preferences such as:

1. game + mode + WebGL variant;
2. game + mode + shared variant;
3. game + default mode + WebGL variant;
4. game + default mode + shared variant.

The fallback policy is data/configuration, not duplicated procedural code at every call site.

A missing optional override is not logged as a fatal error. A missing required final asset is.

### 8.5 Ownership and release

- Every explicit load has an explicit owner.
- Mirror every load with release of the same handle/lease.
- Keep the handle for the complete period in which the result is used.
- Release failed operation handles as well.
- A scope disposes leases in a predictable order.
- A pool releases its prefab lease only after all pool instances are gone.
- Do not use broad “release all game handles” cleanup when the actual owners can be represented directly.

### 8.6 Cache policy

Releasing asset ownership is not cache eviction.

- Normal scene/level unload releases handles.
- `ClearDependencyCacheAsync` is used only by an explicit cache-maintenance or content-version workflow.
- Cache deletion is never hidden inside ordinary resource cleanup.

### 8.7 Groups and builds

- Group assets by shared lifetime and dependency behavior.
- Do not mirror the folder tree blindly.
- Use a platform group schema: `Shared`, `WebGL`, `Desktop` unless/until another real target is added.
- Missing platform classification fails validation.
- The platform-aware build script temporarily selects applicable groups and restores user settings in `finally`.
- Run standard duplicate-dependency analysis and custom validation before release builds.
- Record the Addressables content build version with the player build evidence.

### 8.8 Testing

At minimum, test:

- required load success;
- optional variant fallback;
- missing required content;
- cancellation;
- scope disposal;
- failed-load handle release;
- pooled prefab lifetime ordering;
- group platform filtering;
- restoration of group settings after successful and failed builds;
- WebGL player loading and unload behavior.

---

## 9. Pooling standard

### 9.1 When to pool

Pool objects that are created and retired repeatedly during gameplay or are expensive enough that churn is known to matter.

Do not pool everything by reflex. A rarely created object may be simpler and cheaper to instantiate normally.

### 9.2 Required pool behavior

Each pool defines:

- creation method;
- initial capacity;
- maximum capacity;
- overflow policy;
- checkout reset;
- return reset;
- destruction behavior;
- owner/lifetime;
- development diagnostics.

### 9.3 Poolable contract

A pooled object must restore all semantic state, including relevant:

- active state;
- transform and parent;
- velocities and physics state;
- animation tracks/state;
- particles;
- materials and property blocks;
- sorting and masks;
- callbacks/subscriptions;
- timers and coroutines;
- gameplay data;
- child objects created during use.

A simple inactive flag is insufficient.

### 9.4 Diagnostics

Development builds should detect or report:

- double return;
- foreign-object return;
- double checkout;
- active objects at pool disposal;
- capacity expansion;
- rejected requests;
- peak active count.

### 9.5 Addressable pools

An Addressable prefab pool owns the prefab load lease. The lease outlives all instances and is released only when the pool has been disposed safely.

---

## 10. Performance and WebGL

### 10.1 General

- Do not allocate avoidably in `Update`, `FixedUpdate`, or `LateUpdate`.
- Cache components and stable collections.
- Avoid LINQ, reflection, string construction, and allocating physics APIs in hot paths.
- Use non-allocating APIs where they improve measured or clearly frequent paths.
- Stage heavy work and apply an explicit frame budget when it must occur during play.
- Add profiler markers around custom loading, spawning, pooling, simulation, and expensive generation paths.

### 10.2 Evidence over folklore

- Profile in an actual WebGL player, not only the Editor.
- Record browser, build configuration, content version, and commit.
- Do not call `GC.Collect`, `Resources.UnloadUnusedAssets`, or shader warmup loops as routine superstition. Use them only when profiling demonstrates a justified transition strategy.
- Optimization does not excuse unreadable ownership or hidden state.

### 10.3 Object lifetime

Avoid recurring `Instantiate`/`Destroy` loops for known high-frequency entities. Release assets and pools at deliberate transition boundaries.

---

## 11. ScriptableObjects and data

Use ScriptableObjects for authoring/configuration such as:

- enemy definitions;
- abilities;
- encounters;
- level/region configuration;
- content references;
- platform/build policies;
- tuning profiles.

Treat configuration assets as immutable at runtime unless the type is explicitly designed as state.

Do not store per-play-session state in a shared asset accidentally.

Validation should report missing IDs, duplicate IDs, invalid ranges, and broken references before play/build.

---

## 12. Editor tools

Editor tools must:

- validate input before mutation;
- support Undo for scene/asset authoring changes where applicable;
- mark changed objects/assets dirty correctly;
- use deterministic ordering and output;
- avoid stale output by rebuilding or explicitly reconciling destinations;
- use `try/finally` for progress-bar and temporary-state cleanup;
- provide actionable errors;
- avoid silently rewriting canonical scenes or prefabs;
- live in an Editor assembly;
- keep collection/model logic separate from the editor window/menu orchestration.

Agent/context export tools should produce machine-readable manifests and record their source commit when possible.

---

## 13. Assemblies, folders, and namespaces

Suggested initial structure:

```text
Assets/NoSafeCircle/
├── Core/
│   ├── Runtime/
│   └── Tests/
├── Content/
│   ├── Runtime/
│   ├── Editor/
│   └── Tests/
├── Gameplay/
│   ├── Runtime/
│   └── Tests/
├── UI/
│   ├── Runtime/
│   └── Tests/
├── Editor/
└── Tests/
```

Use namespaces such as:

- `NoSafeCircle.Core`
- `NoSafeCircle.Content`
- `NoSafeCircle.Gameplay.Enemies`
- `NoSafeCircle.Gameplay.Combat`
- `NoSafeCircle.UI`
- `NoSafeCircle.Editor`

Do not create an assembly for every folder. Add a boundary when it improves compilation isolation, dependency direction, package reuse, or testability.

Runtime code must not reference Editor assemblies.

---

## 14. Testing and validation

### 14.1 Tests

Use EditMode tests for pure logic, data validation, editor tooling, and content/build rules.

Use PlayMode tests for lifecycle, scene integration, pooling, signals, and runtime Addressables behavior.

A test should verify behavior and ownership, not merely that a method completed without throwing.

### 14.2 Repository safety

Automated tests and coding agents must not:

- save or rewrite canonical scenes unexpectedly;
- reset, clean, stash, or hide unrelated work;
- leave tracked or untracked artifacts in the repository;
- report success from a different commit/tree than the code being evaluated.

Validation should fail visibly on unexpected repository changes rather than erasing them.

### 14.3 Build evidence

Retain:

- exact Git commit/tree;
- Unity version;
- package lock/version state;
- Addressables content build version;
- test result XML;
- target platform;
- relevant logs;
- WebGL smoke-test outcome.

---

## 15. External reference-project evidence

External projects mounted under `/reference` are optional engineering evidence. They are not No Safe Circle canon, task authority, completion evidence, or runtime dependencies.

Any agent using them must follow [`REFERENCE_PROJECTS.md`](./REFERENCE_PROJECTS.md) and the source registry in `Pipeline/ReferenceSources/reference_sources.json`.

Required rules:

- reference access is opt-in and read-only;
- the active task must name the engineering question that justifies access;
- inspect targeted files rather than ingesting an entire project by default;
- record the exact source path and commit/snapshot identity for any relied-on observation;
- preserve lessons and requirements, not accidental legacy implementation shape;
- use clean reimplementation unless the human explicitly confirms source-level reuse rights;
- never add a compile-time or runtime dependency on a reference project;
- never publish proprietary source, company identifiers, secrets, or unapproved content in patches or artifacts;
- fail closed when the expected source is missing, writable, unsanitized, or outside the approved registry.

Reference code can suggest a solution. It cannot establish that No Safe Circle requires that solution or that a task has been completed.

---

## 16. Review triggers

A design review is required when any of the following occurs:

- a MonoBehaviour approaches 200 lines and still grows;
- a class subscribes to many unrelated signal families;
- a service owns loading, resolution, policy, lifetime, and presentation together;
- a new global singleton is proposed;
- a new string address/label convention is introduced;
- recurring runtime instantiation is added;
- a pooled type lacks a documented reset contract;
- an async operation has no cancellation or owner;
- platform `#if` code appears outside an adapter/composition boundary;
- a manual authoring process must be repeated across several assets;
- a WebGL optimization is proposed without player evidence.

A trigger requires thought, not automatic rejection. The developer documents why the current design remains appropriate or splits it.

---

## 17. Initial engineering-tool backlog

Build or adopt reusable infrastructure only when current game work justifies it. Do not turn this list into a prerequisite for shipping gameplay.

1. Audit current project code for duplicate event, tween/fade, loading, and pooling mechanisms.
2. Verify/adopt deVoid Signals for appropriate cross-system notifications, then refactor only callers that become clearer.
3. Verify/adopt DOTween and establish one semantic hierarchy-fader boundary for ordinary fades/tweens.
4. Add Addressables package/configuration for the verified Unity 6000.1 project when dynamic content work requires it.
5. Add platform group schema and platform-aware packed build script.
6. Add Addressables project validator.
7. Add initialization boundary, typed load result, `AssetLease<T>`, and `AssetScope`.
8. Add logical content resolver with ordered platform/shared fallback.
9. Add typed pool abstraction with development checks/metrics and Addressable prefab-pool ownership where needed.
10. Add content ID/label catalog, WebGL loading/memory smoke evidence, and project-context export tooling as their use cases become real.

---

## 18. Exceptions

These standards serve the game; the game does not serve the standards.

An exception is acceptable when it is:

- deliberate;
- local;
- documented where the reason is not obvious;
- covered by tests or validation appropriate to its risk;
- not used as accidental precedent for unrelated code.

Legacy code may be improved incrementally. New code should not reproduce a known legacy compromise merely to remain consistent with it.
