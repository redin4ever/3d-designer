// The browser smoke suite (Gate B 2.2, cut back to a smoke test at Gate B 6.1).
//
// Everything under frontend/tests/ is pure logic — it imports the ES modules and asserts
// on them with no DOM at all. Nothing had ever checked that index.html renders, that the
// Canvas2D renderer puts pixels on screen, that a CSS custom property resolves, or that a
// keyboard reaches the controls. This file is the only place in the project where a real
// browser evaluates this frontend.
//
// It runs against a real HTTP origin (Chrome blocks `type="module"` over file://) and a
// real WebSocket server speaking src/contracts/wire.py's envelope with canned payloads —
// no Python, no Blender, per the brief. It must FAIL, not skip, when the browser is
// unavailable: there is no try/catch around the launch and no conditional skip anywhere
// in this file, because a browser test that passes without opening a browser is worse
// than no browser test at all.

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import { startStaticServer } from './harness/static-server.mjs';
import { startWireServer } from './harness/ws-server.mjs';
import { FULL_SCENE_GREETING, EMPTY_GREETING, replyToClient } from './harness/fixtures.mjs';
import {
  launchBrowser,
  openConsolePage,
  waitForConnected,
  waitForLogRows,
  complaints,
} from './harness/open-page.mjs';
import { probeCanvas, waitForCanvasDrawn } from './harness/canvas-probe.mjs';

const FRONTEND_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
const NARROW = { width: 360, height: 720 };

