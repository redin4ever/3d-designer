// The conversation panel: a transcript of what the operator asked for and what the agent
// said back. Split from log.js rather than folded into it because it is a different
// decision, not a different style of row — the action log only ever receives, whereas the
// transcript has to reconcile a line this browser printed optimistically against the
// server's later echo of the same line. log.js's append-only counter cannot express that:
// reconciling changes an entry that is already on screen.
//
// The append/cap/drop-from-the-DOM machinery is deliberately the same shape as log.js's,
// for the same reason: this container is an aria-live region, and rebuilding it on every
// message makes a screen reader re-announce the entire history each time.
//
// Roles ride in ServerMessage.data.role (contracts/wire.py's free-form `data` dict):
//   operator — the operator's own words, echoed back once the backend has queued them.
//              Seeing your own line come back IS the delivery confirmation.
//   agent    — what the agent just did or found.
//   system   — status: connected, phase changes, run state.

/** Mirrors the roles src/viewer puts in a LOG message's `data.role`. */
export const TRANSCRIPT_ROLES = Object.freeze(['operator', 'agent', 'system']);

/** Long autonomous runs are the norm (Gate A 4.4); generous, but never unbounded. */
export const DEFAULT_MAX_MESSAGES = 200;

/** What each row says about whether the backend actually has an operator's words yet. */
const OPERATOR_STATE_MARKER = Object.freeze({
  pending: 'sending…',
  confirmed: 'queued for the agent',
  unconfirmed: 'not delivered — send it again',
});

const WHO = Object.freeze({ operator: 'You', agent: 'Agent', system: 'System' });

/**
 * Create the transcript's state.
 *
 * `maxMessages` is a hard ceiling on both the array and the rendered rows. Getting it
 * wrong in the "unbounded" direction is not a leak that shows up in a benchmark — it is a
 * page that grows all day during a build and eventually stops responding to the operator
 * who needs to stop it.
 *
 * @param {number} [maxMessages]
 * @returns {{entries: object[], maxMessages: number, appended: number, lastSeq: number|null, revision: number}}
 */
export function createTranscript(maxMessages = DEFAULT_MAX_MESSAGES) {
  if (!Number.isInteger(maxMessages) || maxMessages < 1) {
    throw new Error(`maxMessages must be a positive integer, got ${maxMessages}`);
  }
  return { entries: [], maxMessages, appended: 0, lastSeq: null, revision: 0 };
}

function push(transcript, entry) {
  // `appended` is a total ever appended, never reset by the cap — reconciling on array
  // length alone cannot tell 'nothing new' from 'one added and one dropped off the
  // front', and the second case renders a panel that silently stops updating.
  transcript.appended += 1;
  transcript.entries.push({ id: transcript.appended, ...entry });
  const overflow = transcript.entries.length - transcript.maxMessages;
  if (overflow > 0) transcript.entries.splice(0, overflow);
  return transcript.entries[transcript.entries.length - 1];
}

/**
 * Show the operator's own line immediately, before the server has seen it.
 *
 * Waiting for the round trip first would leave the panel blank at the one moment the
 * operator is watching it hardest, which reads as "the product ignored me". The entry
 * starts `pending` and is not claimed as delivered until the server echoes it back.
 *
 * @param {ReturnType<typeof createTranscript>} transcript
 * @param {string} text
 * @returns {object} the entry just appended
 */
export function appendOperatorMessage(transcript, text) {
  if (typeof text !== 'string' || text.trim() === '') {
    throw new Error('an empty message would be silently dropped');
  }
  return push(transcript, { role: 'operator', text, state: 'pending', seq: null });
}

function normalizeRole(role) {
  // A LOG with no role must never make a message disappear: older backends send exactly
  // that, and a panel that hides messages from a server that is working perfectly well is
  // indistinguishable, to the operator, from a build that has stopped.
  return TRANSCRIPT_ROLES.includes(role) ? role : 'system';
}

/**
 * Apply one LOG ServerMessage.
 *
 * An `operator` message is the server's echo of something this browser already printed,
 * so it confirms the pending line rather than printing it a second time — an operator who
 * sees their instruction twice believes they sent it twice. When nothing pending matches
 * (a page opened mid-run, or a second browser watching the same build) it is appended
 * instead: showing a duplicate is bad, losing an instruction from the record is worse.
 *
 * @param {ReturnType<typeof createTranscript>} transcript
 * @param {{seq?: number, text?: string, data?: {role?: string}}} message a wire LOG
 *   message, or a locally generated status line with no `seq`.
 */
