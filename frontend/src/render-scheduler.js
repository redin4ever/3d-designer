/** Testable scheduling and triangle-selection seams for the Canvas2D renderer. */

export const INTERACTION_TRIANGLE_BUDGET = 10_000;
export const INTERACTION_SETTLE_MS = 120;

export function createInvalidationScheduler() {
  return {
    start() {},
    stop() {},
    invalidate() {},
  };
}

export function distributedTriangleIndexes() {
  return [];
}
