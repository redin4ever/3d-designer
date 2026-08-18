// Contract: frontend/src/controls.js — client message builders, checked against the
// exact shapes src/contracts/wire.py freezes: RollbackTarget (exactly one of
// steps/checkpoint), RedirectPayload (non-empty text), CadencePayload (one of three
// CheckCadence values). Pure functions — no DOM required.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as controls from '../src/controls.js';
import {
  VALID_CADENCES,
  buildRollbackMessage,
  buildRedirectMessage,
  buildSetCadenceMessage,
} from '../src/controls.js';

test('run controls expose one valid action for the current connection and run state', () => {
  assert.equal(typeof controls.runControlPresentation, 'function');
  assert.deepEqual(controls.runControlPresentation?.({ connected: false, runState: 'running' }), {
    label: 'Unavailable', action: 'pause', disabled: true,
  });
  assert.deepEqual(controls.runControlPresentation?.({ connected: true, runState: 'running' }), {
    label: 'Running', action: 'pause', disabled: false,
  });
  assert.deepEqual(controls.runControlPresentation?.({ connected: true, runState: 'paused' }), {
    label: 'Paused', action: 'resume', disabled: false,
  });
});

test('rollback by steps produces a well-formed client message', () => {
  const msg = buildRollbackMessage({ steps: 3 });
  assert.equal(msg.type, 'rollback');
  assert.deepEqual(msg.data, { steps: 3 });
});

test('rollback by checkpoint produces a well-formed client message', () => {
  const msg = buildRollbackMessage({ checkpoint: 'before-detail-pass' });
  assert.equal(msg.type, 'rollback');
  assert.deepEqual(msg.data, { checkpoint: 'before-detail-pass' });
});

test('rollback rejects both steps and checkpoint together', () => {
  assert.throws(() => buildRollbackMessage({ steps: 1, checkpoint: 'x' }), /exactly one/);
});

test('rollback rejects neither steps nor checkpoint', () => {
  assert.throws(() => buildRollbackMessage({}), /exactly one/);
  assert.throws(() => buildRollbackMessage(), /exactly one/);
});

test('rollback rejects steps < 1', () => {
  assert.throws(() => buildRollbackMessage({ steps: 0 }));
  assert.throws(() => buildRollbackMessage({ steps: -2 }));
});

test('an empty redirect is rejected before sending', () => {
  assert.throws(() => buildRedirectMessage(''), /redirect/);
  assert.throws(() => buildRedirectMessage('   '), /redirect/);
  assert.throws(() => buildRedirectMessage(undefined), /redirect/);
});

test('a non-empty redirect produces a well-formed client message', () => {
  const msg = buildRedirectMessage('add a garage door on the east wall');
  assert.equal(msg.type, 'redirect');
  assert.equal(msg.data.text, 'add a garage door on the east wall');
});

test('set_cadence carries one of the three valid CheckCadence values', () => {
  assert.deepEqual(VALID_CADENCES, ['every_geometry_change', 'phase_boundaries', 'on_request']);
  for (const cadence of VALID_CADENCES) {
    const msg = buildSetCadenceMessage(cadence);
    assert.equal(msg.type, 'set_cadence');
    assert.deepEqual(msg.data, { cadence });
  }
});

test('set_cadence rejects a value outside the three valid ones', () => {
  assert.throws(() => buildSetCadenceMessage('every_frame'));
  assert.throws(() => buildSetCadenceMessage(''));
  assert.throws(() => buildSetCadenceMessage(undefined));
});
