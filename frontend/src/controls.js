// Operator controls (Gate A 5.4, 3.1): pause / resume / rollback N steps / redirect in
// words / check-cadence setting. wire.py's ClientMessageType docstring frames the whole
// module: "The build runs fully autonomously; these exist so a human watching can take
// the wheel without stopping it by default."
//
// Every builder below is pure — validates and returns a plain {type, data} object, never
// touches the socket or the DOM — so frontend/tests/controls.test.js can check the exact
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
 * of `steps` (>= 1) or `checkpoint` (a non-empty name) — never both, never neither.
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
 * would be silently dropped" — rejected here, client-side, before it is ever sent.
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
 * Build a `set_cadence` message — "the settings control asked for at Gate A 3.1"
 * (wire.py). Mirrors contracts.wire.CadencePayload / contracts.phases.CheckCadence.
 *
 * @param {string} cadence one of VALID_CADENCES
 */
export function buildSetCadenceMessage(cadence) {
  if (!VALID_CADENCES.includes(cadence)) {
    throw new Error(`invalid cadence "${cadence}" — must be one of ${VALID_CADENCES.join(', ')}`);
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
 *   conversation panel now — an operator types their instruction where they can see it
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
    // operator's words away whenever the socket was down — the one moment they most need
    // to be able to press Send again without retyping.
    if (queued && redirectInput) redirectInput.value = '';
  });

  cadenceSelect?.addEventListener('change', () => {
    guarded(() => buildSetCadenceMessage(cadenceSelect.value));
  });
}
