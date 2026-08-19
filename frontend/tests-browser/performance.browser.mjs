import { test } from 'node:test';
import assert from 'node:assert/strict';

import { FULL_SCENE_GREETING } from './harness/fixtures.mjs';
import { waitForConnected } from './harness/open-page.mjs';

export function registerPerformanceTests({ withScene }) {
  test('camera input handler returns within 150 ms under invalidation rendering', async () => {
    const session = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(session);
      const latency = await session.page.evaluate(() => {
        const started = performance.now();
        const canvas = document.querySelector('#viewport-canvas');
        canvas.dispatchEvent(new WheelEvent('wheel', { deltaY: 120, cancelable: true }));
        return performance.now() - started;
      });
      assert.ok(latency < 150, `camera input waited ${latency.toFixed(1)} ms`);
    } finally {
      await session.dispose();
    }
  });
}
