import assert from 'node:assert/strict';

import { serverMessage } from './harness/fixtures.mjs';
import { waitForConnected } from './harness/open-page.mjs';

/** Register state and collision coverage for the compact top-bar run control. */
export function registerRunControlTests({ test, withScene, waitUntil, greeting }) {
  test('Pause and Run never overlap status and only the valid action is enabled', async () => {
    const session = await withScene(greeting);
    try {
      await session.page.setViewport({ width: 529, height: 720, deviceScaleFactor: 1 });
      await waitForConnected(session);

      const running = await waitUntil(
        () => session.page.evaluate(() => {
          const status = document.getElementById('connection-status')?.getBoundingClientRect();
          const group = document.querySelector('.run-group')?.getBoundingClientRect();
          const actions = [...document.querySelectorAll('.run-group [data-action]')]
            .map((button) => ({ action: button.dataset.action, disabled: button.disabled, text: button.textContent.trim() }));
          const label = document.querySelector('[data-run-state-label]')?.textContent.trim();
          return status && group && label ? {
            gap: group.left - status.right,
            actions,
            label,
          } : null;
        }),
        'a labelled run control',
      );
      assert.ok(running.gap >= 8, `connection status overlaps the run control by ${-running.gap}px`);

      const commandRects = await session.page.evaluate(() => {
        const selectors = [
          '.brand-lockup',
          '#file-menu-button',
          '#connection-status',
          '#connect-button',
          '.run-group',
          '.settings-menu',
        ];
        return selectors.map((selector) => {
          const rect = document.querySelector(selector)?.getBoundingClientRect();
          return rect ? { selector, left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom } : null;
        }).filter(Boolean);
      });
      for (let left = 0; left < commandRects.length; left += 1) {
        for (let right = left + 1; right < commandRects.length; right += 1) {
          const a = commandRects[left];
          const b = commandRects[right];
          const overlaps = a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
          assert.equal(overlaps, false, `${a.selector} overlaps ${b.selector} at 529px`);
        }
      }
      assert.deepEqual(running.actions, [
        { action: 'pause', disabled: false, text: 'Pause' },
        { action: 'resume', disabled: true, text: 'Run' },
      ]);
      assert.equal(running.label, 'Running');

      session.wire.broadcast(serverMessage('run_state', 6, { text: 'paused' }));
      const paused = await waitUntil(
        () => session.page.evaluate(() => {
          const actions = [...document.querySelectorAll('.run-group [data-action]')]
            .map((button) => ({ action: button.dataset.action, disabled: button.disabled, text: button.textContent.trim() }));
          const label = document.querySelector('[data-run-state-label]')?.textContent.trim();
          return label === 'Paused' && actions[0]?.disabled && actions[1]?.disabled === false
            ? { actions, label }
            : null;
        }),
        'the paused run control',
      );
      assert.deepEqual(paused.actions, [
        { action: 'pause', disabled: true, text: 'Pause' },
        { action: 'resume', disabled: false, text: 'Run' },
      ]);
      assert.equal(paused.label, 'Paused');
    } finally {
      await session.dispose();
    }
  });
}