export function applyServerLog(transcript, message) {
  const seq = message?.seq;
  const hasSeq = typeof seq === 'number';

  // Replayed conversation history, handed over when a client connects. It is exempt from
  // the duplicate rule, and has to be: the entire greeting is sent at a single seq, so
  // every replayed line after the first compares `seq <= lastSeq` and would be dropped —
  // silently, and one layer below the socket's own gate, which needs the same exemption
  // for the same reason. That is the difference between a refresh keeping the
  // conversation and a refresh appearing to erase it.
  const replayed = message?.data?.replayed === true;

  if (!replayed && hasSeq && transcript.lastSeq !== null && seq <= transcript.lastSeq) {
    // wire.py's duplicate/out-of-order rule. Retries happen; a retried frame that
    // double-printed would read as the agent repeating itself.
    return transcript;
  }
  // History does not advance the baseline either — it is older than everything live.
  if (hasSeq && !replayed) transcript.lastSeq = seq;

  const role = normalizeRole(message?.data?.role);
  const text = message?.text ?? '';

  if (role === 'operator') {
    const pending = transcript.entries.find(
      (entry) => entry.role === 'operator' && entry.state === 'pending' && entry.text === text,
    );
    if (pending) {
      pending.state = 'confirmed';
      pending.seq = hasSeq ? seq : null;
      transcript.revision += 1;
      return transcript;
    }
  }

  push(transcript, { role, text, state: 'confirmed', seq: hasSeq ? seq : null });
  return transcript;
}

/**
 * Mark every still-pending operator line as unconfirmed.
 *
 * Called when the socket drops or a send fails. Without it a line whose echo will never
 * arrive sits looking exactly like a delivered one, and the operator waits for something
 * that is never going to happen.
 *
 * @param {ReturnType<typeof createTranscript>} transcript
 */
export function markPendingUnconfirmed(transcript) {
  for (const entry of transcript.entries) {
    if (entry.state === 'pending') {
      entry.state = 'unconfirmed';
      transcript.revision += 1;
    }
  }
  return transcript;
}

function buildRow(entry) {
  const row = document.createElement('li');
  row.className = 'transcript-row';
  row.dataset.role = entry.role;
  row.dataset.state = entry.state;

  const who = document.createElement('span');
  who.className = 'transcript-who';
  who.textContent = WHO[entry.role];

  const text = document.createElement('span');
  text.className = 'transcript-text';
  text.textContent = entry.text;

  const marker = document.createElement('span');
  marker.className = 'transcript-state';
  // aria-hidden because this is the one part of a row that changes after it is announced.
  // Left in the accessibility tree, flipping 'sending…' to 'queued for the agent' would
  // make a polite live region read the whole line back a second time.
  marker.setAttribute('aria-hidden', 'true');
  marker.textContent = stateMarker(entry);

  row.appendChild(who);
  row.appendChild(text);
  row.appendChild(marker);
  row.__marker = marker;
  return row;
}

function stateMarker(entry) {
  return entry.role === 'operator' ? OPERATOR_STATE_MARKER[entry.state] ?? '' : '';
}

function syncRowState(row, entry) {
  if (!row || row.dataset.state === entry.state) return;
  row.dataset.state = entry.state;
  // Only the aria-hidden marker and the data attribute change — never the announced text.
  if (row.__marker) row.__marker.textContent = stateMarker(entry);
}

/**
 * Render the transcript into a container, newest message last.
 *
 * Appends what is new and updates in place what changed state; never rebuilds. A rebuild
 * inside this aria-live region re-announces the entire conversation on every message,
 * which is the difference between a usable panel and an unusable one for a screen-reader
 * user on a build that emits hundreds of them.
 *
 * @param {ReturnType<typeof createTranscript>} transcript
 * @param {HTMLElement} container
 */
export function renderTranscript(transcript, container) {
  const appended = transcript.appended;
  const alreadyRendered = container.__renderedAppended ?? 0;
  const fresh = Math.min(Math.max(appended - alreadyRendered, 0), transcript.entries.length);

  const fragment = document.createDocumentFragment();
  for (const entry of transcript.entries.slice(transcript.entries.length - fresh)) {
    fragment.appendChild(buildRow(entry));
  }
  if (fragment.childElementCount > 0) container.appendChild(fragment);

  // Drop from the front so the DOM never outgrows the cap the transcript actually keeps.
  while (container.childElementCount > transcript.entries.length) {
    container.removeChild(container.firstElementChild);
  }

  if (container.__renderedRevision !== transcript.revision) {
    for (let i = 0; i < transcript.entries.length; i += 1) {
      syncRowState(container.children[i], transcript.entries[i]);
    }
    container.__renderedRevision = transcript.revision;
  }

  container.__renderedAppended = appended;
  // The newest message must be visible without the operator hunting for it.
  container.scrollTop = container.scrollHeight;
}
