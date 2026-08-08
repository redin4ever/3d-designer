# Components

## Framework and component model

- Framework: no framework; a static HTML entrypoint bootstraps native ES modules.
- Component library: none detected; UI is composed from semantic HTML, CSS classes, and small DOM-oriented modules.
- CSS approach: vanilla CSS with custom properties in `frontend/src/tokens.css`; no Tailwind, CSS Modules, or CSS-in-JS.
- Reusable UI modules below are the actual DOM render/event modules. State-only and rendering-adjacent modules are included where they directly feed visible UI.

## Shared UI modules

### frontend/src/annotate.js

```js
// The browser's half of pointing and priority (Q-04, Q-10, Q-11, Q-13).
//
// Pure state and message shapes: no DOM, no socket, no canvas. Same split camera.js got out
// of scene-renderer.js â€” that seam was cut after a user found the view would not tilt or
// zoom, because the camera lived inside the one file this module's docs exempt from unit
// tests and there was nothing to catch it.
//
// THE ONE DISTINCTION THIS FILE EXISTS TO KEEP. Selection and focus are separate sets.
// Selection is what you are pointing at this instant; focus is what you have marked as
// mattering, which the agent is told about on every single turn until you take it down. They
// look similar on screen and they behave nothing alike â€” conflating them would clear the
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
 * agent is actually told every turn, and is echoed to every watcher â€” a browser that kept its
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
      'an annotation with nothing in it â€” no part, no words, no image â€” would reach the agent and do nothing',
    );
  }
  if (image && image.length > MAX_IMAGE_CHARS) {
    // A-011: the transport does not error on an over-length frame, it closes the connection.
    // The operator would watch the live view drop with nothing saying why, at the exact
    // moment they tried to say something.
    throw new Error(
      `that image is too large to send (${image.length} of ${MAX_IMAGE_CHARS} characters) â€” circle a smaller area`,
    );
  }

  return { type: ClientMessageType.ANNOTATE, data: { object_ids: objectIds, text, image } };
}

/**
 * Build a `set_focus` message â€” always the whole set (contracts.wire.FocusPayload is
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
  return `${ids.length} parts â€” ${ids.slice(0, 2).join(', ')} and ${ids.length - 2} more`;
}

```

### frontend/src/controls.js

```js
// Operator controls (Gate A 5.4, 3.1): pause / resume / rollback N steps / redirect in
// words / check-cadence setting. wire.py's ClientMessageType docstring frames the whole
// module: "The build runs fully autonomously; these exist so a human watching can take
// the wheel without stopping it by default."
//
// Every builder below is pure â€” validates and returns a plain {type, data} object, never
// touches the socket or the DOM â€” so frontend/tests/controls.test.js can check the exact
// shapes against src/contracts/wire.py's dataclasses with no browser involved.
// attachControls (bottom of the file) is the impure DOM wiring main.js uses; it is not
// unit-tested for the same reason SocketClient isn't (see socket.js).

import { ClientMessageType } from './socket.js';

/** Mirrors contracts.phases.CheckCadence, in the order documented at Gate A 3.1. */
export const VALID_CADENCES = Object.freeze([
  'every_geometry_change',
  'phase_boundaries',
  'on_request',
]);

export function buildPauseMessage() {
  return { type: ClientMessageType.PAUSE, data: {} };
}

export function buildResumeMessage() {
  return { type: ClientMessageType.RESUME, data: {} };
}

export function buildRequestFullSceneMessage() {
  return { type: ClientMessageType.REQUEST_FULL_SCENE, data: {} };
}

export function buildSelectMessage(objectIds) {
  return { type: ClientMessageType.SELECT, data: { object_ids: [...objectIds] } };
}

/**
 * Build a `rollback` message. Mirrors contracts.wire.RollbackTarget exactly: exactly one
 * of `steps` (>= 1) or `checkpoint` (a non-empty name) â€” never both, never neither.
 *
 * @param {{steps?: number, checkpoint?: string}} [target]
 */
export function buildRollbackMessage(target = {}) {
  const { steps, checkpoint } = target;
  const hasSteps = steps !== undefined && steps !== null;
  const hasCheckpoint = checkpoint !== undefined && checkpoint !== null && checkpoint !== '';

  if (hasSteps === hasCheckpoint) {
    throw new Error('rollback takes exactly one of steps or checkpoint');
  }
  if (hasSteps) {
    if (!Number.isInteger(steps) || steps < 1) {
      throw new Error(`rollback steps must be >= 1, got ${steps}`);
    }
    return { type: ClientMessageType.ROLLBACK, data: { steps } };
  }
  return { type: ClientMessageType.ROLLBACK, data: { checkpoint } };
}

/**
 * Build a `redirect` message. Mirrors contracts.wire.RedirectPayload: text must be
 * non-empty after trimming, or (per the dataclass docstring) "a redirect with no text
 * would be silently dropped" â€” rejected here, client-side, before it is ever sent.
 *
 * @param {string} text
 */
export function buildRedirectMessage(text) {
  if (typeof text !== 'string' || text.trim() === '') {
    throw new Error('a redirect with no text would be silently dropped');
  }
  return { type: ClientMessageType.REDIRECT, data: { text } };
}

/**
 * Build a `set_cadence` message â€” "the settings control asked for at Gate A 3.1"
 * (wire.py). Mirrors contracts.wire.CadencePayload / contracts.phases.CheckCadence.
 *
 * @param {string} cadence one of VALID_CADENCES
 */
export function buildSetCadenceMessage(cadence) {
  if (!VALID_CADENCES.includes(cadence)) {
    throw new Error(`invalid cadence "${cadence}" â€” must be one of ${VALID_CADENCES.join(', ')}`);
  }
  return { type: ClientMessageType.SET_CADENCE, data: { cadence } };
}

/**
 * Wire the controls panel's DOM elements to a `send` function. Kept deliberately dumb:
 * every handler builds a message with the pure functions above and hands it to `send`,
 * catching a validation error into `onError` (e.g. an empty redirect) instead of letting
 * it throw into an event listener and vanish silently.
 *
 * @param {HTMLElement} root an element containing the controls. main.js passes the whole
 *   layout, not just `.controls-panel`, because the redirect composer lives in the
 *   conversation panel now â€” an operator types their instruction where they can see it
 *   land, not in a box on the other side of the page.
 * @param {{send: (msg: object) => boolean|void, onError: (message: string) => void}} io
 *   `send` returning false means the message never left; anything else counts as queued.
 */
export function attachControls(root, io) {
  const pauseButton = root.querySelector('[data-action="pause"]');
  const resumeButton = root.querySelector('[data-action="resume"]');
  const rollbackForm = root.querySelector('[data-action="rollback-form"]');
  const rollbackStepsInput = root.querySelector('[data-field="rollback-steps"]');
  const redirectForm = root.querySelector('[data-action="redirect-form"]');
  const redirectInput = root.querySelector('[data-field="redirect-text"]');
  const cadenceSelect = root.querySelector('[data-field="cadence"]');

  // Returns whether the message was actually queued: false if it failed validation, and
  // false if `send` reported it never left (the socket is down). Callers use that to
  // decide whether it is safe to throw away what the operator typed.
  const guarded = (build) => {
    try {
      return io.send(build()) !== false;
    } catch (err) {
      io.onError(err instanceof Error ? err.message : String(err));
      return false;
    }
  };

  pauseButton?.addEventListener('click', () => guarded(buildPauseMessage));
  resumeButton?.addEventListener('click', () => guarded(buildResumeMessage));

  rollbackForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    const raw = rollbackStepsInput?.value ?? '';
    const steps = Number.parseInt(raw, 10);
    guarded(() => buildRollbackMessage({ steps }));
  });

  redirectForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    const text = redirectInput?.value ?? '';
    const queued = guarded(() => buildRedirectMessage(text));
    // Clear only once the message is actually queued. Clearing unconditionally threw the
    // operator's words away whenever the socket was down â€” the one moment they most need
    // to be able to press Send again without retyping.
    if (queued && redirectInput) redirectInput.value = '';
  });

  cadenceSelect?.addEventListener('change', () => {
    guarded(() => buildSetCadenceMessage(cadenceSelect.value));
  });
}

```

