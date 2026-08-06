// Contract: frontend/src/transcript.js — the conversation panel.
//
// The transcript is the only place an operator can see that the words they typed were
// received, and the only place the agent's replies land. Two failures matter more than
// anything else here and both are silent: a message that never appears (the operator
// re-types it, or worse, assumes the build heard them), and a message that appears twice
// (the operator believes they sent two instructions when they sent one). Every test below
// is one of those two failures, written down.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  createTranscript,
  appendOperatorMessage,
  applyServerLog,
  markPendingUnconfirmed,
  renderTranscript,
  DEFAULT_MAX_MESSAGES,
  TRANSCRIPT_ROLES,
} from '../src/transcript.js';

/** A LOG ServerMessage the way src/viewer/server.py::_encode emits it — every field present. */
function logMessage(seq, text, role) {
  return {
    type: 'log',
    seq,
    meshes: [],
    transforms: [],
    object_ids: [],
    text,
    data: role === undefined ? {} : { role },
  };
}

test('the three roles are exactly the ones the wire carries', () => {
  assert.deepEqual([...TRANSCRIPT_ROLES], ['operator', 'agent', 'system']);
  assert.ok(Number.isInteger(DEFAULT_MAX_MESSAGES) && DEFAULT_MAX_MESSAGES > 0);
});

test('an operator message appears in the transcript the moment it is sent', () => {
  // Optimistic: the agent will not see this until its next tool call, so waiting for a
  // round trip before showing anything makes the panel look dead at exactly the moment
  // the operator is watching it.
  const t = createTranscript();
  const entry = appendOperatorMessage(t, 'move the door to the east wall');

  assert.equal(t.entries.length, 1);
  assert.equal(t.entries[0].role, 'operator');
  assert.equal(t.entries[0].text, 'move the door to the east wall');
  assert.equal(t.entries[0].state, 'pending', 'nothing has confirmed delivery yet');
  assert.strictEqual(entry, t.entries[0], 'the caller gets the entry it just created');
});

test('an empty operator message is refused rather than shown as a blank line', () => {
  const t = createTranscript();
  assert.throws(() => appendOperatorMessage(t, '   '), /empty/i);
  assert.throws(() => appendOperatorMessage(t, undefined), /empty/i);
  assert.equal(t.entries.length, 0);
});

test('an agent line from the wire is appended and attributed to the agent', () => {
  const t = createTranscript();
  applyServerLog(t, logMessage(4, 'measured the gap: 3.2 mm', 'agent'));

  assert.equal(t.entries.length, 1);
  assert.equal(t.entries[0].role, 'agent');
  assert.equal(t.entries[0].text, 'measured the gap: 3.2 mm');
  assert.equal(t.entries[0].state, 'confirmed', 'it came from the server, so it is a fact');
});

test('a LOG with no role is shown as system rather than disappearing', () => {
  // Older backends send LOG with an empty `data`. Dropping those would blank the panel
  // against a server that is working perfectly well.
  const t = createTranscript();
  applyServerLog(t, logMessage(1, 'created wall.north'));

  assert.equal(t.entries.length, 1, 'a role-less LOG must never vanish');
  assert.equal(t.entries[0].role, 'system');
});

test('a LOG with an unrecognised role is shown as system rather than disappearing', () => {
  const t = createTranscript();
  applyServerLog(t, logMessage(1, 'from somewhere new', 'supervisor'));

  assert.equal(t.entries.length, 1, 'an unknown role must never vanish');
  assert.equal(t.entries[0].role, 'system');
});

test("the server's echo of an operator line confirms it instead of printing it twice", () => {
  const t = createTranscript();
  appendOperatorMessage(t, 'move the door to the east wall');
  applyServerLog(t, logMessage(9, 'move the door to the east wall', 'operator'));

  assert.equal(t.entries.length, 1, 'the echo was printed as a second message');
  assert.equal(t.entries[0].state, 'confirmed', 'the echo IS the delivery confirmation');
  assert.equal(t.entries[0].seq, 9, 'the wire seq is what tells one message from another');
});

