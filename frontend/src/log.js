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
  const overflow = log.entries.length - log.maxEntries;
  if (overflow > 0) {
    log.entries.splice(0, overflow);
  }
  return log;
}

/**
 * Render the log into a container element, newest entry last (reading order). Rebuilds
 * the DOM list wholesale — simple and fast enough at `maxEntries` scale, and avoids a
 * second piece of diffing logic in a file with no framework to lean on.
 *
 * @param {ReturnType<typeof createActionLog>} log
 * @param {HTMLElement} container
 */
export function renderActionLog(log, container) {
  container.textContent = '';
  const fragment = document.createDocumentFragment();
  for (const entry of log.entries) {
    const row = document.createElement('li');
    row.className = 'log-row';
    if (entry.kind) row.dataset.kind = entry.kind;
    const text = document.createElement('span');
    text.className = 'log-row-text';
    text.textContent = entry.text ?? '';
    row.appendChild(text);
    fragment.appendChild(row);
  }
  container.appendChild(fragment);
  container.scrollTop = container.scrollHeight;
}
