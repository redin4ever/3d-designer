// Page lifecycle for the smoke suite: launch, collect everything the browser complains
// about, navigate, and wait on a *condition* rather than a sleep (Rule 4, Determinism).
//
// The collectors are the point of the file. A page that throws on load and still paints
// looks fine to a human and fine to a screenshot; it is only distinguishable by listening
// on `pageerror` and `console`. Every listener is attached BEFORE `goto`, or the errors
// raised while the modules are evaluating are missed entirely.

import puppeteer from 'puppeteer';

const NAV_TIMEOUT_MS = 20_000;
const CONDITION_TIMEOUT_MS = 15_000;

export async function launchBrowser() {
  return puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
}

/**
 * @param {import('puppeteer').Browser} browser
 * @param {{origin: string, wsUrl: string, viewport?: {width: number, height: number},
 *   colorScheme?: 'light'|'dark', reducedMotion?: 'reduce'|'no-preference'}} options
 * @returns {Promise<{page: import('puppeteer').Page, consoleErrors: string[],
 *   consoleWarnings: string[], pageErrors: string[], failedRequests: string[],
 *   badResponses: string[], close: () => Promise<void>}>}
 */
export async function openConsolePage(browser, options) {
  const { origin, wsUrl, viewport = { width: 1280, height: 800 }, colorScheme, reducedMotion } =
    options;

  const page = await browser.newPage();
  const consoleErrors = [];
  const consoleWarnings = [];
  const pageErrors = [];
  const failedRequests = [];
  const badResponses = [];

  page.on('console', (msg) => {
    const where = msg.location?.() ?? {};
    const at = where.url ? ` (${where.url}:${where.lineNumber ?? '?'})` : '';
    if (msg.type() === 'error') consoleErrors.push(`${msg.text()}${at}`);
    else if (msg.type() === 'warning') consoleWarnings.push(`${msg.text()}${at}`);
  });
  page.on('pageerror', (err) => pageErrors.push(`${err.name}: ${err.message}`));
  page.on('requestfailed', (req) => {
    failedRequests.push(`${req.url()} — ${req.failure()?.errorText ?? 'unknown'}`);
  });
  page.on('response', (res) => {
    if (res.status() >= 400) badResponses.push(`${res.status()} ${res.url()}`);
  });

  await page.setViewport(viewport);
  const features = [];
  if (colorScheme) features.push({ name: 'prefers-color-scheme', value: colorScheme });
  if (reducedMotion) features.push({ name: 'prefers-reduced-motion', value: reducedMotion });
  if (features.length) await page.emulateMediaFeatures(features);

  const url = `${origin}/index.html?ws=${encodeURIComponent(wsUrl)}`;
  await page.goto(url, { waitUntil: 'load', timeout: NAV_TIMEOUT_MS });

  return {
    page,
    consoleErrors,
    consoleWarnings,
    pageErrors,
    failedRequests,
    badResponses,
    close: () => page.close(),
  };
}

/**
 * Accept either a session or a bare page, and recover both.
 * The collectors are what make a timeout diagnosable, so keep them when they exist.
 */
function unwrap(target) {
  return target?.page ? { page: target.page, session: target } : { page: target, session: null };
}

/**
 * Re-throw a wait timeout with everything the browser complained about attached.
 *
 * This exists because of a real debugging failure: a broken WebSocket handshake in the
 * harness made all ten tests die on `waitForConnected` with a bare "15000ms exceeded",
 * which names the symptom and hides the cause. The console had said exactly what was
 * wrong the whole time. A timeout that discards the collectors turns a one-line fix into
 * a bisect.
 */
async function waitOrExplain(target, description, run) {
  const { session } = unwrap(target);
  try {
    await run();
  } catch (cause) {
    if (!session) throw cause;
    const said = complaints(session);
    const section = (name, lines) => (lines.length ? `\n  ${name}:\n    ${lines.join('\n    ')}` : '');
    throw new Error(
      `timed out waiting for ${description}` +
        section('page errors', said.pageErrors) +
        section('console errors', said.consoleErrors) +
        section('failed requests', said.failedRequests) +
        section('bad responses', said.badResponses) +
        (Object.values(said).every((l) => l.length === 0)
          ? '\n  the browser reported nothing at all — the condition simply never became true'
          : ''),
      { cause },
    );
  }
}

/** Wait until the status pill says the socket is open — proves main.js actually ran. */
export async function waitForConnected(target) {
  const { page } = unwrap(target);
  await waitOrExplain(target, 'the socket to report status=open', () =>
    page.waitForFunction(
      () => document.getElementById('connection-status')?.dataset.status === 'open',
      { timeout: CONDITION_TIMEOUT_MS, polling: 50 },
    ),
  );
}

/** Wait until the action log has rendered at least `count` rows. */
export async function waitForLogRows(target, count) {
  const { page } = unwrap(target);
  await waitOrExplain(target, `${count} action-log rows`, () =>
    page.waitForFunction(
      (n) => document.querySelectorAll('#action-log li').length >= n,
      { timeout: CONDITION_TIMEOUT_MS, polling: 50 },
      count,
    ),
  );
}

/**
 * Everything the collectors caught, as one object — so a failing assertion can print the
 * actual browser complaint instead of just a count.
 */
export function complaints(session) {
  return {
    consoleErrors: session.consoleErrors,
    pageErrors: session.pageErrors,
    failedRequests: session.failedRequests,
    badResponses: session.badResponses,
  };
}
