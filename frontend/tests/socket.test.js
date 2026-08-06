// Contract: frontend/src/socket.js — the two seq rules from wire.py's ServerMessage
// docstring, both required:
//   - gap (seq > last_applied + 1)   -> request a full resync
//   - duplicate/out-of-order (seq <= last_applied) -> ignore
// classifySeq is pure so this is tested with no WebSocket and no server.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { classifySeq } from '../src/socket.js';

test('a gap (seq > last_applied + 1) requests a full resync', () => {
  assert.equal(classifySeq(5, 7), 'resync');
  assert.equal(classifySeq(0, 2), 'resync');
  assert.equal(classifySeq(100, 250), 'resync');
});

test('a duplicate message (seq === last_applied) is ignored', () => {
  assert.equal(classifySeq(5, 5), 'ignore');
  assert.equal(classifySeq(0, 0), 'ignore');
});

test('an out-of-order message (seq < last_applied) is ignored', () => {
  assert.equal(classifySeq(5, 3), 'ignore');
  assert.equal(classifySeq(5, 0), 'ignore');
});

test('the next sequential message (seq === last_applied + 1) is applied', () => {
  assert.equal(classifySeq(5, 6), 'apply');
  assert.equal(classifySeq(0, 1), 'apply');
});

test('the first message received (no prior seq) is applied unconditionally', () => {
  assert.equal(classifySeq(null, 0), 'apply');
  assert.equal(classifySeq(undefined, 42), 'apply');
});

test('a retried duplicate is ignored rather than reapplied — a client that applies mesh updates additively would otherwise double-apply it', () => {
  const lastApplied = 10;
  // The server retries the same seq=10 message (e.g. a dropped ack). It must not be
  // treated as new work a second time.
  assert.equal(classifySeq(lastApplied, 10), 'ignore');
});
