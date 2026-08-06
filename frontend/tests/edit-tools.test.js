import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAULT_SNAP_M,
  DEFAULT_SNAP_DEGREES,
  snapTo,
  dragToTranslation,
  buildMoveMessage,
  buildRotateMessage,
  buildScaleMessage,
  buildDeleteMessage,
  buildDuplicateMessage,
  editingAllowed,
} from '../src/edit-tools.js';

// The arithmetic behind the drag handles (Q-15), and the one rule that decides whether they
// work at all (Q-17: editing needs the run paused). Pure — no DOM, no socket.

test('snapping lands on the grid, and 0 turns it off', () => {
  // Q-16. Every placement being a fraction off is the defect class this product measures,
  // and free-hand dragging produces exactly that.
  assert.equal(snapTo(1.03, 0.1), 1.0);
  assert.equal(snapTo(2.07, 0.1), 2.1);
  assert.equal(snapTo(1.03, 0), 1.03);
});

test('a snapped value is not a floating-point smear', () => {
  // round(1.03 / 0.1) * 0.1 is 1.0000000000000002 in binary floating point. A coordinate
  // that prints like that in a report reads as a precision bug in a product whose entire
  // claim is verified numbers.
  assert.equal(String(snapTo(1.03, 0.1)), '1');
  assert.equal(String(snapTo(0.35, 0.1)), '0.4');
});

test('the defaults are the ones the backend uses', () => {
  // Two implementations of the same snap, one in each language, is how the browser shows a
  // position the backend then rounds somewhere else — the part visibly jumping on commit.
  assert.equal(DEFAULT_SNAP_M, 0.1);
  assert.equal(DEFAULT_SNAP_DEGREES, 15);
});

test('dragging along an axis moves only that axis', () => {
  // A gizmo arrow constrains to one axis; that constraint is the whole reason to grab an
  // arrow rather than the object. Leaking into the other two makes it unusable for the
  // precise correction it exists for.
  const from = [1, 2, 3];

  assert.deepEqual(dragToTranslation(from, 'x', 0.5, 0), [1.5, 2, 3]);
  assert.deepEqual(dragToTranslation(from, 'y', 0.5, 0), [1, 2.5, 3]);
  assert.deepEqual(dragToTranslation(from, 'z', -1, 0), [1, 2, 2]);
});

test('a drag snaps the result, not the delta', () => {
  // Snapping the delta makes the object drift: a part at 1.03 dragged by a snapped 0.1 lands
  // at 1.13, which is still off-grid. Snapping the destination is what actually aligns things.
  assert.deepEqual(dragToTranslation([1.03, 0, 0], 'x', 0.04, 0.1), [1.1, 0, 0]);
});

test('the move message matches the backend operation exactly', () => {
  const message = buildMoveMessage('railing', [1, 2, 3], { snap: 0 });

  assert.equal(message.type, 'annotate');
  assert.equal(message.data.edit.kind, 'move_object');
  assert.deepEqual(message.data.edit.params.translation, [1, 2, 3]);
  assert.equal(message.data.edit.params.snap, 0);
  assert.equal(message.data.edit.params.object_id, 'railing');
});

test('rotate names an axis and degrees, the way a handle produces them', () => {
  const message = buildRotateMessage('railing', 'z', 90);

  assert.equal(message.data.edit.kind, 'rotate_object');
  assert.equal(message.data.edit.params.axis, 'z');
  assert.equal(message.data.edit.params.degrees, 90);
});

test('a rotation about an axis that does not exist is refused here', () => {
  assert.throws(() => buildRotateMessage('railing', 'w', 90), /axis/);
});

test('scaling to zero is refused in the browser too', () => {
  // The backend refuses it as well. Catching it here means the operator gets the reason
  // beside the field they typed it into, rather than an error in the log a moment later.
  assert.throws(() => buildScaleMessage('railing', [1, 0, 1]), /zero/);
});

test('delete and duplicate name the object they act on', () => {
  assert.equal(buildDeleteMessage('railing').data.edit.kind, 'delete_object');
  assert.equal(buildDuplicateMessage('railing', 'railing_copy').data.edit.params.new_id, 'railing_copy');
});

test('duplicating offsets the copy so it is not hidden inside the original', () => {
  // Duplicating in place leaves two identical objects at the same coordinates, which looks
  // exactly like nothing happening and is the first thing anyone tries.
  const offset = buildDuplicateMessage('railing', 'copy').data.edit.params.offset;

  assert.ok(offset.some((component) => component !== 0), 'the copy would sit inside the original');
});

test('editing is only allowed while the run is paused', () => {
  // Q-17, and the whole reason this feature never contends for the write lock: the manual
  // path is unreachable while the agent can be writing, so the entire class of two-writer
  // races stops existing rather than being handled.
  assert.equal(editingAllowed({ runState: 'paused', connected: true }), true);
  assert.equal(editingAllowed({ runState: 'running', connected: true }), false);
});

test('editing is not allowed while disconnected, even when paused', () => {
  // Q-22 chose "the move reverts, and it says so". Allowing an edit with nowhere to send it
  // would show a position that exists only in this browser — the silent lie this product's
  // whole design is arranged against.
  assert.equal(editingAllowed({ runState: 'paused', connected: false }), false);
});

test('the reason editing is blocked is stated, not just the fact', () => {
  // Q-20 chose greyed-out handles with a Pause button beside them. A disabled control with
  // no reason is indistinguishable from a broken one.
  assert.match(editingAllowed({ runState: 'running', connected: true }, { explain: true }), /paus/i);
  assert.match(editingAllowed({ runState: 'paused', connected: false }, { explain: true }), /connect/i);
  assert.equal(editingAllowed({ runState: 'paused', connected: true }, { explain: true }), '');
});
