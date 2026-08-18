import assert from 'node:assert/strict';

import { serverMessage } from './harness/fixtures.mjs';
import { waitForConnected } from './harness/open-page.mjs';

/** Register state and collision coverage for the compact top-bar run control. */
export function registerRunControlTests({ test, withScene, waitUntil, greeting }) {
  test('run controls never overlap connection status and show only the valid action', async () => {
    const session = await withScene(greeting);
    try {
      await session.page.setViewport({ width: 529, height: 720, deviceScaleFactor: 1 });
      await waitForConnected(session);

      const running = await waitUntil(
        () => session.page.evaluate(() => {
          const status = document.getElementById('connection-status')?.getBoundingClientRect();
          const group = document.querySelector('.run-group')?.getBoundingClientRect();
          const visibleActions = [...document.querySelectorAll('.run-group [data-action]')]
            .filter((button) => !button.hidden)
            .map((button) => button.dataset.action);
          const label = document.querySelector('[data-run-state-label]')?.textContent.trim();
          return status && group && label ? {
            gap: group.left - status.right,
            visibleActions,
            label,
          } : null;
        }),
        'a labelled run control',
      );
      assert.ok(running.gap >= 8, `connection status overlaps the run control by ${-running.gap}px`);
      assert.deepEqual(running.visibleActions, ['pause']);
      assert.equal(running.label, 'Running');

      session.wire.broadcast(serverMessage('run_state', 6, { text: 'paused' }));
      const paused = await waitUntil(
        () => session.page.evaluate(() => {
          const visibleActions = [...document.querySelectorAll('.run-group [data-action]')]
            .filter((button) => !button.hidden)
            .map((button) => button.dataset.action);
          const label = document.querySelector('[data-run-state-label]')?.textContent.trim();
          return label === 'Paused' && visibleActions[0] === 'resume'
            ? { visibleActions, label }
            : null;
        }),
        'the paused run control',
      );
      assert.deepEqual(paused.visibleActions, ['resume']);
      assert.equal(paused.label, 'Paused');
    } finally {
      await session.dispose();
    }
  });
}
