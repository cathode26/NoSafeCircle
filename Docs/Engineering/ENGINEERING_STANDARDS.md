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
## 19. Runtime world composition

**APPENDED AS 19 RATHER THAN INSERTED NEAR ITS SUBJECT ON PURPOSE.** Sections 4.1, 5.3, 5.4, 7.2 and
9 are cited by number in task contracts and in code comments. Inserting a section mid-document
renumbers every one of those citations silently, so this goes at the end even though it reads oddly
after Exceptions.

### 19.1 The world is built at runtime. A scene holds one object.

`Assets/Scenes/RuntimeWorld.unity` contains `GameManagers` and nothing else. Every room, wall, floor,
prop, door, the wizard, the camera, the enemies and the HUD are **instantiated at Play** from
prefabs. Do not compose content into a scene and commit the result.

This is not a style preference. A composed scene is a single file that every contributor must edit,
which makes it the one guaranteed merge conflict on a project with parallel work; and a committed
scene can silently become the **sole carrier** of art nothing regenerates, so deleting it loses work
with no test failing.

**What you do:** add content by shipping a prefab and a spawner. Never by editing a scene.

### 19.2 A prefab is a text file. Author it.

Unity prefabs, scenes and `.asset` files are YAML. **You can write one with an editor and you do not
need to click anything.** Reference another asset by the `guid` in its `.meta`.

A whole content pipeline was once written as edit-time generators on the belief that an agent cannot
author assets. That belief was false, and the generators were a large, permanent cost paid to avoid
a text file.

**What you do:** write the `.prefab`, run `Tools/prefab_lint.py` (`--package-cache
Library/PackageCache`, so package guids resolve), and read a real example from the package's own
`Samples~` before guessing a serialized field's format. A field whose YAML form you guessed can
deserialize to a legal-but-wrong value - an omitted list becomes empty, which for
`NavMeshModifier.m_AffectedAgents` means "None" while the C# default is "All". Nothing warns.

### 19.3 Spawners are discovered, never listed

`GameBootstrap` finds spawner prefabs by scanning `Resources/Spawners`. There is **no serialized list
and no registry file**.

The reason is mechanical: a shared list is a single file every contributor must append to, so it
becomes the merge hotspot the folder scan exists to remove. A lane ships **one prefab no other branch
contains** and it is picked up with no edit to anything shared.

**What you do:** to add a system, drop `Resources/Spawners/<Name>Spawner.prefab` in the folder. Do
not add it to a list; there isn't one.

### 19.4 The seam: `ISpawner` and `SpawnPhase`

```csharp
public interface ISpawner
{
    SpawnPhase Phase { get; }
    int Spawn();                 // returns how many objects it created
}
```

`Spawn()` is **synchronous on purpose**: section 7.2 forbids blocking for content and forbids
`WaitForCompletion` on WebGL, so a spawner cannot legally wait inside it. Content that must be
preloaded implements the separate `IContentPreloader` interface, which `GameBootstrap` awaits before
any `Spawn()` runs. Keeping that off `ISpawner` is deliberate - a member added to a shared interface
breaks every in-flight implementation at once.

Phase order is explicit because it is sorted on:

```
Rooms(0)  Props(1)  Navigation(2)  Doors(3)  Player(4)  Enemies(5)  Hud(6)
```

**Phase order is a contract between systems, not a hint.** Navigation bakes at 2, before Doors at 3,
so no door stands in an opening at bake time. Player at 4 precedes Enemies at 5 because enemies
acquire the wizard as a target, and precedes Hud at 6 because the HUD binds to him.

**What you do:** pick your phase from what must already exist. If your spawner leaves a solid
collider alive and runs after Navigation, put a `NavMeshModifier` with `ignoreFromBuild` and
`applyToChildren` on your prefab root - a re-bake finds the previous build's objects still standing
and bakes them as walls.

### 19.5 Wire with Signals, not with serialized slots

