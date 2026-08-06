import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createFrame, clearFrame, drawTriangle } from '../src/raster.js';

// The reported bug, stated as a test: "i can see triangles dissapearing and reaapearing
// when moving my camera". Under a painter's algorithm the answer depends on draw order, and
// draw order depends on a sort that flips as the camera moves. Under a depth buffer the
// answer does not depend on draw order at all — which is what every test here checks.

const RED = [255, 0, 0];
const BLUE = [0, 0, 255];
const BLACK = [0, 0, 0];

/** A big triangle covering most of a small frame, at a given depth. */
function bigTriangle(invW) {
  return [[-5, -5, invW], [40, -5, invW], [-5, 40, invW]];
}

function pixel(frame, x, y) {
  const o = (y * frame.width + x) * 4;
  return [frame.color[o], frame.color[o + 1], frame.color[o + 2]];
}

test('a nearer triangle wins no matter which order they are drawn', () => {
  // This is the whole point. The painter's algorithm gets this right only if the sort
  // happens to put them in the right order, and the sort flips as the camera moves.
  const far = bigTriangle(0.1);
  const near = bigTriangle(0.9);

  const a = createFrame(16, 16);
  clearFrame(a, BLACK);
  drawTriangle(a, ...far, RED);
  drawTriangle(a, ...near, BLUE);

  const b = createFrame(16, 16);
  clearFrame(b, BLACK);
  drawTriangle(b, ...near, BLUE); // near first — the order a sort would call wrong
  drawTriangle(b, ...far, RED);

  assert.deepEqual(pixel(a, 4, 4), BLUE, 'the nearer triangle is not on top');
  assert.deepEqual(pixel(b, 4, 4), BLUE, 'draw order changed the result');
  assert.deepEqual(pixel(a, 4, 4), pixel(b, 4, 4));
});

test('a farther triangle drawn second writes nothing at all', () => {
  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);
  drawTriangle(frame, ...bigTriangle(0.9), BLUE);

  const written = drawTriangle(frame, ...bigTriangle(0.1), RED);

  assert.equal(written, 0, 'a hidden surface painted over a visible one');
});

test('two triangles at the same depth do not fight', () => {
  // Coplanar geometry — the deck's top face and anything lying flat on it. A depth test
  // that used `<` instead of `<=` would let the second one win half the time.
  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);
  drawTriangle(frame, ...bigTriangle(0.5), BLUE);

  const written = drawTriangle(frame, ...bigTriangle(0.5), RED);

  assert.equal(written, 0, 'equal depth must not overwrite, or coplanar faces flicker');
});

test('interpenetrating triangles resolve per pixel, not per triangle', () => {
  // No sort can express this: each triangle is nearer than the other over part of its area.
  // A painter's algorithm must pick one and be wrong somewhere. This is the case that made
  // the whole approach unfixable.
  const frame = createFrame(32, 8);
  clearFrame(frame, BLACK);

  // Depth varies across x: one rises left-to-right, the other falls.
  drawTriangle(frame, [-2, -2, 0.1], [40, -2, 0.9], [-2, 20, 0.1], RED);
  drawTriangle(frame, [-2, -2, 0.9], [40, -2, 0.1], [-2, 20, 0.9], BLUE);

  assert.deepEqual(pixel(frame, 1, 1), BLUE, 'left edge should be the blue one');
  assert.deepEqual(pixel(frame, 30, 1), RED, 'right edge should be the red one');
});

test('adjacent triangles leave no seam between them', () => {
  // Two right triangles making a square. Under ctx.fill() each antialiases its own edge and
  // the background shows through the diagonal — the crack that inflation was papering over.
  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);

  drawTriangle(frame, [0, 0, 0.5], [16, 0, 0.5], [0, 16, 0.5], RED);
  drawTriangle(frame, [16, 0, 0.5], [16, 16, 0.5], [0, 16, 0.5], RED);

  let background = 0;
  for (let y = 1; y < 15; y += 1) {
    for (let x = 1; x < 15; x += 1) {
      if (pixel(frame, x, y)[0] === 0) background += 1;
    }
  }
  assert.equal(background, 0, `${background} pixels of seam showed through`);
});

test('a triangle entirely off screen costs nothing and writes nothing', () => {
  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);
  assert.equal(drawTriangle(frame, [100, 100, 0.5], [120, 100, 0.5], [100, 120, 0.5], RED), 0);
});

test('a degenerate triangle is skipped rather than producing NaN', () => {
  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);
  assert.equal(drawTriangle(frame, [4, 4, 0.5], [4, 4, 0.5], [4, 4, 0.5], RED), 0);
  assert.deepEqual(pixel(frame, 4, 4), BLACK);
});

test('winding does not decide visibility', () => {
  // No back-face culling: this renderer draws open shells, where a back face is the only
  // thing between the viewer and the inside of an object.
  const cw = createFrame(16, 16);
  clearFrame(cw, BLACK);
  drawTriangle(cw, [0, 0, 0.5], [14, 0, 0.5], [0, 14, 0.5], RED);

  const ccw = createFrame(16, 16);
  clearFrame(ccw, BLACK);
  drawTriangle(ccw, [0, 14, 0.5], [14, 0, 0.5], [0, 0, 0.5], RED);

  assert.deepEqual(pixel(cw, 3, 3), RED);
  assert.deepEqual(pixel(ccw, 3, 3), RED, 'a reversed triangle vanished');
});

test('clearing resets depth, so the next frame is not occluded by the last one', () => {
  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);
  drawTriangle(frame, ...bigTriangle(0.9), BLUE);

  clearFrame(frame, BLACK);
  const written = drawTriangle(frame, ...bigTriangle(0.1), RED);

  assert.ok(written > 0, 'stale depth made the whole scene invisible');
  assert.deepEqual(pixel(frame, 4, 4), RED);
});
