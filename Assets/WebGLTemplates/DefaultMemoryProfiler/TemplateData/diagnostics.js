// Optional floating diagnostics for Unity 6000.6 GetMetricsInfo().
var unityDiagnostics = (function () {
  var overlay, header, summary, graph, status, intervalId = 0, readMetrics;
  var rows = [], graphPanels = [], compact, drag;
  var smallViewport = window.matchMedia('(max-width: 700px), (max-height: 480px)');
  var mobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  var fields = [
    ['totalWASMHeapSize', 'Total WASM heap', 'wasmTotalMem', 'bytes', true],
    ['usedWASMHeapSize', 'Used WASM heap', 'wasmUsedMem', 'bytes', true],
    ['fps', 'FPS', 'fps', 'number', true],
    ['totalJSHeapSize', 'Total JS memory', 'jsTotalMem', 'bytes'],
    ['usedJSHeapSize', 'Used JS memory', 'jsUsedMem', 'bytes'],
    ['movingAverageFps', 'Average FPS (10 seconds)', 'movingAverageFps', 'number'],
    ['numJankedFrames', 'Frame stalls', 'numJankedFrames', 'integer'],
    ['pageLoadTimeToFrame1', 'Load to first frame', 'pageLoadTimeToFrame1', 'time'],
    ['pageLoadTime', 'Page load', 'pageLoadTime', 'time'],
    ['codeDownloadTime', 'Code download', 'codeDownloadTime', 'time'],
    ['assetLoadTime', 'Asset load', 'assetLoadTime', 'time'],
    ['webAssemblyStartupTime', 'WASM startup', 'webAssemblyStartupTime', 'time'],
    ['gameStartupTime', 'Game startup', 'gameStartupTime', 'time']
  ];
  var inputEvents = ['pointerdown', 'pointermove', 'pointerup', 'pointercancel',
    'mousedown', 'mousemove', 'mouseup', 'click', 'dblclick', 'contextmenu',
    'touchstart', 'touchmove', 'touchend', 'touchcancel', 'wheel', 'keydown', 'keyup'];

  function stopGameInput(event) {
    event.stopPropagation();
    if (event.type === 'keydown' && event.key === 'Escape') closeOverlay();
  }

  function viewport() {
    var view = window.visualViewport;
    var style = getComputedStyle(overlay);
    function inset(side) { return parseFloat(style.getPropertyValue('--diag-safe-' + side)) || 0; }
    var left = (view ? view.offsetLeft : 0) + inset('left') + 12;
    var top = (view ? view.offsetTop : 0) + inset('top') + 12;
    return { left: left, top: top,
      right: (view ? view.offsetLeft + view.width : window.innerWidth) - inset('right') - 12,
      bottom: (view ? view.offsetTop + view.height : window.innerHeight) - inset('bottom') - 12 };
  }

  function clamp(value, min, max) { return Math.max(min, Math.min(value, Math.max(min, max))); }

  function showFloating(element) {
    if (!element || element.hidden || typeof element.showPopover !== 'function') return;
    element.setAttribute('popover', 'manual');
    try { if (!element.matches(':popover-open')) element.showPopover(); } catch (_) {}
  }

  function hideFloating(element) {
    if (!element || typeof element.hidePopover !== 'function') return;
    try { if (element.matches(':popover-open')) element.hidePopover(); } catch (_) {}
  }

  function positionCard(reset) {
    if (!overlay || overlay.hidden) return;
    var bounds = viewport();
    overlay.style.width = Math.max(0, Math.min(compact ? 280 : 600, bounds.right - bounds.left)) + 'px';
    overlay.style.maxHeight = Math.max(0, bounds.bottom - bounds.top) + 'px';
    var size = overlay.getBoundingClientRect();
    var left = reset ? bounds.right - size.width : parseFloat(overlay.style.left);
    var top = reset ? bounds.bottom - size.height : parseFloat(overlay.style.top);
    overlay.style.left = clamp(Number.isFinite(left) ? left : bounds.left, bounds.left, bounds.right - size.width) + 'px';
    overlay.style.top = clamp(Number.isFinite(top) ? top : bounds.top, bounds.top, bounds.bottom - size.height) + 'px';
  }

  function moveToFullscreen() {
    var parent = document.fullscreenElement || document.body;
    if (overlay && overlay.parentNode !== parent) {
      hideFloating(overlay);
      parent.appendChild(overlay);
    }
    showFloating(overlay);
    positionCard(false);
  }

  // The game's rotate prompt may enter the top layer after an orientation change.
  function onGamePopover(event) {
    if (event.newState !== 'open' || event.target.getAttribute('aria-label') !== 'Rotate your device') return;
    if (overlay && !overlay.hidden) {
      hideFloating(overlay);
      showFloating(overlay);
    }
  }

  function resize() {
    if (!overlay || overlay.hidden) return;
    update();
    positionCard(false);
  }

  function startDrag(event) {
    if (event.button !== 0 || event.isPrimary === false || event.target.closest('button')) return;
    var rect = overlay.getBoundingClientRect();
    drag = { id: event.pointerId, x: event.clientX - rect.left, y: event.clientY - rect.top };
    header.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function moveDrag(event) {
    if (!drag || drag.id !== event.pointerId) return;
    overlay.style.left = event.clientX - drag.x + 'px';
    overlay.style.top = event.clientY - drag.y + 'px';
    positionCard(false);
  }

  function endDrag(event) {
    if (!drag || drag.id !== event.pointerId) return;
    drag = null;
    if (header.hasPointerCapture(event.pointerId)) header.releasePointerCapture(event.pointerId);
  }

  function createLayout() {
    overlay = document.createElement('section');
    overlay.id = 'diagnostics-overlay';
    overlay.hidden = true;
    overlay.setAttribute('role', 'region');
    overlay.setAttribute('aria-label', 'Memory diagnostics');
    header = document.createElement('div');
    header.id = 'diagnostics-header';
    var title = document.createElement('strong');
    title.textContent = 'Memory';
    var hint = document.createElement('span');
    hint.textContent = 'Drag to move';
    var close = document.createElement('button');
    close.id = 'diagnostics-btn';
    close.type = 'button';
    close.textContent = '\u00d7';
    close.setAttribute('aria-label', 'Close memory diagnostics');
    close.addEventListener('click', closeOverlay);
    header.append(title, hint, close);
    var content = document.createElement('div');
    content.id = 'diagnostics-content';
    summary = document.createElement('div');
    summary.id = 'diagnostics-summary';
    graph = document.createElement('div');
    graph.id = 'diagnostics-graph';
    status = document.createElement('div');
    status.id = 'diagnostics-status';
    status.hidden = true;
    content.append(summary, graph, status);
    overlay.append(header, content);
    inputEvents.forEach(function (name) { overlay.addEventListener(name, stopGameInput); });
    header.addEventListener('pointerdown', startDrag);
    header.addEventListener('pointermove', moveDrag);
    header.addEventListener('pointerup', endDrag);
    header.addEventListener('pointercancel', endDrag);
    header.addEventListener('lostpointercapture', function () { drag = null; });
    window.addEventListener('resize', resize);
    document.addEventListener('fullscreenchange', moveToFullscreen);
    document.addEventListener('toggle', onGamePopover, true);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', resize);
      window.visualViewport.addEventListener('scroll', resize);
    }
    moveToFullscreen();
  }

  function createRow(field) {
    var row = document.createElement('div');
    row.className = 'data-row';
    row.dataset.metric = field[0];
    var label = document.createElement('span');
    label.className = 'label';
    label.textContent = field[1];
    var value = document.createElement('span');
    value.id = field[2];
    value.className = 'data';
    row.append(label, value);
    summary.appendChild(row);
    return { element: row, value: value, field: field };
  }

  function setMode(nextCompact) {
    if (compact === nextCompact && rows.length) return;
    compact = nextCompact;
    overlay.classList.toggle('diagnostics-compact', compact);
    summary.replaceChildren();
    graph.replaceChildren();
    rows = fields.filter(function (field) { return !compact || field[4]; }).map(createRow);
    graphPanels = [];
    graph.hidden = compact;
  }

  function formatBytes(value) {
    var units = ['B', 'KB', 'MB', 'GB'], unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
    return (unit ? value.toFixed(1) : Math.round(value)) + ' ' + units[unit];
  }

  function formatMetric(value, kind) {
    if (kind === 'bytes') return formatBytes(value);
    if (kind === 'time') return (value / 1000).toFixed(2) + ' sec';
    if (kind === 'integer') return Math.round(value).toString();
    return value.toFixed(1);
  }

  function update() {
    var metrics;
    try { metrics = readMetrics() || {}; }
    catch (_) { metrics = {}; }
    setMode(mobile || smallViewport.matches);
    var visible = 0;
    rows.forEach(function (row) {
      var value = metrics[row.field[0]];
      row.element.hidden = !Number.isFinite(value) || value < 0;
      if (!row.element.hidden) { row.value.textContent = formatMetric(value, row.field[3]); visible++; }
    });
    status.hidden = visible > 0;
    status.textContent = visible ? '' : 'Memory diagnostics unavailable';
    if (!compact) updateGraphs(metrics);
    positionCard(false);
  }

  function updateGraphs(metrics) {
    var specs = [
      ['fps', 'FPS', '#7ff', '#102a32', ''],
      ['movingAverageFps', 'Average FPS', '#8fa', '#122c25', ''],
      ['usedWASMHeapSize', 'Used WASM', '#ffe599', '#29291c', ' MB', 1048576],
      ['usedJSHeapSize', 'Used JS', '#ffb388', '#2e201a', ' MB', 1048576]
    ];
    specs.forEach(function (spec, index) {
      var available = Number.isFinite(metrics[spec[0]]) && metrics[spec[0]] >= 0;
      var panel = graphPanels[index];
      if (!available) { if (panel) panel.canvas.hidden = true; return; }
      if (!panel) {
        panel = graphPanels[index] = GraphPanel(spec[1], spec[2], spec[3]);
        panel.canvas.dataset.metric = spec[0];
        graph.appendChild(panel.canvas);
      }
      panel.canvas.hidden = false;
      panel.update(metrics[spec[0]] / (spec[5] || 1), spec[4]);
    });
  }

  function closeOverlay() {
    clearInterval(intervalId);
    intervalId = 0;
    readMetrics = null;
    drag = null;
    hideFloating(overlay);
    if (overlay) overlay.hidden = true;
    var icon = document.getElementById('diagnostics-icon');
    if (icon) {
      icon.hidden = false;
      icon.setAttribute('aria-expanded', 'false');
      showFloating(icon);
    }
  }

  function openDiagnosticsDiv(getMetrics) {
    if (typeof getMetrics !== 'function') return;
    if (intervalId) return;
    var resetPosition = !overlay || !overlay.style.left;
    readMetrics = getMetrics;
    if (!overlay) createLayout();
    overlay.hidden = false;
    update();
    showFloating(overlay);
    positionCard(resetPosition);
    var icon = document.getElementById('diagnostics-icon');
    if (icon) {
      hideFloating(icon);
      icon.hidden = true;
      icon.setAttribute('aria-expanded', 'true');
    }
    intervalId = setInterval(update, 1000);
  }

  function destroy() {
    closeOverlay();
    window.removeEventListener('resize', resize);
    document.removeEventListener('fullscreenchange', moveToFullscreen);
    document.removeEventListener('toggle', onGamePopover, true);
    if (window.visualViewport) {
      window.visualViewport.removeEventListener('resize', resize);
      window.visualViewport.removeEventListener('scroll', resize);
    }
    if (overlay) overlay.remove();
    overlay = header = summary = graph = status = null;
    rows = graphPanels = [];
    compact = undefined;
  }

  function GraphPanel(name, color, background) {
    var canvas = document.createElement('canvas');
    canvas.className = 'diagnostics-graph-canvas';
    canvas.width = 250;
    canvas.height = 150;
    var context = canvas.getContext('2d'), max = 0;
    context.font = 'bold 13px Arial,sans-serif';
    context.textBaseline = 'top';
    context.fillStyle = background;
    context.fillRect(0, 0, 250, 150);
    return { canvas: canvas, update: function (value, unit) {
      max = Math.max(max, value);
      context.fillStyle = background; context.fillRect(0, 0, 250, 28);
      context.fillStyle = color; context.textAlign = 'left'; context.fillText(name, 8, 8);
      context.textAlign = 'right'; context.fillText(value.toFixed(1) + unit, 242, 8);
      context.drawImage(canvas, 9, 30, 233, 112, 8, 30, 233, 112);
      context.fillStyle = background; context.fillRect(241, 30, 1, 112);
      context.fillStyle = color;
      var height = Math.round(112 * value / Math.max(1, max));
      context.fillRect(241, 142 - height, 1, height);
    } };
  }

  return { openDiagnosticsDiv: openDiagnosticsDiv, closeDiagnosticsDiv: closeOverlay, destroy: destroy };
})();
