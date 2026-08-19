/** Testable scheduling and triangle-selection seams for the Canvas2D renderer. */

export const INTERACTION_TRIANGLE_BUDGET = 10_000;
export const INTERACTION_SETTLE_MS = 120;
export const CANVAS_TRIANGLE_BUDGET = 500;

export function createInvalidationScheduler({ requestFrame, cancelFrame, draw }) {
  let running = false;
  let frameId = null;
  const invalidate = () => {
    if (!running || frameId !== null) return;
    frameId = requestFrame((now) => {
      frameId = null;
      if (running) draw(now);
    });
  };
  return {
    start() {
      if (running) return;
      running = true;
      invalidate();
    },
    stop() {
      running = false;
      if (frameId !== null) cancelFrame(frameId);
      frameId = null;
    },
    invalidate,
  };
}

export function distributedTriangleIndexes(total, budget) {
  const count = Math.max(0, Math.floor(Number(total) || 0));
  const limit = Math.max(0, Math.floor(Number(budget) || 0));
  if (count <= limit) return Array.from({ length: count }, (_, index) => index);
  if (limit === 0) return [];
  return Array.from({ length: limit }, (_, index) => Math.floor(index * count / limit));
}
