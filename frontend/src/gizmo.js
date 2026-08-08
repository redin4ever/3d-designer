/** Pure screen-space arithmetic for the move gizmo. Browser wiring lives in point-ui.js. */

import { zUpToYUp } from './camera.js';

export const MOVE_AXES = ['x', 'y', 'z'];

const WORLD_AXES = {
  x: [1, 0, 0],
  y: [0, 1, 0],
  z: [0, 0, 1],
};

function rotateY([x, y, z], angle) {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return [x * c + z * s, y, -x * s + z * c];
}

function rotateX([x, y, z], angle) {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return [x, y * c - z * s, y * s + z * c];
}

function toView(point, yaw, pitch) {
  return rotateX(rotateY(zUpToYUp(point), yaw), pitch);
}

function project([x, y, z], cameraDistance, focalLength, width, height) {
  const depth = cameraDistance - z;
  if (!(depth > 0)) return null;
  return [width / 2 + (x * focalLength) / depth, height / 2 - (y * focalLength) / depth];
}

/**
 * Project the selected object's world origin and world axes into the current raster frame.
 * Visible arrows stay a constant screen size, while `pixelsPerWorld` retains the perspective
 * scale needed to convert a pointer drag back into metres.
 */
export function projectMoveGizmo({
  position,
  yaw,
  pitch,
  cameraDistance,
  focalLength,
  width,
  height,
  arrowLength = 72,
}) {
  const originView = toView(position, yaw, pitch);
  const origin = project(originView, cameraDistance, focalLength, width, height);
  if (!origin) return null;

  const axes = {};
  for (const axis of MOVE_AXES) {
    const tipWorld = position.map((component, index) => component + WORLD_AXES[axis][index]);
    const tip = project(toView(tipWorld, yaw, pitch), cameraDistance, focalLength, width, height);
    const dx = (tip?.[0] ?? origin[0]) - origin[0];
    const dy = (tip?.[1] ?? origin[1]) - origin[1];
    const pixelsPerWorld = Math.hypot(dx, dy);
    const direction = pixelsPerWorld > 1e-6 ? [dx / pixelsPerWorld, dy / pixelsPerWorld] : [0, 0];
    axes[axis] = {
      label: axis.toUpperCase(),
      direction,
      normal: [-direction[1], direction[0]],
      pixelsPerWorld,
      end: [origin[0] + direction[0] * arrowLength, origin[1] + direction[1] * arrowLength],
    };
  }
  return { origin, axes };
}

function distanceToSegment(point, start, end) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared === 0) return Infinity;
  const t = Math.max(0.18, Math.min(1.12,
    ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / lengthSquared,
  ));
  return Math.hypot(point[0] - (start[0] + dx * t), point[1] - (start[1] + dy * t));
}

/** Return the closest labelled axis inside a generous invisible screen-space corridor. */
export function hitTestMoveAxis(point, gizmo, hitRadius = 14) {
  if (!gizmo) return null;
  let nearest = null;
  let nearestDistance = hitRadius;
  for (const axis of MOVE_AXES) {
    const projected = gizmo.axes[axis];
    if (!(projected?.pixelsPerWorld > 1e-6)) continue;
    const distance = distanceToSegment(point, gizmo.origin, projected.end);
    if (distance <= nearestDistance) {
      nearest = axis;
      nearestDistance = distance;
    }
  }
  return nearest;
}

/** Convert pointer displacement along a projected axis into signed world metres. */
export function dragDeltaAlongAxis(start, current, projectedAxis) {
  if (!(projectedAxis?.pixelsPerWorld > 1e-6)) return 0;
  const dx = current[0] - start[0];
  const dy = current[1] - start[1];
  return (dx * projectedAxis.direction[0] + dy * projectedAxis.direction[1])
    / projectedAxis.pixelsPerWorld;
}
