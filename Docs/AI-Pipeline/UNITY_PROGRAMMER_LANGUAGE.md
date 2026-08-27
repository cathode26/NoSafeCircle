# Human-Facing Language for a Unity Programmer

This file is operating guidance, not game-design canon. It changes how work is described; it does not add mechanics, choose architecture, or change task ownership.

## Primary audience

The primary human reader is an experienced Unity game programmer. Human-facing output must let that reader recognize the Unity work immediately without first translating pipeline, product, or game-design jargon.

This applies to:

- task titles, acceptance criteria, completion gates, notes, and dependency explanations;
- decomposition proposals and decomposition-review findings;
- implementation, test, and validation summaries;
- GitHub issue comments, planned approaches, closeouts, handoffs, and operator instructions;
- generated project documentation intended for human review.

## Use concrete Unity language

Lead with the actual Unity asset, component, behavior, method, scene object, or test involved.

Prefer terms such as:

- Prefab, GameObject, MonoBehaviour, Component, ScriptableObject;
- Scene, SpriteRenderer, Animator, Collider, Rigidbody or Rigidbody2D, LayerMask;
- player target, movement speed, attack wind-up, projectile, collision, damage, health, reset method;
- public method, serialized field, interface, event, callback, file path, class name, or existing API name;
- Edit Mode test, Play Mode test, prefab test, scene test, and runtime test.

When an exact existing API is known, name it directly, for example `PlayerHealth.TakeDamage`.

## Translate abstract wording

Use the concrete term that matches what the programmer must build or test.

| Avoid when a concrete term is available | Prefer |
| --- | --- |
| archetype | enemy type for the design concept; prefab for the Unity asset |
| capability | component, behavior, system, method, or interface |
| presentation | SpriteRenderer setup, visual GameObject, prefab, or animation |
| foundation | the named shared component or system |
| consumes | uses, calls, reads from, or connects to |
| owner-controlled operation | public method on the component that owns the state |
| integration | name the exact components or systems being connected |
| lifecycle | name the state, timer, spawn, defeat, or reset behavior |
| gameplay-geometry occluder | cover collider, wall collider, pew collider, or column collider |
| acquired-player state | current player target from the pursuit component |
| floor-initial state | the values and objects restored when the floor restarts |

Do not use a slash-compressed phrase when it hides separate behaviors. For example, target knowledge, the decision to fire, and projectile collision are different behaviors and should be described separately when they are actually required.

## Titles

A human-facing task title should answer both questions immediately:

1. What Unity thing or behavior is being built?
2. What does it do?

Examples:

- Avoid: `Ranged Enemy Archetype Prefab Assembly and Frost Integration`
- Prefer: `Ranged Enemy Prefab Setup and Frost Movement Test`

- Avoid: `Ranged Enemy Keep-Away Positioning`
- Prefer: `Ranged Enemy Keep-Distance Movement`

- Avoid: `Telegraphed Projectile, Occlusion, and Reset`
- Prefer: `Projectile Attack, Cover Collision, and Reset`

Machine-facing taxonomy may still use abstract values such as `type: enemy_archetype` when the schema requires them. The human-facing title should use the concrete Unity term.

## Requirements and tests

Write one observable implementation or test requirement at a time. Name the existing owner or API instead of describing it indirectly.

Examples:

- Avoid: `Consumes the shared pursuit foundation's acquired-player state.`
- Prefer: `Uses the current player target supplied by the shared enemy pursuit component.`

- Avoid: `Exposes an owner-controlled attack reset operation.`
- Prefer: `Expose a public reset method on the ranged-attack component that cancels the current wind-up and destroys its active projectiles.`

- Avoid: `Using representative gameplay geometry, verify projectile occlusion.`
- Prefer: `In a Play Mode test, place a cover collider in the projectile path. Verify the projectile hits the cover, is destroyed, and does not call the player damage method.`

## Accuracy limits

Concrete wording must not invent implementation details.

- Do not invent a class, method, file, physics dimension, package, layer, tag, or serialized field that is not established by the task, GDD, repository, or an approved design decision.
- Do not convert a design option into a requirement merely because it is easy to describe in Unity terms.
- Do not require a specific implementation technique when the contract only requires observable behavior.
- Preserve exact schema fields, IDs, local keys, reconciliation keys, dependency IDs, coverage dispositions, and authority language.

The goal is not to make the work less technical. The goal is to make it technical in the language a Unity programmer uses every day.
