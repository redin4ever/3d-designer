// The Connect button's decisions, tested with no DOM and no server.
//
// Same seam as socket.js's `classifySeq` and transcript.js's `applyServerLog`: everything
// that *decides* — how many clients were found, which one to write, what to say afterwards
// — is pure, and only the DOM wiring in connect-ui.js is left untested. The thing being
// pinned down here is a setup flow a user runs once and cannot easily debug: if it picks
// the wrong branch, they are left with an AI client that shows no tools and no idea why.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  planConnect,
  choiceLabel,
  describeSuccess,
  describeFailure,
  loadClients,
  connectClient,
} from '../src/connect.js';

/** A client row exactly as src/app/connect.py::detect_clients builds it. */
function client(overrides = {}) {
  return {
    id: 'claude-code',
    label: 'Claude Code',
    transport: 'stdio',
    config_path: 'C:\\Users\\someone\\.claude.json',
    configured: false,
    note: 'Or run:  claude mcp add forge3d -- python -X utf8 -m mcp_server',
    ...overrides,
  };
}

/** A `fetch` that answers once with `status` and `payload`, recording what it was asked. */
function fakeFetch(status, payload) {
  const calls = [];
  const impl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => {
        if (payload === undefined) throw new SyntaxError('Unexpected end of JSON input');
        return payload;
      },
    };
  };
  impl.calls = calls;
  return impl;
}

test('no clients found is a normal answer with a way forward, not a failure', () => {
  const plan = planConnect([]);

  assert.equal(plan.action, 'none', 'an empty list must not be routed to a picker or a POST');
  assert.equal(plan.outcome.tone, 'empty', 'an empty machine is not an error state');
  const said = [plan.outcome.title, ...plan.outcome.lines].join(' ');
  assert.match(
    said,
    /forge3d connect/,
    'the fallback the user can actually run must be named — otherwise this is a dead end',
  );
});

test('a garbled or missing client list is treated as none, never as a crash', () => {
  for (const value of [null, undefined, 'clients', { clients: [] }, [{}], [null]]) {
    const plan = planConnect(value);
    assert.equal(plan.action, 'none', `planConnect(${JSON.stringify(value)}) must degrade to "none"`);
  }
});

test('exactly one client is connected outright — nobody picks from a list of one', () => {
  const only = client();
  const plan = planConnect([only]);

  assert.equal(plan.action, 'connect');
  assert.deepEqual(plan.client, only, 'the one client found is the one that gets written');
});

test('more than one client is offered as a choice, in the order the backend found them', () => {
  const many = [
    client({ id: 'claude-desktop', label: 'Claude Desktop' }),
    client({ id: 'claude-code', label: 'Claude Code' }),
    client({ id: 'cursor', label: 'Cursor' }),
  ];
  const plan = planConnect(many);

  assert.equal(plan.action, 'choose');
  assert.deepEqual(
    plan.clients.map((c) => c.id),
    ['claude-desktop', 'claude-code', 'cursor'],
  );
});

test('an already-configured client is offered as a re-write, not as something new', () => {
  const fresh = choiceLabel(client({ configured: false }));
  const already = choiceLabel(client({ configured: true }));

  assert.equal(fresh, 'Claude Code', 'an unconfigured client is just its name');
  assert.notEqual(already, fresh, 'a client that already has forge3d must say so before it is picked');
  assert.match(already, /Claude Code/, 'the label still has to name the client');
  assert.match(
    already,
    /already/i,
    'pretending a re-write is a first-time connect hides the one fact that decides the click',
  );
});

