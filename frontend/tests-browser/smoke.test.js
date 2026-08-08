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
//
// Rule 2 soft cap, justified: `test:frontend:browser` names *this file* by path, and the
// root package.json is main-agent-only — a sibling file would never be run, so splitting
// along a seam here would silently delete tests rather than organise them.

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import { startStaticServer } from './harness/static-server.mjs';
import { startWireServer } from './harness/ws-server.mjs';
import {
  FULL_SCENE_GREETING,
  EMPTY_GREETING,
  replyToClient,
  serverMessage,
} from './harness/fixtures.mjs';
import {
  launchBrowser,
  openConsolePage,
  waitForConnected,
  waitForLogRows,
  complaints,
} from './harness/open-page.mjs';
import { probeCanvas, waitForCanvasDrawn } from './harness/canvas-probe.mjs';
import { registerConnectTests } from './connect.browser.mjs';

const FRONTEND_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
const NARROW = { width: 360, height: 720 };

/** Every conversation row currently on screen, in reading order. */
const transcriptRows = (page) =>
  page.evaluate(() =>
    [...document.querySelectorAll('#chat-transcript li')].map((li) => ({
      role: li.dataset.role ?? null,
      state: li.dataset.state ?? null,
      text: li.querySelector('.transcript-text')?.textContent ?? '',
      background: getComputedStyle(li).backgroundColor,
    })),
  );

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
        '/src/chat.css',
        '/src/connect.css',
        '/src/main.js',
        '/src/socket.js',
        '/src/viewport.js',
        '/src/scene-renderer.js',
        '/src/log.js',
        '/src/transcript.js',
        '/src/controls.js',
        '/src/connect.js',
        '/src/connect-ui.js',
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
      assert.ok(structure.liveRegions.includes('chat-transcript'), 'the transcript is an aria-live region');
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

  test('geometry does not pop in and out while the camera moves in close', async () => {
    // Reported: "i can see triangles dissapearing and reaapearing when moving my camera".
    // The projection divides by (camDist - z), and zoom scales camDist — at the closest
    // stop the camera sits inside the scene's own bounding radius, so geometry genuinely
    // passes behind the eye. That divisor used to be clamped rather than the triangle
    // clipped, which flung vertices thousands of pixels away and back.
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      await waitForCanvasDrawn(s.page, 500);

      const box = await s.page.$eval('#viewport-canvas', (el) => {
        const r = el.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      });
      await s.page.mouse.move(box.x, box.y);
      await s.page.mouse.wheel({ deltaY: -3000 }); // all the way in
      await new Promise((r) => setTimeout(r, 250));

      // Orbit in small steps. Every frame must stay a plausible render: never blank, and
      // never a single sliver smeared over the whole canvas.
      const samples = [];
      for (let i = 0; i < 8; i += 1) {
        await s.page.mouse.move(box.x, box.y);
        await s.page.mouse.down();
        await s.page.mouse.move(box.x + 18, box.y + 6, { steps: 3 });
        await s.page.mouse.up();
        await new Promise((r) => setTimeout(r, 90));
        const probe = await probeCanvas(s.page);
        samples.push(probe.nonModalPixels / probe.totalPixels);
      }

      for (const [i, share] of samples.entries()) {
        assert.ok(
          share > 0.01,
          `frame ${i}: the scene vanished (${(share * 100).toFixed(1)}% drawn) — ${JSON.stringify(samples)}`,
        );
      }
      assert.deepEqual(complaints(s).pageErrors, [], 'moving the camera in close must not throw');
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

  // The conversation panel. Before it existed you typed into the redirect box, the box
  // cleared, and the page showed nothing at all — no record, no confirmation, no reply.
  // These two cover the round trip the panel exists to make visible.

  test('a page refresh does not erase the conversation', async () => {
    // Reported: "if i refresh the chat gets cleared". The transcript lived only in the
    // page, so reloading showed an empty conversation while the run carried on around it.
    // The backend now replays it in the greeting — and because the whole greeting shares
    // one seq, those lines have to bypass the duplicate-seq rule or they are discarded in
    // silence and the fix does nothing at all.
    const replayed = [
      serverMessage('log', 4, { text: 'put a crate by the stairs', data: { role: 'operator', replayed: true } }),
      serverMessage('log', 4, { text: 'add_primitive applied (1 object)', data: { role: 'agent', replayed: true } }),
    ];
    const s = await withScene([...FULL_SCENE_GREETING, ...replayed]);
    try {
      await waitForConnected(s);

      const rows = await waitUntil(async () => {
        const all = await transcriptRows(s.page);
        return all.length >= 2 ? all : null;
      }, 'the replayed conversation to appear after a reconnect');

      const texts = rows.map((r) => r.text);
      assert.ok(
        texts.includes('put a crate by the stairs'),
        `the operator's line did not survive: ${JSON.stringify(texts)}`,
      );
      assert.ok(
        texts.includes('add_primitive applied (1 object)'),
        `the agent's line did not survive: ${JSON.stringify(texts)}`,
      );

      const operator = rows.find((r) => r.text === 'put a crate by the stairs');
      assert.equal(operator.role, 'operator', 'replayed history lost who said it');

      assert.deepEqual(complaints(s).pageErrors, []);
    } finally {
      await s.dispose();
    }
  });

  test('a message typed into the composer appears in the transcript and reaches the server', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      const words = 'add a garage door on the east wall';
      const mine = async () => (await transcriptRows(s.page)).filter((r) => r.text === words);

      await s.page.focus('#redirect-text');
      await s.page.keyboard.type(words);
      await s.page.keyboard.press('Enter');

      // Optimistic: the operator's line is on screen before the server has said a word
      // about it, because the agent will not even see it until its next tool call.
      const shown = await waitUntil(async () => {
        const rows = await mine();
        return rows.length === 1 ? rows : null;
      }, 'the operator line to appear in the transcript');
      assert.equal(shown[0].role, 'operator');
      assert.equal(shown[0].state, 'pending', 'nothing has confirmed delivery yet');

      const redirect = await waitUntil(
        () => s.wire.received.find((m) => m.type === 'redirect'),
        'the redirect to reach the fake socket server',
      );
      assert.equal(redirect.data.text, words);
      assert.equal(
        await s.page.$eval('#redirect-text', (el) => el.value),
        '',
        'the field must clear once the message is queued',
      );

      // The server echoes the operator's own words back once it has queued them; that
      // echo IS the delivery confirmation, so it must reconcile, never double-print.
      s.wire.broadcast(serverMessage('log', 6, { text: words, data: { role: 'operator' } }));
      await waitUntil(async () => (await mine())[0]?.state === 'confirmed', 'the echo to confirm the line');
      assert.equal((await mine()).length, 1, 'the echo printed the operator line a second time');

      // What "sent" means here is genuinely unusual, so it has to be said in the UI.
      const note = await s.page.evaluate(() => {
        const input = document.getElementById('redirect-text');
        const described = document.getElementById(input.getAttribute('aria-describedby'));
        return { text: described?.textContent.trim() ?? '', visible: described?.offsetParent !== null };
      });
      assert.ok(note.visible, 'the explanation must be on the page, not in a tooltip');
      assert.match(
        note.text,
        /next tool call/i,
        'the UI must say the agent picks the message up on its next tool call',
      );

      assert.deepEqual(complaints(s).pageErrors, [], 'sending a message must not throw');
      assert.deepEqual(complaints(s).consoleErrors, []);
    } finally {
      await s.dispose();
    }
  });

  test('operator, agent and role-less lines are told apart in the transcript', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      s.wire.broadcast(serverMessage('log', 6, { text: 'measured the gap: 3.2 mm', data: { role: 'agent' } }));
      s.wire.broadcast(serverMessage('log', 7, { text: 'an older backend sends no role' }));

      await s.page.focus('#redirect-text');
      await s.page.keyboard.type('raise the roof');
      await s.page.keyboard.press('Enter');

      const rows = await waitUntil(async () => {
        const seen = await transcriptRows(s.page);
        return seen.length >= 3 && seen.some((r) => r.text === 'raise the roof') ? seen : null;
      }, 'the agent, role-less and operator lines to all be on screen');

      const agent = rows.find((r) => r.text === 'measured the gap: 3.2 mm');
      const roleless = rows.find((r) => r.text === 'an older backend sends no role');
      const operator = rows.find((r) => r.text === 'raise the roof');

      assert.ok(agent, `the agent line never rendered: ${JSON.stringify(rows)}`);
      assert.equal(agent.role, 'agent');
      assert.ok(roleless, 'a LOG with no role must never make a message disappear');
      assert.equal(roleless.role, 'system', 'a missing role is treated as system');
      assert.ok(operator, 'the operator line never rendered');
      assert.equal(operator.role, 'operator');
      assert.notEqual(
        operator.background,
        agent.background,
        'operator and agent lines must be distinguishable at a glance — that is the whole point',
      );

      const live = await s.page.$eval('#chat-transcript', (el) => el.getAttribute('aria-live'));
      assert.equal(live, 'polite', 'assertive would interrupt a screen-reader user on every agent message');
      assert.deepEqual(complaints(s).pageErrors, []);
    } finally {
      await s.dispose();
    }
  });

  // The Connect button's own tests, registered here rather than written here: they are one
  // control with its own HTTP backend and its own modal, which is a responsibility seam
  // (Rule 2) — but `test:frontend:browser` names this file by path, so a sibling *file*
  // would never run. Registering into this describe gives them the seam and the one
  // browser and static server this suite already pays for.
  registerConnectTests({ withScene, waitUntil });

  // ---- pointing, priority and the edit tools --------------------------------------
  //
  // Written AFTER the wiring they cover, not before. That is a Rule 4 violation, and it is
  // recorded as one in docs/features/point-and-edit/FEATURE.md rather than glossed over: the
  // decisions underneath were all covered test-first in picking/annotate/capture/edit-tools,
  // but the DOM wiring itself was not, and the gate says so.

  test('pointing and the edit tools are wired into the real page', async () => {
    const s2 = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s2);

      // Point mode announces its state, or a screen-reader user cannot tell which mode
      // dragging is currently in — and dragging means two different things (Q-05).
      const before = await s2.page.$eval('[data-action="point-mode"]', (el) => el.getAttribute('aria-pressed'));
      await s2.page.click('[data-action="point-mode"]');
      const after = await s2.page.$eval('[data-action="point-mode"]', (el) => el.getAttribute('aria-pressed'));
      assert.equal(before, 'false');
      assert.equal(after, 'true', 'a screen reader could not tell point mode was on');

      // `hidden`, not merely invisible. A composer a keyboard user can tab into while it is
      // not on screen is a trap they cannot see their way out of.
      assert.equal(await s2.page.$eval('#point-composer', (el) => el.hidden), true);

      // Q-20: the tools are visible and refused, never absent. A control you cannot see is a
      // feature you do not know exists; one you can see and cannot use teaches you the rule.
      assert.equal(
        await s2.page.$eval('#edit-group', (el) => el.dataset.blocked),
        'true',
        'editing was offered while the run was neither paused nor connected',
      );

      // Q-13: a mark the operator put up has to be tellable from a change that happened to
      // them, so the two colours must not be the same one.
      const colors = await s2.page.evaluate(() => {
        const css = getComputedStyle(document.documentElement);
        return { marked: css.getPropertyValue('--marked').trim(), accent: css.getPropertyValue('--accent').trim() };
      });
      assert.ok(colors.marked, '--marked is not defined');
      assert.notEqual(colors.marked, colors.accent, 'a mark is indistinguishable from a change highlight');

      assert.deepEqual(s2.pageErrors, [], 'the pointing wiring threw on load');
    } finally {
      await s2.dispose();
    }
  });

  test('point mode visibly highlights hover and keeps a clicked part selected', async () => {
    const s2 = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s2);
      await waitForCanvasDrawn(s2.page, 500);
      await s2.page.click('[data-action="point-mode"]');

      // Find a stable interior scene pixel instead of assuming where the orbit projection
      // put a cube. Requiring a same-colour 3x3 neighbourhood keeps the probe off an edge.
      const sample = await s2.page.evaluate(() => {
        const canvas = document.getElementById('viewport-canvas');
        const ctx = canvas.getContext('2d');
        const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const rect = canvas.getBoundingClientRect();
        const keyAt = (x, y) => {
          const i = (y * canvas.width + x) * 4;
          return [...image.data.slice(i, i + 4)].join(',');
        };
        const background = keyAt(0, 0);
        for (let y = 1; y < canvas.height - 1; y += 1) {
          for (let x = 1; x < canvas.width - 1; x += 1) {
            const key = keyAt(x, y);
            if (key === background) continue;
            let solid = true;
            for (let dy = -1; dy <= 1; dy += 1) {
              for (let dx = -1; dx <= 1; dx += 1) {
                if (keyAt(x + dx, y + dy) !== key) solid = false;
              }
            }
            if (!solid) continue;
            return {
              x,
              y,
              before: key,
              clientX: rect.left + ((x + 0.5) * rect.width) / canvas.width,
              clientY: rect.top + ((y + 0.5) * rect.height) / canvas.height,
              outsideX: rect.right + 8,
              outsideY: rect.top + 8,
            };
          }
        }
        return null;
      });
      assert.ok(sample, 'could not find an interior object pixel to point at');

      const pixel = () =>
        s2.page.evaluate(({ x, y }) => {
          const canvas = document.getElementById('viewport-canvas');
          const data = canvas.getContext('2d').getImageData(x, y, 1, 1).data;
          return [...data].join(',');
        }, sample);

      await s2.page.mouse.move(sample.clientX, sample.clientY);
      await waitUntil(async () => {
        const value = await pixel();
        return value !== sample.before ? value : null;
      }, 'the part under the point cursor to change colour');

      await s2.page.mouse.click(sample.clientX, sample.clientY);
      await waitUntil(
        () => s2.page.$eval('#point-composer', (element) => element.hidden === false),
        'the clicked part to become selected',
      );
      await s2.page.mouse.move(sample.outsideX, sample.outsideY);
      const afterLeave = await s2.page.evaluate(({ x, y }) => {
        const canvas = document.getElementById('viewport-canvas');
        const data = canvas.getContext('2d').getImageData(x, y, 1, 1).data;
        return {
          pixel: [...data].join(','),
          selection: document.getElementById('point-selection')?.textContent ?? '',
          composerHidden: document.getElementById('point-composer')?.hidden,
        };
      }, sample);
      assert.notEqual(
        afterLeave.pixel,
        sample.before,
        `leaving the part cleared the committed selection highlight: ${JSON.stringify(afterLeave)}`,
      );

      await s2.page.click('[data-action="close-composer"]');
      await waitUntil(async () => (await pixel()) === sample.before, 'clearing selection to restore the prior colour');
      assert.deepEqual(complaints(s2).pageErrors, []);
    } finally {
      await s2.dispose();
    }
  });
});
