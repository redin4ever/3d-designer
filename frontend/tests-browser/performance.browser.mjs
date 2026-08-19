import { test } from 'node:test';
import assert from 'node:assert/strict';

import { serverMessage, transform } from './harness/fixtures.mjs';
import { waitForConnected } from './harness/open-page.mjs';

function gridMesh(size = 72) {
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
    object_id: 'semi-complex',
    positions,
    indices,
    normals: null,
    uvs: null,
    materials: ['surface'],
    groups: [],
    triangle_count: indices.length / 3,
  };
}

export function registerPerformanceTests({ withScene }) {
  test('semi-complex preview accepts camera input within 150 ms and discloses simplification', async () => {
    const mesh = gridMesh();
    const greeting = [
      serverMessage('hello', 0, { data: { wire_version: 1, scene_id: 'performance' } }),
      serverMessage('full_scene', 1, {
        meshes: [mesh],
        transforms: [transform(mesh.object_id, [0, 0, 0])],
        data: { preview: { simplified: true, source_triangles: 80_000, preview_triangles: mesh.triangle_count, budget: 40_000 } },
      }),
    ];
    const session = await withScene(greeting);
    try {
      await waitForConnected(session);
      await session.page.waitForFunction(
        () => [...document.querySelectorAll('#action-log li')].some((node) => /preview simplified/i.test(node.textContent)),
      );
      const latency = await session.page.evaluate(() => new Promise((resolve) => {
        const started = performance.now();
        setTimeout(() => {
          const canvas = document.querySelector('#scene-canvas');
          canvas.dispatchEvent(new WheelEvent('wheel', { deltaY: 120, cancelable: true }));
          resolve(performance.now() - started);
        }, 0);
      }));
      assert.ok(latency < 150, `camera input waited ${latency.toFixed(1)} ms`);
    } finally {
      await session.dispose();
    }
  });
}