### frontend/src/edit-tools.js

```js
// The arithmetic behind the drag handles (Q-15), and the one rule that decides whether they
// are usable at all (Q-17).
//
// WHY EDITING IS GATED ON PAUSED. The agent holds a single write lock. Asked who should win
// when both want to write, the answer chosen was "you have to press Pause first" â€” which is
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
 * **Half steps round away from zero â€” not with Math.round.** This has to agree exactly with
 * ops/transform.py's `_snapped`, because both snap the same drag, and the two rounding
 * conventions disagree in two different places:
 *
 *   - Python's built-in `round` is banker's rounding: `round(2.5)` is 2. So 0.25 on a 0.1
 *     grid gave 0.3 here and 0.2 there.
 *   - `Math.round` rounds half toward +Infinity: `Math.round(-2.5)` is -2. So -0.25 gave
 *     -0.2 here and -0.3 there once the Python side was fixed.
 *
 * Either way the operator lets go of a part, watches it sit where they put it, and sees it
 * jump one grid step on commit â€” only on half-steps, and for negatives only on one side of
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
 * aligns things â€” which is the entire point of having a snap.
 *
 * @param {[number, number, number]} from current world position
 * @param {'x'|'y'|'z'} axis the arrow being dragged
 * @param {number} delta metres along that axis
 * @param {number} [snap] grid, 0 to disable
 */
export function dragToTranslation(from, axis, delta, snap = DEFAULT_SNAP_M) {
  const index = AXES.indexOf(axis);
  if (index === -1) throw new Error(`axis must be one of x, y, z â€” got "${axis}"`);
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
  if (!AXES.includes(axis)) throw new Error(`axis must be one of x, y, z â€” got "${axis}"`);
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
    throw new Error('a zero scale collapses the part into a plane â€” every component must be non-zero');
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
 * Whether the edit handles work right now â€” and, with `{explain: true}`, why not.
 *
 * Two conditions, each from a chosen answer:
 *
 * - **Paused** (Q-17). The manual path may never race the agent for the write lock.
 * - **Connected** (Q-22). An edit with nowhere to send it would move the part in this browser
 *   only, showing a position that exists nowhere else â€” the silent lie this product's whole
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
    ? 'Not connected to the build â€” reconnecting. Editing will come back on its own.'
    : runState !== 'paused'
      ? 'Editing needs the build paused, so your change cannot land mid-action.'
      : '';
  return options.explain ? reason : reason === '';
}

```

### frontend/src/point-ui.js

