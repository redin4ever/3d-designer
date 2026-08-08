import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  MOVE_AXES,
  dragDeltaAlongAxis,
  hitTestMoveAxis,
  projectMoveGizmo,
} from '../src/gizmo.js';

const view = {
  position: [0, 0, 0],
  yaw: 0.55,
  pitch: 0.4,
  cameraDistance: 10,
  focalLength: 100,
  width: 200,
  height: 100,
  arrowLength: 40,
};

test('the three labelled world axes project to constant-size screen arrows', () => {
  const gizmo = projectMoveGizmo(view);

  assert.deepEqual(gizmo.origin, [100, 50]);
  assert.deepEqual(Object.keys(gizmo.axes), MOVE_AXES);
  for (const axis of MOVE_AXES) {
    const projected = gizmo.axes[axis];
    assert.equal(projected.label, axis.toUpperCase());
    assert.ok(projected.pixelsPerWorld > 1, `${axis} became unusably edge-on`);
    assert.ok(Math.abs(Math.hypot(
      projected.end[0] - gizmo.origin[0],
      projected.end[1] - gizmo.origin[1],
    ) - 40) < 1e-6);
  }
});

test('axis hit testing uses a generous screen-space corridor but rejects empty canvas', () => {
  const gizmo = projectMoveGizmo(view);
  const x = gizmo.axes.x;
  const nearX = [
    gizmo.origin[0] + (x.end[0] - gizmo.origin[0]) * 0.75 + x.normal[0] * 8,
    gizmo.origin[1] + (x.end[1] - gizmo.origin[1]) * 0.75 + x.normal[1] * 8,
  ];

  assert.equal(hitTestMoveAxis(nearX, gizmo, 12), 'x');
  assert.equal(hitTestMoveAxis([4, 4], gizmo, 12), null);
});

test('pointer travel along a projected axis converts back to signed world metres', () => {
  const axis = { direction: [0.8, -0.6], pixelsPerWorld: 20 };

  assert.equal(dragDeltaAlongAxis([10, 10], [26, -2], axis), 1);
  assert.equal(dragDeltaAlongAxis([26, -2], [10, 10], axis), -1);
});

test('an edge-on axis cannot create an infinite or invented movement', () => {
  assert.equal(
    dragDeltaAlongAxis([0, 0], [100, 100], { direction: [0, 0], pixelsPerWorld: 0 }),
    0,
  );
});

test('a framed object remains at the gizmo centre when the camera target moves to it', () => {
  const gizmo = projectMoveGizmo({ ...view, position: [4, -2, 1], target: [4, -2, 1] });

  assert.deepEqual(gizmo.origin, [100, 50]);
});
