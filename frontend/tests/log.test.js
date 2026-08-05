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