```js
// DOM wiring for pointing, priority and the edit tools.
//
// Impure by design and not unit-tested, for the same reason `attachControls` and
// `SocketClient` are not: every decision worth checking has already been lifted out into
// picking.js, annotate.js, capture.js and edit-tools.js, which are pure and covered. What is
// left here is listeners and element lookups, where a test would be testing a fake DOM.
//
// Kept out of main.js so that file stays a composition root â€” the same split connect-ui.js
// made for the Connect button.

import {
  createPointState,
  setSelection,
  toggleFocus,
  applyServerFocus,
  clearSelection,
  buildAnnotateMessage,
  buildFocusMessage,
  describeSelection,
} from './annotate.js';
import { cropRect, fitWithin } from './capture.js';
import {
  buildDeleteMessage,
  buildDuplicateMessage,
  buildMoveMessage,
  editingAllowed,
} from './edit-tools.js';
import { NOTHING, cssToFrame, pickAt, pickInPath } from './picking.js';

/** How far a pointer must travel before a click becomes a lasso, in CSS pixels. */
const DRAG_THRESHOLD = 6;

/**
 * Wire the pointing and editing controls.
 *
 * @param {HTMLElement} root the whole layout â€” the composer lives over the canvas and the
 *   controls live in the panel, so this needs to see both (same reason attachControls takes
 *   the layout rather than .controls-panel).
 * @param {{renderer: object, send: (msg: object) => boolean, onError: (m: string) => void}} io
 */
export function attachPointing(root, io) {
  const state = createPointState();
  const canvas = root.querySelector('#viewport-canvas');
  const panel = root.querySelector('.viewport-panel');
  const composer = root.querySelector('#point-composer');
  const selectionLabel = root.querySelector('#point-selection');
  const textInput = root.querySelector('[data-field="annotate-text"]');
  const note = root.querySelector('#point-note');
  const focusList = root.querySelector('#focus-list');
  const modeButton = root.querySelector('[data-action="point-mode"]');
  const editGroup = root.querySelector('#edit-group');
  const editBlocked = root.querySelector('#edit-blocked');
  const pauseToEdit = root.querySelector('[data-action="pause-to-edit"]');

  let pointMode = false;
  let attachView = false;
  let run = { runState: 'running', connected: false };
  let drag = null;

  const only = () => [...state.selection][0] ?? '';

  const renderFocus = () => {
    focusList.replaceChildren(
      ...[...state.focus].map((objectId) => {
        const li = document.createElement('li');
        li.className = 'focus-chip';
        li.textContent = objectId;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = 'Ã—';
        remove.setAttribute('aria-label', `Stop watching ${objectId}`);
        remove.addEventListener('click', () => {
          toggleFocus(state, objectId);
          io.send(buildFocusMessage(state));
          renderFocus();
        });
        li.append(remove);
        return li;
      }),
    );
    io.renderer.setFocused(state.focus);
  };

  const renderSelection = () => {
    io.renderer.setSelected(state.selection);
    selectionLabel.textContent = describeSelection(state);
    composer.hidden = state.selection.size === 0;
    if (!composer.hidden) textInput.focus();
    renderEditability();
  };

  // Q-20: the reason, not just the fact. A disabled control with nothing said about it is
  // indistinguishable from a broken one, and the Pause that unblocks it is right here.
  const renderEditability = () => {
    const reason = editingAllowed(run, { explain: true });
    editGroup.dataset.blocked = reason ? 'true' : 'false';
    editBlocked.textContent = state.selection.size === 0 ? '' : reason;
    pauseToEdit.hidden = !(reason && run.connected && state.selection.size > 0);
  };

  /** The crop of the live view that goes with an annotation (Q-08, Q-23). */
  const captureCrop = (path) => {
    const frame = io.renderer.frame;
    if (!frame || !attachView) return '';
    const rect = cropRect(path, frame);
    const fitted = fitWithin(rect.width, rect.height);
    const out = document.createElement('canvas');
    out.width = fitted.width;
    out.height = fitted.height;
    out
      .getContext('2d')
      .drawImage(canvas, rect.x, rect.y, rect.width, rect.height, 0, 0, fitted.width, fitted.height);
    return out.toDataURL('image/png');
  };

  let lastPath = [];

  const pickFrom = (path) => {
    const frame = io.renderer.frame;
    if (!frame) return;
    lastPath = path;
    const ids =
      path.length > 2 ? pickInPath(frame, path) : [pickAt(frame, path[0][0], path[0][1])];
    const names = ids
      .filter((id) => id !== NOTHING)
      .map((id) => io.renderer.ids.objectFor(id))
      .filter(Boolean);
    setSelection(state, names);
    renderSelection();
  };

  const hoverFrom = (event) => {
    const frame = io.renderer.frame;
    if (!frame) return;
    const point = cssToFrame(frame, canvas.getBoundingClientRect(), event.clientX, event.clientY);
    const picked = pickAt(frame, point[0], point[1]);
    const objectId = picked === NOTHING ? null : io.renderer.ids.objectFor(picked);
    io.renderer.setHovered(objectId ? [objectId] : []);
  };

  const clearHover = () => io.renderer.setHovered([]);

  // ---- point mode -----------------------------------------------------------------
  // Q-05 chose a mode you switch into, so nothing an operator already does changes
  // behaviour and a camera angle can never be lost by trying to circle something.
  modeButton?.addEventListener('click', () => {
    pointMode = !pointMode;
    modeButton.setAttribute('aria-pressed', String(pointMode));
    panel.dataset.pointMode = pointMode ? 'on' : 'off';
    if (!pointMode) {
      clearHover();
      clearSelection(state);
      renderSelection();
    }
  });

  canvas?.addEventListener(
    'pointerdown',
    (event) => {
      if (!pointMode) return;
      // Stop the orbit camera seeing this one. Point mode means drag draws a loop.
      event.stopPropagation();
      clearHover();
      drag = { path: [cssToFrame(io.renderer.frame ?? { width: 0, height: 0 }, canvas.getBoundingClientRect(), event.clientX, event.clientY)], startX: event.clientX, startY: event.clientY };
    },
    true,
  );

  canvas?.addEventListener(
    'pointermove',
    (event) => {
      if (!pointMode) return;
      if (!drag) {
        hoverFrom(event);
        return;
      }
      event.stopPropagation();
      drag.path.push(
        cssToFrame(io.renderer.frame ?? { width: 0, height: 0 }, canvas.getBoundingClientRect(), event.clientX, event.clientY),
      );
    },
    true,
  );

  const endDrag = (event) => {
    if (!pointMode || !drag) return;
    event.stopPropagation();
    const moved = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
    // A click is a one-point path. Treating a stray click as a loop would select the whole
    // scene, which picking.js refuses anyway â€” this is what makes the click a click.
    pickFrom(moved < DRAG_THRESHOLD ? [drag.path[0]] : drag.path);
    drag = null;
  };
  canvas?.addEventListener('pointerup', endDrag, true);
  canvas?.addEventListener('pointercancel', endDrag, true);
  canvas?.addEventListener('pointerleave', clearHover, true);

  // Q-24: the canvas is already keyboard-operable for orbit and zoom, so pointing not being
  // would make this the one thing on the page needing a mouse.
  canvas?.addEventListener('keydown', (event) => {
    if (!pointMode) return;
    const ids = [...io.renderer.nodes.values()].map((node) => node.id).sort();
    if (ids.length === 0) return;
    if (event.key === 'Tab' && !event.shiftKey) {
      event.preventDefault();
      const next = ids[(ids.indexOf(only()) + 1) % ids.length];
      setSelection(state, [next]);
      renderSelection();
    } else if (event.key === ' ' && only()) {
      event.preventDefault();
      toggleFocus(state, only());
      io.send(buildFocusMessage(state));
      renderFocus();
    } else if (event.key === 'Escape') {
      clearSelection(state);
      renderSelection();
    }
  });

  // ---- the composer ---------------------------------------------------------------
  composer?.addEventListener('submit', (event) => {
    event.preventDefault();
    try {
      const message = buildAnnotateMessage(state, {
        text: textInput.value,
        image: captureCrop(lastPath),
      });
      if (io.send(message) !== false) {
        textInput.value = '';
        note.textContent = 'Sent. The agent picks it up on its next action.';
      }
    } catch (err) {
      // Beside the field they typed into, which is the whole reason the guards are
      // duplicated client-side rather than left to the backend.
      note.textContent = err instanceof Error ? err.message : String(err);
    }
  });

  root.querySelector('[data-action="toggle-focus"]')?.addEventListener('click', () => {
    for (const objectId of state.selection) toggleFocus(state, objectId);
    io.send(buildFocusMessage(state));
    renderFocus();
  });

  root.querySelector('[data-action="attach-image"]')?.addEventListener('click', (event) => {
    attachView = !attachView;
    event.currentTarget.setAttribute('aria-pressed', String(attachView));
    note.textContent = attachView ? 'The next message will carry a picture of this view.' : '';
  });

  root.querySelector('[data-action="close-composer"]')?.addEventListener('click', () => {
    clearSelection(state);
    renderSelection();
  });

  root.querySelector('[data-action="clear-focus"]')?.addEventListener('click', () => {
    applyServerFocus(state, []);
    io.send(buildFocusMessage(state));
    renderFocus();
  });

  // Pasting a reference image is the common case of Q-09 ("more like this"), and it needs no
  // affordance of its own â€” Ctrl+V into the composer is where anyone would try it first.
  textInput?.addEventListener('paste', (event) => {
    const file = [...(event.clipboardData?.items ?? [])]
      .find((item) => item.type.startsWith('image/'))
      ?.getAsFile();
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        io.send(buildAnnotateMessage(state, { text: textInput.value, image: String(reader.result) }));
        textInput.value = '';
        note.textContent = 'Sent, with your image.';
      } catch (err) {
        note.textContent = err instanceof Error ? err.message : String(err);
      }
    };
    reader.readAsDataURL(file);
  });

  // ---- the edit tools -------------------------------------------------------------
  const sendEdit = (build) => {
    if (!only()) return;
    try {
      io.send(build(only()));
    } catch (err) {
      io.onError(err instanceof Error ? err.message : String(err));
    }
  };

  root.querySelector('[data-action="edit-move"]')?.addEventListener('click', () => {
    const to = ['x', 'y', 'z'].map((axis) =>
      Number.parseFloat(root.querySelector(`[data-field="edit-${axis}"]`)?.value ?? ''),
    );
    if (to.some((component) => !Number.isFinite(component))) {
      io.onError('Enter an x, y and z to move to.');
      return;
    }
    sendEdit((objectId) => buildMoveMessage(objectId, to));
  });

  root.querySelector('[data-action="edit-duplicate"]')?.addEventListener('click', () => {
    sendEdit((objectId) => buildDuplicateMessage(objectId, `${objectId}_copy`));
  });

  root.querySelector('[data-action="edit-delete"]')?.addEventListener('click', () => {
    sendEdit(buildDeleteMessage);
  });

  pauseToEdit?.addEventListener('click', () => io.send({ type: 'pause', data: {} }));

  renderFocus();
  renderSelection();

  return {
    /** The server is the authority on focus â€” see annotate.js's applyServerFocus. */
    applyFocus(objectIds) {
      applyServerFocus(state, objectIds);
      renderFocus();
    },
    /**
     * Q-22: a disconnect reverts and says so. The selection is dropped because the ids it
     * names may not survive the resync, and a stale selection would silently annotate the
     * wrong part once the scene came back.
     */
    setRun(next) {
      run = { ...run, ...next };
      if (!run.connected) {
        clearSelection(state);
        renderSelection();
      }
      renderEditability();
    },
  };
}

```

### frontend/src/connect-ui.js

