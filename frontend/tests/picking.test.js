import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createFrame, clearFrame, drawTriangle } from '../src/raster.js';
import {
  NOTHING,
  createIdIndex,
  pickAt,
  pickInPath,
  pointInPolygon,
  cssToFrame,
} from '../src/picking.js';

// Q-25 chose "pointing feeling instant and exact" as what the effort goes into, and Q-06
// chose "the nearest one" when parts overlap. Both are the same requirement: the part you
// get is the part whose pixel is under the cursor.
//
// That is why picking reads an id written by the rasterizer in the same inner loop that
// already writes depth, rather than casting a ray into the scene. A ray is a second, parallel
// answer to "what is visible", and the moment it disagrees with the depth buffer the operator
// picks one thing and sees another highlighted. Reading the id the depth test already chose
// makes the two impossible to disagree — it is not approximately right, it is the same answer.

const RED = [255, 0, 0];
const BLUE = [0, 0, 255];
const BLACK = [0, 0, 0];

/** A big triangle covering most of a small frame, at a given depth. */
function bigTriangle(invW) {
  return [[-5, -5, invW], [40, -5, invW], [-5, 40, invW]];
}

/** A triangle covering roughly the left half of a 32-wide frame. */
function leftHalf(invW) {
  return [[-2, -2, invW], [16, -2, invW], [-2, 40, invW]];
}

test('an object keeps the same id for as long as it exists', () => {
  // The id is written into a typed array once per pixel, so it has to be an integer — but
  // everything else in this product names objects with the string id the wire protocol uses.
  // An id that changed between frames would highlight a different object than the one picked.
  const index = createIdIndex();

  const first = index.idFor('stair_railing_02');
  const again = index.idFor('stair_railing_02');

  assert.equal(first, again, 'the same object got two different ids');
  assert.equal(index.objectFor(first), 'stair_railing_02');
});

test('two objects never share an id, and nothing is ever id 0', () => {
  // 0 is reserved for "no object drawn here" — clearFrame writes it everywhere. An object
  // that were allotted 0 would be unpickable and indistinguishable from empty space.
  const index = createIdIndex();
  const a = index.idFor('wall_01');
  const b = index.idFor('wall_02');

  assert.notEqual(a, b);
  assert.notEqual(a, NOTHING);
  assert.notEqual(b, NOTHING);
});

test('an id is not reused after the object is gone', () => {
  // A long build creates and deletes constantly. Reusing an id means an in-flight pick
  // resolves to whatever took the dead object's place — a click landing on the wrong thing,
  // occasionally, unreproducibly.
  const index = createIdIndex();
  const railing = index.idFor('railing');
  index.forget('railing');
  const tread = index.idFor('tread');

  assert.notEqual(tread, railing);
  assert.equal(index.objectFor(railing), null, 'a forgotten object still resolves');
});

test('picking returns the nearest object, whichever order they were drawn', () => {
  // The reason this reads the depth buffer's own answer rather than a second one. Under any
  // per-triangle ordering the result would flip with the camera — the exact bug that made
  // triangles disappear and reappear before raster.js kept depth per pixel.
  const index = createIdIndex();
  const far = index.idFor('wall');
  const near = index.idFor('railing');

  const a = createFrame(16, 16);
  clearFrame(a, BLACK);
  drawTriangle(a, ...bigTriangle(0.1), RED, far);
  drawTriangle(a, ...bigTriangle(0.9), BLUE, near);

  const b = createFrame(16, 16);
  clearFrame(b, BLACK);
  drawTriangle(b, ...bigTriangle(0.9), BLUE, near); // near first — the order a sort calls wrong
  drawTriangle(b, ...bigTriangle(0.1), RED, far);

  assert.equal(pickAt(a, 4, 4), near, 'picked the object behind the one on screen');
  assert.equal(pickAt(b, 4, 4), near, 'draw order changed what was picked');
});

test('picking empty space returns nothing rather than the last thing drawn', () => {
  const index = createIdIndex();
  const frame = createFrame(32, 8);
  clearFrame(frame, BLACK);
  drawTriangle(frame, ...leftHalf(0.5), RED, index.idFor('wall'));

  assert.equal(pickAt(frame, 30, 4), NOTHING, 'empty space picked an object');
});

test('picking outside the view returns nothing instead of reading past the buffer', () => {
  // A pointer can leave the canvas mid-drag. Reading out of bounds on a typed array returns
  // undefined, which would flow onward as an object id nothing can resolve.
  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);

  assert.equal(pickAt(frame, -1, 4), NOTHING);
  assert.equal(pickAt(frame, 4, -1), NOTHING);
  assert.equal(pickAt(frame, 16, 4), NOTHING);
  assert.equal(pickAt(frame, 4, 16), NOTHING);
});

test('clearing the frame makes last frame objects unpickable', () => {
  // The ids have to be reset with the depth, or an object deleted from the scene stays
  // pickable in the space it used to occupy until something else is drawn over it.
  const index = createIdIndex();
  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);
  drawTriangle(frame, ...bigTriangle(0.9), BLUE, index.idFor('railing'));

  clearFrame(frame, BLACK);

  assert.equal(pickAt(frame, 4, 4), NOTHING, 'a stale id survived the clear');
});

