import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { attachConnectButton } from '../src/connect-ui.js';

test('main refreshes agent readiness when the app becomes visible again', () => {
  const source = readFileSync(new URL('../src/main.js', import.meta.url), 'utf8');

  assert.match(source, /const connectController = attachConnectButton\(document\)/);
  assert.match(source, /visibilitychange/);
  assert.match(source, /connectController\.refreshStatus\(\)/);
});

class FakeButton {
  constructor() {
    this.dataset = {};
    this.attributes = new Map();
    this.listeners = new Map();
    this.textContent = 'Connect';
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  addEventListener(name, callback) {
    this.listeners.set(name, callback);
  }
}

function connectionRoot(button) {
  const dialog = {
    open: false,
    addEventListener() {},
    showModal() { this.open = true; },
    close() { this.open = false; },
  };
  const body = { dataset: {}, replaceChildren() {} };
  return {
    querySelector(selector) {
      if (selector === '#connect-button') return button;
      if (selector === '#connect-dialog') return dialog;
      if (selector === '#connect-dialog-body') return body;
      return null;
    },
  };
}

test('attaching connection UI detects configured clients without waiting for a click', async () => {
  const button = new FakeButton();
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: true,
      status: 200,
      async json() {
        return {
          clients: [{
            id: 'codex',
            label: 'Codex',
            transport: 'stdio',
            config_path: 'C:\\Users\\someone\\.codex\\config.toml',
            configured: true,
            status: 'ready',
            note: 'Restart Codex after configuration changes.',
          }],
        };
      },
    };
  };

  attachConnectButton(connectionRoot(button), { fetchImpl });
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(calls.map((call) => call.url), ['/api/clients']);
  assert.equal(button.dataset.connectionState, 'ready');
  assert.equal(button.textContent, 'Codex ready');
  assert.match(button.attributes.get('aria-label'), /Codex.*ready/i);
  assert.equal(
    calls.some((call) => call.url === '/api/connect'),
    false,
    'automatic detection must not silently rewrite an external client config',
  );
});

test('startup reports action required without writing an unconfigured client', async () => {
  const button = new FakeButton();
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(url);
    return {
      ok: true,
      status: 200,
      async json() {
        return {
          clients: [{
            id: 'cursor',
            label: 'Cursor',
            transport: 'stdio',
            config_path: 'C:\\Users\\someone\\.cursor\\mcp.json',
            configured: false,
            status: 'needs_configuration',
            note: 'Settings -> MCP shows it once saved.',
          }],
        };
      },
    };
  };

  attachConnectButton(connectionRoot(button), { fetchImpl });
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(calls, ['/api/clients']);
  assert.equal(button.dataset.connectionState, 'action-required');
  assert.equal(button.textContent, 'Set up Cursor');
});
