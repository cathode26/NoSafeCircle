// Optional Unity diagnostics. Without ?diag or ?diags, the default page has no extra UI.
(function () {
    const query = new URLSearchParams(window.location.search);
    const enabled = query.has('diags') || query.has('diag');
    const assetBase = new URL('.', document.currentScript.src);
    let attached = false;

    window.unityMemoryProfiler = {
        attach: function (instance) {
            if (!enabled || attached || document.getElementById('diagnostics-icon')) return;
            if (typeof instance.GetMetricsInfo !== 'function') {
                console.warn('Unity memory diagnostics are unavailable in this build.');
                return;
            }
            const container = document.querySelector('#unity-container');
            if (!container) return;
            attached = true;
            const stylesheet = document.createElement('link');
            stylesheet.rel = 'stylesheet';
            stylesheet.href = new URL('diagnostics.css', assetBase).href;
            const script = document.createElement('script');
            script.src = new URL('diagnostics.js', assetBase).href;
            let icon, stylesheetReady = false, scriptReady = false;
            const observer = new MutationObserver(function () {
                if (!container.isConnected) cleanup();
            });
            observer.observe(container.parentNode, { childList: true });

            function moveIcon() {
                if (!icon) return;
                const parent = document.fullscreenElement || document.body;
                if (icon.parentNode !== parent) {
                    try { if (icon.matches(':popover-open')) icon.hidePopover(); } catch (_) {}
                    parent.appendChild(icon);
                }
                if (!icon.hidden && typeof icon.showPopover === 'function') {
                    icon.setAttribute('popover', 'manual');
                    try { if (!icon.matches(':popover-open')) icon.showPopover(); } catch (_) {}
                }
            }
            function onGamePopover(event) {
                if (!icon || icon.hidden || event.newState !== 'open' ||
                    event.target.getAttribute('aria-label') !== 'Rotate your device') return;
                try { if (icon.matches(':popover-open')) icon.hidePopover(); } catch (_) {}
                moveIcon();
            }
            function cleanup() {
                observer.disconnect();
                document.removeEventListener('fullscreenchange', moveIcon);
                document.removeEventListener('toggle', onGamePopover, true);
                window.unityDiagnostics?.destroy();
                if (icon) { icon.onclick = icon.onkeydown = null; icon.remove(); icon = null; }
                script.onload = script.onerror = null;
                stylesheet.onload = stylesheet.onerror = null;
                script.remove();
                stylesheet.remove();
                instance = null;
                attached = false;
            }
            function stopGameInput(event) { event.stopPropagation(); }
            function createIconWhenReady() {
                if (!stylesheetReady || !scriptReady || icon) return;
                if (!container.isConnected) { cleanup(); return; }
                icon = document.createElement('img');
                icon.id = 'diagnostics-icon';
                icon.src = new URL('webmemd-icon.png', assetBase).href;
                icon.width = icon.height = 44;
                icon.alt = icon.title = 'Memory profiler';
                icon.tabIndex = 0;
                icon.setAttribute('role', 'button');
                icon.setAttribute('aria-expanded', 'false');
                ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'mousedown', 'mouseup',
                    'touchstart', 'touchmove', 'touchend', 'touchcancel', 'click', 'keydown', 'keyup']
                    .forEach(name => icon.addEventListener(name, stopGameInput));
                icon.onclick = function () {
                    unityDiagnostics.openDiagnosticsDiv(() => instance.GetMetricsInfo());
                };
                icon.onkeydown = function (event) {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        icon.click();
                    }
                };
                document.addEventListener('fullscreenchange', moveIcon);
                document.addEventListener('toggle', onGamePopover, true);
                moveIcon();
            }
            function loadFailed() {
                cleanup();
                console.warn('Could not load the optional Unity memory diagnostics.');
            }
            stylesheet.onload = function () {
                stylesheet.onload = stylesheet.onerror = null;
                stylesheetReady = true;
                createIconWhenReady();
            };
            script.onload = function () {
                script.onload = script.onerror = null;
                scriptReady = true;
                createIconWhenReady();
            };
            stylesheet.onerror = script.onerror = loadFailed;
            document.head.appendChild(stylesheet);
            document.head.appendChild(script);
        }
    };
})();