```js
// The Connect button's DOM wiring. Every decision it makes comes from connect.js; this
// file only moves text and focus around, which is why it has no unit test of its own â€”
// the same reason `attachControls` and `SocketClient` do not (frontend/CLAUDE.md). What it
// *is* covered by is frontend/tests-browser/connect.browser.mjs, in a real browser, because
// the parts that can be wrong here â€” a modal that leaves focus behind it, a picker Escape
// does not close â€” are not visible to node:test at all.
//
// All three outcomes are shown in the dialog, not in the sidebar. That is a layout decision
// with a reason: the conversation panel is ~340px wide, and a written-config result is five
// lines including the restart warning. Rendered inline it squeezed the transcript to zero
// height â€” the operator lost the panel they use continuously to a setup step they run once.
//
// The dialog is a native <dialog>. Written by hand, a modal has to move focus in, keep it
// there, close on Escape and put focus back where it came from; the platform already does
// all four, and a hand-rolled one that misses the last of them strands a keyboard user in a
// panel they can no longer see.

import {
  planConnect,
  choiceLabel,
  describeSuccess,
  describeFailure,
  loadClients,
  connectClient,
} from './connect.js';

function outcomeNodes(outcome) {
  const nodes = [];

  const title = document.createElement('p');
  title.className = 'connect-result-title';
  title.textContent = outcome.title;
  nodes.push(title);

  if (outcome.path) {
    const path = document.createElement('p');
    path.className = 'connect-result-path';
    path.textContent = outcome.path;
    nodes.push(path);
  }

  for (const line of outcome.lines ?? []) {
    const row = document.createElement('p');
    // `critical` is the restart instruction. Rendered as one more muted line among four it
    // gets skimmed past, and the user goes looking for tools that will not be there until
    // they do the one thing this paragraph asked for.
    row.className =
      line === outcome.critical ? 'connect-result-line connect-result-critical' : 'connect-result-line';
    row.textContent = line;
    nodes.push(row);
  }
  return nodes;
}

function buildChoice(client, onPick) {
  const item = document.createElement('li');
  const choice = document.createElement('button');
  choice.type = 'button';
  choice.className = 'connect-choice';
  choice.dataset.clientId = client.id;

  const name = document.createElement('span');
  name.className = 'connect-choice-label';
  name.textContent = choiceLabel(client);

  // The path is part of the choice, not decoration: this is the file about to change, and
  // on a machine with more than one checkout it is the only thing telling two rows apart.
  const path = document.createElement('span');
  path.className = 'connect-choice-path';
  path.textContent = client.config_path ?? '';

  choice.append(name, path);
  choice.addEventListener('click', () => onPick(client));
  item.appendChild(choice);
  return item;
}

/**
 * Wire the Connect button and its dialog.
 *
 * The one thing this must never do is claim more than it did. Connecting writes a config
 * file; it does not open a connection, and nothing in this page changes when it works â€” the
 * agent turns up the next time that client starts. A user who believes otherwise stands
 * here waiting for something that is going to happen somewhere else, decides the product is
 * broken, and is right to.
 *
 * @param {ParentNode} root anything containing the button and the dialog â€” main.js passes
 *   `document`, since the dialog renders in the top layer and sits outside `<main>`.
 * @param {{fetchImpl?: typeof fetch}} [io] `fetchImpl` exists for tests; the default
 *   resolves the page's own `fetch` at call time.
 */
export function attachConnectButton(root, io = {}) {
  const button = root.querySelector('#connect-button');
  const dialog = root.querySelector('#connect-dialog');
  const body = root.querySelector('#connect-dialog-body');
  const dismiss = root.querySelector('[data-action="connect-cancel"]');
  if (!button || !dialog || !body) return;

  const fetchImpl = io.fetchImpl ?? ((...args) => globalThis.fetch(...args));
  let busy = false;

  // Never `disabled`: disabling the element that currently has focus drops focus to the
  // body, so a keyboard user who just pressed Enter loses their place mid-action. A flag
  // plus aria-busy says the same thing to everyone and keeps the button where it was.
  const setBusy = (value) => {
    busy = value;
    button.setAttribute('aria-busy', String(value));
  };

  const open = () => {
    if (!dialog.open) dialog.showModal();
  };

  /** Show a finished outcome. `dismiss` becomes the way out, so focus belongs on it. */
  const showOutcome = (outcome) => {
    body.dataset.tone = outcome.tone;
    body.replaceChildren(...outcomeNodes(outcome));
    if (dismiss) dismiss.textContent = 'Close';
    open();
    // The picker's buttons have just been removed. Something has to hold focus or it falls
    // to the dialog itself and the next Tab starts from the top of the page.
    dismiss?.focus();
  };

  const showChoices = (clients, onPick) => {
    body.dataset.tone = 'choose';
    const list = document.createElement('ul');
    list.className = 'connect-choices';
    list.append(...clients.map((client) => buildChoice(client, onPick)));
    body.replaceChildren(list);
    if (dismiss) dismiss.textContent = 'Cancel';
    open();
    list.querySelector('button')?.focus();
  };

  async function write(client) {
    setBusy(true);
    const result = await connectClient(fetchImpl, client.id);
    setBusy(false);
    showOutcome(result.ok ? describeSuccess(result, client) : describeFailure(result.error));
  }

  button.addEventListener('click', async () => {
    if (busy) return;
    // Cleared before the lookup: a result left over from the last press, sitting there while
    // a fresh one is still in flight, reads as the answer to the click just made.
    body.replaceChildren();
    setBusy(true);
    const found = await loadClients(fetchImpl);
    setBusy(false);

    if (!found.ok) {
      showOutcome(describeFailure(found.error));
      return;
    }

    const plan = planConnect(found.clients);
    if (plan.action === 'none') showOutcome(plan.outcome);
    else if (plan.action === 'connect') await write(plan.client);
    else showChoices(plan.clients, (picked) => write(picked));
  });

  dismiss?.addEventListener('click', () => dialog.close());
  // `close` fires for Escape and for the dismiss button alike. Chrome restores focus to the
  // opener on its own, but only when nothing else has claimed it in between â€” putting it
  // back explicitly is one line and removes the "in between".
  dialog.addEventListener('close', () => button.focus());
}

```

### frontend/src/log.js

```js
// The action log (Gate A 5.1, 5.3): a running record of what the build has done, capped
// so a run of thousands of operations (Gate A 11.4) does not grow the DOM or memory
// without bound. Split from viewport.js because it is a distinct actor â€” it reacts to
// LOG server messages, not mesh/transform/highlight ones â€” and from controls.js because
// it only ever receives, never sends.

/** Long autonomous runs are the norm (Gate A 4.4); this is generous but not unbounded. */
export const DEFAULT_MAX_ENTRIES = 500;

/**
 * @param {number} [maxEntries]
 * @returns {{entries: object[], maxEntries: number}}
 */
export function createActionLog(maxEntries = DEFAULT_MAX_ENTRIES) {
  if (!Number.isInteger(maxEntries) || maxEntries < 1) {
    throw new Error(`maxEntries must be a positive integer, got ${maxEntries}`);
  }
  return { entries: [], maxEntries };
}

/**
 * Append one entry, oldest-first, dropping the oldest entries once maxEntries is
 * exceeded. Mutates and returns `log` so callers can chain.
 *
 * @param {ReturnType<typeof createActionLog>} log
 * @param {object} entry any JSON-shaped record â€” main.js appends `{text, seq, at}` for
 *   every LOG message and a synthesized entry for phase/run_state/problems changes.
 */
export function appendLogEntry(log, entry) {
  log.entries.push(entry);
  // Total ever appended, never reset by the cap. Reconciling on list length alone
  // cannot distinguish 'nothing new' from 'one added and one dropped off the front',
  // and the second case renders a log that silently stops updating.
  log.appended = (log.appended ?? 0) + 1;
  const overflow = log.entries.length - log.maxEntries;
  if (overflow > 0) {
    log.entries.splice(0, overflow);
  }
  return log;
}

/**
 * Render the log into a container element, newest entry last (reading order).
 *
 * Appends only what is new. Rebuilding wholesale was simpler, but this container is an
 * aria-live region and this runs on every incoming message â€” so a full rebuild made a
 * screen reader announce the entire reconstructed history on every geometry update.
 *
 * @param {ReturnType<typeof createActionLog>} log
 * @param {HTMLElement} container
 */
function buildRow(entry) {
  const row = document.createElement('li');
  row.className = 'log-row';
  if (entry.kind) row.dataset.kind = entry.kind;
  const text = document.createElement('span');
  text.className = 'log-row-text';
  text.textContent = entry.text ?? '';
  row.appendChild(text);
  return row;
}

export function renderActionLog(log, container) {
  const appended = log.appended ?? log.entries.length;
  const alreadyRendered = container.__renderedAppended ?? 0;
  const fresh = Math.min(Math.max(appended - alreadyRendered, 0), log.entries.length);

  const fragment = document.createDocumentFragment();
  for (const entry of log.entries.slice(log.entries.length - fresh)) {
    fragment.appendChild(buildRow(entry));
  }
  if (fragment.childElementCount > 0) container.appendChild(fragment);

  // Drop from the front so the DOM never outgrows the log the cap actually keeps.
  while (container.childElementCount > log.entries.length) {
    container.removeChild(container.firstElementChild);
  }

  container.__renderedAppended = appended;
  container.scrollTop = container.scrollHeight;
}

```

### frontend/src/transcript.js