test('success says which file was written, that a restart is required, and that nothing happened here', () => {
  const target = client();
  const outcome = describeSuccess(
    { ok: true, client: 'claude-code', path: 'C:\\Users\\someone\\.claude.json', note: target.note },
    target,
  );

  assert.equal(outcome.tone, 'ok');
  assert.equal(outcome.path, 'C:\\Users\\someone\\.claude.json', 'the file that changed must be named exactly');
  const said = [outcome.title, ...outcome.lines].join(' ');
  assert.match(
    said,
    /restart/i,
    'a user who does not restart sees no tools and concludes the product is broken — this is the whole message',
  );
  assert.match(said, /Claude Code/, 'the restart instruction has to name the client to restart');
  assert.ok(
    outcome.lines.includes(target.note),
    "the client's own note is written to be read by a person and must be surfaced verbatim",
  );
  assert.match(
    said,
    /next time|nothing (changed|happens) in this page/i,
    'connecting changes a file, not this page — saying otherwise sends the user looking for something that will not appear',
  );
});

test('the restart line is marked as the one that must not be skimmed past', () => {
  const target = client();
  const outcome = describeSuccess({ ok: true, path: target.config_path, note: target.note }, target);

  assert.match(outcome.critical, /Restart Claude Code/, 'the critical line is the restart instruction');
  assert.ok(
    outcome.lines.includes(outcome.critical),
    'the critical line must also be in `lines` — a renderer that ignores `critical` must still show it',
  );
  assert.notEqual(
    outcome.critical,
    target.note,
    "the client's own note is not the critical line; the restart is, and only one can be",
  );
});

test('re-writing an already-configured client says re-wrote, not wrote', () => {
  const target = client({ configured: true });
  const outcome = describeSuccess({ ok: true, path: target.config_path, note: target.note }, target);
  assert.match(outcome.title, /re-?wrote/i, 'claiming a first connect where there was already one is a lie');
});

test('a failed connect shows the server error verbatim', async () => {
  const message =
    'C:\\Users\\someone\\.claude.json exists but could not be read as JSON. Left untouched — fix or move it, then run this again.';
  const impl = fakeFetch(500, { error: message });

  const result = await connectClient(impl, 'claude-code');

  assert.equal(result.ok, false);
  assert.equal(result.error, message, 'the backend writes these to be read by a person; paraphrasing loses the fix');
  assert.equal(impl.calls.length, 1);
  assert.equal(impl.calls[0].url, '/api/connect');
  assert.equal(impl.calls[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(impl.calls[0].init.body), { client: 'claude-code' });

  const outcome = describeFailure(result.error);
  assert.equal(outcome.tone, 'error');
  assert.ok(outcome.lines.includes(message), 'the error must reach the screen unedited');
});

test('a 400 for an unknown client is surfaced the same way as a 500', async () => {
  const result = await connectClient(fakeFetch(400, { error: "unknown client 'nope'" }), 'nope');
  assert.equal(result.ok, false);
  assert.equal(result.error, "unknown client 'nope'");
});

test('an unreachable backend is reported as unreachable, not as an empty machine', async () => {
  const dead = async () => {
    throw new TypeError('Failed to fetch');
  };
  const result = await loadClients(dead);

  assert.equal(result.ok, false, 'a dead server must never be rendered as "no clients found"');
  assert.match(result.error, /Failed to fetch|reach/i);
});

test('a non-JSON error body still produces a readable reason', async () => {
  const result = await loadClients(fakeFetch(500, undefined));
  assert.equal(result.ok, false);
  assert.match(result.error, /500/, 'with no error field to quote, the status is the only honest thing to say');
});

test('a successful client list comes back as a plain array', async () => {
  const rows = [client(), client({ id: 'cursor', label: 'Cursor' })];
  const impl = fakeFetch(200, { clients: rows });

  const result = await loadClients(impl);

  assert.equal(result.ok, true);
  assert.deepEqual(result.clients, rows);
  assert.equal(impl.calls[0].url, '/api/clients');
});

test('a 200 with no clients key is an empty list, not a crash', async () => {
  const result = await loadClients(fakeFetch(200, {}));
  assert.equal(result.ok, true);
  assert.deepEqual(result.clients, []);
});
