// Wiring an AI client to this tool — the decisions, with no DOM and no server.
//
// Connecting is a setup step a person does once, usually in a hurry, and almost never
// debugs. The three shapes a machine can be in — no AI client installed, exactly one, or
// several — are three genuinely different screens, and getting the branch wrong is
// invisible until someone with that machine hits it. So the branch lives here, pure and
// covered, exactly like socket.js's `classifySeq` and transcript.js's `applyServerLog`;
// connect-ui.js is left with nothing but DOM.
//
// The endpoints are served from the same origin as this page by src/app/live.py, so this
// is a plain `fetch` with no CORS and no configuration. What comes back is described in
// src/app/connect.py::detect_clients.

const CLIENTS_ENDPOINT = '/api/clients';
const CONNECT_ENDPOINT = '/api/connect';

/**
 * @typedef {{id: string, label: string, transport: string, config_path: string,
 *   configured: boolean, note: string}} Client
 * @typedef {{tone: 'ok'|'error'|'empty', title: string, path?: string, lines: string[]}} Outcome
 */

function isClient(value) {
  return (
    value !== null &&
    typeof value === 'object' &&
    typeof value.id === 'string' &&
    value.id !== '' &&
    typeof value.label === 'string'
  );
}

function noClientsOutcome() {
  return {
    tone: 'empty',
    title: 'No AI client found on this machine.',
    lines: [
      'None of the clients forge3d knows how to wire itself into have been set up here yet. ' +
        'That is an ordinary machine, not a fault.',
      'Run  forge3d connect  in a terminal: it prints the exact config, with this machine’s ' +
        'own paths already filled in, for every client it supports.',
    ],
  };
}

function alreadyReadyOutcome(clients) {
  const labels = clients.map((client) => client.label).join(', ');
  return {
    tone: 'ok',
    title: clients.length === 1 ? `${labels} is configured.` : 'AI clients are configured.',
    lines: [
      `${labels} already has the current forge3d server configuration.`,
      'No external file was rewritten. If its tools are not visible, restart that client and refresh this status.',
    ],
  };
}

/**
 * Decide what pressing Connect should actually do with the clients the backend found.
 *
 * The three branches are not interchangeable. Presenting an empty list as a picker is a
 * dead end with no way out of it; making someone choose from a list of one is a step that
 * exists only because the code could not be bothered to count; and silently connecting the
 * first of several would write a config file the user never asked for, into an application
 * they were not thinking about.
 *
 * Anything that is not a well-formed array of client rows degrades to `none` rather than
 * throwing, because a backend that answered strangely must still leave the user with the
 * terminal fallback rather than a button that does nothing at all.
 *
 * @param {Client[]} clients rows from GET /api/clients
 * @returns {{action: 'none', clients: Client[], outcome: Outcome}
 *   | {action: 'connect', client: Client, clients: Client[]}
 *   | {action: 'choose', clients: Client[]}}
 */
export function planConnect(clients) {
  const found = Array.isArray(clients) ? clients.filter(isClient) : [];
  if (found.length === 0) return { action: 'none', clients: found, outcome: noClientsOutcome() };
  if (found.every((client) => client.configured === true)) {
    return { action: 'none', clients: found, outcome: alreadyReadyOutcome(found) };
  }
  if (found.length === 1) return { action: 'connect', client: found[0], clients: found };
  return { action: 'choose', clients: found };
}

/**
 * How one client reads in the picker.
 *
 * A client that already has forge3d in its config must say so before it is picked. Writing
 * it again is harmless — and is exactly what someone wants after moving the checkout — but
 * offering it as though it were new hides the one fact that decides the click.
 *
 * @param {Client} client
 */
export function choiceLabel(client) {
  return client?.configured === true
    ? `${client.label} — already connected, write it again`
    : `${client?.label ?? 'Unknown client'}`;
}

