# Optional Web memory profiler

`Assets/WebGLTemplates/DefaultMemoryProfiler` copies the Default template from Unity 6000.6.3f1. The canvas, loading bar, warning banner, mobile sizing, fullscreen button, build macros and development controls stay as shipped by Unity. Two added hooks load `TemplateData/memory-profiler.js` and pass it the completed Unity instance.

## Use

1. In **Player > Web > Resolution and Presentation > Web Template**, select **DefaultMemoryProfiler** before building.
2. For a normal page, leave **Publishing Settings > Show Diagnostics Overlay** off and open the build URL normally.
3. Append `?diags` (or `&diags` if the URL already has a query). Click the memory icon in Unity's footer to open diagnostics. Close the panel with **X**.

The query follows the production example: presence enables it, including `?diags=false`. The diagnostics CSS and JavaScript are fetched only after Unity loads and only when requested. Unity's existing Show Diagnostics Overlay build option remains available; enabling it uses Unity's normal icon and the helper does not add a duplicate.

This uses Unity 6.6's stock `diagnostics.js`, `diagnostics.css` and `webmemd-icon.png`, with `GetMetricsInfo()` from the loaded instance. The older example's `GetMemoryInfo()` API does not exist in this build. The copied diagnostics script has one guard added when closing: the icon may already have been removed by the development Unload button. The helper closes the polling timer and removes its optional DOM and script references when the Unity container is removed. No production-game configuration or startup code is imported. Installed Unity files and generated website files are not edited.

Copy source: `PlaybackEngines/WebGLSupport/BuildTools/WebGLTemplates/Base/Default`; diagnostics source: `WebGLTemplates/WebGLIncludes/TemplateData`. On a Unity upgrade, compare these copies to the new editor version. The existing template selection and all other Player settings are preserved by this change.

Unity documentation: [Custom templates](https://docs.unity.com/en-us/engine/6000.6/manual/platform-specific/webgl/building-distribution/templates/web-templates-add), [template variables](https://docs.unity.com/en-us/engine/6000.6/manual/platform-specific/webgl/building-distribution/templates/web-templates-variables).
