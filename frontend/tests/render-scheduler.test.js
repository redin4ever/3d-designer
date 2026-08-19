import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  createInvalidationScheduler,
  distributedTriangleIndexes,
} from '../src/render-scheduler.js';

test('invalidation coalesces changes and stays idle after drawing', () => {
  const queued = new Map();
  const draws = [];
  let nextId = 1;
  const scheduler = createInvalidationScheduler({
    requestFrame(callback) {
      const id = nextId++;
      queued.set(id, callback);
      return id;
    },
    cancelFrame(id) { queued.delete(id); },
    draw(now) { draws.push(now); },
  });

  scheduler.start();
  scheduler.invalidate();
  scheduler.invalidate();
  assert.equal(queued.size, 1, 'multiple changes before a frame must share one callback');
  const callback = [...queued.values()][0];
  queued.clear();
  callback(10);
  assert.deepEqual(draws, [10]);
  assert.equal(queued.size, 0, 'an idle scene must not schedule another frame');

  scheduler.invalidate();
  assert.equal(queued.size, 1, 'a later scene change must schedule a new frame');
  scheduler.stop();
  assert.equal(queued.size, 0, 'stop must cancel a queued frame');
});

test('interaction triangle selection is exact below budget and distributed above it', () => {
  assert.deepEqual(distributedTriangleIndexes(3, 3), [0, 1, 2]);
  assert.deepEqual(distributedTriangleIndexes(6, 2), [0, 3]);
  assert.equal(distributedTriangleIndexes(40_000, 10_000).length, 10_000);
});
