// The action log (Gate A 5.1, 5.3): a running record of what the build has done, capped
// so a run of thousands of operations (Gate A 11.4) does not grow the DOM or memory
// without bound. Split from viewport.js because it is a distinct actor — it reacts to
// LOG server messages, not mesh/transform/highlight ones — and from controls.js because
// it only ever receives, never sends.

/** Long autonomous runs are the norm (Gate A 4.4); this is generous but not unbounded. */
export const DEFAULT_MAX_ENTRIES = 500;

/**
 * @param {number} [maxEntries]
 * @returns {{entries: object[], maxEntries: number}}
 */
export function createActionLog(maxEntries = DEFAULT_MAX_ENTRIES) {
  if (!Number.isInteger(maxEntries) || maxEntries < 1) {
    throw new Error(`maxEntries must be a positive integer, got ${maxEntries}`);
  }
  return { entries: [], maxEntries };
}

/**
 * Append one entry, oldest-first, dropping the oldest entries once maxEntries is
 * exceeded. Mutates and returns `log` so callers can chain.
 *
 * @param {ReturnType<typeof createActionLog>} log
 * @param {object} entry any JSON-shaped record — main.js appends `{text, seq, at}` for
 *   every LOG message and a synthesized entry for phase/run_state/problems changes.
 */
export function appendLogEntry(log, entry) {
  log.entries.push(entry);
  // Total ever appended, never reset by the cap. Reconciling on list length alone
  // cannot distinguish 'nothing new' from 'one added and one dropped off the front',
  // and the second case renders a log that silently stops updating.
  log.appended = (log.appended ?? 0) + 1;
  const overflow = log.entries.length - log.maxEntries;
  if (overflow > 0) {
    log.entries.splice(0, overflow);
  }
  return log;
}

/**
 * Render the log into a container element, newest entry last (reading order).
 *
 * Appends only what is new. Rebuilding wholesale was simpler, but this container is an
 * aria-live region and this runs on every incoming message — so a full rebuild made a
 * screen reader announce the entire reconstructed history on every geometry update.
 *
 * @param {ReturnType<typeof createActionLog>} log
 * @param {HTMLElement} container
 */
function buildRow(entry) {
  const row = document.createElement('li');
  row.className = 'log-row';
  if (entry.kind) row.dataset.kind = entry.kind;
  const text = document.createElement('span');
  text.className = 'log-row-text';
  text.textContent = entry.text ?? '';
  row.appendChild(text);
  return row;
}

export function renderActionLog(log, container) {
  const appended = log.appended ?? log.entries.length;
  const alreadyRendered = container.__renderedAppended ?? 0;
  const fresh = Math.min(Math.max(appended - alreadyRendered, 0), log.entries.length);

  const fragment = document.createDocumentFragment();
  for (const entry of log.entries.slice(log.entries.length - fresh)) {
    fragment.appendChild(buildRow(entry));
  }
  if (fragment.childElementCount > 0) container.appendChild(fragment);

  // Drop from the front so the DOM never outgrows the log the cap actually keeps.
  while (container.childElementCount > log.entries.length) {
    container.removeChild(container.firstElementChild);
  }

  container.__renderedAppended = appended;
  container.scrollTop = container.scrollHeight;
}
