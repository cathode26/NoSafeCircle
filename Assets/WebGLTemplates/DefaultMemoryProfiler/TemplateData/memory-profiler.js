// Optional Unity diagnostics. Without ?diag or ?diags, the default page has no extra UI.
(function () {
    const query = new URLSearchParams(window.location.search);
    const enabled = query.has("diags") || query.has("diag");
    const assetBase = new URL(".", document.currentScript.src);

    window.unityMemoryProfiler = {
        attach: function (instance) {
            if (!enabled || document.getElementById("diagnostics-icon")) return;
            if (typeof instance.GetMetricsInfo !== "function") {
                console.warn("Unity memory diagnostics are unavailable in this build.");
                return;
            }

            const container = document.querySelector("#unity-container");
            const fullscreenButton = document.querySelector("#unity-fullscreen-button");
            if (!container || !fullscreenButton) return;

            const stylesheet = document.createElement("link");
            stylesheet.rel = "stylesheet";
            stylesheet.href = new URL("diagnostics.css", assetBase).href;
            document.head.appendChild(stylesheet);

            const script = document.createElement("script");
            script.src = new URL("diagnostics.js", assetBase).href;
            // Unity's development Unload button removes this container. Release
            // the optional panel's polling callback and its instance references.
            const observer = new MutationObserver(function () {
                if (!container.isConnected) cleanup();
            });
            observer.observe(container.parentNode, { childList: true });
            function cleanup() {
                observer.disconnect();
                document.getElementById("diagnostics-btn")?.click();
                document.getElementById("diagnostics-overlay")?.remove();
                script.onload = script.onerror = null;
                script.remove();
                stylesheet.remove();
            }
            script.onload = function () {
                script.onload = script.onerror = null;
                if (!container.isConnected) return;
                const icon = document.createElement("img");
                icon.id = "diagnostics-icon";
                icon.src = new URL("webmemd-icon.png", assetBase).href;
                icon.width = icon.height = 38;
                icon.alt = icon.title = "Memory profiler";
                icon.tabIndex = 0;
                icon.setAttribute("role", "button");
                icon.onclick = function () {
                    unityDiagnostics.openDiagnosticsDiv(() => instance.GetMetricsInfo());
                };
                icon.onkeydown = function (event) {
                    if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        icon.click();
                    }
                };
                fullscreenButton.after(icon);
                const canvas = document.querySelector("#unity-canvas");
                if (canvas.classList.contains("unity-mobile")) {
                    icon.style.position = "fixed";
                    icon.style.bottom = "10px";
                    icon.style.right = "0px";
                    canvas.after(icon);
                }
            };
            script.onerror = function () {
                cleanup();
                console.warn("Could not load the optional Unity memory diagnostics.");
            };
            document.head.appendChild(script);
        }
    };
})();
