import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  createPointState,
  setSelection,
  toggleFocus,
  applyServerFocus,
  clearSelection,
  buildAnnotateMessage,
  buildFocusMessage,
  describeSelection,
} from '../src/annotate.js';

// The browser's half of pointing. Pure state and message shapes, no DOM and no socket, so
// the decisions can be checked without a browser — the same reason camera.js was split out
// of scene-renderer.js after a camera that could only turn left and right shipped.

test('selecting parts replaces the selection rather than accumulating', () => {
  // Q-04: a click picks one part. If clicks accumulated, the second click would annotate two
  // objects and the operator would have no idea which they were talking about.
  const state = createPointState();

  setSelection(state, ['railing']);
  setSelection(state, ['tread']);

  assert.deepEqual([...state.selection], ['tread']);
});

test('circling several parts selects all of them', () => {
  const state = createPointState();

  setSelection(state, ['railing', 'post', 'tread']);

  assert.equal(state.selection.size, 3);
});

test('selection and focus are different sets', () => {
  // Q-13's constraint, in the state model. Selection is what you are pointing at right now;
  // focus is what you have marked as mattering. Conflating them would clear the operator's
  // standing marks every time they clicked somewhere else.
  const state = createPointState();
  toggleFocus(state, 'railing');

  setSelection(state, ['tread']);

  assert.deepEqual([...state.focus], ['railing']);
  assert.deepEqual([...state.selection], ['tread']);
});

test('marking a part twice unmarks it', () => {
  // The only way to take a mark down from the view itself (Q-11). Without it the operator
  // has to find a list somewhere else to undo a click they just made.
  const state = createPointState();

  toggleFocus(state, 'railing');
  toggleFocus(state, 'railing');

  assert.equal(state.focus.size, 0);
});

test('the server is the authority on what is focused', () => {
  // Focus lives on the orchestrator and is echoed to every watcher. A browser that kept its
  // own idea would drift from what the agent is actually being told, and the screen showing
  // the truth would be the wrong one.
  const state = createPointState();
  toggleFocus(state, 'guessed_locally');

  applyServerFocus(state, ['railing', 'post']);

  assert.deepEqual([...state.focus].sort(), ['post', 'railing']);
});

test('a focus message carries the whole set, not the one that changed', () => {
  // contracts.FocusPayload is declarative. Sending only the delta would need a separate
  // clear message, and the two drift apart the first time one is dropped.
  const state = createPointState();
  toggleFocus(state, 'a');
  toggleFocus(state, 'b');

  const message = buildFocusMessage(state);

  assert.equal(message.type, 'set_focus');
  assert.deepEqual(message.data.object_ids.sort(), ['a', 'b']);
});

test('clearing every mark still sends a message', () => {
  // The empty set IS the clear (Q-11). Skipping the send because there is nothing in it
  // would leave the agent being told those parts matter forever.
  const state = createPointState();

  assert.deepEqual(buildFocusMessage(state).data.object_ids, []);
});

test('an annotation carries what is selected and what was typed', () => {
  const state = createPointState();
  setSelection(state, ['railing']);

  const message = buildAnnotateMessage(state, { text: 'too shallow' });

  assert.equal(message.type, 'annotate');
  assert.deepEqual(message.data.object_ids, ['railing']);
  assert.equal(message.data.text, 'too shallow');
});

test('pointing with nothing typed is a valid annotation', () => {
  // Q-04's click is a complete gesture — "look at this" without words.
  const state = createPointState();
  setSelection(state, ['railing']);

  assert.doesNotThrow(() => buildAnnotateMessage(state, {}));
});

test('an annotation with no part, no words and no image is refused here', () => {
  // Mirrors contracts.AnnotatePayload's own guard, client-side, before it is ever sent —
  // exactly as buildRedirectMessage rejects an empty redirect rather than letting the
  // backend silently drop it.
  const state = createPointState();

  assert.throws(() => buildAnnotateMessage(state, {}), /nothing/);
  assert.throws(() => buildAnnotateMessage(state, { text: '   ' }), /nothing/);
});

test('an oversized image is refused before it can close the socket', () => {
  // A-011. The transport does not error on an over-length frame, it closes the connection,
  // so the operator would watch the live view drop with nothing saying why at the exact
  // moment they tried to say something. Refusing here produces a message instead.
  const state = createPointState();
  setSelection(state, ['railing']);
  const huge = `data:image/png;base64,${'A'.repeat(4_000_001)}`;

  assert.throws(() => buildAnnotateMessage(state, { image: huge }), /too large/i);
});

test('clearing the selection leaves focus alone', () => {
  // Pressing Escape puts the composer away. It must not also take down marks the operator
  // set deliberately and expects to persist until they clear them (Q-11).
  const state = createPointState();
  toggleFocus(state, 'railing');
  setSelection(state, ['tread']);

  clearSelection(state);

  assert.equal(state.selection.size, 0);
  assert.deepEqual([...state.focus], ['railing']);
});

test('the selection describes itself for a person, not as a list of ids', () => {
  // This string goes above the composer so the operator can see what is attached before
  // they send. A raw array of forty ids is not something anyone reads.
  const state = createPointState();

  setSelection(state, ['railing']);
  assert.equal(describeSelection(state), 'railing');

  setSelection(state, ['a', 'b', 'c', 'd', 'e']);
  assert.match(describeSelection(state), /5 parts/);

  clearSelection(state);
  assert.equal(describeSelection(state), 'nothing selected');
});
