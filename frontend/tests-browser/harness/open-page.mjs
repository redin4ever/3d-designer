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

/** Wait until the status pill says the socket is open — proves main.js actually ran. */
export async function waitForConnected(page) {
  await page.waitForFunction(
    () => document.getElementById('connection-status')?.dataset.status === 'open',
    { timeout: CONDITION_TIMEOUT_MS, polling: 50 },
  );
}

/** Wait until the action log has rendered at least `count` rows. */
export async function waitForLogRows(page, count) {
  await page.waitForFunction(
    (n) => document.querySelectorAll('#action-log li').length >= n,
    { timeout: CONDITION_TIMEOUT_MS, polling: 50 },
    count,
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
