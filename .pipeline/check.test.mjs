import test from 'node:test';
import assert from 'node:assert/strict';

import { buildChecks, overallExitCode, resolveBrowser } from './check.mjs';

test('the project gate covers every promised verification layer', () => {
  const checks = buildChecks({ python: 'python', browser: 'chrome' });
  assert.deepEqual(
    checks.map((check) => check.id),
    ['backend', 'frontend', 'browser', 'doctor', 'feature-wiring'],
  );
  assert.match(checks.find((check) => check.id === 'backend').args.join(' '), /src.*-q/);
  assert.match(checks.find((check) => check.id === 'browser').args.join(' '), /tests-browser/);
  assert.match(checks.find((check) => check.id === 'feature-wiring').args.join(' '), /\.feature.*check/);
});

test('missing browser is reported as unavailable rather than a passing skip', () => {
  const browser = resolveBrowser({
    env: {},
    platform: 'win32',
    exists: () => false,
    probe: () => false,
  });
  assert.equal(browser, null);

  const results = [{ id: 'browser', status: 'unavailable' }];
  assert.equal(overallExitCode(results), 2);
});

test('product failures take precedence over unavailable prerequisites', () => {
  assert.equal(overallExitCode([
    { id: 'browser', status: 'unavailable' },
    { id: 'backend', status: 'failed' },
  ]), 1);
  assert.equal(overallExitCode([{ id: 'backend', status: 'passed' }]), 0);
});