test('an operator echo with nothing pending to match is still shown', () => {
  // A page opened mid-run, or a second browser watching the same build, sees an operator
  // line it never sent. Showing a line twice is bad; losing someone else's instruction
  // from the record is worse.
  const t = createTranscript();
  applyServerLog(t, logMessage(9, 'typed in another tab', 'operator'));

  assert.equal(t.entries.length, 1);
  assert.equal(t.entries[0].role, 'operator');
  assert.equal(t.entries[0].state, 'confirmed');
});

test('a duplicate or out-of-order echo is ignored, per the wire seq rule', () => {
  const t = createTranscript();
  applyServerLog(t, logMessage(5, 'measured the gap', 'agent'));
  applyServerLog(t, logMessage(5, 'measured the gap', 'agent'));
  applyServerLog(t, logMessage(4, 'an older frame', 'agent'));

  assert.equal(t.entries.length, 1, 'a retried frame double-printed');
});

test('a locally generated status line has no seq and is always kept', () => {
  const t = createTranscript();
  applyServerLog(t, logMessage(5, 'measured the gap', 'agent'));
  applyServerLog(t, { text: 'connected', data: { role: 'system' } });
  applyServerLog(t, { text: 'disconnected — retrying', data: { role: 'system' } });

  assert.deepEqual(t.entries.map((e) => e.text), [
    'measured the gap',
    'connected',
    'disconnected — retrying',
  ]);
});

test('the transcript caps its length rather than growing over a long run', () => {
  const t = createTranscript(3);
  for (const text of ['a', 'b', 'c', 'd', 'e']) {
    applyServerLog(t, { text, data: { role: 'agent' } });
  }

  assert.equal(t.entries.length, 3, 'a long build must not grow the page without limit');
  assert.deepEqual(t.entries.map((e) => e.text), ['c', 'd', 'e'], 'oldest drop first');
});

test('a message the server never confirmed is marked, not silently shown as delivered', () => {
  // The echo can simply never come — the socket drops, or the backend predates the role
  // field. A line that sits looking exactly like a delivered one is the failure that
  // makes an operator wait for something that will never happen.
  const t = createTranscript();
  appendOperatorMessage(t, 'stop before the roof');
  applyServerLog(t, logMessage(2, 'unrelated', 'agent'));
  markPendingUnconfirmed(t);

  assert.equal(t.entries[0].state, 'unconfirmed');
  assert.equal(t.entries[1].state, 'confirmed', 'server messages are untouched');
});

// --- a minimal DOM, so the real renderTranscript is exercised ----------------------
// Same approach as log.test.js: node:test has no DOM and this project adds no jsdom
// dependency. The prior global is restored after each render test because
// log.test.js installs its own fake at module scope and both files run in one process.

class FakeNode {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.className = '';
    this._text = '';
    this.scrollTop = 0;
    this.scrollHeight = 0;
  }
  get childElementCount() { return this.children.length; }
  get firstElementChild() { return this.children[0] ?? null; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  appendChild(node) {
    if (node instanceof FakeFragment) { this.children.push(...node.children); return node; }
    this.children.push(node);
    return node;
  }
  removeChild(node) {
    const i = this.children.indexOf(node);
    if (i >= 0) this.children.splice(i, 1);
    return node;
  }
  querySelector(selector) {
    const wanted = selector.replace('.', '');
    for (const child of this.children) {
      if (child.className === wanted) return child;
      const found = child.querySelector?.(selector);
      if (found) return found;
    }
    return null;
  }
  set textContent(value) { this._text = value; if (value === '') this.children = []; }
  get textContent() { return this._text || this.children.map((c) => c.textContent).join(''); }
}

class FakeFragment extends FakeNode {
  constructor() { super('#fragment'); }
}

function withFakeDom(run) {
  const prior = globalThis.document;
  globalThis.document = {
    createElement: (tag) => new FakeNode(tag),
    createDocumentFragment: () => new FakeFragment(),
  };
  try {
    return run();
  } finally {
    globalThis.document = prior;
  }
}

const rowText = (row) => row.querySelector('.transcript-text').textContent;