```js
// The conversation panel: a transcript of what the operator asked for and what the agent
// said back. Split from log.js rather than folded into it because it is a different
// decision, not a different style of row â€” the action log only ever receives, whereas the
// transcript has to reconcile a line this browser printed optimistically against the
// server's later echo of the same line. log.js's append-only counter cannot express that:
// reconciling changes an entry that is already on screen.
//
// The append/cap/drop-from-the-DOM machinery is deliberately the same shape as log.js's,
// for the same reason: this container is an aria-live region, and rebuilding it on every
// message makes a screen reader re-announce the entire history each time.
//
// Roles ride in ServerMessage.data.role (contracts/wire.py's free-form `data` dict):
//   operator â€” the operator's own words, echoed back once the backend has queued them.
//              Seeing your own line come back IS the delivery confirmation.
//   agent    â€” what the agent just did or found.
//   system   â€” status: connected, phase changes, run state.

/** Mirrors the roles src/viewer puts in a LOG message's `data.role`. */
export const TRANSCRIPT_ROLES = Object.freeze(['operator', 'agent', 'system']);

/** Long autonomous runs are the norm (Gate A 4.4); generous, but never unbounded. */
export const DEFAULT_MAX_MESSAGES = 200;

/** What each row says about whether the backend actually has an operator's words yet. */
const OPERATOR_STATE_MARKER = Object.freeze({
  pending: 'sendingâ€¦',
  confirmed: 'queued for the agent',
  unconfirmed: 'not delivered â€” send it again',
});

const WHO = Object.freeze({ operator: 'You', agent: 'Agent', system: 'System' });

/**
 * Create the transcript's state.
 *
 * `maxMessages` is a hard ceiling on both the array and the rendered rows. Getting it
 * wrong in the "unbounded" direction is not a leak that shows up in a benchmark â€” it is a
 * page that grows all day during a build and eventually stops responding to the operator
 * who needs to stop it.
 *
 * @param {number} [maxMessages]
 * @returns {{entries: object[], maxMessages: number, appended: number, lastSeq: number|null, revision: number}}
 */
export function createTranscript(maxMessages = DEFAULT_MAX_MESSAGES) {
  if (!Number.isInteger(maxMessages) || maxMessages < 1) {
    throw new Error(`maxMessages must be a positive integer, got ${maxMessages}`);
  }
  return { entries: [], maxMessages, appended: 0, lastSeq: null, revision: 0 };
}

function push(transcript, entry) {
  // `appended` is a total ever appended, never reset by the cap â€” reconciling on array
  // length alone cannot tell 'nothing new' from 'one added and one dropped off the
  // front', and the second case renders a panel that silently stops updating.
  transcript.appended += 1;
  transcript.entries.push({ id: transcript.appended, ...entry });
  const overflow = transcript.entries.length - transcript.maxMessages;
  if (overflow > 0) transcript.entries.splice(0, overflow);
  return transcript.entries[transcript.entries.length - 1];
}

/**
 * Show the operator's own line immediately, before the server has seen it.
 *
 * Waiting for the round trip first would leave the panel blank at the one moment the
 * operator is watching it hardest, which reads as "the product ignored me". The entry
 * starts `pending` and is not claimed as delivered until the server echoes it back.
 *
 * @param {ReturnType<typeof createTranscript>} transcript
 * @param {string} text
 * @returns {object} the entry just appended
 */
export function appendOperatorMessage(transcript, text) {
  if (typeof text !== 'string' || text.trim() === '') {
    throw new Error('an empty message would be silently dropped');
  }
  return push(transcript, { role: 'operator', text, state: 'pending', seq: null });
}

function normalizeRole(role) {
  // A LOG with no role must never make a message disappear: older backends send exactly
  // that, and a panel that hides messages from a server that is working perfectly well is
  // indistinguishable, to the operator, from a build that has stopped.
  return TRANSCRIPT_ROLES.includes(role) ? role : 'system';
}

/**
 * Apply one LOG ServerMessage.
 *
 * An `operator` message is the server's echo of something this browser already printed,
 * so it confirms the pending line rather than printing it a second time â€” an operator who
 * sees their instruction twice believes they sent it twice. When nothing pending matches
 * (a page opened mid-run, or a second browser watching the same build) it is appended
 * instead: showing a duplicate is bad, losing an instruction from the record is worse.
 *
 * @param {ReturnType<typeof createTranscript>} transcript
 * @param {{seq?: number, text?: string, data?: {role?: string}}} message a wire LOG
 *   message, or a locally generated status line with no `seq`.
 */
export function applyServerLog(transcript, message) {
  const seq = message?.seq;
  const hasSeq = typeof seq === 'number';

  // Replayed conversation history, handed over when a client connects. It is exempt from
  // the duplicate rule, and has to be: the entire greeting is sent at a single seq, so
  // every replayed line after the first compares `seq <= lastSeq` and would be dropped â€”
  // silently, and one layer below the socket's own gate, which needs the same exemption
  // for the same reason. That is the difference between a refresh keeping the
  // conversation and a refresh appearing to erase it.
  const replayed = message?.data?.replayed === true;

  if (!replayed && hasSeq && transcript.lastSeq !== null && seq <= transcript.lastSeq) {
    // wire.py's duplicate/out-of-order rule. Retries happen; a retried frame that
    // double-printed would read as the agent repeating itself.
    return transcript;
  }
  // History does not advance the baseline either â€” it is older than everything live.
  if (hasSeq && !replayed) transcript.lastSeq = seq;

  const role = normalizeRole(message?.data?.role);
  const text = message?.text ?? '';

  if (role === 'operator') {
    const pending = transcript.entries.find(
      (entry) => entry.role === 'operator' && entry.state === 'pending' && entry.text === text,
    );
    if (pending) {
      pending.state = 'confirmed';
      pending.seq = hasSeq ? seq : null;
      transcript.revision += 1;
      return transcript;
    }
  }

  push(transcript, { role, text, state: 'confirmed', seq: hasSeq ? seq : null });
  return transcript;
}

/**
 * Mark every still-pending operator line as unconfirmed.
 *
 * Called when the socket drops or a send fails. Without it a line whose echo will never
 * arrive sits looking exactly like a delivered one, and the operator waits for something
 * that is never going to happen.
 *
 * @param {ReturnType<typeof createTranscript>} transcript
 */
export function markPendingUnconfirmed(transcript) {
  for (const entry of transcript.entries) {
    if (entry.state === 'pending') {
      entry.state = 'unconfirmed';
      transcript.revision += 1;
    }
  }
  return transcript;
}

function buildRow(entry) {
  const row = document.createElement('li');
  row.className = 'transcript-row';
  row.dataset.role = entry.role;
  row.dataset.state = entry.state;

  const who = document.createElement('span');
  who.className = 'transcript-who';
  who.textContent = WHO[entry.role];

  const text = document.createElement('span');
  text.className = 'transcript-text';
  text.textContent = entry.text;

  const marker = document.createElement('span');
  marker.className = 'transcript-state';
  // aria-hidden because this is the one part of a row that changes after it is announced.
  // Left in the accessibility tree, flipping 'sendingâ€¦' to 'queued for the agent' would
  // make a polite live region read the whole line back a second time.
  marker.setAttribute('aria-hidden', 'true');
  marker.textContent = stateMarker(entry);

  row.appendChild(who);
  row.appendChild(text);
  row.appendChild(marker);
  row.__marker = marker;
  return row;
}

function stateMarker(entry) {
  return entry.role === 'operator' ? OPERATOR_STATE_MARKER[entry.state] ?? '' : '';
}

function syncRowState(row, entry) {
  if (!row || row.dataset.state === entry.state) return;
  row.dataset.state = entry.state;
  // Only the aria-hidden marker and the data attribute change â€” never the announced text.
  if (row.__marker) row.__marker.textContent = stateMarker(entry);
}

/**
 * Render the transcript into a container, newest message last.
 *
 * Appends what is new and updates in place what changed state; never rebuilds. A rebuild
 * inside this aria-live region re-announces the entire conversation on every message,
 * which is the difference between a usable panel and an unusable one for a screen-reader
 * user on a build that emits hundreds of them.
 *
 * @param {ReturnType<typeof createTranscript>} transcript
 * @param {HTMLElement} container
 */
export function renderTranscript(transcript, container) {
  const appended = transcript.appended;
  const alreadyRendered = container.__renderedAppended ?? 0;
  const fresh = Math.min(Math.max(appended - alreadyRendered, 0), transcript.entries.length);

  const fragment = document.createDocumentFragment();
  for (const entry of transcript.entries.slice(transcript.entries.length - fresh)) {
    fragment.appendChild(buildRow(entry));
  }
  if (fragment.childElementCount > 0) container.appendChild(fragment);

  // Drop from the front so the DOM never outgrows the cap the transcript actually keeps.
  while (container.childElementCount > transcript.entries.length) {
    container.removeChild(container.firstElementChild);
  }

  if (container.__renderedRevision !== transcript.revision) {
    for (let i = 0; i < transcript.entries.length; i += 1) {
      syncRowState(container.children[i], transcript.entries[i]);
    }
    container.__renderedRevision = transcript.revision;
  }

  container.__renderedAppended = appended;
  // The newest message must be visible without the operator hunting for it.
  container.scrollTop = container.scrollHeight;
}

```


