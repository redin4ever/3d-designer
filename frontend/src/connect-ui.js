// The Connect button's DOM wiring. Every decision it makes comes from connect.js; this
// file only moves text and focus around, which is why it has no unit test of its own —
// the same reason `attachControls` and `SocketClient` do not (frontend/CLAUDE.md). What it
// *is* covered by is frontend/tests-browser/connect.browser.mjs, in a real browser, because
// the parts that can be wrong here — a modal that leaves focus behind it, a picker Escape
// does not close — are not visible to node:test at all.
//
// All three outcomes are shown in the dialog, not in the sidebar. That is a layout decision
// with a reason: the conversation panel is ~340px wide, and a written-config result is five
// lines including the restart warning. Rendered inline it squeezed the transcript to zero
// height — the operator lost the panel they use continuously to a setup step they run once.
//
// The dialog is a native <dialog>. Written by hand, a modal has to move focus in, keep it
// there, close on Escape and put focus back where it came from; the platform already does
// all four, and a hand-rolled one that misses the last of them strands a keyboard user in a
// panel they can no longer see.

import {
  planConnect,
  choiceLabel,
  describeSuccess,
  describeFailure,
  loadClients,
  connectClient,
} from './connect.js';

function outcomeNodes(outcome) {
  const nodes = [];

  const title = document.createElement('p');
  title.className = 'connect-result-title';
  title.textContent = outcome.title;
  nodes.push(title);

  if (outcome.path) {
    const path = document.createElement('p');
    path.className = 'connect-result-path';
    path.textContent = outcome.path;
    nodes.push(path);
  }

  for (const line of outcome.lines ?? []) {
    const row = document.createElement('p');
    // `critical` is the restart instruction. Rendered as one more muted line among four it
    // gets skimmed past, and the user goes looking for tools that will not be there until
    // they do the one thing this paragraph asked for.
    row.className =
      line === outcome.critical ? 'connect-result-line connect-result-critical' : 'connect-result-line';
    row.textContent = line;
    nodes.push(row);
  }
  return nodes;
}

function buildChoice(client, onPick) {
  const item = document.createElement('li');
  const choice = document.createElement('button');
  choice.type = 'button';
  choice.className = 'connect-choice';
  choice.dataset.clientId = client.id;

  const name = document.createElement('span');
  name.className = 'connect-choice-label';
  name.textContent = choiceLabel(client);

  // The path is part of the choice, not decoration: this is the file about to change, and
  // on a machine with more than one checkout it is the only thing telling two rows apart.
  const path = document.createElement('span');
  path.className = 'connect-choice-path';
  path.textContent = client.config_path ?? '';

  choice.append(name, path);
  choice.addEventListener('click', () => onPick(client));
  item.appendChild(choice);
  return item;
}

/**
 * Wire the Connect button and its dialog.
 *
 * The one thing this must never do is claim more than it did. Connecting writes a config
 * file; it does not open a connection, and nothing in this page changes when it works — the
 * agent turns up the next time that client starts. A user who believes otherwise stands
 * here waiting for something that is going to happen somewhere else, decides the product is
 * broken, and is right to.
 *
 * @param {ParentNode} root anything containing the button and the dialog — main.js passes
 *   `document`, since the dialog renders in the top layer and sits outside `<main>`.
 * @param {{fetchImpl?: typeof fetch}} [io] `fetchImpl` exists for tests; the default
 *   resolves the page's own `fetch` at call time.
 */
