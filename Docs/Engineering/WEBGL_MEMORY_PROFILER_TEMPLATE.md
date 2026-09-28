# Optional Web memory profiler

`Assets/WebGLTemplates/DefaultMemoryProfiler` copies the Default template from Unity 6000.6.3f1. The canvas, loading bar, warning banner, mobile sizing, fullscreen button, build macros and development controls stay as shipped by Unity. Two added hooks load `TemplateData/memory-profiler.js` and pass it the completed Unity instance.

## Use

1. In **Player > Web > Resolution and Presentation > Web Template**, select **DefaultMemoryProfiler** before building.
2. Leave **Publishing Settings > Show Diagnostics Overlay** off to use this optional display.
3. Append `?diag` or `?diags` to the build URL (use `&` if there is already a query).
4. Tap the floating memory icon at the bottom right. Drag the **Memory** header to move the card; **X** closes it and restores the icon.

The card has a translucent background and stays inside the visible browser viewport. Its position is clamped again when readings change, after rotation, browser toolbar changes, or fullscreen changes. The icon respects safe-area insets; the card accounts for them when positioning. Touches on the card or icon do not bubble to gameplay handlers; the rest of the game remains interactive. The close button and icon are 44 CSS pixels. Where supported, a nonmodal manual popover keeps diagnostics above the game's rotation prompt, including in fullscreen. There is no screen-sized diagnostics input blocker.

Phones and tablets show **Total WASM heap**, **Used WASM heap**, and **FPS**, omitting any unavailable reading. They do not create graphs or show startup timing and JavaScript heap panels. Desktop browsers show supported detailed readings and responsive graphs; small desktop windows also use the compact card. JavaScript heap metrics are unavailable in Safari/iOS and Firefox, so those rows and graphs are omitted there instead of displaying N/A or a fake zero.

The query enables diagnostics by its presence, including `?diags=false`; both spellings are accepted. The diagnostics CSS and JavaScript are fetched only after Unity loads and only when requested. A normal URL adds no profiler UI or diagnostics asset requests. Unity's native Show Diagnostics Overlay option remains available, and the helper does not create a duplicate icon if it is already enabled; that option uses the editor's own built-in diagnostics implementation.

The helper uses `GetMetricsInfo()` on the loaded Unity instance. Espresso's older `GetMemoryInfo()` API is not used. Both stylesheet and script must finish loading before the icon is exposed. Metrics are sampled immediately when the card opens and then once per second. Closing releases the timer and metrics callback. Removing the Unity container also destroys the card, removes viewport/fullscreen/popover listeners, and releases the icon and helper assets. The optional UI is moved into the fullscreen element while fullscreen is active.

The index and ordinary `style.css` remain unchanged. The mobile correction changes only the optional `memory-profiler.js`, `diagnostics.js` and `diagnostics.css`, with matching helper files in the exported website. It requires no Unity gameplay rebuild. No production-game configuration or startup code is copied from Espresso.

Copy source: `PlaybackEngines/WebGLSupport/BuildTools/WebGLTemplates/Base/Default`; original diagnostics source: `WebGLTemplates/WebGLIncludes/TemplateData`. The diagnostics files now contain the floating, compact display rather than an unmodified copy of the stock overlay. On a Unity upgrade, verify the `GetMetricsInfo()` field names against the new loader. Player settings are preserved.

Unity documentation: [Custom templates](https://docs.unity.com/en-us/engine/6000.6/manual/platform-specific/webgl/building-distribution/templates/web-templates-add), [template variables](https://docs.unity.com/en-us/engine/6000.6/manual/platform-specific/webgl/building-distribution/templates/web-templates-variables), [diagnostics and unavailable JavaScript memory metrics](https://docs.unity.com/en-us/engine/6000.6/manual/platform-specific/webgl/develop/class-player-settings-web-gl#show-diagnostic-overlay-setting).
