# Approved Feature Brief: Sealed Door Prototype

## Game

**No Safe Circle**

## Unity Version

`6000.1.8f1`

## Purpose

Create a small playable Unity prototype of the central sealed-door interaction from the No Safe Circle GDD.

The player must create enough safety to remain at a sealed door for five uninterrupted seconds. Moving or taking damage cancels the attempt.

## Approved Player Experience

1. The player controls a simple placeholder character using WASD.
2. The player approaches a sealed door.
3. A visible prompt indicates that the door can be opened.
4. The player holds E to begin opening it.
5. A visible progress indicator fills over five seconds.
6. Releasing E before completion cancels the attempt.
7. Moving while opening cancels and resets the attempt.
8. Receiving damage while opening cancels and resets the attempt.
9. Completing the five-second interaction opens the door.
10. Once opened, the doorway can be crossed.

## Required Implementation Qualities

- The interaction duration is configurable but defaults to five seconds.
- Interaction state is testable without simulated keyboard input.
- Door progress is exposed as a normalized value from 0 to 1.
- Cancellation behavior is explicit and deterministic.
- Placeholder Unity primitives are acceptable.
- No external art assets are required.
- A Unity Editor menu command must build the prototype scene so manual Inspector wiring is minimized.
- The scene builder must be safe to run more than once.
- Play Mode tests must cover completion, movement cancellation, damage cancellation, and interaction release.
- Generated scripts must be organized under `Assets/NoSafeCircle/DoorPrototype/`.

## Explicitly Out of Scope

- Enemy AI
- NavMesh pursuit
- Ranged enemies
- Frost Field
- Force Wave
- Fireball
- Door locking
- Door durability
- Enemies damaging or breaking the door
- Multiple rooms
- Final escape sequence
- Custom art
- Runtime generative AI
- Unity MCP

## Human Responsibilities

The human developer will:

- Open the project in Unity.
- Allow Unity to compile the generated scripts.
- Run the scene-builder menu command.
- Inspect the generated scene.
- Run the Play Mode tests.
- Play the prototype.
- Review and commit the result.
