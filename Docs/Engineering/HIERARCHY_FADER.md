# HierarchyFader

`HierarchyFader` in `Assets/NoSafeCircle/DoorPrototype/Scripts/Presentation/`
fades presentation alpha for one GameObject hierarchy. It never changes
colliders, health, targeting, scene flow, or other gameplay state.

Attach it to a parent GameObject and call `FadeTo(opacity, duration)`, where
opacity is a multiplier from 0 (transparent) to 1 (each target's captured
alpha). The first fade discovers child `CanvasGroup`, UI `Graphic`,
`SpriteRenderer`, and generic `Renderer` components, including inactive
children. The outermost `CanvasGroup` on each branch owns its nested groups and
Graphics so their alpha is not multiplied twice. A `SpriteRenderer` is handled once through
its own color adapter, not again as a generic `Renderer`.
Timed fades require Play Mode because DOTween does not initialize in Edit Mode;
zero-duration fades can still be used for immediate state checks in Edit Mode.

The fader captures each target's original state immediately before the first
fade. DOTween drives one normalized value; adapters apply it to the captured
alpha. A completed ordinary fade holds its terminal opacity. `Restore()`
restores every original color, `CanvasGroup.alpha`, and generic Renderer's full
`MaterialPropertyBlock`. `Cancel()` kills the tween and restores; `Cancel(false)`
kills it while holding the current appearance for a later fade. Replacing a fade
kills the old tween and starts at its current opacity. `FadeTo(...,
restoreOnComplete: true)` restores after a temporary effect. Disabling or
destroying the fader kills its tween and restores surviving targets. Call
`RefreshTargets()` after changing the hierarchy; it restores current targets
and discovers the new set on the next fade.

Generic `Renderer` fading uses the first shared material's `_BaseColor` or
`_Color` shader property. Renderers without either color property are skipped.
The adapter writes a `MaterialPropertyBlock`, never `renderer.material`, and
restores the full previous block. Its shader must already blend color alpha;
an opaque shader will not become transparent merely because alpha changes.
If a new visual technology needs different
handling, implement `IFadeTarget` and register it with `RegisterTarget`; do not
add renderer-specific fading to gameplay callers.

For NSC-058 VAL-003, in a disposable Play Mode scene put a `SpriteRenderer` or
UI hierarchy under a GameObject with `HierarchyFader`. From the component's
Inspector menu choose **Preview → Fade Out**, observe the fade, then choose
**Preview → Restore** and confirm the original alpha/color returns. Disable
the component during another fade and confirm it restores immediately. This is
a presentation check for Vincent; automated tests and repository state do not
claim that he has performed it.
