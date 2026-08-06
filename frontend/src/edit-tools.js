// The arithmetic behind the drag handles (Q-15), and the one rule that decides whether they
// are usable at all (Q-17).
//
// WHY EDITING IS GATED ON PAUSED. The agent holds a single write lock. Asked who should win
// when both want to write, the answer chosen was "you have to press Pause first" — which is
// the most conservative option and also, unexpectedly, the most simplifying one: the manual
// path is unreachable while the agent can be writing, so the entire class of two-writer races
// stops existing rather than being handled. Nothing here contends for a lease, because
// nothing here can run while a lease is live.
//
// Every edit is sent as an annotation carrying an `edit` payload rather than as its own
// message type. An operator's edit IS a thing they are telling the agent about (Q-18 chose
// "yes, always"), so it travels the channel that already reaches the agent, in order, beside
// the words about it.

import { ClientMessageType } from './socket.js';

/** Mirrors ops.transform.DEFAULT_SNAP_M. */
export const DEFAULT_SNAP_M = 0.1;

/** Mirrors ops.transform.DEFAULT_SNAP_DEGREES. */
export const DEFAULT_SNAP_DEGREES = 15;

const AXES = ['x', 'y', 'z'];

/**
 * Round to the nearest multiple of `step`; `step <= 0` means no snapping (Q-16).
 *
 * **Half steps round away from zero — not with Math.round.** This has to agree exactly with
 * ops/transform.py's `_snapped`, because both snap the same drag, and the two rounding
 * conventions disagree in two different places:
 *
 *   - Python's built-in `round` is banker's rounding: `round(2.5)` is 2. So 0.25 on a 0.1
 *     grid gave 0.3 here and 0.2 there.
 *   - `Math.round` rounds half toward +Infinity: `Math.round(-2.5)` is -2. So -0.25 gave
 *     -0.2 here and -0.3 there once the Python side was fixed.
 *
 * Either way the operator lets go of a part, watches it sit where they put it, and sees it
 * jump one grid step on commit — only on half-steps, and for negatives only on one side of
 * the origin. That is the kind of thing reported as "the snapping is broken sometimes" and
 * never reproduced. Both suites pin the same table so they cannot drift apart again.
 *
 * Re-rounded to nine places because `1.03 / 0.1 * 0.1` is 1.0000000000000002 in binary
 * floating point, and a coordinate that prints like that in a numeric field reads as a
 * precision bug in a product whose entire claim is verified numbers.
 */
export function snapTo(value, step) {
  if (!(step > 0)) return value;
  const steps = value / step;
  const awayFromZero = Math.sign(steps) * Math.floor(Math.abs(steps) + 0.5);
  return Number((awayFromZero * step).toFixed(9));
}

/**
 * Where a part ends up after dragging one gizmo arrow.
 *
 * The snap is applied to the **destination**, not to the delta. Snapping the delta lets the
 * object drift: a part at 1.03 dragged by a snapped 0.1 lands at 1.13, which is still
 * off-grid, and repeating that never converges. Snapping the destination is what actually
 * aligns things — which is the entire point of having a snap.
 *
 * @param {[number, number, number]} from current world position
 * @param {'x'|'y'|'z'} axis the arrow being dragged
 * @param {number} delta metres along that axis
 * @param {number} [snap] grid, 0 to disable
 */
export function dragToTranslation(from, axis, delta, snap = DEFAULT_SNAP_M) {
  const index = AXES.indexOf(axis);
  if (index === -1) throw new Error(`axis must be one of x, y, z — got "${axis}"`);
  const next = [...from];
  next[index] = snapTo(next[index] + delta, snap);
  return next;
}

/** An edit, wrapped as the annotation that carries it to the agent. */
function editMessage(kind, params) {
  return { type: ClientMessageType.ANNOTATE, data: { object_ids: [params.object_id], text: '', image: '', edit: { kind, params } } };
}

/** Move one part. Mirrors ops.transform.move_object's parameters exactly. */
export function buildMoveMessage(objectId, translation, options = {}) {
  return editMessage('move_object', {
    object_id: objectId,
    translation,
    snap: options.snap ?? DEFAULT_SNAP_M,
  });
}

/**
 * Turn one part about a world axis. Axis-and-degrees rather than a quaternion because that is
 * what a drag handle produces, and because an angle snap is expressible in degrees and not in
 * a quaternion's four components.
 */
export function buildRotateMessage(objectId, axis, degrees, options = {}) {
  if (!AXES.includes(axis)) throw new Error(`axis must be one of x, y, z — got "${axis}"`);
  return editMessage('rotate_object', {
    object_id: objectId,
    axis,
    degrees,
    snap_degrees: options.snapDegrees ?? DEFAULT_SNAP_DEGREES,
  });
}

/**
 * Resize one part. Zero is refused here as well as on the backend, so the operator gets the
 * reason beside the field they typed it into rather than in the log a moment later.
 */
export function buildScaleMessage(objectId, scale) {
  if (!Array.isArray(scale) || scale.length !== 3) throw new Error('scale must be [x, y, z]');
  if (scale.some((component) => component === 0)) {
    throw new Error('a zero scale collapses the part into a plane — every component must be non-zero');
  }
  return editMessage('scale_object', { object_id: objectId, scale });
}

export function buildDeleteMessage(objectId) {
  return editMessage('delete_object', { object_id: objectId });
}

/**
 * Copy one part. Offset by one grid step by default: duplicating in place leaves two
 * identical objects at the same coordinates, which looks exactly like nothing happening and
 * is the first thing anyone tries.
 */
export function buildDuplicateMessage(objectId, newId, options = {}) {
  return editMessage('duplicate_object', {
    object_id: objectId,
    new_id: newId,
    offset: options.offset ?? [DEFAULT_SNAP_M, 0, 0],
  });
}

/**
 * Whether the edit handles work right now — and, with `{explain: true}`, why not.
 *
 * Two conditions, each from a chosen answer:
 *
 * - **Paused** (Q-17). The manual path may never race the agent for the write lock.
 * - **Connected** (Q-22). An edit with nowhere to send it would move the part in this browser
 *   only, showing a position that exists nowhere else — the silent lie this product's whole
 *   design is arranged against.
 *
 * The explanation is not decoration. Q-20 chose greyed-out handles with a Pause button beside
 * them, and a disabled control with no stated reason is indistinguishable from a broken one.
 *
 * @returns {boolean|string} a boolean, or the reason (empty string when allowed) under
 *   `{explain: true}`
 */
export function editingAllowed({ runState, connected }, options = {}) {
  const reason = !connected
    ? 'Not connected to the build — reconnecting. Editing will come back on its own.'
    : runState !== 'paused'
      ? 'Editing needs the build paused, so your change cannot land mid-action.'
      : '';
  return options.explain ? reason : reason === '';
}
