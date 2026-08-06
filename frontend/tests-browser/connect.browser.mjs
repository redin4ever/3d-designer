// The Connect button's browser coverage, registered into smoke.test.js's suite.
//
// Split out of smoke.test.js along a responsibility seam (Rule 2): that file is the page's
// smoke test — it loads, it draws, it speaks the wire protocol — and this is one control
// with its own backend, its own three-way branch and its own modal. It is not a second
// entry point: `test:frontend:browser` names smoke.test.js by path and the root
// package.json is main-agent-only, so this registers into that file's describe block
// rather than standing alone, where nothing would ever run it.
//
// (The file-size hook reads the `.mjs` extension and applies the 300-line source cap. This
// is a test file: the budget is 1.5×, and it is inside it.)

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { FULL_SCENE_GREETING } from './harness/fixtures.mjs';
import { complaints, waitForConnected } from './harness/open-page.mjs';

// The Connect button is the only control on this page that talks to the HTTP origin rather
// than the socket, so the wire harness cannot exercise it — `fetch` is stubbed in the page
// instead, after load, which is why connect.js resolves the global at call time rather than
// capturing it at import. What is being checked is the branch: a machine with no AI client,
// one, and several are three genuinely different screens, and the one that is wrong is
// invisible until a user with that machine hits it.

/** Canned answers for /api/clients and /api/connect, recording every call the page made. */
async function stubConnectApi(page, canned) {
  await page.evaluate((replies) => {
    window.__connectCalls = [];
    window.fetch = async (url, init) => {
      const path = String(url);
      window.__connectCalls.push({
        url: path,
        method: init?.method ?? 'GET',
        body: init?.body ?? null,
      });
      const reply = path.includes('/api/connect') ? replies.connect : replies.clients;
      return {
        ok: reply.status >= 200 && reply.status < 300,
        status: reply.status,
        json: async () => reply.payload,
      };
    };
  }, canned);
}

const CONNECT_BUTTON = '#connect-button';
/** Whatever the dialog is currently saying — the picker, the result, or nothing. */
const connectSaid = (page) =>
  page.$eval('#connect-dialog-body', (el) => el.textContent.replace(/\s+/g, ' ').trim());
const connectCalls = (page) => page.evaluate(() => window.__connectCalls ?? []);
const dialogOpen = (page) => page.evaluate(() => document.querySelector('#connect-dialog')?.open === true);

const clientRow = (over = {}) => ({
  id: 'claude-code',
  label: 'Claude Code',
  transport: 'stdio',
  config_path: 'C:\\Users\\someone\\.claude.json',
  configured: false,
  note: 'Or run:  claude mcp add forge3d -- python -X utf8 -m mcp_server',
  ...over,
});

/**
 * Register the Connect tests into the calling suite.
 *
 * Called from inside smoke.test.js's `describe` body, which node:test runs synchronously
 * — so every `test()` below lands in that suite, sharing its one browser and one static
 * server. Called anywhere else and these become top-level tests that run before the
 * browser exists, and every one of them fails on a fixture that is not there yet.
 *
 * @param {{withScene: Function, waitUntil: Function}} suite the host suite's fixtures
 */
