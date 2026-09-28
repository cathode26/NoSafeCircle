// Unity WebGL adapter. One MobileGameplayControls owner initializes/disposes it.
// Browser orientation locking is best effort; portrait always shows a rotate UI.
mergeInto(LibraryManager.library,
{
    $NSC_MobileLandscape:
    {
        state: null,

        isMobileBrowser: function ()
        {
            var touch = navigator.maxTouchPoints > 0 || "ontouchstart" in window;
            var userAgent = navigator.userAgent || "";
            var mobileHint = navigator.userAgentData && navigator.userAgentData.mobile;
            var mobileAgent = /Android|iPhone|iPad|iPod|IEMobile|Mobile|Silk|Kindle/i.test(userAgent);
            var iPadDesktopAgent = /Macintosh/i.test(userAgent) && navigator.maxTouchPoints > 1;
            return touch && (mobileHint || mobileAgent || iPadDesktopAgent);
        },

        isLandscape: function ()
        {
            var orientation = window.screen && window.screen.orientation;
            var type = orientation && orientation.type;
            if (typeof type === "string" && /^(portrait|landscape)/.test(type))
            {
                return type.indexOf("landscape") === 0;
            }
            return window.innerWidth >= window.innerHeight;
        },

        fullscreenElement: function ()
        {
            return document.fullscreenElement || document.webkitFullscreenElement || null;
        },

        listen: function (state, target, type, handler, passive)
        {
            target.addEventListener(type, handler, { passive: !!passive });
            state.listeners.push({ target: target, type: type, handler: handler });
        },

        settle: function (operation, success, failure)
        {
            if (operation && typeof operation.then === "function")
            {
                // Handle browser rejections and callback failures; never leak a promise.
                Promise.resolve(operation).then(success, failure).catch(function () {});
            }
            else
            {
                success();
            }
        },

        refresh: function (state)
        {
            if (state.disposed || !state.overlay)
            {
                return;
            }
            var portrait = !NSC_MobileLandscape.isLandscape();
            var overlay = state.overlay;
            if (!portrait && typeof overlay.hidePopover === "function")
            {
                try { overlay.hidePopover(); } catch (ignored) {}
            }
            overlay.style.display = portrait ? "flex" : "none";
            overlay.setAttribute("aria-hidden", portrait ? "false" : "true");
            // Manual popover is non-modal and can sit above an existing canvas fullscreen.
            if (portrait && NSC_MobileLandscape.fullscreenElement() &&
                typeof overlay.showPopover === "function")
            {
                try
                {
                    overlay.setAttribute("popover", "manual");
                    if (!overlay.matches(":popover-open"))
                    {
                        overlay.showPopover();
                    }
                }
                catch (ignored) {}
            }
            state.button.disabled = state.fullscreenPending || state.lockPending;
            state.button.textContent = state.button.disabled ? "Entering landscape..." : "Enter landscape";
        },

        requestLock: function (state)
        {
            if (state.disposed || state.lockPending || state.hasLock)
            {
                return;
            }
            var orientation = window.screen && window.screen.orientation;
            if (!orientation || typeof orientation.lock !== "function")
            {
                NSC_MobileLandscape.refresh(state);
                return;
            }
            state.lockPending = true;
            state.lockOrientation = orientation;
            var requestId = ++state.lockRequestId;
            NSC_MobileLandscape.refresh(state);
            var failed = function ()
            {
                if (state.disposed || state.lockRequestId !== requestId) { return; }
                state.lockPending = false;
                NSC_MobileLandscape.refresh(state);
            };
            try
            {
                NSC_MobileLandscape.settle(orientation.lock("landscape"), function ()
                {
                    if (state.disposed || state.lockRequestId !== requestId) { return; }
                    state.lockPending = false;
                    state.hasLock = true;
                    NSC_MobileLandscape.refresh(state);
                }, failed);
            }
            catch (error)
            {
                failed();
            }
        },

        releaseLock: function (state)
        {
            state.lockRequestId++;
            if ((state.hasLock || state.lockPending) && state.lockOrientation &&
                typeof state.lockOrientation.unlock === "function")
            {
                try { state.lockOrientation.unlock(); } catch (ignored) {}
            }
            state.hasLock = false;
            state.lockPending = false;
        },

        requestLandscape: function (state)
        {
            if (state.disposed || state.fullscreenPending || state.lockPending)
            {
                return;
            }
            if (NSC_MobileLandscape.fullscreenElement())
            {
                NSC_MobileLandscape.requestLock(state);
                return;
            }
            // Fullscreen is requested only from our button or one trusted canvas gesture.
            // Use the document root so the rotate overlay remains inside fullscreen.
            var root = document.documentElement;
            var requestFullscreen = root.requestFullscreen || root.webkitRequestFullscreen;
            if (typeof requestFullscreen !== "function")
            {
                NSC_MobileLandscape.requestLock(state);
                return;
            }
            state.fullscreenPending = true;
            NSC_MobileLandscape.refresh(state);
            var finished = function ()
            {
                if (state.disposed) { return; }
                state.fullscreenPending = false;
                NSC_MobileLandscape.requestLock(state);
                NSC_MobileLandscape.refresh(state);
            };
            try
            {
                NSC_MobileLandscape.settle(requestFullscreen.call(root), finished, finished);
            }
            catch (error)
            {
                finished();
            }
        },

        createOverlay: function (state)
        {
            if (state.disposed || state.overlay || !document.body)
            {
                return;
            }
            var overlay = document.createElement("div");
            overlay.setAttribute("role", "region");
            overlay.setAttribute("aria-label", "Rotate your device");
            overlay.style.cssText = "position:fixed;inset:0;width:100%;height:100%;margin:0;" +
                "box-sizing:border-box;padding:32px;border:0;z-index:2147483647;" +
                "background:#0d0c16;color:#fff1df;display:none;flex-direction:column;" +
                "align-items:center;justify-content:center;gap:18px;text-align:center;" +
                "font-family:system-ui,sans-serif;touch-action:none;";
            var title = document.createElement("h1");
            title.textContent = "Rotate your device";
            title.style.cssText = "font-size:clamp(26px,6vw,40px);margin:0;";
            var description = document.createElement("p");
            description.textContent = "Turn your phone or tablet sideways to continue.";
            description.style.cssText = "font-size:18px;max-width:32rem;margin:0;line-height:1.5;";
            var button = document.createElement("button");
            button.type = "button";
            button.textContent = "Enter landscape";
            button.style.cssText = "font:600 18px system-ui,sans-serif;padding:14px 24px;" +
                "border:0;border-radius:8px;background:#e680ae;color:#201326;cursor:pointer;";
            var orientation = window.screen && window.screen.orientation;
            var root = document.documentElement;
            button.style.display = (orientation && typeof orientation.lock === "function") ||
                typeof root.requestFullscreen === "function" ||
                typeof root.webkitRequestFullscreen === "function" ? "block" : "none";
            overlay.appendChild(title);
            overlay.appendChild(description);
            overlay.appendChild(button);
            document.body.appendChild(overlay);
            state.overlay = overlay;
            state.button = button;
            NSC_MobileLandscape.listen(state, button, "click", function (event)
            {
                event.stopPropagation();
                if (event.isTrusted !== false)
                {
                    NSC_MobileLandscape.requestLandscape(state);
                }
            }, false);
            NSC_MobileLandscape.refresh(state);
        },

        initialize: function ()
        {
            if (typeof window === "undefined" || typeof document === "undefined" ||
                typeof navigator === "undefined" || !NSC_MobileLandscape.isMobileBrowser())
            {
                return;
            }
            if (NSC_MobileLandscape.state)
            {
                NSC_MobileLandscape.refresh(NSC_MobileLandscape.state);
                return;
            }
            var state = { disposed: false, listeners: [], overlay: null, button: null,
                fullscreenPending: false, lockPending: false, hasLock: false,
                lockOrientation: null, lockRequestId: 0, canvasGestureUsed: false };
            NSC_MobileLandscape.state = state;
            var refresh = function () { NSC_MobileLandscape.refresh(state); };
            NSC_MobileLandscape.listen(state, window, "resize", refresh, true);
            NSC_MobileLandscape.listen(state, window, "orientationchange", refresh, true);
            var orientation = window.screen && window.screen.orientation;
            if (orientation && typeof orientation.addEventListener === "function")
            {
                NSC_MobileLandscape.listen(state, orientation, "change", refresh, true);
            }
            var fullscreenChanged = function ()
            {
                if (!NSC_MobileLandscape.fullscreenElement())
                {
                    NSC_MobileLandscape.releaseLock(state);
                }
                else
                {
                    NSC_MobileLandscape.requestLock(state);
                }
                refresh();
            };
            NSC_MobileLandscape.listen(state, document, "fullscreenchange", fullscreenChanged, true);
            NSC_MobileLandscape.listen(state, document, "webkitfullscreenchange", fullscreenChanged, true);
            NSC_MobileLandscape.createOverlay(state);
            if (!document.body)
            {
                NSC_MobileLandscape.listen(state, document, "DOMContentLoaded", function ()
                {
                    NSC_MobileLandscape.createOverlay(state);
                }, true);
            }
            var canvas = typeof Module !== "undefined" && Module["canvas"] ?
                Module["canvas"] : document.getElementById("unity-canvas");
            if (canvas)
            {
                var gestureType = typeof window.PointerEvent !== "undefined" ? "pointerup" : "touchend";
                NSC_MobileLandscape.listen(state, canvas, gestureType, function (event)
                {
                    if (state.disposed || state.canvasGestureUsed || event.isTrusted === false ||
                        event.isPrimary === false)
                    {
                        return;
                    }
                    state.canvasGestureUsed = true;
                    // Observe the gesture without cancelling Unity's original input event.
                    NSC_MobileLandscape.requestLandscape(state);
                }, true);
            }
            if (NSC_MobileLandscape.fullscreenElement())
            {
                NSC_MobileLandscape.requestLock(state);
            }
        },

        dispose: function ()
        {
            var state = NSC_MobileLandscape.state;
            if (!state) { return; }
            state.disposed = true;
            NSC_MobileLandscape.state = null;
            for (var index = 0; index < state.listeners.length; index++)
            {
                var listener = state.listeners[index];
                listener.target.removeEventListener(listener.type, listener.handler, false);
            }
            if (state.overlay && state.overlay.parentNode)
            {
                state.overlay.parentNode.removeChild(state.overlay);
            }
            NSC_MobileLandscape.releaseLock(state);
            // Fullscreen belongs to the page/user. Never exit or hijack another owner's mode.
            // Pending promises retain this disposed state and cannot recreate UI or request locks.
        }
    },

    NSC_IsMobileBrowser__deps: ["$NSC_MobileLandscape"],
    NSC_IsMobileBrowser: function ()
    {
        return NSC_MobileLandscape.isMobileBrowser() ? 1 : 0;
    },

    NSC_InitializeMobileLandscape__deps: ["$NSC_MobileLandscape"],
    NSC_InitializeMobileLandscape: function ()
    {
        NSC_MobileLandscape.initialize();
    },

    NSC_DisposeMobileLandscape__deps: ["$NSC_MobileLandscape"],
    NSC_DisposeMobileLandscape: function ()
    {
        NSC_MobileLandscape.dispose();
    }
});