/**
 * What to say once the config has been written.
 *
 * The restart line is the whole message. Every client here reads its MCP config at start-up
 * and never again, so a user who does not restart sees no forge3d tools at all — which is
 * indistinguishable, from where they are standing, from this button not working. Saying it
 * afterwards, in the client's own name, is the difference between a setup that succeeded
 * and a bug report.
 *
 * The client's own `note` is passed through verbatim: src/app/connect.py writes those to be
 * read by a person, and they carry the per-client detail this page cannot know.
 *
 * `critical` names the one line that must not be skimmed past, so a renderer can lift it out
 * of the surrounding prose. It is also present in `lines`: a renderer that ignores `critical`
 * still shows the restart instruction, because dropping it is the one failure this whole
 * function exists to prevent.
 *
 * @param {{path?: string, note?: string, client?: string}} response the 200 body from POST /api/connect
 * @param {Client} [client] the row this came from — carries the label and `configured`
 * @returns {Outcome & {critical: string}}
 */
export function describeSuccess(response, client) {
  const label = client?.label ?? response?.client ?? 'that client';
  const rewritten = client?.configured === true;
  const note = typeof response?.note === 'string' ? response.note.trim() : '';
  const restart =
    `Restart ${label} before you go looking for the tools. Until you do it shows none of ` +
    'them, which looks exactly like this did not work.';
  return {
    tone: 'ok',
    title: `${rewritten ? 'Re-wrote' : 'Wrote'} the ${label} config.`,
    path: response?.path ?? '',
    critical: restart,
    lines: [
      restart,
      ...(note ? [note] : []),
      `Nothing changed in this page — forge3d appears inside ${label} the next time it starts.`,
    ],
  };
}

/**
 * What to say when the write did not happen.
 *
 * The server's message reaches the screen unedited. src/app/live.py answers 400 and 500
 * with a sentence written for a person — "exists but could not be read as JSON. Left
 * untouched — fix or move it, then run this again" — and paraphrasing that into "could not
 * connect" throws away the only part that tells them what to do next.
 *
 * @param {string} error the `error` field the backend sent
 * @returns {Outcome}
 */
export function describeFailure(error) {
  const said = String(error ?? '').trim();
  return {
    tone: 'error',
    title: 'Could not write the config.',
    lines: [said || 'The server gave no reason, which is itself worth reporting.'],
  };
}

async function requestJson(fetchImpl, url, init) {
  let response;
  try {
    response = await fetchImpl(url, init);
  } catch (err) {
    // A dead backend and an empty machine must never render the same way: one is fixed by
    // restarting `forge3d run`, the other by installing a client.
    const detail = err?.message ?? String(err);
    return { ok: false, error: `Could not reach ${url} (${detail}). Is "forge3d run" still going?` };
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    return { ok: false, error: payload?.error ?? `${url} answered ${response.status}.` };
  }
  return { ok: true, payload: payload ?? {} };
}

/**
 * Ask which AI clients this machine has.
 *
 * `fetchImpl` defaults to the page's own `fetch`, resolved at call time rather than
 * captured at import — that is what lets a browser test swap it after the page has loaded,
 * and calling it through a wrapper rather than passing the bare function is what stops
 * Chrome throwing "Illegal invocation" on an unbound `fetch`.
 *
 * @param {typeof fetch} [fetchImpl]
 * @returns {Promise<{ok: true, clients: Client[]}|{ok: false, error: string}>}
 */
export async function loadClients(fetchImpl = (...args) => globalThis.fetch(...args)) {
  const result = await requestJson(fetchImpl, CLIENTS_ENDPOINT);
  if (!result.ok) return result;
  return { ok: true, clients: Array.isArray(result.payload.clients) ? result.payload.clients : [] };
}

/**
 * Ask the backend to merge forge3d into one client's config.
 *
 * Merged, never replaced — src/app/connect.py::write_config keeps every other MCP server
 * the person has set up. Getting that wrong would silently disconnect all of them, which is
 * why this endpoint takes a client id and not a path.
 *
 * @param {typeof fetch} fetchImpl
 * @param {string} id one of the ids from `loadClients`
 * @returns {Promise<{ok: true, path?: string, note?: string}|{ok: false, error: string}>}
 */
export async function connectClient(fetchImpl, id) {
  const result = await requestJson(fetchImpl, CONNECT_ENDPOINT, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ client: id }),
  });
  if (!result.ok) return result;
  return { ok: true, ...result.payload };
}