## Rendering components

The canvas itself is a native element, but this renderer is the full implementation that produces the visible 3D scene and hover/selection feedback.


### frontend/src/scene-renderer.js

```js
// The real renderer-like object, implemented on Canvas2D â€” no three.js, no network
// fetch, no dependency (see frontend/CLAUDE.md "Why no three.js"). Implements the exact
// four-method shape frontend/src/viewport.js drives against a fake in tests:
// createNode / updateTransform / removeNode / setHighlighted, plus the operator's
// hovered/selected/focused emphasis and start()/stop() for its own render loop.
//
// Most of this file is a browser adapter and is exercised by eye. The camera is NOT: it
// lives in ./camera.js and is covered by frontend/tests/camera.test.js. That split exists
// because this file's "exercised by eye" exemption used to include the camera, and a user
// found what eyes miss â€” the view turned left and right and would not tilt or zoom, since
// `pointermove` read only `clientX`, the tilt was the module constant below, and nothing
// listened for `wheel` at all.
//
// Colors are never hard-coded here: every stroke/fill comes from getComputedStyle of a
// `--token` custom property defined in tokens.css, read once per resize/theme change and
// cached as opaque CSS color strings â€” translucency is done with ctx.globalAlpha rather
// than hand-parsed rgba(), so no hex digit ever appears as a literal in this file. The
// fallbacks below are CSS color keywords, not hex, for the same reason. That is what
// lets frontend/tests/tokens.test.js scan this file for a raw hex literal and find none.

import { OrbitCamera, clipTriangleNear, shadeFactor, triangleNormal, zUpToYUp } from './camera.js';
import { paintIdOutline } from './point-outline.js';
import { clearFrame, createFrame, drawTriangle } from './raster.js';
import { createIdIndex } from './picking.js';

function readColor(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

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

/** Standard v' = v + 2w(qÃ—v) + 2qÃ—(qÃ—v), the per-node orientation from TRANSFORM_UPDATE. */
function rotateByQuaternion([x, y, z], [qx, qy, qz, qw]) {
  const c1x = qy * z - qz * y;
  const c1y = qz * x - qx * z;
  const c1z = qx * y - qy * x;
  const c2x = qy * c1z - qz * c1y;
  const c2y = qz * c1x - qx * c1z;
  const c2z = qx * c1y - qy * c1x;
  return [x + 2 * qw * c1x + 2 * c2x, y + 2 * qw * c1y + 2 * c2y, z + 2 * qw * c1z + 2 * c2z];
}

// The view no longer turns on its own. It used to rotate one slow turn per 40s as a
// "this is live" cue, which is a cue nobody asked for and which makes a model you are
// trying to look at drift out from under you. Liveness is the action log's job.

export class SceneRenderer {
  /** @param {HTMLCanvasElement} canvas */
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.nodes = new Map();
    this._nextHandleId = 0;
    this._running = false;
    this._rafId = null;
    this._lastFrameAt = 0;
    this.camera = new OrbitCamera();
    this._dragging = false;
    this._lastPointerX = 0;
    this._lastPointerY = 0;
    // Named CSS colours as the pre-theme fallback, never hex: tests/tokens.test.js scans
    // every source file for a hex literal outside tokens.css and fails on one.
    this._colors = {
      ink: 'white',
      muted: 'gray',
      accent: 'slateblue',
      pointed: 'mediumslateblue',
      canvas: 'black',
      marked: 'gold',
    };
    this._frame = null;
    this._image = null;
    this._rgbCache = new Map();
    // Picking reads the id the depth test chose, so the renderer is the one place that
    // can assign these â€” see picking.js for why this is not a ray cast.
    this.ids = createIdIndex();
    this._focused = new Set();
    this._hovered = new Set();
    this._selected = new Set();
    this._probeCtx = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
    this._bindPointer();
    this._resizeObserver = new ResizeObserver(() => this._resize());
    this._resizeObserver.observe(canvas);
    this._resize();
  }

  refreshTheme() {
    this._colors = {
      ink: readColor('--ink', this._colors.ink),
      muted: readColor('--muted', this._colors.muted),
      accent: readColor('--accent', this._colors.accent),
      pointed: readColor('--accent-hover', this._colors.pointed),
      marked: readColor('--marked', this._colors.marked),
      canvas: readColor('--canvas', this._colors.canvas),
    };
    this._rgbCache.clear(); // the tokens just changed; the resolved bytes are stale
  }

  createNode(objectId, geometry, materials, groups) {
    const handle = {
      id: objectId,
      handleId: this._nextHandleId++,
      geometry,
      materials,
      groups,
      highlighted: false,
      transform: { position: [0, 0, 0], quaternion: [0, 0, 0, 1], scale: [1, 1, 1] },
    };
    this.nodes.set(handle.handleId, handle);
    return handle;
  }

  updateTransform(handle, position, quaternion, scale) {
    handle.transform = { position, quaternion, scale };
  }

  removeNode(handle) {
    this.nodes.delete(handle.handleId);
    // Retire the picking id with the node. Reusing it would let a pick that was in
    // flight when the object was deleted resolve to whatever took its place.
    this.ids.forget(handle.id);
    this._hovered.delete(handle.id);
    this._selected.delete(handle.id);
    this._focused.delete(handle.id);
  }

  setHighlighted(handle, on) {
    handle.highlighted = on;
  }

  /**
   * The parts the operator marked as important (Q-13).
   *
   * Kept separate from `highlighted`, deliberately. HIGHLIGHT means 'the agent just
   * changed this' and clears every previous id on each message â€” reusing it would wipe
   * the operator's marks every time the agent touched anything, which is the one thing
   * a standing mark must not do.
   */
  setFocused(objectIds) {
    this._focused = new Set(objectIds ?? []);
  }

  /** The visible part currently under the point cursor; cleared as soon as it leaves. */
  setHovered(objectIds) {
    this._hovered = new Set(objectIds ?? []);
  }

  /** Click, lasso and keyboard selections that stay visible until explicitly cleared. */
  setSelected(objectIds) {
    this._selected = new Set(objectIds ?? []);
  }

  /** The current colour+depth+id frame, for picking. Null before the first draw. */
  get frame() {
    return this._frame;
  }

  start() {
    if (this._running) return;
    this.refreshTheme();
    this._running = true;
    this._lastFrameAt = performance.now();
    const tick = (now) => {
      if (!this._running) return;
      this._lastFrameAt = now;
      this._draw();
      this._rafId = requestAnimationFrame(tick);
    };
    this._rafId = requestAnimationFrame(tick);
  }

  stop() {
    this._running = false;
    if (this._rafId) cancelAnimationFrame(this._rafId);
    this._rafId = null;
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(1, Math.round(rect.width * dpr));
    this.canvas.height = Math.max(1, Math.round(rect.height * dpr));
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  _bindPointer() {
    this.canvas.addEventListener('pointerdown', (event) => {
      this._dragging = true;
      this._lastPointerX = event.clientX;
      this._lastPointerY = event.clientY;
      this.canvas.setPointerCapture(event.pointerId);
    });

    // Incremental deltas rather than "current minus drag-start", because the pitch clamp
    // makes the camera's state not a pure function of total displacement: drag past the
    // pole and back and an absolute mapping teleports the view.
    this.canvas.addEventListener('pointermove', (event) => {
      if (!this._dragging) return;
      this.camera.drag(event.clientX - this._lastPointerX, event.clientY - this._lastPointerY);
      this._lastPointerX = event.clientX;
      this._lastPointerY = event.clientY;
    });

    const release = () => {
      this._dragging = false;
    };
    this.canvas.addEventListener('pointerup', release);
    this.canvas.addEventListener('pointercancel', release);

    // `passive: false` and preventDefault, or the wheel zooms the model *and* scrolls the
    // page under it. Only over the canvas; the log beside it must still scroll normally.
    this.canvas.addEventListener(
      'wheel',
      (event) => {
        event.preventDefault();
        this.camera.zoomByWheel(event.deltaY);
      },
      { passive: false },
    );

    // A canvas is not focusable by default, so a keyboard user could reach the controls
    // beside the view and never the view itself. index.html gives it tabindex="0".
    this.canvas.addEventListener('keydown', (event) => {
      const step = event.shiftKey ? 40 : 12;
      const keys = {
        ArrowLeft: () => this.camera.drag(-step, 0),
        ArrowRight: () => this.camera.drag(step, 0),
        ArrowUp: () => this.camera.drag(0, -step),
        ArrowDown: () => this.camera.drag(0, step),
        '+': () => this.camera.zoomBySteps(-1),
        '=': () => this.camera.zoomBySteps(-1),
        '-': () => this.camera.zoomBySteps(1),
        _: () => this.camera.zoomBySteps(1),
        '0': () => this.camera.reset(),
      };
      const action = keys[event.key];
      if (!action) return;
      event.preventDefault();
      action();
    });
  }

  _worldVertices(handle) {
    const { positions } = handle.geometry;
    const { position, quaternion, scale } = handle.transform;
    const out = new Array(positions.length / 3);
    const orbit = this.camera.yaw;
    for (let i = 0; i < positions.length; i += 3) {
      let v = [positions[i] * scale[0], positions[i + 1] * scale[1], positions[i + 2] * scale[2]];
      v = rotateByQuaternion(v, quaternion);
      v = [v[0] + position[0], v[1] + position[1], v[2] + position[2]];
      // World space is Blender's, which is Z-up. Everything below this line â€” the orbit,
      // the projection, the painter's sort â€” assumes Y-up. Without the conversion an 8x8m
      // deck rendered as a wall standing on its edge, which is what the live view showed
      // the first time it had geometry in it.
      v = zUpToYUp(v);
      v = rotateY(v, orbit);
      v = rotateX(v, this.camera.pitch);
      out[i / 3] = v;
    }
    return out;
  }

  /** Resolve a CSS colour string to [r, g, b] without ever naming one in this file.

   * The rasterizer writes bytes, so it needs numbers; `tests/tokens.test.js` scans this file
   * and forbids a colour literal. Letting the browser resolve the token through a 1x1
   * canvas keeps both true â€” the value still comes from `tokens.css`, and nothing here
   * hard-codes it.
   */
  _rgb(cssColor) {
    const cached = this._rgbCache.get(cssColor);
    if (cached) return cached;
    const probe = this._probeCtx;
    probe.clearRect(0, 0, 1, 1);
    probe.fillStyle = cssColor;
    probe.fillRect(0, 0, 1, 1);
    const [r, g, b] = probe.getImageData(0, 0, 1, 1).data;
    const rgb = [r, g, b];
    this._rgbCache.set(cssColor, rgb);
    return rgb;
  }

  /** Mix `rgb` toward the background by `1 - shade`, the flat-shading composite. */
  _shaded(rgb, background, shade) {
    return [
      rgb[0] * shade + background[0] * (1 - shade),
      rgb[1] * shade + background[1] * (1 - shade),
      rgb[2] * shade + background[2] * (1 - shade),
    ];
  }

  _draw() {
    const { ctx, canvas } = this;
    const width = canvas.width;
    const height = canvas.height;
    if (width === 0 || height === 0) return;

    const background = this._rgb(this._colors.canvas);
    const surface = this._rgb(this._colors.muted);
    const accent = this._rgb(this._colors.accent);
    const pointed = this._rgb(this._colors.pointed);
    const marked = this._rgb(this._colors.marked);
    const ink = this._rgb(this._colors.ink);

    if (!this._frame || this._frame.width !== width || this._frame.height !== height) {
      this._frame = createFrame(width, height);
      this._image = ctx.createImageData(width, height);
    }
    const frame = this._frame;
    clearFrame(frame, background);

    if (this.nodes.size === 0) {
      this._image.data.set(frame.color);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.putImageData(this._image, 0, 0);
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return;
    }

    let radius = 1;
    const allWorld = new Map();
    const pointedIds = new Set();
    for (const handle of this.nodes.values()) {
      const world = this._worldVertices(handle);
      allWorld.set(handle.handleId, world);
      for (const [x, y, z] of world) {
        radius = Math.max(radius, Math.hypot(x, y, z));
      }
    }

    const camDist = this.camera.distanceFor(radius);
    // Backing-store pixels, not CSS pixels: the rasterizer writes into the backing store
    // directly, so a 2x display would otherwise render a half-size image into a full-size
    // buffer.
    const focal = Math.min(width, height) * 0.9;

    // Anything at or past `camDist` in view depth is level with or behind the eye, where
    // the perspective divide has no answer. Clipped, never clamped.
    const nearPlane = camDist - Math.max(camDist * 0.02, 1e-4);

    // Depth is 1/w, which is what the rasterizer interpolates: 1/w is linear in screen
    // space under a perspective divide and view-space z is not.
    const project = ([x, y, z]) => {
      const invW = 1 / (camDist - z);
      const f = focal * invW;
      return [width / 2 + x * f, height / 2 - y * f, invW];
    };

    for (const handle of this.nodes.values()) {
      const world = allWorld.get(handle.handleId);
      const { indices } = handle.geometry;
      // Point feedback reads first while it is active, then reveals the exact standing
      // state underneath when cleared. Focus is persistent operator intent; a change
      // highlight is the last thing the agent touched and may be replaced at any moment.
      const isPointed = this._selected.has(handle.id) || this._hovered.has(handle.id);
      const focused = this._focused.has(handle.id);
      const base = isPointed ? pointed : focused ? marked : handle.highlighted ? accent : surface;
      const id = this.ids.idFor(handle.id);
      if (isPointed) pointedIds.add(id);

      for (let i = 0; i < indices.length; i += 3) {
        const a = world[indices[i]];
        const b = world[indices[i + 1]];
        const c = world[indices[i + 2]];
        if (!a || !b || !c) continue;

        const shade = shadeFactor(triangleNormal(a, b, c));
        const rgb = this._shaded(base, background, shade);

        // No sort, no subdivision, no seam inflation. The depth buffer decides visibility
        // per pixel, so draw order does not matter and none of those are needed.
        for (const [ca, cb, cc] of clipTriangleNear(a, b, c, nearPlane)) {
          drawTriangle(frame, project(ca), project(cb), project(cc), rgb, id);
        }
      }
    }

    this._image.data.set(frame.color);
    // Fill colour alone can disappear into flat shading. Draw an unshaded, DPR-aware halo
    // around the visible silhouette so hover and committed selection read at a glance.
    const dpr = window.devicePixelRatio || 1;
    paintIdOutline(
      this._image.data,
      frame.ids,
      width,
      height,
      pointedIds,
      ink,
      Math.max(2, Math.round(dpr * 2)),
    );
    // putImageData ignores the current transform, so the DPR scale set in _resize would
    // double-apply. Reset around it and restore afterwards for anything drawing in CSS
    // pixels later.
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.putImageData(this._image, 0, 0);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
}

```

