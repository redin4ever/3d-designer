/** Pure move-gizmo lifecycle. DOM events and renderer previews are adapters around this. */

export function createMoveSession() {
  return { phase: 'idle' };
}

export function beginMove() {
  throw new Error('beginMove not implemented');
}

export function updateMove() {
  throw new Error('updateMove not implemented');
}

export function finishMove() {
  throw new Error('finishMove not implemented');
}

export function cancelMove() {
  throw new Error('cancelMove not implemented');
}

export function reconcileMove() {
  throw new Error('reconcileMove not implemented');
}
