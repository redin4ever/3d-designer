import { test } from 'node:test';
import assert from 'node:assert/strict';

import { paintIdOutline } from '../src/point-outline.js';

function rgbAt(image, width, x, y) {
  const offset = (y * width + x) * 4;
  return [...image.slice(offset, offset + 3)];
}

test('a selected id gets a visible perimeter without changing the picking buffer', () => {
  const width = 7;
  const height = 7;
  const ids = new Int32Array(width * height);
  for (let y = 1; y <= 5; y += 1) {
    for (let x = 1; x <= 5; x += 1) ids[y * width + x] = 7;
  }
  const originalIds = ids.slice();
  const image = new Uint8ClampedArray(width * height * 4);

  const painted = paintIdOutline(image, ids, width, height, new Set([7]), [247, 248, 248], 1);

  assert.ok(painted >= 20, 'the perimeter should be large enough to read as an outline');
  assert.deepEqual(rgbAt(image, width, 3, 0), [247, 248, 248], 'the outline should halo the silhouette');
  assert.deepEqual(rgbAt(image, width, 3, 3), [0, 0, 0], 'the interior should retain its shaded fill');
  assert.deepEqual(ids, originalIds, 'presentation feedback must not alter picking');
});

test('nothing is painted when no visible id is targeted', () => {
  const image = new Uint8ClampedArray(4 * 4 * 4);
  const ids = new Int32Array(4 * 4).fill(3);

  assert.equal(paintIdOutline(image, ids, 4, 4, [9], [255, 255, 255], 2), 0);
  assert.ok(image.every((channel) => channel === 0));
});