### frontend/src/viewport.js

```js
// The live 3D view's state layer (Gate A 5.1, 5.3).
//
// Split on purpose: this file owns the payload -> BufferGeometry-shaped-buffer
// translation and the scene-graph bookkeeping (which object_id maps to which renderer
// handle), and nothing here touches a canvas, WebGL context, or three.js. That is what
// lets frontend/tests/viewport.test.js exercise the translation with a plain object
// standing in for the renderer â€” see "Why no three.js" in frontend/CLAUDE.md. The real
// renderer (frontend/src/scene-renderer.js) implements the same four-method shape
// (createNode/updateTransform/removeNode/setHighlighted) against a 2D canvas, and
// frontend/src/main.js is the only file that wires the two together.
//
// wire.py's own comment on MeshPayload is the reason for the typed-array conversion:
// "flat lists of floats/ints ... map straight onto BufferGeometry attributes ... with no
// per-vertex object churn, which is what keeps a thousands-of-objects scene responsive."

/**
 * Convert one wire MeshPayload into typed-array buffers.
 *
 * Pure and synchronous. Throws if the payload is internally inconsistent (indices not a
 * multiple of 3, or a triangle_count that disagrees with the index buffer) rather than
 * silently building a corrupt mesh â€” the same "measurement over guesswork" stance the
 * rest of this product takes (Gate A 11.3).
 *
 * @param {object} mesh a wire MeshPayload: object_id, positions, indices, normals?,
 *   uvs?, materials?, groups?, triangle_count
 * @returns {{positions: Float32Array, indices: Uint32Array, normals: Float32Array|null,
 *   uvs: Float32Array|null, vertexCount: number, triangleCount: number,
 *   materials: readonly string[], groups: readonly (readonly [number, number, number])[]}}
 */
export function buildGeometryBuffers(mesh) {
  const positions = Float32Array.from(mesh.positions ?? []);
  const indices = Uint32Array.from(mesh.indices ?? []);

  if (positions.length % 3 !== 0) {
    throw new Error(
      `mesh ${mesh.object_id ?? '?'}: positions length ${positions.length} is not a multiple of 3`,
    );
  }
  if (indices.length % 3 !== 0) {
    throw new Error(
      `mesh ${mesh.object_id ?? '?'}: indices length ${indices.length} is not a multiple of 3`,
    );
  }

  const vertexCount = positions.length / 3;
  const triangleCount = indices.length / 3;

  if (typeof mesh.triangle_count === 'number' && mesh.triangle_count !== triangleCount) {
    throw new Error(
      `mesh ${mesh.object_id ?? '?'}: triangle_count ${mesh.triangle_count} does not match the ` +
        `index buffer (${triangleCount} triangles) â€” the payload is internally inconsistent`,
    );
  }

  return {
    positions,
    indices,
    normals: mesh.normals ? Float32Array.from(mesh.normals) : null,
    uvs: mesh.uvs ? Float32Array.from(mesh.uvs) : null,
    vertexCount,
    triangleCount,
    materials: mesh.materials ?? [],
    groups: mesh.groups ?? [],
  };
}

/** A fresh, empty viewport scene graph. */
export function createViewportState() {
  return {
    /** @type {Map<string, {handle: unknown, transform: {position: number[], quaternion: number[], scale: number[]}}>} */
    nodes: new Map(),
    /** @type {Set<string>} exactly the object_ids the last HIGHLIGHT message named */
    highlighted: new Set(),
  };
}

const IDENTITY_TRANSFORM = Object.freeze({
  position: [0, 0, 0],
  quaternion: [0, 0, 0, 1],
  scale: [1, 1, 1],
});

/**
 * Apply a MESH_UPSERT: "new or topology-changed objects, with buffers" (wire.py). This
 * is the expensive path â€” it always rebuilds geometry, even for an id that already has
 * a node, because a topology change means the old buffers are no longer valid. A node
 * that only moved arrives as TRANSFORM_UPDATE instead; see applyTransformUpdate.
 *
 * @param {ReturnType<typeof createViewportState>} state
 * @param {{meshes: object[]}} message
 * @param {object} renderer createNode/updateTransform/removeNode/setHighlighted
 */
export function applyMeshUpsert(state, message, renderer) {
  for (const meshPayload of message.meshes ?? []) {
    const objectId = meshPayload.object_id;
    const existing = state.nodes.get(objectId);
    if (existing) {
      renderer.removeNode(existing.handle);
    }
    const geometry = buildGeometryBuffers(meshPayload);
    const handle = renderer.createNode(objectId, geometry, geometry.materials, geometry.groups);
    state.nodes.set(objectId, { handle, transform: IDENTITY_TRANSFORM });
    if (state.highlighted.has(objectId)) {
      renderer.setHighlighted(handle, true);
    }
  }
}

/**
 * Apply a TRANSFORM_UPDATE: "the cheap path â€” node transforms only, no buffers. The
 * common case" (wire.py). Must never call renderer.createNode â€” that is the entire
 * reason the wire protocol has two message types instead of one.
 *
 * An update naming an object_id with no existing node is a no-op: the operator's view
 * can only ever be a beat behind the scene, and a stray transform for an id that has not
 * arrived yet (or was already removed) is not an error worth surfacing as one.
 *
 * @param {ReturnType<typeof createViewportState>} state
 * @param {{transforms: object[]}} message
 * @param {object} renderer
 */
export function applyTransformUpdate(state, message, renderer) {
  for (const transform of message.transforms ?? []) {
    const entry = state.nodes.get(transform.object_id);
    if (!entry) continue;
    const { position, quaternion, scale = [1, 1, 1] } = transform;
    renderer.updateTransform(entry.handle, position, quaternion, scale);
    entry.transform = { position, quaternion, scale };
  }
}

/**
 * Apply OBJECTS_REMOVED: drop the node and free its map entry (not just hide it) so a
 * long run does not leak renderer handles for objects that no longer exist.
 *
 * @param {ReturnType<typeof createViewportState>} state
 * @param {{object_ids: string[]}} message
 * @param {object} renderer
 */
export function applyObjectsRemoved(state, message, renderer) {
  for (const objectId of message.object_ids ?? []) {
    const entry = state.nodes.get(objectId);
    if (!entry) continue;
    renderer.removeNode(entry.handle);
    state.nodes.delete(objectId);
    state.highlighted.delete(objectId);
  }
}

/**
 * Drop every node and clear the highlight set. Used when a FULL_SCENE snapshot arrives
 * (on connect, or after a resync) â€” the incoming snapshot is authoritative, so anything
 * the client currently holds that is not in it must not linger as a stale ghost.
 *
 * @param {ReturnType<typeof createViewportState>} state
 * @param {object} renderer
 */
export function clearViewportState(state, renderer) {
  for (const entry of state.nodes.values()) {
    renderer.removeNode(entry.handle);
  }
  state.nodes.clear();
  state.highlighted.clear();
}

/**
 * Apply HIGHLIGHT: "what just changed, so the operator can find it without hunting"
 * (wire.py, citing Gate A 5.3). Marks exactly the given ids and clears every previously
 * highlighted id â€” a highlight that accumulates makes "what just changed" useless within
 * a minute of a long-running build.
 *
 * @param {ReturnType<typeof createViewportState>} state
 * @param {{object_ids: string[]}} message
 * @param {object} renderer
 */
export function applyHighlight(state, message, renderer) {
  for (const objectId of state.highlighted) {
    const entry = state.nodes.get(objectId);
    if (entry) renderer.setHighlighted(entry.handle, false);
  }

  state.highlighted = new Set(message.object_ids ?? []);

  for (const objectId of state.highlighted) {
    const entry = state.nodes.get(objectId);
    if (entry) renderer.setHighlighted(entry.handle, true);
  }
}

```