export function registerConnectTests({ withScene, waitUntil }) {
  test('the Connect button sits in the conversation panel, lifted rather than shouting', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);

      const look = await s.page.evaluate((selector) => {
        const button = document.querySelector(selector);
        if (!button) return null;
        const panel = button.closest('.chat-panel') ?? button.parentElement;
        const style = getComputedStyle(button);
        const root = getComputedStyle(document.documentElement);
        return {
          text: button.textContent.trim(),
          tag: button.tagName,
          type: button.getAttribute('type'),
          inConversationPanel: button.closest('.chat-panel') !== null,
          background: style.backgroundColor,
          panelBackground: getComputedStyle(panel).backgroundColor,
          boxShadow: style.boxShadow,
          accent: root.getPropertyValue('--accent').trim(),
          describedBy: button.getAttribute('aria-describedby'),
          note: document.getElementById(button.getAttribute('aria-describedby'))?.textContent.trim() ?? '',
          // The panel must not pay for this button in height: the conversation is what the
          // operator uses continuously, and a five-line setup result rendered inline
          // squeezed the transcript to nothing.
          panelChrome: [...document.querySelector('.chat-panel').children]
            .filter((el) => el !== document.querySelector('.panel-header'))
            .map((el) => el.tagName + (el.id ? `#${el.id}` : '')),
        };
      }, CONNECT_BUTTON);

      assert.ok(look, 'there is no Connect button on the page at all');
      assert.equal(look.text, 'Connect');
      assert.equal(look.tag, 'BUTTON');
      assert.equal(look.type, 'button', 'an untyped button inside a form would submit it');
      assert.ok(look.inConversationPanel, 'the button belongs to the conversation panel');
      assert.notEqual(
        look.background,
        look.panelBackground,
        'a button the same colour as the panel behind it is not lifted off it, it is invisible',
      );
      assert.notEqual(look.boxShadow, 'none', 'the elevation must actually render, not just be declared');
      assert.notEqual(
        look.background,
        look.accent,
        'this is a quiet raised control, not a bright call-to-action competing with Send',
      );

      // Connecting writes a file and does nothing to this page. A user who thinks
      // otherwise waits here for an agent that is going to appear somewhere else.
      assert.ok(look.describedBy, 'the button must point at the line explaining what it does');
      assert.match(look.note, /config/i, 'say that it writes a config file');
      assert.match(
        look.note,
        /next time|starts/i,
        'say that the tools appear the next time the client starts, not now',
      );

      assert.deepEqual(
        look.panelChrome,
        ['OL#chat-transcript', 'FORM'],
        'the conversation panel gains the button and nothing else — a setup step run once ' +
          'must not permanently shrink the panel the operator reads all day',
      );
      assert.deepEqual(complaints(s).pageErrors, []);
    } finally {
      await s.dispose();
    }
  });

  test('a keyboard alone reaches Connect and can press it', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      await stubConnectApi(s.page, {
        clients: { status: 200, payload: { clients: [] } },
        connect: { status: 200, payload: {} },
      });

      const seen = [];
      let reached = false;
      for (let i = 0; i < 15 && !reached; i += 1) {
        await s.page.keyboard.press('Tab');
        const where = await s.page.evaluate(() => {
          const el = document.activeElement;
          const style = getComputedStyle(el);
          return { id: el.id || el.tagName, outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
        });
        seen.push(where.id);
        if (where.id === 'connect-button') {
          reached = true;
          assert.notEqual(where.outlineStyle, 'none', ':focus-visible must draw a ring on Connect too');
          assert.notEqual(where.outlineWidth, '0px', 'the focus ring must have a width');
        }
      }
      assert.ok(reached, `Tab never reached the Connect button; stops were ${JSON.stringify(seen)}`);

      await s.page.keyboard.press('Enter');
      await waitUntil(async () => (await connectCalls(s.page)).length > 0, 'Enter to fire the client lookup');
      assert.deepEqual(complaints(s).pageErrors, []);
    } finally {
      await s.dispose();
    }
  });

  test('with no AI client on the machine, Connect says so and names the fallback', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      await stubConnectApi(s.page, {
        clients: { status: 200, payload: { clients: [] } },
        connect: { status: 200, payload: {} },
      });

      await s.page.click(CONNECT_BUTTON);
      const said = await waitUntil(
        async () => (await connectSaid(s.page)) || null,
        'the empty-machine message to appear',
      );

      assert.match(said, /forge3d connect/, `the terminal fallback must be named; got "${said}"`);
      assert.doesNotMatch(said, /error|failed/i, 'no clients installed is a normal machine, not a failure');
      const choices = await s.page.evaluate(() => document.querySelectorAll('[data-client-id]').length);
      assert.equal(choices, 0, 'an empty list must never render a picker with nothing in it');
      const calls = await connectCalls(s.page);
      assert.equal(calls.filter((c) => c.url.includes('/api/connect')).length, 0, 'nothing to connect to');
      assert.deepEqual(complaints(s).pageErrors, []);
    } finally {
      await s.dispose();
    }
  });

  test('with exactly one AI client, Connect writes it without making anyone choose', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      const only = clientRow();
      await stubConnectApi(s.page, {
        clients: { status: 200, payload: { clients: [only] } },
        connect: {
          status: 200,
          payload: { ok: true, client: only.id, path: only.config_path, note: only.note },
        },
      });

      await s.page.click(CONNECT_BUTTON);
      const posted = await waitUntil(
        async () => (await connectCalls(s.page)).find((c) => c.url.includes('/api/connect')) ?? null,
        'the connect POST to be sent for the only client found',
      );
      assert.equal(posted.method, 'POST');
      assert.deepEqual(JSON.parse(posted.body), { client: 'claude-code' });

      const choices = await s.page.evaluate(() => document.querySelectorAll('[data-client-id]').length);
      assert.equal(choices, 0, 'nobody picks from a list of one');

      const said = await waitUntil(
        async () => {
          const text = await connectSaid(s.page);
          return text.includes('.claude.json') ? text : null;
        },
        'the written path to be reported back',
      );
      assert.match(said, /Restart/i, 'without a restart the client shows no tools and looks broken');
      assert.match(said, /Claude Code/, 'the restart instruction must name the client');
      assert.ok(said.includes('claude mcp add forge3d'), `the client's own note must be surfaced: "${said}"`);

      const after = await s.page.evaluate(() => {
        const note = document.getElementById('connect-dialog-note');
        const body = document.getElementById('connect-dialog-body');
        const restart = [...body.querySelectorAll('p')].find((p) => /^Restart/.test(p.textContent));
        const ordinary = [...body.querySelectorAll('p')].find((p) => /^Nothing changed/.test(p.textContent));
        return {
          open: document.getElementById('connect-dialog').open,
          noteVisible: note.offsetParent !== null,
          note: note.textContent.replace(/\s+/g, ' ').trim(),
          focused: document.activeElement?.dataset?.action ?? null,
          restartColor: restart ? getComputedStyle(restart).color : null,
          ordinaryColor: ordinary ? getComputedStyle(ordinary).color : null,
        };
      });
      assert.notEqual(
        after.restartColor,
        after.ordinaryColor,
        'the restart line decides whether the user thinks this worked — it cannot be styled ' +
          'as just another muted line to skim past',
      );
      assert.equal(after.open, true, 'the result has to be somewhere the user can actually read it');
      assert.ok(after.noteVisible, 'what "connect" means must be on screen, not in a tooltip');
      assert.match(after.note, /nothing connects/i, 'say plainly that nothing connected just now');
      assert.equal(
        after.focused,
        'connect-cancel',
        'focus must land on the way out; left on a removed button it falls to the top of the page',
      );

      await s.page.keyboard.press('Escape');
      await waitUntil(async () => (await dialogOpen(s.page)) === false, 'Escape to dismiss the result');
      assert.equal(
        await s.page.evaluate(() => document.activeElement?.id ?? null),
        'connect-button',
        'focus must return to the button that opened it',
      );
      assert.deepEqual(complaints(s).pageErrors, []);
    } finally {
      await s.dispose();
    }
  });

  test('with several AI clients, Connect opens a picker that Escape closes and returns focus', async () => {
    const s = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(s);
      const rows = [
        clientRow({ id: 'claude-desktop', label: 'Claude Desktop', configured: true }),
        clientRow(),
        clientRow({ id: 'cursor', label: 'Cursor', config_path: 'C:\\Users\\someone\\.cursor\\mcp.json' }),
      ];
      await stubConnectApi(s.page, {
        clients: { status: 200, payload: { clients: rows } },
        connect: {
          status: 200,
          payload: { ok: true, client: 'cursor', path: rows[2].config_path, note: 'Settings -> MCP shows it.' },
        },
      });

      await s.page.click(CONNECT_BUTTON);
      const dialog = await waitUntil(
        async () =>
          (await s.page.evaluate(() => {
            const el = document.querySelector('#connect-dialog');
            if (!el?.open) return null;
            const labelledBy = el.getAttribute('aria-labelledby');
            return {
              choices: [...el.querySelectorAll('[data-client-id]')].map((b) => ({
                id: b.dataset.clientId,
                text: b.textContent.replace(/\s+/g, ' ').trim(),
              })),
              name: document.getElementById(labelledBy)?.textContent.trim() ?? el.getAttribute('aria-label') ?? '',
              focusInside: el.contains(document.activeElement),
            };
          })) ?? null,
        'the picker to open with focus inside it',
      );

      assert.equal(dialog.choices.length, 3, 'every client found must be offered');
      assert.ok(dialog.name.length > 0, 'a dialog with no reachable name is unannounceable');
      assert.ok(dialog.focusInside, 'a modal that leaves focus behind it is a keyboard trap in reverse');
      const already = dialog.choices.find((c) => c.id === 'claude-desktop');
      assert.match(
        already.text,
        /already/i,
        `a client that already has forge3d must say so before it is picked: ${JSON.stringify(dialog.choices)}`,
      );

      await s.page.keyboard.press('Escape');
      const afterEscape = await waitUntil(
        async () =>
          (await s.page.evaluate(() => ({
            open: document.querySelector('#connect-dialog')?.open === true,
            focused: document.activeElement?.id ?? null,
          }))) ?? null,
        'the picker to close on Escape',
      );
      assert.equal(afterEscape.open, false, 'Escape must dismiss the picker');
      assert.equal(afterEscape.focused, 'connect-button', 'focus must come back to the button that opened it');
      assert.equal(
        (await connectCalls(s.page)).filter((c) => c.url.includes('/api/connect')).length,
        0,
        'dismissing must not write anything',
      );

      // Reopen and pick one with the keyboard alone.
      await s.page.keyboard.press('Enter');
      await waitUntil(
        () => s.page.evaluate(() => document.querySelector('#connect-dialog')?.open === true),
        'the picker to reopen',
      );
      await s.page.evaluate(() => document.querySelector('[data-client-id="cursor"]').focus());
      await s.page.keyboard.press('Enter');

      const posted = await waitUntil(
        async () => (await connectCalls(s.page)).find((c) => c.url.includes('/api/connect')) ?? null,
        'the chosen client to be written',
      );
      assert.deepEqual(JSON.parse(posted.body), { client: 'cursor' });
      const said = await waitUntil(
        async () => {
          const text = await connectSaid(s.page);
          return text.includes('mcp.json') ? text : null;
        },
        'the chosen client’s path to be reported',
      );
      assert.match(said, /Restart/i);
      assert.match(said, /Cursor/, 'the result must name the client that was picked, not the first one');
      assert.deepEqual(complaints(s).pageErrors, []);
      assert.deepEqual(complaints(s).consoleErrors, []);
    } finally {
      await s.dispose();
    }
  });
}