test('a triangle drawn with no id is still drawn, and picks as nothing', () => {
  // raster.js is used by the renderer for things that are not scene objects — and the id
  // argument has to stay optional so every existing caller and test keeps working unedited.
  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);

  const written = drawTriangle(frame, ...bigTriangle(0.5), RED);

  assert.ok(written > 0, 'an id-less triangle stopped being drawn');
  assert.equal(pickAt(frame, 4, 4), NOTHING);
});

test('a hidden triangle does not overwrite the id of the one in front', () => {
  // The id must be written only where the depth test passed. Writing it unconditionally
  // would make the last-drawn object pickable through everything in front of it.
  const index = createIdIndex();
  const near = index.idFor('railing');
  const far = index.idFor('wall');

  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);
  drawTriangle(frame, ...bigTriangle(0.9), BLUE, near);
  drawTriangle(frame, ...bigTriangle(0.1), RED, far);

  assert.equal(pickAt(frame, 4, 4), near, 'a hidden object became pickable');
});

test('circling a region picks every object you can see inside it', () => {
  // Q-04: "click, and drag to circle". Drawing a loop round four parts has to select four
  // parts, not the one whose centre happens to be nearest the middle.
  const index = createIdIndex();
  const left = index.idFor('wall_left');
  const right = index.idFor('wall_right');

  const frame = createFrame(32, 8);
  clearFrame(frame, BLACK);
  drawTriangle(frame, ...leftHalf(0.5), RED, left);
  drawTriangle(frame, [16, -2, 0.5], [40, -2, 0.5], [40, 40, 0.5], BLUE, right);

  const whole = pickInPath(frame, [[0, 0], [32, 0], [32, 8], [0, 8]]);
  assert.deepEqual([...whole].sort(), [left, right].sort());

  const justLeft = pickInPath(frame, [[0, 0], [10, 0], [10, 8], [0, 8]]);
  assert.deepEqual([...justLeft], [left], 'the loop selected something outside itself');
});

test('circling does not pick something hidden behind what you circled', () => {
  // You select what you can see. An object entirely occluded has no pixel inside the loop —
  // and picking it would mean the operator points at a wall and annotates the floor behind it.
  const index = createIdIndex();
  const near = index.idFor('railing');
  const far = index.idFor('wall');

  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);
  drawTriangle(frame, ...bigTriangle(0.1), RED, far);
  drawTriangle(frame, ...bigTriangle(0.9), BLUE, near);

  assert.deepEqual(pickInPath(frame, [[0, 0], [16, 0], [16, 16], [0, 16]]), [near]);
});

test('an empty or degenerate loop picks nothing rather than everything', () => {
  // A click registers as a one-point drag. Treating a zero-area path as "select all" would
  // make a stray click select the entire scene.
  const index = createIdIndex();
  const frame = createFrame(16, 16);
  clearFrame(frame, BLACK);
  drawTriangle(frame, ...bigTriangle(0.5), RED, index.idFor('wall'));

  assert.deepEqual(pickInPath(frame, []), []);
  assert.deepEqual(pickInPath(frame, [[4, 4]]), []);
  assert.deepEqual(pickInPath(frame, [[4, 4], [8, 8]]), []);
});

test('a concave loop excludes what falls in its notch', () => {
  // Lassos drawn by hand are not convex. A convex-hull approximation would quietly select
  // things the operator deliberately drew around.
  const cShape = [[0, 0], [10, 0], [10, 4], [4, 4], [4, 6], [10, 6], [10, 10], [0, 10]];

  assert.equal(pointInPolygon(cShape, 2, 5), true, 'a point inside the C was excluded');
  assert.equal(pointInPolygon(cShape, 8, 5), false, 'a point in the notch was included');
  assert.equal(pointInPolygon(cShape, 20, 5), false);
});

test('a pointer position becomes the pixel underneath it, at any display scale', () => {
  // The canvas backing store is sized in device pixels and laid out in CSS pixels; on a
  // 2x display they differ by a factor of two. Getting this wrong picks the object a
  // quarter of the way across the screen from the cursor, and only on some machines.
  const frame = createFrame(800, 600);
  const rect = { left: 100, top: 50, width: 400, height: 300 };

  assert.deepEqual(cssToFrame(frame, rect, 100, 50), [0, 0], 'the top-left corner missed');
  assert.deepEqual(cssToFrame(frame, rect, 300, 200), [400, 300], 'the centre missed');
});

test('a pointer outside the canvas produces a position that picks nothing', () => {
  const frame = createFrame(16, 16);
  const rect = { left: 0, top: 0, width: 16, height: 16 };

  assert.equal(pickAt(frame, ...cssToFrame(frame, rect, -5, 8)), NOTHING);
  assert.equal(pickAt(frame, ...cssToFrame(frame, rect, 8, 99)), NOTHING);
});