/** Poll a predicate to a deadline. No sleeps anywhere in this suite (Rule 4). */
async function waitUntil(predicate, description, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = await predicate();
    if (value) return value;
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${description}`);
    await new Promise((done) => setTimeout(done, 50));
  }
}

describe('frontend smoke — a real browser, a real origin, a real socket', () => {
  let browser;
  let statics;

  before(async () => {
    browser = await launchBrowser();
    statics = await startStaticServer(FRONTEND_DIR);
  });

  after(async () => {
    await browser?.close();
    await statics?.close();
  });

  /** Open the console against a fresh wire server; caller closes both. */
  async function withScene(greeting, pageOptions = {}) {
    const wire = await startWireServer({ greeting, onClientMessage: replyToClient });
    const session = await openConsolePage(browser, {
      origin: statics.origin,
      wsUrl: wire.url,
      ...pageOptions,
    });
    return {
      ...session,
      wire,
      async dispose() {
        await session.close();
        await wire.close();
      },
    };
  }

  test('index.html loads with zero console errors and zero uncaught exceptions', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      await waitForLogRows(s, 4);

      assert.deepEqual(s.pageErrors, [], 'an uncaught exception on load still paints a page that looks fine');
      assert.deepEqual(s.consoleErrors, [], 'the browser logged an error while loading the console');
      assert.deepEqual(s.failedRequests, [], 'a request the page made never completed');
      assert.deepEqual(s.badResponses, [], 'the page asked for something the server could not serve');
    } finally {
      await s.dispose();
    }
  });

  test('every stylesheet and ES module index.html pulls in is actually served', async () => {
    const from = statics.requests.length;
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      const served = statics.requests.slice(from);
      const paths = served.map((r) => r.path);

      for (const expected of [
        '/index.html',
        '/src/tokens.css',
        '/src/app.css',
        '/src/main.js',
        '/src/socket.js',
        '/src/viewport.js',
        '/src/scene-renderer.js',
        '/src/log.js',
        '/src/controls.js',
      ]) {
        assert.ok(paths.includes(expected), `${expected} was never requested — the module graph did not load`);
      }
      assert.deepEqual(
        served.filter((r) => r.status !== 200),
        [],
        'every asset must answer 200; a 404 stylesheet renders an unstyled page, not a broken one',
      );
    } finally {
      await s.dispose();
    }
  });

  test('the page exposes the main landmark and the h1, in the live DOM', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      const structure = await s.page.evaluate(() => ({
        mains: document.querySelectorAll('main').length,
        h1s: [...document.querySelectorAll('h1')].map((h) => h.textContent.trim()),
        mainHasContent: document.querySelector('main')?.querySelector('canvas') !== null,
        liveRegions: [...document.querySelectorAll('[aria-live]')].map((el) => el.id),
        labelledInputs: [...document.querySelectorAll('input, select')].every(
          (el) => document.querySelector(`label[for="${el.id}"]`) !== null,
        ),
      }));

      assert.equal(structure.mains, 1, 'exactly one <main> landmark');
      assert.deepEqual(structure.h1s, ['forge3d'], 'exactly one <h1>, naming the product');
      assert.ok(structure.mainHasContent, 'the 3D view must be inside the main landmark');
      assert.ok(structure.liveRegions.includes('action-log'), 'the action log is an aria-live region');
      assert.ok(structure.liveRegions.includes('connection-status'), 'the status pill is an aria-live region');
      assert.ok(structure.labelledInputs, 'every input and select has a real <label for=...>');
    } finally {
      await s.dispose();
    }
  });

  test('the action log renders one row per narrative message from the wire', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      await waitForLogRows(s, 6);
      const rows = await s.page.evaluate(() =>
        [...document.querySelectorAll('#action-log li')].map((li) => ({
          text: li.textContent.trim(),
          kind: li.dataset.kind ?? null,
        })),
      );

      const texts = rows.map((r) => r.text);
      assert.ok(texts.includes('connected'), `expected a "connected" row, got ${JSON.stringify(texts)}`);
      assert.ok(texts.includes('hello — wire v1'), 'the HELLO message must reach the log');
      assert.ok(texts.includes('full scene — 2 objects'), 'the FULL_SCENE object count must reach the log');
      assert.ok(texts.includes('phase → shell'), 'a PHASE message must reach the log');
      assert.ok(texts.some((t) => t.startsWith('changed: wall.south')), 'HIGHLIGHT must reach the log');
      assert.ok(
        rows.some((r) => r.kind === 'highlight'),
        'log rows must carry their kind so app.css can colour them',
      );
    } finally {
      await s.dispose();
    }
  });

  test('the 3D canvas is sized in device pixels and actually draws the scene', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      await waitForCanvasDrawn(s.page, 500);
      const probe = await probeCanvas(s.page);

      assert.ok(probe.width > 0 && probe.height > 0, `canvas backing store is ${probe.width}x${probe.height}`);
      assert.ok(probe.cssWidth > 0 && probe.cssHeight > 0, `canvas lays out at ${probe.cssWidth}x${probe.cssHeight}`);
      assert.ok(
        probe.distinctColors > 1,
        `canvas is a single flat colour (${probe.modalColor}) — nothing was drawn`,
      );
      assert.ok(
        probe.nonModalPixels >= 500,
        `only ${probe.nonModalPixels} of ${probe.totalPixels} pixels differ from the background`,
      );
    } finally {
      await s.dispose();
    }
  });

  // These three exist because a user opened the page and found the view would only turn
  // left and right — no tilt, no zoom, and it span on its own the whole time. None of it
  // was catchable: the camera lived inside scene-renderer.js, the one file this module's
  // own docs exempt from node:test. The arithmetic now lives in camera.js and is unit
  // tested; these assert that the arithmetic is actually *wired to the input events*,
  // which is the half a unit test cannot see.

  test('dragging up and down changes the view, not just left and right', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      await waitForCanvasDrawn(s.page, 500);

      const box = await s.page.$eval('#viewport-canvas', (el) => {
        const r = el.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      });

      const before = (await probeCanvas(s.page)).signature;

      await s.page.mouse.move(box.x, box.y);
      await s.page.mouse.down();
      await s.page.mouse.move(box.x, box.y - 120, { steps: 8 }); // straight up, no x at all
      await s.page.mouse.up();
      await new Promise((r) => setTimeout(r, 200));

      const after = (await probeCanvas(s.page)).signature;
      assert.notEqual(after, before, 'a purely vertical drag left the render identical');
      assert.deepEqual(complaints(s).pageErrors, []);
    } finally {
      await s.dispose();
    }
  });

  test('the wheel zooms, and does not scroll the page instead', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      await waitForCanvasDrawn(s.page, 500);

      const box = await s.page.$eval('#viewport-canvas', (el) => {
        const r = el.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      });
      const before = (await probeCanvas(s.page)).nonModalPixels;

      await s.page.mouse.move(box.x, box.y);
      await s.page.mouse.wheel({ deltaY: -400 }); // toward the viewer
      await new Promise((r) => setTimeout(r, 200));

      const after = (await probeCanvas(s.page)).nonModalPixels;
      assert.ok(
        after > before,
        `zooming in must cover more pixels, went ${before} -> ${after}`,
      );

      const scrolled = await s.page.evaluate(() => window.scrollY);
      assert.equal(scrolled, 0, 'the wheel scrolled the page instead of zooming the view');
      assert.deepEqual(complaints(s).pageErrors, []);
    } finally {
      await s.dispose();
    }
  });

  test('the view holds still when nobody is touching it', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      await waitForCanvasDrawn(s.page, 500);

      // Settle first: the greeting's objects arrive over several frames, so an immediate
      // probe catches the scene mid-arrival and would fail for a reason that is not drift.
      let settled = (await probeCanvas(s.page)).signature;
      for (let i = 0; i < 25; i += 1) {
        await new Promise((r) => setTimeout(r, 120));
        const next = (await probeCanvas(s.page)).signature;
        if (next === settled) break;
        settled = next;
      }

      await new Promise((r) => setTimeout(r, 1500));
      const later = (await probeCanvas(s.page)).signature;

      assert.equal(later, settled, 'the view drifted on its own — it used to auto-rotate');
    } finally {
      await s.dispose();
    }
  });

  test('a connected-but-empty scene leaves the canvas flat — the pixel check discriminates', async () => {
    const s = await withScene(EMPTY_GREETING);
    try {
      await waitForConnected(s);
      await waitForLogRows(s, 3);
      const probe = await probeCanvas(s.page);

      assert.equal(
        probe.distinctColors,
        1,
        `an empty scene must clear to one flat colour, saw ${probe.distinctColors}`,
      );
      assert.equal(probe.nonModalPixels, 0, 'nothing may be drawn when the scene has no objects');
    } finally {
      await s.dispose();
    }
  });

  test('no horizontal page scroll at a narrow viewport', async () => {
    const s = await withScene(FULL_SCENE_GREETING, { viewport: NARROW });
    try {
      await waitForConnected(s);
      await waitForLogRows(s, 4);
      const overflow = await s.page.evaluate(() => {
        const doc = document.documentElement;
        const widest = [...document.querySelectorAll('body *')]
          .map((el) => ({ el: el.tagName + (el.id ? `#${el.id}` : `.${el.className}`), right: el.getBoundingClientRect().right }))
          .filter((e) => e.right > doc.clientWidth + 1)
          .sort((a, b) => b.right - a.right)
          .slice(0, 5);
        return {
          scrollWidth: doc.scrollWidth,
          clientWidth: doc.clientWidth,
          bodyScrollWidth: document.body.scrollWidth,
          innerWidth: window.innerWidth,
          widest,
        };
      });

      assert.ok(
        overflow.scrollWidth <= overflow.clientWidth,
        `page scrolls sideways at ${NARROW.width}px: ${overflow.scrollWidth} > ${overflow.clientWidth}; ` +
          `widest offenders ${JSON.stringify(overflow.widest)}`,
      );
      assert.ok(
        overflow.bodyScrollWidth <= overflow.innerWidth,
        `body overflows the viewport: ${overflow.bodyScrollWidth} > ${overflow.innerWidth}`,
      );
    } finally {
      await s.dispose();
    }
  });

  for (const scheme of ['dark', 'light']) {
    test(`the theme resolves and renders under prefers-color-scheme: ${scheme}`, async () => {
      const s = await withScene(FULL_SCENE_GREETING, { colorScheme: scheme });
      try {
        await waitForConnected(s);
        await waitForCanvasDrawn(s.page, 500);
        const theme = await s.page.evaluate(() => {
          const root = getComputedStyle(document.documentElement);
          const body = getComputedStyle(document.body);
          const token = (name) => root.getPropertyValue(name).trim();
          return {
            declaredColorScheme: root.colorScheme,
            usedColorScheme: body.colorScheme,
            unresolved: ['--canvas', '--ink', '--muted', '--accent', '--accent-focus', '--surface-1', '--hairline']
              .filter((name) => token(name) === ''),
            bodyBackground: body.backgroundColor,
            bodyColor: body.color,
            bannerBackground: getComputedStyle(document.getElementById('connection-banner')).backgroundColor,
          };
        });

        assert.deepEqual(theme.unresolved, [], 'a CSS custom property the renderer reads did not resolve');
        assert.notEqual(theme.bodyBackground, theme.bodyColor, 'text must not be the same colour as the page');
        assert.notEqual(theme.bodyBackground, 'rgba(0, 0, 0, 0)', 'the page background token did not apply');
        // Chrome serialises a resolved `color-mix(in srgb, …)` as `color(srgb r g b / a)`,
        // not as `rgb(...)`. Asserting the `rgb` prefix tested the serialisation form
        // rather than the thing that matters, which is that the mix resolved at all: an
        // unsupported or malformed color-mix() is an invalid declaration, so
        // background-color falls back to the transparent initial value and the banner's
        // text sits directly on the 3D view with nothing behind it.
        assert.match(
          theme.bannerBackground,
          /^(?:rgba?|color)\(/,
          `the connection banner's background did not resolve to a colour: ${theme.bannerBackground}`,
        );
        assert.notEqual(
          theme.bannerBackground,
          'rgba(0, 0, 0, 0)',
          'color-mix() was dropped as invalid — the banner scrim is fully transparent',
        );
        assert.ok(
          theme.declaredColorScheme.includes('dark'),
          `this is a dark-only design (DESIGN.md), so :root must declare color-scheme: dark — ` +
            `otherwise a light-theme browser draws light scrollbars and light select popups over it. ` +
            `Saw "${theme.declaredColorScheme}".`,
        );

        const probe = await probeCanvas(s.page);
        assert.ok(probe.nonModalPixels >= 500, `the scene did not draw under prefers-color-scheme: ${scheme}`);
        assert.deepEqual(complaints(s).pageErrors, [], 'no uncaught exception under either scheme');
      } finally {
        await s.dispose();
      }
    });
  }

  test('a keyboard alone can drive the controls, and focus is visible', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);

      const describeFocus = () =>
        s.page.evaluate(() => {
          const el = document.activeElement;
          const style = getComputedStyle(el);
          return {
            tag: el.tagName,
            id: el.id || null,
            action: el.dataset?.action ?? null,
            outlineWidth: style.outlineWidth,
            outlineStyle: style.outlineStyle,
          };
        });

      // The 3D view is the first stop, and that is deliberate: it is a control now, not
      // decoration. Arrow keys orbit it and +/- zoom, so a keyboard user who could never
      // reach it could never look at the thing this product exists to build. It used to be
      // skipped entirely because a <canvas> is not focusable without tabindex.
      await s.page.keyboard.press('Tab');
      const viewport = await describeFocus();
      assert.equal(viewport.id, 'viewport-canvas', `first Tab must reach the 3D view, reached ${JSON.stringify(viewport)}`);
      assert.notEqual(viewport.outlineStyle, 'none', ':focus-visible must draw a ring on the view too');

      await s.page.keyboard.press('Tab');
      const focused = await describeFocus();
      assert.equal(focused.action, 'pause', `Tab from the view must reach Pause, reached ${JSON.stringify(focused)}`);
      assert.notEqual(focused.outlineStyle, 'none', ':focus-visible must draw a ring on keyboard focus');
      assert.notEqual(focused.outlineWidth, '0px', 'the focus ring must have a width');

      await s.page.keyboard.press('Enter');
      await waitUntil(
        () => s.wire.received.some((m) => m.type === 'pause'),
        'the pause message to reach the server',
      );

      await s.page.focus('#redirect-text');
      await s.page.keyboard.type('add a garage door on the east wall');
      await s.page.keyboard.press('Enter');
      const redirect = await waitUntil(
        () => s.wire.received.find((m) => m.type === 'redirect'),
        'the redirect message to reach the server',
      );
      assert.equal(redirect.data.text, 'add a garage door on the east wall');

      const cleared = await s.page.$eval('#redirect-text', (el) => el.value);
      assert.equal(cleared, '', 'the redirect field must clear after sending');
      assert.deepEqual(s.pageErrors, [], 'driving the controls must not throw');
      assert.deepEqual(s.consoleErrors, [], 'driving the controls must not log an error');
    } finally {
      await s.dispose();
    }
  });
});