test('the transcript appends rather than rebuilding, so a live region announces only what is new', () =>
  withFakeDom(() => {
    const container = new FakeNode('ol');
    const t = createTranscript();

    applyServerLog(t, { text: 'first', data: { role: 'agent' } });
    renderTranscript(t, container);
    const firstRow = container.children[0];

    applyServerLog(t, { text: 'second', data: { role: 'agent' } });
    renderTranscript(t, container);

    assert.equal(container.children.length, 2);
    assert.strictEqual(container.children[0], firstRow, 'the existing row was re-created');
    assert.equal(rowText(container.children[1]), 'second');
  }));

test('rows dropped by the message cap are dropped from the DOM too', () =>
  withFakeDom(() => {
    const container = new FakeNode('ol');
    const t = createTranscript(2);

    applyServerLog(t, { text: 'a', data: { role: 'agent' } });
    applyServerLog(t, { text: 'b', data: { role: 'agent' } });
    renderTranscript(t, container);
    applyServerLog(t, { text: 'c', data: { role: 'agent' } });
    renderTranscript(t, container);

    assert.equal(container.children.length, 2, 'the DOM grew past the transcript cap');
    assert.equal(rowText(container.children[1]), 'c');
  }));

test('every row carries its role, so operator and agent are distinguishable at a glance', () =>
  withFakeDom(() => {
    const container = new FakeNode('ol');
    const t = createTranscript();

    appendOperatorMessage(t, 'mine');
    applyServerLog(t, { text: 'theirs', data: { role: 'agent' } });
    renderTranscript(t, container);

    assert.deepEqual(container.children.map((r) => r.dataset.role), ['operator', 'agent']);
    assert.equal(container.children[0].dataset.state, 'pending');
  }));

test('confirming a pending line updates the row in place and never changes its text', () =>
  withFakeDom(() => {
    // Rebuilding the row would make a screen reader re-announce a line the user already
    // heard, purely because a delivery badge changed.
    const container = new FakeNode('ol');
    const t = createTranscript();

    appendOperatorMessage(t, 'move the door');
    renderTranscript(t, container);
    const row = container.children[0];
    const textBefore = rowText(row);

    applyServerLog(t, { seq: 3, text: 'move the door', data: { role: 'operator' } });
    renderTranscript(t, container);

    assert.equal(container.children.length, 1, 'the confirmed line was printed twice');
    assert.strictEqual(container.children[0], row, 'the row was rebuilt instead of updated');
    assert.equal(rowText(row), textBefore, 'the announced text must not change');
    assert.equal(row.dataset.state, 'confirmed');
  }));

test('the delivery marker is aria-hidden, so confirming does not re-announce the line', () =>
  withFakeDom(() => {
    const container = new FakeNode('ol');
    const t = createTranscript();

    appendOperatorMessage(t, 'move the door');
    renderTranscript(t, container);
    const marker = container.children[0].querySelector('.transcript-state');

    assert.equal(marker.getAttribute('aria-hidden'), 'true');
    assert.notEqual(marker.textContent, '', 'a pending line must say so');

    applyServerLog(t, { seq: 3, text: 'move the door', data: { role: 'operator' } });
    renderTranscript(t, container);
    assert.notEqual(marker.textContent, '', 'a confirmed line must say what "sent" got it to');
  }));

test('an unconfirmed line renders as unconfirmed rather than looking delivered', () =>
  withFakeDom(() => {
    const container = new FakeNode('ol');
    const t = createTranscript();

    appendOperatorMessage(t, 'stop before the roof');
    renderTranscript(t, container);
    markPendingUnconfirmed(t);
    renderTranscript(t, container);

    assert.equal(container.children[0].dataset.state, 'unconfirmed');
  }));

test('the newest message is scrolled into view without the operator hunting for it', () =>
  withFakeDom(() => {
    const container = new FakeNode('ol');
    container.scrollHeight = 900;
    const t = createTranscript();

    applyServerLog(t, { text: 'newest', data: { role: 'agent' } });
    renderTranscript(t, container);

    assert.equal(container.scrollTop, 900);
  }));
