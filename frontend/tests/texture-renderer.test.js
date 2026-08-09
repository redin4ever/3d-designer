import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  createTextureCache,
  normalizeModulo,
  perspectiveCorrectUv,
  resolveMaterialGroup,
  sampleRgba,
  transformUv,
} from '../src/texture-renderer.js';

const texture = {
  width: 2,
  height: 2,
  data: new Uint8ClampedArray([
    255, 0, 0, 255, 0, 255, 0, 255,
    0, 0, 255, 255, 255, 255, 255, 255,
  ]),
};

test('samples deterministic RGBA texels with repeat wrapping', () => {
  assert.deepEqual(sampleRgba(texture, [0.1, 0.1]), [255, 0, 0, 255]);
  assert.deepEqual(sampleRgba(texture, [1.1, 0.1]), [255, 0, 0, 255]);
  assert.deepEqual(sampleRgba(texture, [-0.1, 0.1]), [0, 255, 0, 255]);
});

test('normalizes negative modulo into the positive interval', () => {
  assert.equal(normalizeModulo(-0.25, 1), 0.75);
  assert.equal(normalizeModulo(-5, 3), 1);
  assert.equal(normalizeModulo(7, 3), 1);
});

test('applies repeat, rotation, and offset to UV coordinates', () => {
  const uv = transformUv([0.25, 0.5], {
    repeat: [2, 3],
    rotation: Math.PI / 2,
    offset: [0.1, -0.2],
  });
  assert.ok(Math.abs(uv[0] - 0.6) < 1e-10);
  assert.ok(Math.abs(uv[1] - 0.3) < 1e-10);
});

test('perspective-corrects UV interpolation using reciprocal W', () => {
  const uv = perspectiveCorrectUv([
    { uv: [0, 0], invW: 1 },
    { uv: [1, 0], invW: 0.5 },
    { uv: [0, 1], invW: 0.5 },
  ], [0.2, 0.4, 0.4]);
  assert.deepEqual(uv.map((value) => Number(value.toFixed(6))), [0.285714, 0.285714]);
});

test('resolves the material group covering a triangle index', () => {
  const groups = [
    { start: 0, count: 2, material_index: 3 },
    { start: 2, count: 4, material_index: 7 },
  ];
  assert.deepEqual(resolveMaterialGroup(groups, 0), groups[0]);
  assert.deepEqual(resolveMaterialGroup(groups, 3), groups[1]);
  assert.equal(resolveMaterialGroup(groups, 8), null);
});

test('async texture cache deduplicates loads and falls back deterministically', async () => {
  let calls = 0;
  const fallback = [17, 19, 23, 255];
  const cache = createTextureCache({
    fallback,
    loadImage: async (source) => {
      calls += 1;
      return source === 'wood' ? texture : null;
    },
  });
  const [first, second, missing] = await Promise.all([
    cache.load('wood'),
    cache.load('wood'),
    cache.load('missing'),
  ]);
  assert.strictEqual(first, texture);
  assert.strictEqual(second, texture);
  assert.deepEqual(missing, fallback);
  assert.equal(calls, 2);
  assert.strictEqual(cache.get('wood'), texture);
  cache.clear();
  assert.deepEqual(cache.get('wood'), fallback);
});

