// Real Chromium, fixture-only HTTP; never connects to the operator's browser.
const {test, before, after, beforeEach, afterEach} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const ids = Array.from({length: 8}, (_, i) => `NSC-${1001 + i}`);
let browser, context, page, errors;
before(async () => {
  browser = await chromium.launch(process.env.NSC_VIEW_CHROMIUM
    ? {executablePath: process.env.NSC_VIEW_CHROMIUM} : {});
});
after(async () => { if (browser) await browser.close(); });
beforeEach(async () => {
  context = await browser.newContext({viewport: {width: 1440, height: 900}});
  await context.route('**/*', route => new URL(route.request().url()).origin === process.env.NSC_VIEW_TEST_URL
    ? route.continue() : route.abort());
  page = await context.newPage();
  errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(process.env.NSC_VIEW_TEST_URL);
  await page.waitForFunction(() => typeof snapshot !== 'undefined' && snapshot !== null);
});
afterEach(async () => {
  await context.close();
  assert.deepEqual(errors, [], 'No browser JavaScript errors');
});
const box = selector => page.locator(selector).boundingBox();
const near = (a, b, message) => assert.ok(Math.abs(a - b) <= 2, `${message}: ${a} vs ${b}`);
async function control(selector) {
  assert.equal(await page.locator(selector).count(), 1, `Missing usable control ${selector}`);
  return page.locator(selector);
}
async function reload() {
  await page.reload();
  await page.waitForFunction(() => snapshot !== null);
}
async function drag(selector, dx, dy) {
  await control(selector);
  const b = await box(selector);
  assert.ok(b, `Visible resize handle ${selector}`);
  const x = b.x + b.width / 2, y = b.y + b.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, {steps: 6});
  await page.mouse.up();
}
async function assertEight() {
  assert.deepEqual(await page.evaluate(() => cy.nodes().map(n => n.id()).sort()), ids);
}
async function screenshot(name) {
  if (process.env.NSC_VIEW_SCREENSHOTS) {
    fs.mkdirSync(process.env.NSC_VIEW_SCREENSHOTS, {recursive: true});
    await page.screenshot({path: path.join(process.env.NSC_VIEW_SCREENSHOTS, name + '.png')});
  }
}

