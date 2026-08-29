# Fader, Signals, and Tool Selection

## Hierarchy fader gem

The production fade subsystem is valuable because it treats a fade as a coordinated operation across heterogeneous visual state rather than as one `SpriteRenderer.color` tween. The reusable lesson is:

1. discover participating visual targets;
2. capture each target's original state once;
3. adapt each rendering technology behind a small fade-target contract;
4. drive one normalized fade operation across the targets;
5. restore captured state exactly on completion or cancellation.

The production implementation accumulated many package- and feature-specific responsibilities. No Safe Circle should preserve the behavior with a small `HierarchyFader` plus `IFadeTarget` adapters. Add Spine, video, particles, line renderers, or other special cases only when the game actually needs them.

When DOTween is installed and approved for the project, use it as the timing/interpolation engine behind the semantic fader rather than writing another per-frame tween loop. Gameplay code should depend on the fader abstraction, not on scattered DOTween calls.

## Typed signal gem

Space Invaders confirms the preferred deVoid usage pattern: typed `ASignal` classes, `Signals.Get<T>()`, `Dispatch`, and lifecycle-symmetric `AddListener` / `RemoveListener` calls. SlotEngine also showed strong subscription symmetry at production scale.

Use signals for cross-system, one-to-many, fire-and-observe communication. Prefer a normal reference when ownership is local and one-to-one. Search for an existing signal before creating another contract.

## Dependency boundary

Reference examples may name public APIs such as deVoid Signals or DOTween, but the examples do not install those packages and do not prove they exist in the current No Safe Circle checkout. Agents must verify package/plugin/assembly availability before writing against them and must not add or upgrade dependencies outside explicit task authority.

## Agent reuse rule

Before introducing a new event bus, tween helper, fade coroutine, content loader, or pool, inspect the current repository and engineering standards. Prefer reuse or a narrow extension when it fits. A different implementation is acceptable when it is simpler or better suited to the task; the standard requires consideration, not cargo-cult use.
