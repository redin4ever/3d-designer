// Contract: frontend/src/log.js — the action log. Appends in order; caps length rather
// than growing without bound over a long autonomous run (a build can run for thousands
// of operations, Gate A 11.4).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createActionLog, appendLogEntry, DEFAULT_MAX_ENTRIES } from '../src/log.js';

test('the action log appends entries in order', () => {
  const log = createActionLog();
  appendLogEntry(log, { text: 'first' });
  appendLogEntry(log, { text: 'second' });
  appendLogEntry(log, { text: 'third' });
  assert.deepEqual(log.entries.map((e) => e.text), ['first', 'second', 'third']);
});

test('the action log caps its length rather than growing without bound', () => {
  const log = createActionLog(3);
  for (const text of ['a', 'b', 'c', 'd', 'e']) {
    appendLogEntry(log, { text });
  }
  assert.equal(log.entries.length, 3, 'must not exceed maxEntries over a long run');
  assert.deepEqual(log.entries.map((e) => e.text), ['c', 'd', 'e'], 'oldest entries drop first; newest survive');
});

test('appendLogEntry returns the log so callers can chain', () => {
  const log = createActionLog(5);
  const returned = appendLogEntry(log, { text: 'x' });
  assert.strictEqual(returned, log);
});

test('DEFAULT_MAX_ENTRIES is a sane positive bound', () => {
  assert.ok(Number.isInteger(DEFAULT_MAX_ENTRIES) && DEFAULT_MAX_ENTRIES > 0);
});

// --- a minimal DOM, so the real renderActionLog can be exercised ------------------
// node:test has no DOM and this project has no jsdom dependency. Shimming the four calls
// renderActionLog actually makes is smaller than adding a dependency and keeps the test
// exercising the shipped function rather than a re-implementation of it.

class FakeNode {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.className = '';
    this._text = '';
    this.scrollTop = 0;
    this.scrollHeight = 0;
  }
  get childElementCount() { return this.children.length; }
  get firstElementChild() { return this.children[0] ?? null; }
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
  set textContent(value) { this._text = value; if (value === '') this.children = []; }
  get textContent() { return this._text || this.children.map((c) => c.textContent).join(''); }
}

class FakeFragment extends FakeNode {
  constructor() { super('#fragment'); }
}

globalThis.document = {
  createElement: (tag) => new FakeNode(tag),
  createDocumentFragment: () => new FakeFragment(),
};

const { renderActionLog } = await import('../src/log.js');

test('the log appends rather than rebuilding, so a live region announces only what is new', () => {
  // The container is aria-live. Clearing and re-creating every row on each message made a
  // screen reader announce the whole reconstructed history on every geometry update —
  // unusable on a run that emits hundreds of them. Node identity is the observable proof
  // that existing rows were left alone.
  const container = new FakeNode('ul');
  const log = createActionLog();

  appendLogEntry(log, { text: 'first' });
  renderActionLog(log, container);
  const firstNode = container.children[0];

  appendLogEntry(log, { text: 'second' });
  renderActionLog(log, container);

  assert.strictEqual(container.children.length, 2);
  assert.strictEqual(container.children[0], firstNode, 'the existing row was re-created');
  assert.strictEqual(container.children[1].textContent, 'second');
});

test('rows dropped by the entry cap are dropped from the DOM too', () => {
  const container = new FakeNode('ul');
  const log = createActionLog(2);

  appendLogEntry(log, { text: 'a' });
  appendLogEntry(log, { text: 'b' });
  renderActionLog(log, container);
  appendLogEntry(log, { text: 'c' });
  renderActionLog(log, container);

  assert.strictEqual(container.children.length, 2, 'the DOM grew past the log cap');
  assert.strictEqual(container.children[1].textContent, 'c');
});