test('explicit eight-task scope renders with one-task run and survives reload', async () => {
  const state = await (await context.request.get(process.env.NSC_VIEW_TEST_URL + '/api/state')).json();
  assert.deepEqual(state.tasks.map(t => t.id), ids);
  assert.equal(state.run.targets.length, 1);
  await assertEight();
  await reload();
  await assertEight();
  await screenshot('eight-tasks-compact');
});
test('run filter is optional, persisted, and does not replace display selection', async () => {
  await assertEight();
  await page.locator('#f-scope').check();
  assert.equal(await page.evaluate(() => cy.nodes().length), 1);
  await reload();
  assert.equal(await page.evaluate(() => cy.nodes().length), 1);
  await page.locator('#f-scope').uncheck();
  await assertEight();
});
test('pipeline starts compact and graph remains primary', async () => {
  const panel = await box('#pipeline-activity'), graph = await box('#cy');
  assert.ok(panel.height <= 200, `Initial panel height ${panel.height} must be compact`);
  assert.ok(graph.height > 2 * panel.height);
});
test('pipeline collapses, preserves stage, releases space and persists', async () => {
  const toggle = await control('#pipeline-toggle');
  const before = await box('#cy');
  const headline = await page.locator('#pipeline-headline').textContent();
  await toggle.click();
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
  assert.equal(await page.locator('#pipeline-body').isVisible(), false);
  assert.equal(await page.locator('#pipeline-headline').textContent(), headline);
  assert.ok((await box('#cy')).height > before.height + 60);
  await reload();
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
  await toggle.focus();
  await page.keyboard.press('Enter');
  assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
  near((await box('#cy')).height, before.height, 'Expanded graph height');
});
test('pipeline drag grows/shrinks, bounds height and persists selected size', async () => {
  await control('#pipeline-resize');
  const before = await box('#pipeline-activity');
  await drag('#pipeline-resize', 0, 100);
  assert.ok((await box('#pipeline-activity')).height > before.height + 80);
  await screenshot('pipeline-larger');
  const grown = await box('#pipeline-activity');
  await reload();
  near((await box('#pipeline-activity')).height, grown.height, 'Saved pipeline height');
  await drag('#pipeline-resize', 0, -2000);
  const small = await box('#pipeline-activity');
  assert.ok(small.height >= 120 && small.height <= 160);
  await screenshot('pipeline-smaller');
  await drag('#pipeline-resize', 0, 3000);
  assert.ok((await box('#pipeline-activity')).height <= 450);
  assert.ok((await box('#cy')).height >= 400);
});
test('detail collapse releases width, persists and selection never reopens it', async () => {
  const toggle = await control('#detail-toggle');
  const before = await box('#cy');
  await toggle.click();
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
  assert.ok((await box('#cy')).width > before.width + 200);
  await page.evaluate(() => cy.getElementById('NSC-1002').emit('tap'));
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
  assert.match(await page.locator('#detail').textContent(), /NSC-1002/);
  await reload();
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
  await toggle.focus();
  await page.keyboard.press('Space');
  assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
  near((await box('#cy')).width, before.width, 'Expanded graph width');
});
test('detail drag bounds width, reclaims space and persists', async () => {
  await control('#detail-resize');
  const before = await box('#cy');
  await drag('#detail-resize', -100, 0);
  assert.ok((await box('#cy')).width < before.width - 80);
  const width = (await box('#detail-panel')).width;
  await reload();
  near((await box('#detail-panel')).width, width, 'Saved detail width');
  await drag('#detail-resize', 3000, 0);
  assert.ok((await box('#detail-panel')).width >= 220);
  assert.ok((await box('#detail-panel')).width <= 260);
  await drag('#detail-resize', -3000, 0);
  assert.ok((await box('#detail-panel')).width <= 560);
  assert.ok((await box('#cy')).width >= 360);
});
test('resize handles support keyboard and expose accessible values', async () => {
  for (const [id, key] of [['#pipeline-resize', 'ArrowDown'], ['#detail-resize', 'ArrowLeft']]) {
    const handle = await control(id);
    assert.equal(await handle.getAttribute('role'), 'separator');
    assert.ok(await handle.getAttribute('aria-label'));
    const before = Number(await handle.getAttribute('aria-valuenow'));
    await handle.focus();
    await page.keyboard.press(key);
    assert.ok(Number(await handle.getAttribute('aria-valuenow')) > before);
    await page.keyboard.press('End');
    assert.equal(await handle.getAttribute('aria-valuenow'), await handle.getAttribute('aria-valuemax'));
    await page.keyboard.press('Home');
    assert.equal(await handle.getAttribute('aria-valuenow'), await handle.getAttribute('aria-valuemin'));
  }
});
test('both collapsed panels yield graph area, SSE keeps scope and saved layout', async () => {
  await (await control('#pipeline-toggle')).click();
  await (await control('#detail-toggle')).click();
  const before = await box('#cy');
  const nextCycle = 2;
  fs.writeFileSync(process.env.NSC_VIEW_TEST_PROGRESS, JSON.stringify({poll_cycles_total: nextCycle}));
  await page.waitForFunction(value => snapshot.run.progress.poll_cycles_total === value, nextCycle);
  await assertEight();
  assert.equal(await page.locator('#pipeline-toggle').getAttribute('aria-expanded'), 'false');
  assert.equal(await page.locator('#detail-toggle').getAttribute('aria-expanded'), 'false');
  near((await box('#cy')).width, before.width, 'SSE graph width');
  near((await box('#cy')).height, before.height, 'SSE graph height');
  await screenshot('both-collapsed');
});
test('fit and zoom use actual resized viewport without moving graph nodes', async () => {
  await control('#pipeline-resize');
  const positions = await page.evaluate(() => cy.nodes().map(n => n.position()));
  await drag('#pipeline-resize', 0, 120);
  await drag('#detail-resize', -150, 0);
  await page.locator('#fit').click();
  const actual = await page.evaluate(() => ({width: cy.width(), height: cy.height(),
    bounds: cy.nodes().renderedBoundingBox(), positions: cy.nodes().map(n => n.position())}));
  const graph = await box('#cy');
  near(actual.width, graph.width, 'Cytoscape width');
  near(actual.height, graph.height, 'Cytoscape height');
  assert.deepEqual(actual.positions, positions);
  assert.ok(actual.bounds.x1 >= 0 && actual.bounds.y1 >= 0);
  assert.ok(actual.bounds.x2 <= graph.width && actual.bounds.y2 <= graph.height);
  const center = await page.evaluate(() => ({x: (cy.width()/2 - cy.pan().x)/cy.zoom(), y: (cy.height()/2 - cy.pan().y)/cy.zoom()}));
  await page.locator('#zin').click();
  const next = await page.evaluate(() => ({x: (cy.width()/2 - cy.pan().x)/cy.zoom(), y: (cy.height()/2 - cy.pan().y)/cy.zoom()}));
  near(center.x, next.x, 'Zoom anchor x'); near(center.y, next.y, 'Zoom anchor y');
});
test('desktop viewport changes clamp panels and keep controls accessible', async () => {
  await drag('#detail-resize', -2000, 0);
  await drag('#pipeline-resize', 0, 2000);
  for (const viewport of [{width: 1280, height: 720}, {width: 1024, height: 768}]) {
    await page.setViewportSize(viewport);
    await page.waitForFunction(() => Math.abs(cy.width() - document.getElementById('cy').clientWidth) < 2);
    const graph = await box('#cy');
    assert.ok(graph.width >= 350 && graph.height >= 300);
    assert.ok((await box('#detail-panel')).x + (await box('#detail-panel')).width <= viewport.width + 1);
    await page.locator('#fit').click();
    assert.ok(await page.locator('#fit').isVisible());
  }
  await screenshot('desktop-1024');
});
test('task details preserve workflow labels and exact Issue and PR links', async () => {
  await page.evaluate(() => showDetail('NSC-1001'));
  assert.match(await page.locator('#detail').textContent(), /Task Needs You/);
  assert.equal(await page.getByRole('link', {name: 'Open GitHub Issue'}).getAttribute('href'),
    'https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/issues/112');
  assert.equal(await page.locator('#detail a[href$="/pull/116"]').count(), 1);
});
test('out-of-range saved sizes are clamped and corrupt preferences recover', async () => {
  await page.evaluate(() => localStorage.setItem('nsc.gauntlet.panels.v1', JSON.stringify({
    pipelineHeight: 99999, detailWidth: -1000,
  })));
  await reload();
  assert.ok((await box('#pipeline-activity')).height <= 450);
  assert.ok((await box('#detail-panel')).width >= 220);
  await page.evaluate(() => localStorage.setItem('nsc.gauntlet.panels.v1', 'broken JSON'));
  await reload();
  near((await box('#pipeline-activity')).height, 176, 'Recovered initial height');
  near((await box('#detail-panel')).width, 320, 'Recovered initial width');
  await assertEight();
});
test('blocked localStorage still allows scope, collapse and drag in this session', async () => {
  await context.addInitScript(() => Object.defineProperty(window, 'localStorage', {
    get() { throw new DOMException('Storage disabled', 'SecurityError'); },
  }));
  await reload();
  await assertEight();
  await drag('#pipeline-resize', 0, 60);
  await drag('#detail-resize', -60, 0);
  await (await control('#pipeline-toggle')).click();
  await (await control('#detail-toggle')).click();
  assert.equal(await page.locator('#pipeline-toggle').getAttribute('aria-expanded'), 'false');
  assert.equal(await page.locator('#detail-toggle').getAttribute('aria-expanded'), 'false');
});
