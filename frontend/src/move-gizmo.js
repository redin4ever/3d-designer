/** Pure move-gizmo lifecycle. DOM events and renderer previews are adapters around this. */

import { dragToTranslation } from './edit-tools.js';
import { dragDeltaAlongAxis } from './gizmo.js';

export function createMoveSession() {
  return { phase: 'idle' };
}

export function beginMove(session, {
  objectId,
  pointerId,
  axis,
  startPointer,
  startPosition,
  projectedAxis,
}) {
  if (session.phase !== 'idle') return session;
  return {
    phase: 'armed',
    objectId,
    pointerId,
    axis,
    startPointer: [...startPointer],
    startPosition: [...startPosition],
    previewPosition: [...startPosition],
    projectedAxis,
    moved: false,
  };
}

export function updateMove(session, { pointerId, point, snap, threshold = 3 }) {
  if (!['armed', 'dragging'].includes(session.phase) || pointerId !== session.pointerId) return session;
  const travel = Math.hypot(point[0] - session.startPointer[0], point[1] - session.startPointer[1]);
  const delta = dragDeltaAlongAxis(session.startPointer, point, session.projectedAxis);
  const previewPosition = dragToTranslation(session.startPosition, session.axis, delta, snap);
  const moved = travel >= threshold
    && previewPosition.some((component, index) => component !== session.startPosition[index]);
  return {
    ...session,
    phase: moved ? 'dragging' : 'armed',
    previewPosition,
    moved,
  };
}

export function finishMove(session, pointerId) {
  if (!['armed', 'dragging'].includes(session.phase) || pointerId !== session.pointerId) {
    return { session, translation: null, restore: null };
  }
  if (!session.moved) {
    return { session: createMoveSession(), translation: null, restore: session.startPosition };
  }
  return {
    session: { ...session, phase: 'pending', pointerId: null },
    translation: [...session.previewPosition],
    restore: null,
  };
}

export function cancelMove(session) {
  if (session.phase === 'idle') return { session, restore: null };
  return { session: createMoveSession(), restore: [...session.startPosition] };
}

export function reconcileMove(session, objectId) {
  return session.phase !== 'idle' && session.objectId === objectId
    ? createMoveSession()
    : session;
}
