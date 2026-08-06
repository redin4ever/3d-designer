// The browser's half of pointing and priority (Q-04, Q-10, Q-11, Q-13).
//
// Pure state and message shapes: no DOM, no socket, no canvas. Same split camera.js got out
// of scene-renderer.js — that seam was cut after a user found the view would not tilt or
// zoom, because the camera lived inside the one file this module's docs exempt from unit
// tests and there was nothing to catch it.
//
// THE ONE DISTINCTION THIS FILE EXISTS TO KEEP. Selection and focus are separate sets.
// Selection is what you are pointing at this instant; focus is what you have marked as
// mattering, which the agent is told about on every single turn until you take it down. They
// look similar on screen and they behave nothing alike — conflating them would clear the
// operator's standing marks every time they clicked somewhere else, silently.

import { ClientMessageType } from './socket.js';

/** Mirrors contracts.wire.MAX_ANNOTATION_IMAGE_BYTES. */
export const MAX_IMAGE_CHARS = 4_000_000;

/** Fresh, empty pointing state. */
export function createPointState() {
  return {
    /** @type {Set<string>} what is being pointed at right now */
    selection: new Set(),
    /** @type {Set<string>} what the operator has marked as important */
    focus: new Set(),
  };
}

/**
 * Replace what is selected.
 *
 * Replaces rather than adds: Q-04's click picks one part, and if clicks accumulated the
 * second one would annotate two objects with the operator having no idea which they were
 * talking about. Circling several is a single gesture that arrives here as one call.
 */
export function setSelection(state, objectIds) {
  state.selection = new Set(objectIds);
}

/**
 * Mark or unmark one part as important.
 *
 * Toggling is the only way to take a mark down from the view itself (Q-11). Without it the
 * operator has to find a list elsewhere to undo a click they just made.
 */
export function toggleFocus(state, objectId) {
  if (state.focus.has(objectId)) state.focus.delete(objectId);
  else state.focus.add(objectId);
}

/**
 * Adopt the focus set the server just echoed.
 *
 * The server is the authority, not this browser. Focus lives on the orchestrator, is what the
 * agent is actually told every turn, and is echoed to every watcher — a browser that kept its
 * own idea would drift from it, and the screen showing the truth would be the wrong one.
 */
export function applyServerFocus(state, objectIds) {
  state.focus = new Set(objectIds ?? []);
}

/**
 * Put the composer away. Deliberately does not touch focus: pressing Escape must not take
 * down marks the operator set on purpose and expects to persist until they clear them.
 */
export function clearSelection(state) {
  state.selection.clear();
}

/**
 * Build an `annotate` message. Mirrors contracts.wire.AnnotatePayload, including its guards,
 * so a refusal happens next to the composer the operator typed into rather than arriving in
 * the log a moment later.
 *
 * @param {{text?: string, image?: string}} [extra]
 */
export function buildAnnotateMessage(state, extra = {}) {
  const objectIds = [...state.selection];
  const text = extra.text ?? '';
  const image = extra.image ?? '';

  if (objectIds.length === 0 && text.trim() === '' && !image) {
    throw new Error(
      'an annotation with nothing in it — no part, no words, no image — would reach the agent and do nothing',
    );
  }
  if (image && image.length > MAX_IMAGE_CHARS) {
    // A-011: the transport does not error on an over-length frame, it closes the connection.
    // The operator would watch the live view drop with nothing saying why, at the exact
    // moment they tried to say something.
    throw new Error(
      `that image is too large to send (${image.length} of ${MAX_IMAGE_CHARS} characters) — circle a smaller area`,
    );
  }

  return { type: ClientMessageType.ANNOTATE, data: { object_ids: objectIds, text, image } };
}

/**
 * Build a `set_focus` message — always the whole set (contracts.wire.FocusPayload is
 * declarative), and always sent even when empty, because the empty set IS the clear (Q-11).
 * Skipping the empty send would leave the agent told those parts matter forever.
 */
export function buildFocusMessage(state) {
  return { type: ClientMessageType.SET_FOCUS, data: { object_ids: [...state.focus] } };
}

/**
 * What is attached, for a person to read above the composer before they press Send.
 *
 * Named ids up to a handful, then a count. A raw list of forty ids is not something anyone
 * reads, and the point of showing it at all is that the operator can tell at a glance whether
 * the lasso caught what they meant.
 */
export function describeSelection(state) {
  const ids = [...state.selection];
  if (ids.length === 0) return 'nothing selected';
  if (ids.length <= 3) return ids.join(', ');
  return `${ids.length} parts — ${ids.slice(0, 2).join(', ')} and ${ids.length - 2} more`;
}
