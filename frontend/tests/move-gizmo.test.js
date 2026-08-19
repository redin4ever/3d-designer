import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  beginMove,
  cancelMove,
  createMoveSession,
  finishMove,
  reconcileMove,
  updateMove,
} from '../src/move-gizmo.js';

const start = () => beginMove(createMoveSession(), {
  objectId: 'beam',
  pointerId: 7,
  axis: 'x',
  startPointer: [20, 30],
  startPosition: [1.03, 2, 3],
  projectedAxis: { direction: [1, 0], pixelsPerWorld: 20 },
});

test('a move session arms one object, pointer, and axis without moving it', () => {
  assert.deepEqual(start(), {
    phase: 'armed',
    objectId: 'beam',
    pointerId: 7,
    axis: 'x',
    startPointer: [20, 30],
    startPosition: [1.03, 2, 3],
    previewPosition: [1.03, 2, 3],
    projectedAxis: { direction: [1, 0], pixelsPerWorld: 20 },
    moved: false,
  });
});

test('only the captured pointer previews a snapped move on the armed axis', () => {
  const armed = start();
  assert.equal(updateMove(armed, { pointerId: 99, point: [40, 30], snap: 0.1 }), armed);

  const dragging = updateMove(armed, { pointerId: 7, point: [40, 30], snap: 0.1 });
  assert.equal(dragging.phase, 'dragging');
  assert.deepEqual(dragging.previewPosition, [2, 2, 3]);
  assert.equal(dragging.moved, true);
});

test('release commits once only after meaningful pointer travel', () => {
  const click = finishMove(start(), 7);
  assert.equal(click.translation, null);
  assert.equal(click.session.phase, 'idle');

  const dragging = updateMove(start(), { pointerId: 7, point: [40, 30], snap: 0.1 });
  const committed = finishMove(dragging, 7);
  assert.deepEqual(committed.translation, [2, 2, 3]);
  assert.equal(committed.session.phase, 'idle');
  assert.deepEqual(committed.pending, {
    objectId: 'beam',
    restorePosition: [1.03, 2, 3],
    previewPosition: [2, 2, 3],
  });
  assert.equal(finishMove(committed.session, 7).translation, null);
});

test('a released drag can immediately arm a different axis before confirmation', () => {
  const first = finishMove(
    updateMove(start(), { pointerId: 7, point: [40, 30], snap: 0.1 }),
    7,
  );

  const second = beginMove(first.session, {
    objectId: 'beam',
    pointerId: 8,
    axis: 'y',
    startPointer: [40, 30],
    startPosition: first.translation,
    projectedAxis: { direction: [0, 1], pixelsPerWorld: 20 },
  });

  assert.equal(second.phase, 'armed');
  assert.equal(second.axis, 'y');
});

test('cancel restores the authoritative position and retires the pointer', () => {
  const dragging = updateMove(start(), { pointerId: 7, point: [40, 30], snap: 0.1 });
  const cancelled = cancelMove(dragging);

  assert.deepEqual(cancelled.restore, [1.03, 2, 3]);
  assert.equal(cancelled.session.phase, 'idle');
  assert.equal(updateMove(cancelled.session, { pointerId: 7, point: [60, 30], snap: 0.1 }), cancelled.session);
});

test('an authoritative update does not cancel a fresh active drag', () => {
  const dragging = updateMove(start(), { pointerId: 7, point: [40, 30], snap: 0.1 });
  const active = beginMove(finishMove(dragging, 7).session, {
    objectId: 'beam',
    pointerId: 8,
    axis: 'y',
    startPointer: [40, 30],
    startPosition: [2, 2, 3],
    projectedAxis: { direction: [0, 1], pixelsPerWorld: 20 },
  });

  assert.equal(reconcileMove(active, 'other'), active);
  assert.equal(reconcileMove(active, 'beam'), active);
});
