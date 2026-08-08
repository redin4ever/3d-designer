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
  DEFAULT_SNAP_M,
  buildDeleteMessage,
  buildDuplicateMessage,
  buildMoveMessage,
  dragToTranslation,
  editingAllowed,
} from './edit-tools.js';
import {
  beginMove,
  cancelMove,
  createMoveSession,
  finishMove,
  reconcileMove,
  updateMove,
} from './move-gizmo.js';
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
  const moveButton = root.querySelector('[data-action="move-tool"]');
  const moveStatus = root.querySelector('#move-status');
  const axisButtons = [...root.querySelectorAll('[data-action="move-axis"]')];
  const frameButton = root.querySelector('[data-action="frame-selection"]');
  const resetButton = root.querySelector('[data-action="reset-view"]');
  const snapButton = root.querySelector('[data-action="snap-toggle"]');

  let pointMode = false;
  let attachView = false;
  let run = { runState: 'running', connected: false };
  let drag = null;
  let moveMode = false;
  let moveSession = createMoveSession();
  let keyboardMove = null;
  let snap = DEFAULT_SNAP_M;

  const only = () => [...state.selection][0] ?? '';

  const setMoveStatus = (message) => {
    if (moveStatus) moveStatus.textContent = message;
  };

  const syncPositionFields = (position) => {
    if (!position) return;
    ['x', 'y', 'z'].forEach((axis, index) => {
      const input = root.querySelector(`[data-field="edit-${axis}"]`);
      if (input) input.value = String(position[index]);
    });
  };

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
    io.renderer.setSelected(state.selection);
    selectionLabel.textContent = describeSelection(state);
    composer.hidden = state.selection.size === 0;
    if (!composer.hidden) textInput.focus();
    syncPositionFields(io.renderer.objectPosition?.(only()));
    renderEditability();
  };

  // Q-20: the reason, not just the fact. A disabled control with nothing said about it is
  // indistinguishable from a broken one, and the Pause that unblocks it is right here.
  const renderEditability = () => {
    const reason = editingAllowed(run, { explain: true });
    const hasOne = state.selection.size === 1;
    const allowed = hasOne && !reason;
    editGroup.dataset.blocked = reason ? 'true' : 'false';
    editBlocked.textContent = state.selection.size === 0 ? '' : reason;
    pauseToEdit.hidden = !(reason && run.connected && state.selection.size > 0);
    if (moveButton) moveButton.disabled = !allowed;
    for (const button of axisButtons) button.disabled = !allowed;
    if (frameButton) frameButton.disabled = !hasOne;
    io.renderer.setMoveEnabled?.(allowed);
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

  const activateMoveMode = () => {
    if (!only() || !editingAllowed(run)) return false;
    pointMode = false;
    moveMode = true;
    modeButton?.setAttribute('aria-pressed', 'false');
    moveButton?.setAttribute('aria-pressed', 'true');
    panel.dataset.pointMode = 'off';
    panel.dataset.tool = 'move';
    io.renderer.setToolMode?.('move');
    setMoveStatus('Move active. Drag an X, Y or Z arrow, or press an axis key.');
    return true;
  };

  const leaveMoveMode = (nextMode = 'orbit') => {
    moveMode = false;
    moveButton?.setAttribute('aria-pressed', 'false');
    panel.dataset.tool = nextMode;
    io.renderer.setToolMode?.(nextMode);
    io.renderer.setActiveMoveAxis?.(null);
  };

  const cancelPointerMove = (message = 'Move cancelled.') => {
    const cancelled = cancelMove(moveSession);
    if (cancelled.restore && moveSession.objectId) {
      io.renderer.previewTranslation?.(moveSession.objectId, cancelled.restore);
      syncPositionFields(cancelled.restore);
    }
    moveSession = cancelled.session;
    io.renderer.setActiveMoveAxis?.(null);
    setMoveStatus(message);
  };

  const cancelKeyboardMove = (message = 'Move cancelled.') => {
    if (!keyboardMove) return;
    io.renderer.previewTranslation?.(keyboardMove.objectId, keyboardMove.startPosition);
    syncPositionFields(keyboardMove.startPosition);
    keyboardMove = null;
    io.renderer.setActiveMoveAxis?.(null);
    setMoveStatus(message);
  };

  // ---- move gizmo -----------------------------------------------------------------
  // Capture before point/lasso and before the renderer's bubble-phase orbit listener. A
  // click on empty canvas is deliberately ignored here so orbit remains unchanged.
  canvas?.addEventListener('pointerdown', (event) => {
    if (!moveMode || !editingAllowed(run) || moveSession.phase !== 'idle') return;
    const frame = io.renderer.frame;
    if (!frame) return;
    const point = cssToFrame(frame, canvas.getBoundingClientRect(), event.clientX, event.clientY);
    const dpr = window.devicePixelRatio || 1;
    const axis = io.renderer.hitMoveAxis?.(point, 14 * dpr);
    const startPosition = io.renderer.objectPosition?.(only());
    const projectedAxis = io.renderer.moveGizmo?.axes?.[axis];
    if (!axis || !startPosition || !projectedAxis) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    canvas.setPointerCapture(event.pointerId);
    moveSession = beginMove(moveSession, {
      objectId: only(),
      pointerId: event.pointerId,
      axis,
      startPointer: point,
      startPosition,
      projectedAxis,
    });
    io.renderer.setActiveMoveAxis?.(axis);
    setMoveStatus(`Moving on ${axis.toUpperCase()}. Release to commit; Escape cancels.`);
  }, true);

  canvas?.addEventListener('pointermove', (event) => {
    if (!['armed', 'dragging'].includes(moveSession.phase)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const point = cssToFrame(io.renderer.frame, canvas.getBoundingClientRect(), event.clientX, event.clientY);
    moveSession = updateMove(moveSession, {
      pointerId: event.pointerId,
      point,
      snap,
      threshold: 3 * (window.devicePixelRatio || 1),
    });
    if (moveSession.phase === 'dragging') {
      io.renderer.previewTranslation?.(moveSession.objectId, moveSession.previewPosition);
      syncPositionFields(moveSession.previewPosition);
      setMoveStatus(`${moveSession.axis.toUpperCase()}: ${moveSession.previewPosition.join(', ')} m`);
    }
  }, true);

  const finishPointerMove = (event) => {
    if (!['armed', 'dragging'].includes(moveSession.phase)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const objectId = moveSession.objectId;
    const result = finishMove(moveSession, event.pointerId);
    moveSession = result.session;
    io.renderer.setActiveMoveAxis?.(null);
    if (result.restore) io.renderer.previewTranslation?.(objectId, result.restore);
    if (!result.translation) {
      setMoveStatus('Move unchanged.');
      return;
    }
    if (io.send(buildMoveMessage(objectId, result.translation, { snap })) === false) {
      cancelPointerMove('Move reverted because the build is not connected.');
      return;
    }
    setMoveStatus('Saving move… awaiting the build.');
  };
  canvas?.addEventListener('pointerup', finishPointerMove, true);
  canvas?.addEventListener('pointercancel', () => cancelPointerMove(), true);

  moveButton?.addEventListener('click', () => activateMoveMode());

  for (const button of axisButtons) {
    button.addEventListener('click', () => {
      if (!activateMoveMode()) return;
      const objectId = only();
      const startPosition = io.renderer.objectPosition?.(objectId);
      if (!startPosition) return;
      keyboardMove = { objectId, axis: button.dataset.axis, startPosition, previewPosition: [...startPosition] };
      io.renderer.setActiveMoveAxis?.(keyboardMove.axis);
      setMoveStatus(`${keyboardMove.axis.toUpperCase()} constrained. Use arrow keys, Enter, or Escape.`);
      canvas.focus();
    });
  }

  frameButton?.addEventListener('click', () => {
    if (io.renderer.frameSelection?.(only())) setMoveStatus(`Framed ${only()}.`);
  });

  resetButton?.addEventListener('click', () => {
    io.renderer.resetView?.();
    setMoveStatus('View reset.');
  });

  snapButton?.addEventListener('click', () => {
    snap = snap > 0 ? 0 : DEFAULT_SNAP_M;
    snapButton.setAttribute('aria-pressed', String(snap > 0));
    snapButton.textContent = snap > 0 ? `Snap ${DEFAULT_SNAP_M} m` : 'Snap off';
    setMoveStatus(snap > 0 ? `Translation snap ${DEFAULT_SNAP_M} m.` : 'Translation snap off.');
  });

  // ---- point mode -----------------------------------------------------------------
  // Q-05 chose a mode you switch into, so nothing an operator already does changes
  // behaviour and a camera angle can never be lost by trying to circle something.
  modeButton?.addEventListener('click', () => {
    pointMode = !pointMode;
    if (pointMode) leaveMoveMode('point');
    modeButton.setAttribute('aria-pressed', String(pointMode));
    panel.dataset.pointMode = pointMode ? 'on' : 'off';
    if (!pointMode) {
      io.renderer.setToolMode?.('orbit');
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
    // scene, which picking.js refuses anyway — this is what makes the click a click.
    pickFrom(moved < DRAG_THRESHOLD ? [drag.path[0]] : drag.path);
    drag = null;
  };
  canvas?.addEventListener('pointerup', endDrag, true);
  canvas?.addEventListener('pointercancel', endDrag, true);
  canvas?.addEventListener('pointerleave', clearHover, true);

  // Blender-like keyboard flow: G enters Move, X/Y/Z constrains it, arrows nudge by the
  // active snap, Enter commits once, and Escape restores the authoritative position.
  canvas?.addEventListener('keydown', (event) => {
    const key = event.key.toLowerCase();
    if (key === 'g') {
      if (!activateMoveMode()) return;
      const objectId = only();
      const startPosition = io.renderer.objectPosition?.(objectId);
      if (!startPosition) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      keyboardMove = { objectId, axis: null, startPosition, previewPosition: [...startPosition] };
      setMoveStatus('Move ready. Press X, Y or Z to constrain.');
      return;
    }
    if (!keyboardMove) return;
    if (['x', 'y', 'z'].includes(key)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      keyboardMove.axis = key;
      io.renderer.setActiveMoveAxis?.(key);
      setMoveStatus(`${key.toUpperCase()} constrained. Use arrow keys, Enter, or Escape.`);
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopImmediatePropagation();
      cancelKeyboardMove();
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!keyboardMove.axis
          || keyboardMove.previewPosition.every((value, index) => value === keyboardMove.startPosition[index])) {
        cancelKeyboardMove('Move unchanged.');
        return;
      }
      const pending = keyboardMove;
      keyboardMove = null;
      io.renderer.setActiveMoveAxis?.(null);
      if (io.send(buildMoveMessage(pending.objectId, pending.previewPosition, { snap })) === false) {
        io.renderer.previewTranslation?.(pending.objectId, pending.startPosition);
        syncPositionFields(pending.startPosition);
        setMoveStatus('Move reverted because the build is not connected.');
      } else {
        keyboardMove = { ...pending, pending: true };
        setMoveStatus('Saving move… awaiting the build.');
      }
      return;
    }
    if (!keyboardMove.axis || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const sign = ['ArrowRight', 'ArrowUp'].includes(event.key) ? 1 : -1;
    keyboardMove.previewPosition = dragToTranslation(
      keyboardMove.previewPosition,
      keyboardMove.axis,
      sign * DEFAULT_SNAP_M,
      snap,
    );
    io.renderer.previewTranslation?.(keyboardMove.objectId, keyboardMove.previewPosition);
    syncPositionFields(keyboardMove.previewPosition);
    setMoveStatus(`${keyboardMove.axis.toUpperCase()}: ${keyboardMove.previewPosition.join(', ')} m`);
  }, true);

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
    sendEdit((objectId) => buildMoveMessage(objectId, to, { snap }));
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
    /** The server transform replaces any optimistic preview and closes its pending state. */
    reconcileTransforms(transforms) {
      for (const transform of transforms ?? []) {
        const matchedPointer = moveSession.objectId === transform.object_id;
        const next = reconcileMove(moveSession, transform.object_id);
        if (next !== moveSession) moveSession = next;
        const matchedKeyboard = keyboardMove?.pending && keyboardMove.objectId === transform.object_id;
        if (matchedKeyboard) keyboardMove = null;
        if (matchedPointer || matchedKeyboard) {
          syncPositionFields(transform.position);
          io.renderer.setActiveMoveAxis?.(null);
          setMoveStatus('Move saved.');
        }
      }
    },
    /** A rejected edit restores the position captured before the local preview. */
    rejectMove(message = 'Move rejected by the build.') {
      if (moveSession.phase !== 'idle') cancelPointerMove(message);
      if (keyboardMove) cancelKeyboardMove(message);
    },
    /**
     * Q-22: a disconnect reverts and says so. The selection is dropped because the ids it
     * names may not survive the resync, and a stale selection would silently annotate the
     * wrong part once the scene came back.
     */
    setRun(next) {
      run = { ...run, ...next };
      if (!editingAllowed(run)) {
        if (moveSession.phase !== 'idle') cancelPointerMove('Move cancelled because editing is unavailable.');
        if (keyboardMove) cancelKeyboardMove('Move cancelled because editing is unavailable.');
      }
      if (!run.connected) {
        clearSelection(state);
        leaveMoveMode('orbit');
        renderSelection();
      }
      renderEditability();
    },
  };
}