export function attachConnectButton(root, io = {}) {
  const button = root.querySelector('#connect-button');
  const dialog = root.querySelector('#connect-dialog');
  const body = root.querySelector('#connect-dialog-body');
  const dismiss = root.querySelector('[data-action="connect-cancel"]');
  if (!button || !dialog || !body) return;

  const fetchImpl = io.fetchImpl ?? ((...args) => globalThis.fetch(...args));
  let busy = false;

  const showStatus = (state, label, description) => {
    button.dataset.connectionState = state;
    button.textContent = label;
    button.setAttribute('aria-label', description);
    button.setAttribute('title', description);
  };

  const applyDetectedState = (found) => {
    if (!found.ok) {
      showStatus('unavailable', 'Agent unavailable', found.error);
      return;
    }
    const clients = found.clients;
    const ready = clients.filter((client) => client.configured === true);
    const pending = clients.filter((client) => client.configured !== true);
    if (clients.length === 0) {
      showStatus('unavailable', 'No agent found', 'No supported AI client was detected on this machine.');
    } else if (pending.length === 0) {
      const label = ready.length === 1 ? `${ready[0].label} ready` : `${ready.length} agents ready`;
      showStatus('ready', label, `${ready.map((client) => client.label).join(', ')} configuration ready.`);
    } else {
      const label = clients.length === 1 ? `Set up ${clients[0].label}` : 'Set up agent';
      const names = pending.map((client) => client.label).join(', ');
      showStatus('action-required', label, `${names} requires configuration or an update.`);
    }
  };

  const refreshStatus = async () => {
    showStatus('checking', 'Checking agentâ€¦', 'Checking supported AI client configuration.');
    const found = await loadClients(fetchImpl);
    applyDetectedState(found);
    return found;
  };

  // Never `disabled`: disabling the element that currently has focus drops focus to the
  // body, so a keyboard user who just pressed Enter loses their place mid-action. A flag
  // plus aria-busy says the same thing to everyone and keeps the button where it was.
  const setBusy = (value) => {
    busy = value;
    button.setAttribute('aria-busy', String(value));
  };

  const open = () => {
    if (!dialog.open) dialog.showModal();
  };

  /** Show a finished outcome. `dismiss` becomes the way out, so focus belongs on it. */
  const showOutcome = (outcome) => {
    body.dataset.tone = outcome.tone;
    body.replaceChildren(...outcomeNodes(outcome));
    if (dismiss) dismiss.textContent = 'Close';
    open();
    // The picker's buttons have just been removed. Something has to hold focus or it falls
    // to the dialog itself and the next Tab starts from the top of the page.
    dismiss?.focus();
  };

  const showChoices = (clients, onPick) => {
    body.dataset.tone = 'choose';
    const list = document.createElement('ul');
    list.className = 'connect-choices';
    list.append(...clients.map((client) => buildChoice(client, onPick)));
    body.replaceChildren(list);
    if (dismiss) dismiss.textContent = 'Cancel';
    open();
    list.querySelector('button')?.focus();
  };

  async function write(client) {
    setBusy(true);
    const result = await connectClient(fetchImpl, client.id);
    setBusy(false);
    if (result.ok) {
      showStatus(
        'restart-required',
        `Restart ${client.label}`,
        `${client.label} was configured and must be restarted before forge3d tools appear.`,
      );
    } else {
      showStatus('action-required', `Set up ${client.label}`, result.error);
    }
    showOutcome(result.ok ? describeSuccess(result, client) : describeFailure(result.error));
  }

  button.addEventListener('click', async () => {
    if (busy) return;
    // Cleared before the lookup: a result left over from the last press, sitting there while
    // a fresh one is still in flight, reads as the answer to the click just made.
    body.replaceChildren();
    setBusy(true);
    const found = await loadClients(fetchImpl);
    setBusy(false);

    if (!found.ok) {
      showOutcome(describeFailure(found.error));
      return;
    }

    const plan = planConnect(found.clients);
    if (plan.action === 'none') showOutcome(plan.outcome);
    else if (plan.action === 'connect') await write(plan.client);
    else showChoices(plan.clients, (picked) => write(picked));
  });

  dismiss?.addEventListener('click', () => dialog.close());
  // `close` fires for Escape and for the dismiss button alike. Chrome restores focus to the
  // opener on its own, but only when nothing else has claimed it in between — putting it
  // back explicitly is one line and removes the "in between".
  dialog.addEventListener('close', () => button.focus());

  // Detection is read-only and happens on attachment so the top bar tells the truth before
  // anyone goes looking for a Connect action. External configuration writes remain behind
  // the button click above.
  void refreshStatus();

  return { refreshStatus };
}
