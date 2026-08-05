# Human-Approved Scope Amendment — Controls HUD

## Game

No Safe Circle

## Feature

Sealed Door Prototype

## Approval

The human developer approves this small presentation enhancement without
reopening the full feature-planning stage.

## Purpose

Add an always-visible controls panel so a first-time player understands the
prototype controls and the central interruption rule.

## Required HUD Content

The HUD must clearly communicate:

- `WASD` — Move
- `Hold E` — Open Door
- Moving or taking damage cancels the opening attempt

Do not present a debug-only damage key as a normal player ability. If a damage
test key is shown, label it clearly as a debug/test control and use the actual
binding implemented by the prototype.

## Presentation Requirements

- Keep the panel compact and readable.
- Place it where it does not obscure the player, door, interaction prompt, or
  progress indicator.
- Use built-in Unity UI and fonts already available in the project.
- Do not add external packages or art.
- The scene-builder command must create and wire the panel every time it runs.
- Running the scene builder repeatedly must not duplicate the HUD.
- Preserve the existing door interaction and progress behavior.

## Human Acceptance Criteria

1. The controls panel is visible immediately in Play Mode.
2. The displayed controls match the actual implemented controls.
3. The interruption rule is visible.
4. The panel does not overlap the door progress indicator.
5. Rebuilding the scene twice does not create duplicate panels.
6. The door still opens after five uninterrupted seconds.
7. Release, movement, and damage still reset progress.