Cross-lane notification uses deVoid Signals (`Assets/Plugins/deVoid`, namespace `deVoid.Utils`),
already referenced by the runtime assembly. `WorldSignals` declares the world-build facts:
`WorldBuilt`, `PlayerSpawned`, `PhaseCompleted`.

Sections 5.3 and 5.4 already prefer signals for typed one-to-many notification. **The composition
reason is additional and is why it matters here:** a listener holds no reference to the emitter, so
there is no serialized slot to drag an object into and no shared field for two lanes to fight over.
Combined with 19.2 and 19.3, **nothing in the build path requires a mouse.**

This does not widen 5.3. A spawner talking to a prefab it just instantiated uses the reference it
already has. Signals are for genuinely cross-system, one-to-many facts. Subscribe in `OnEnable`,
remove in `OnDisable`, never with an anonymous lambda.

**What you do:** if you need another lane's object, listen for its signal. Do not use
`GameObject.Find`, and do not add a reflection binder.

### 19.6 Verify C# without opening Unity

`Tools/compile_check.ps1` compiles every project assembly with Unity's own Roslyn, in seconds, with
no editor. **Many workers can run it at once where none can share an editor.**

Read its exit codes exactly: `0` every assembly compiled, `1` a real compile failure, `2` **nothing
was checked** - which is never a pass, and is what you get before Unity has imported once.

It is close to Unity's compile, not identical: defines and asmdef resolution are Unity's. **A FAILURE
here is proof. A PASS is strong evidence.** Two known limits: immediately after a `Library` wipe it
exits 2 until Unity imports once, and a test assembly's references point at the last import's DLLs,
so new types added since then can read as missing. Those are phantoms; re-import and re-run before
believing them.

**What you do:** run it before every Unity run and before handing work on.

### 19.7 An asset and its `.meta` ship in the same commit

Commit a `.cs`, `.prefab` or `.asset` without its `.meta` and Unity generates one on the next import
- which is a repository mutation **during** a test run, and the runner correctly refuses to report
results from a run that changed the tree under itself (exit 40).

**What you do:** `git status` after adding any file under `Assets/`. If a `.meta` appears, it belongs
in that commit.

### 19.8 What a test must assert here

These are not general testing advice; each one has cost this project a wrong answer in this
architecture.

- **When an operation's job is to REMOVE or EXCLUDE something, count what survives.** A suite of
  assertions that an object is *correct* cannot detect that the object should not exist, and adding
  more such assertions deepens the blind spot rather than closing it.
- **Assert the durable relation, not today's number.** "Two jambs per doorway, against the doors the
  world builds" survives a content change; "18 jambs" does not, and freezing a number is how a
  defect gets locked in as an expectation.
- **Before comparing two artifacts, check they are commensurable.** The per-room room scenes and the
  single combined world both describe one world and count shared doorways differently - 18 and 10,
  both correct. A **total** is where that hides. Compare per role, per kind, per category.
- **Derive the expectation from a different artifact than the one under test.** An expectation copied
  from the code it checks is self-consistent by construction and passes while proving nothing.
- **Guard against the vacuous pass.** `Assert.Greater(count, 0)` beside the real assertion, so a
  match on an empty set cannot read as success.
- **A test that passes alone and fails in the suite is an ORDER-DEPENDENT LEAK, not a broken test.**
  Diagnose it by running it alone, then with its own fixture, then with suspects - not by reading the
  source, which cannot show it because every file involved is individually correct.
- **Zero discovered tests is a FAILURE, never a pass.** A comma-separated Unity test filter is read
  as one group name and silently matches nothing; use regex alternation `(A|B)`.

### 19.9 Re-derive what you are handed

Every bounded worker that built this architecture found an error in its own brief: a piece count that
was wrong, a tile size that was wrong, a named asset that did not exist, a prescribed test that could
not compile, an address that could never match its catalog, and a task id that named the wrong task.
**Every one was caught by re-deriving the brief from source rather than trusting it.**

A brief is a starting point and its line numbers are stale the moment `main` moves. Verify what you
are given, and report what you could not verify alongside what you did.
