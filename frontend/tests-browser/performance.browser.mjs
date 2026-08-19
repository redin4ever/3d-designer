import { test } from 'node:test';
import assert from 'node:assert/strict';

import { FULL_SCENE_GREETING } from './harness/fixtures.mjs';
import { waitForCanvasDrawn } from './harness/canvas-probe.mjs';
import { waitForConnected } from './harness/open-page.mjs';

function gridMesh(size = 28) {
  const positions = [];
  const indices = [];
  for (let y = 0; y <= size; y += 1) {
    for (let x = 0; x <= size; x += 1) positions.push(x / size - 0.5, y / size - 0.5, 0);
  }
  const stride = size + 1;
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const a = y * stride + x;
      indices.push(a, a + 1, a + stride + 1, a, a + stride + 1, a + stride);
    }
  }
  return {
    object_id: 'semi-complex', positions, indices, normals: null, uvs: null,
    materials: ['surface'], groups: [], triangle_count: indices.length / 3,
  };
}

export function registerPerformanceTests({ withScene }) {
  test('camera input handler returns within 150 ms under invalidation rendering', async () => {
    const mesh = gridMesh();
    const greeting = FULL_SCENE_GREETING.map((message) => message.type === 'full_scene'
      ? {
        ...message,
        meshes: [mesh],
        transforms: [{ object_id: mesh.object_id, position: [0, 0, 0], quaternion: [0, 0, 0, 1], scale: [1, 1, 1] }],
        data: { preview: { simplified: true, source_triangles: 80_000, preview_triangles: mesh.triangle_count, budget: 40_000 } },
      }
      : message);
    const session = await withScene(greeting);
    try {
      await waitForConnected(session);
      await waitForCanvasDrawn(session.page, 100);
      const latency = await session.page.evaluate(() => {
        const started = performance.now();
        const canvas = document.querySelector('#viewport-canvas');
        canvas.dispatchEvent(new WheelEvent('wheel', { deltaY: 120, cancelable: true }));
        return performance.now() - started;
      });
      assert.ok(latency < 150, `camera input waited ${latency.toFixed(1)} ms`);
      assert.ok(
        await session.page.evaluate(
          () => [...document.querySelectorAll('#action-log li')].some((node) => /preview simplified/i.test(node.textContent)),
        ),
        'the viewport did not disclose that the preview was simplified',
      );
    } finally {
      await session.dispose();
    }
  });
}
