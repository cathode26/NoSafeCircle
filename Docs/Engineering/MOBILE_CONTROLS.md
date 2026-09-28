# Mobile controls

`Resources/Hud/MobileControls.prefab` is instantiated by `HudBindings` under the existing HUD Canvas.
It uses the HUD's Input System UI module, including its separate touch pointers. There is no new input package.

The two hold buttons are stacked at the bottom left, inside `Screen.safeArea`:

- **Stand + fire** (upper): immediately cancels the current destination and pending door interaction. Tap the world to aim and fire. Releasing never restores the canceled path.
- **Fire while moving** (lower): retains the current destination. Tap the world to aim and fire without selecting a new destination.

Stand takes priority when both buttons are held. Each button tracks its own pointer IDs, so one release cannot end another finger's hold. With neither held, each fresh world pointer-down is a movement/door command. Dragging or holding a world finger does not repeat it. A finger that started on a hold button cannot become a world command by dragging away.

`PlayerMovement` owns the mode and cancellation rules. `MobileWorldTapSurface` routes each world pointer's own position. `DemoRunFlow.TryCastFireball` shares the mouse cast's mana and cooldown checks. Mouse movement rejects the entire press that started over UI, including a drag away from it; normal desktop left-click movement and right-click casting remain available.

Controls appear for mobile platforms or a connected Input System Touchscreen, after gameplay handoff. They reject input in portrait, during menus/cutscene, after death/victory, on focus loss, and while suspended. Holds clear on suspension, reset and HUD disable. Native mobile startup allows only the two landscape orientations.

`Assets/Plugins/WebGL/MobileLandscape.jslib` requests fullscreen and `screen.orientation.lock("landscape")` from a user gesture. Browsers that reject or lack orientation locking show a portrait rotate prompt. Browser support and fullscreen requirements are documented by [MDN](https://developer.mozilla.org/en-US/docs/Web/API/ScreenOrientation/lock). The plugin changes no Unity index/template files. A new WebGL build is required to include both the gameplay code and plugin; the earlier localhost build has neither.

Validation: `MobileControlsPlayModeTests` covers route retention, irreversible stop, priority/pointer release, suspension/reset, door cancellation, UI-origin mouse presses, actual cast mana/cooldown, and the real two-finger Input System UI path. Run alongside the existing movement, Hold Position, door and HUD Play Mode regressions.
