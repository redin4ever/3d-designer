// DOM wiring for pointing, priority and the edit tools.
//
// Impure by design and not unit-tested, for the same reason `attachControls` and
// `SocketClient` are not: every decision worth checking has already been lifted out into
// picking.js, annotate.js, capture.js and edit-tools.js, which are pure and covered. What is
// left here is listeners and element lookups, where a test would be testing a fake DOM.
//
// Kept out of main.js so that file stays a composition root — the same split connect-ui.js
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
 * @param {HTMLElement} root the whole layout — the composer lives over the canvas and the
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
        remove.textContent = '×';
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

  // ---- point mode -----------------------------------------------------------------
  // Q-05 chose a mode you switch into, so nothing an operator already does changes
  // behaviour and a camera angle can never be lost by trying to circle something.
  modeButton?.addEventListener('click', () => {
    pointMode = !pointMode;
    modeButton.setAttribute('aria-pressed', String(pointMode));
    panel.dataset.pointMode = pointMode ? 'on' : 'off';
    if (!pointMode) {
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
      drag = { path: [cssToFrame(io.renderer.frame ?? { width: 0, height: 0 }, canvas.getBoundingClientRect(), event.clientX, event.clientY)], startX: event.clientX, startY: event.clientY };
    },
    true,
  );

  canvas?.addEventListener(
    'pointermove',
    (event) => {
      if (!pointMode || !drag) return;
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
    // scene, which picking.js refuses anyway — this is what makes the click a click.
    pickFrom(moved < DRAG_THRESHOLD ? [drag.path[0]] : drag.path);
    drag = null;
  };
  canvas?.addEventListener('pointerup', endDrag, true);
  canvas?.addEventListener('pointercancel', endDrag, true);

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
  // affordance of its own — Ctrl+V into the composer is where anyone would try it first.
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
    /** The server is the authority on focus — see annotate.js's applyServerFocus. */
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
