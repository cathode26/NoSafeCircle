# Mobile controls

`Resources/Hud/MobileControls.prefab` is instantiated by `HudBindings` under the existing HUD Canvas.
It uses the HUD's Input System UI module, including its separate touch pointers. There is no new input package.

The two hold buttons are stacked at the bottom left, inside `Screen.safeArea`:

- **Stand + fire** (upper): immediately cancels the current destination and pending door interaction. Tap the world to aim and fire. Releasing never restores the canceled path.
- **Fire while moving** (lower): retains the current destination. Tap the world to aim and fire without selecting a new destination.

Slide a held finger onto the other button to switch modes. Leaving the old button releases it; entering the new button presses it. Neither mode is held in the gap. Pointer-up releases the current mode even when UGUI delivers it to the original button. A world-origin finger cannot become a fire-button hold by sliding over one.

Stand takes priority when both buttons are held. Each button tracks its own pointer IDs, so one release cannot end another finger's hold. With neither held, each fresh world pointer-down is a movement/door command. Dragging or holding a world finger does not repeat it. A finger that started on a hold button cannot become a world command by dragging away.

`PlayerMovement` owns the mode and cancellation rules. `MobileWorldTapSurface` routes each world pointer's own position. `DemoRunFlow.TryCastFireball` shares the mouse cast's mana and cooldown checks. Mouse movement rejects the entire press that started over UI, including a drag away from it; normal desktop left-click movement and right-click casting remain available.

Controls appear for native mobile platforms or a mobile browser, after gameplay handoff. Desktop touchscreens do not enable them. The Editor requires the explicit preview toggle. They reject input in portrait, during menus/cutscene, after death/victory, on focus loss, and while suspended. Holds clear on suspension, reset and HUD disable. Native mobile startup allows only the two landscape orientations.

`Assets/Plugins/WebGL/MobileLandscape.jslib` requests fullscreen and `screen.orientation.lock("landscape")` from a user gesture. Browsers that reject or lack orientation locking show a portrait rotate prompt. Browser support and fullscreen requirements are documented by [MDN](https://developer.mozilla.org/en-US/docs/Web/API/ScreenOrientation/lock). The plugin changes no Unity index/template files. A new WebGL build is required to include both the gameplay code and plugin; the earlier localhost build has neither.

Validation: `MobileControlsPlayModeTests` covers route retention, irreversible stop, priority/pointer release, suspension/reset, door cancellation, UI-origin mouse presses, actual cast mana/cooldown, and the real two-finger Input System UI path. Run alongside the existing movement, Hold Position, door and HUD Play Mode regressions.

## Unity Editor preview

Enable **No Safe Circle > Preview > Force Mobile Controls** and use a landscape Game View.
This Editor preference survives recompilation and never changes device/build settings.
The buttons also support mouse hold-and-slide. To test world aiming with one mouse,
hold **Left Ctrl** for Stand + fire or **Left Shift** for Fire while moving, then click the world.
Ctrl takes priority, and releasing either shortcut follows the same path rules as touch.
These shortcuts are compiled only in the Editor.
