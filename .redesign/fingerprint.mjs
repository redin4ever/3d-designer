#!/usr/bin/env node
/**
 * Captures what a page looks like, so "it changed" can be measured rather than asserted.
 *
 *   node .redesign/fingerprint.mjs baseline    # before the sweep
 *   node .redesign/fingerprint.mjs after       # after it
 *
 * Writes .redesign/<phase>/<item-id>/{fingerprint.json, ltr.png, rtl.png}.
 * Requires puppeteer and a running app at config.baseUrl.
 */

import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';

// puppeteer is imported further down, once we know we are going to use a browser. A static
// import is hoisted above every check in this file, so a missing dependency would preempt
// the baseline guard below — and an unhelpful ERR_MODULE_NOT_FOUND would preempt saying so.

const DIR = '.redesign';
const phase = process.argv[2] === 'after' ? 'after' : 'baseline';
const force = process.argv.includes('--force');

/**
 * A baseline is captured once, before anything is edited. Capturing it again over a site
 * that has already been redesigned does not lose a step — it destroys the measurement, and
 * silently: the gate then compares the design against itself, reports 0% changed, and
 * phase-6-verify tells you to go and redesign the page again. The record of what it used
 * to look like is gone by then.
 *
 * So this refuses, and says which command you probably wanted instead.
 */
if (phase === 'baseline' && !force && fs.existsSync(path.join(DIR, 'baseline'))) {
  const captured = fs.readdirSync(path.join(DIR, 'baseline'))
    .filter((d) => fs.existsSync(path.join(DIR, 'baseline', d, 'fingerprint.json')));
  if (captured.length) {
    console.error(`\n  ${DIR}/baseline already holds ${captured.length} captured surface(s).`);
    console.error('  Re-capturing would record the current — already redesigned — site as the "before",');
    console.error('  and the gate would then be comparing the design to itself.\n');
    const how = [
      ['node .redesign/fingerprint.mjs after', 'capture the post-sweep state (Phase 6)'],
      ['node .redesign/check.mjs', 'report where the run stands'],
      [`mv ${DIR} ${DIR}.previous`, 'start over, keeping the old evidence'],
    ];
    const w = Math.max(...how.map(([c]) => c.length));
    for (const [cmd, why] of how) console.error(`    ${cmd.padEnd(w)}   ${why}`);
    console.error('');
    console.error('  --force overrides this, and discards what the baseline recorded.\n');
    process.exit(2);
  }
}

/**
 * Missing setup is "I cannot run", not a stack trace.
 *
 * This is the first command Phase 0 tells you to run, and it used to end in a raw ENOENT on
 * config.json — a file no phase created. The gate encodes exactly this distinction; the
 * capture step did not.
 */
const load = (file, fix) => {
  try {
    return JSON.parse(fs.readFileSync(path.join(DIR, file), 'utf8'));
  } catch (err) {
    console.error(`\n  cannot read ${DIR}/${file}${err.code === 'ENOENT' ? '' : ` — ${err.message}`}\n  ${fix}\n`);
    process.exit(2);
  }
};

const cfg = load('config.json', 'It ships with the skill\'s assets — copy them in and fill it in (phase-0-preflight.md).');
const inventory = load('inventory.json', 'Generate it first — see phase-1-inventory.md.');

/** The style properties that carry visual identity. Changing a design changes these. */
const PROPS = [
  'color', 'background-color', 'border-color', 'border-width', 'border-style',
  'border-radius', 'box-shadow', 'font-family', 'font-size', 'font-weight',
  'line-height', 'letter-spacing', 'text-transform', 'padding', 'margin', 'gap',
  'opacity', 'text-align',
];

const capture = async (page) =>
  page.evaluate((PROPS) => {
    const styles = {};
    const colours = new Set();
    const sizes = new Set();
    let structure = '';

    const els = document.querySelectorAll('body *');
    for (const el of els) {
      if (!el.checkVisibility?.({ checkOpacity: true, checkVisibilityCSS: true })) continue;
      const cs = getComputedStyle(el);
      // key by role, not by identity, so adding a row does not read as a redesign
      const key = `${el.tagName.toLowerCase()}.${(el.className || '').toString().split(/\s+/)[0] || '-'}`;
      const decl = {};
      for (const p of PROPS) {
        const v = cs.getPropertyValue(p);
        if (v) decl[p] = v;
        if (/color/.test(p) && v && v !== 'rgba(0, 0, 0, 0)') colours.add(v);
        if (/size|width|radius|padding|margin|gap/.test(p) && v) v.split(' ').forEach((x) => sizes.add(x));
      }
      styles[key] = decl;
      structure += `${el.tagName}>`;
    }

    // geometry problems that only show in one direction
    const vw = document.documentElement.clientWidth;
    let overflow = false;
    const boxes = [];
    for (const el of els) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.right > vw + 1 || r.left < -1) overflow = true;
      boxes.push(r);
    }

    /**
     * What the page lets you DO, and what it lets you REACH.
     *
     * The gate used to guarantee safety by requiring the structure hash to be identical
     * before and after — which made it impossible to add anything, and so impossible to
     * turn a bare page into a designed one. These are what replace it: a redesign may add
     * to any of them, and may remove from none. Adding a dropdown is enrichment; dropping a
     * form action is a broken product.
     */
    const norm = (href) => {
      try {
        const u = new URL(href, location.href);
        if (u.origin !== location.origin) return null;         // external: not ours to keep
        // /orders/123 and /orders/456 are the same destination for wayfinding purposes.
        return u.pathname.replace(/\/\d+(?=\/|$)/g, '/:id').replace(/\/$/, '') || '/';
      } catch { return null; }
    };
    const nameOf = (el) =>
      (el.getAttribute('aria-label') || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80);

    const region = (el) => {
      if (el.closest('nav, [role="navigation"]')) return 'nav';
      if (el.closest('footer, [role="contentinfo"]')) return 'footer';
      if (el.closest('header, [role="banner"]')) return 'header';
      return 'content';
    };

    const anchors = {
      links: [...new Set([...document.querySelectorAll('a[href]')].map((a) => norm(a.getAttribute('href'))).filter(Boolean))],
      forms: [...document.querySelectorAll('form')].map((f) => `${(f.getAttribute('method') || 'get').toLowerCase()} ${norm(f.getAttribute('action') || location.pathname) ?? ''}`),
      controls: [...document.querySelectorAll('input[name], select[name], textarea[name]')].map((c) => `${c.tagName.toLowerCase()}:${c.getAttribute('name')}`),
      testids: [...document.querySelectorAll('[data-testid], [data-test], [data-cy]')].map((e) => e.getAttribute('data-testid') || e.getAttribute('data-test') || e.getAttribute('data-cy')),
      submits: document.querySelectorAll('button[type="submit"], input[type="submit"], form button:not([type])').length,
    };

    /** Where this page can take you, and from which part of the page. */
    const outbound = [...new Set([...document.querySelectorAll('a[href]')]
      .map((a) => { const to = norm(a.getAttribute('href')); return to ? `${region(a)} ${to} ${nameOf(a)}` : null; })
      .filter(Boolean))];

    /**
     * How much there is here.
     *
     * A bare page and a designed one differ in these before they differ in anything a style
     * fingerprint can see. Counted rather than judged, so "this page is still empty" is
     * something the gate can say out loud.
     */
    const navFor = document.querySelector('nav, [role="navigation"]');

    const headings = {};
    for (const h of document.querySelectorAll('h1,h2,h3,h4,h5,h6')) {
      const t = h.tagName.toLowerCase();
      if (nameOf(h)) headings[t] = (headings[t] ?? 0) + 1;
    }
    const imgs = [...document.querySelectorAll('img, svg, picture, [role="img"]')];
    const fields = [...document.querySelectorAll('input:not([type="hidden"]), select, textarea')];

    /**
     * A *visible* label, not merely an accessible name.
     *
     * `aria-label` satisfies a screen reader and adds no text to the page — so a form can
     * score fully labelled and still look exactly as bare as it did. The distinction is the
     * whole point here: this pass is about what a sighted user sees appear.
     */
    const visibleLabel = (f) => {
      const id = f.getAttribute('id');
      const forLabel = id && document.querySelector(`label[for="${CSS.escape(id)}"]`);
      const wrapping = f.closest('label');
      const el = forLabel || wrapping;
      return !!(el && (el.textContent || '').trim() && el.checkVisibility?.());
    };
    const labelled = fields.filter((f) =>
      visibleLabel(f) || f.getAttribute('aria-label') || f.getAttribute('aria-labelledby') || f.getAttribute('title'));
    const visiblyLabelled = fields.filter(visibleLabel);

    /**
     * Controls that sit inside a named group.
     *
     * Fourteen loose inputs is a wall; the same fourteen under "Details / Access /
     * Notifications" is a form somebody designed. This is the single change that most turns
     * one into the other, and it is countable.
     */
    const grouped = fields.filter((f) => {
      const g = f.closest('fieldset, section, [role="group"], [role="region"]');
      if (!g) return false;
      const legend = g.querySelector('legend, h1, h2, h3, h4');
      return !!(g.getAttribute('aria-label') || (legend && (legend.textContent || '').trim()));
    });

    /** A form you have committed to, with no way out that is not the browser's back button. */
    const formsWithoutExit = [...document.querySelectorAll('form')].filter((f) => {
      if (!f.querySelector('button[type="submit"], input[type="submit"], button:not([type])')) return false;
      const exits = [...f.querySelectorAll('a[href], button[type="reset"], input[type="reset"], button, [role="button"]')]
        .filter((e) => /cancel|back|discard|never mind|close/i.test(nameOf(e)));
      return exits.length === 0;
    }).length;

    /** The scaffold's own title, still there — proof nobody has been through this page. */
    const title = (document.title || '').trim();
    const titleIsScaffold = !title
      || /^(react app|vite app|vite \+ react|next\.js|create next app|document|untitled|app|home)$/i.test(title);

    const content = {
      text: (document.body.innerText || '').replace(/\s+/g, ' ').trim().length,
      headings,
      images: imgs.length,
      imagesDescribed: imgs.filter((i) => (i.getAttribute('alt') ?? '').trim() || i.getAttribute('aria-label') || i.getAttribute('role') === 'presentation' || i.getAttribute('aria-hidden') === 'true').length,
      fields: fields.length,
      fieldsLabelled: labelled.length,
      landmarks: [...new Set([...document.querySelectorAll('main,nav,header,footer,aside,section[aria-label],[role]')].map((e) => e.getAttribute('role') || e.tagName.toLowerCase()))],
      // A page that offers no way onward is a dead end however good it looks.
      onward: outbound.filter((o) => !o.startsWith('nav ') && !o.startsWith('footer ')).length,
      // Does the navigation say where you are? Cheapest wayfinding win there is, and its
      // absence is why an app feels like a set of pages rather than a place.
      navCurrent: !!(navFor && (navFor.querySelector('[aria-current]')
        || navFor.querySelector('.active, .current, [class*="--active"], [class*="is-active"], [data-active="true"]'))),
      title,
      titleIsScaffold,
      // Containers rendering a collection. A page with one of these has an empty state
      // whether or not anybody has designed it — and if nobody has, it renders as blank
      // space, which a user cannot tell apart from broken.
      collections: [...document.querySelectorAll('table tbody, ul, ol, [role="list"], [role="grid"], [role="table"]')]
        .filter((c) => c.children.length >= 2 && c.checkVisibility?.()).length,
      fieldsVisiblyLabelled: visiblyLabelled.length,
      fieldsGrouped: grouped.length,
      formsWithoutExit,
    };

    /**
     * How the page is ARRANGED, as distinct from how it is painted.
     *
     * A redesign that only swaps colour, type and spacing leaves every box where it was, and
     * the result still reads as the old product wearing new paint. Nothing in a style
     * fingerprint can see that: `padding` changing from 8px to 16px looks the same to it as
     * a sidebar becoming a top bar.
     *
     * These are the arrangement facts — where the regions sit, how many columns, how wide
     * the measure is, which way the nav runs, where the primary action lives. A redesign is
     * expected to move some of them, and the gate can now say so.
     */
    const vwNow = document.documentElement.clientWidth || 1;
    const vhNow = document.documentElement.clientHeight || 1;
    const box = (el) => {
      const r = el.getBoundingClientRect();
      // Bucketed to tenths of the viewport: a 3px nudge is not a new layout, and this must
      // not be satisfiable by jitter.
      return [Math.round((r.x / vwNow) * 10), Math.round((r.y / vhNow) * 10),
        Math.round((r.width / vwNow) * 10), Math.round((r.height / vhNow) * 10)].join(',');
    };

    const regions = {};
    for (const sel of ['header', 'nav', 'main', 'aside', 'footer', '[role="banner"]', '[role="navigation"]', '[role="main"]']) {
      const el = document.querySelector(sel);
      if (el && el.checkVisibility?.()) regions[sel] = box(el);
    }

    const main = document.querySelector('main, [role="main"]') || document.body;
    const tracks = (el) => {
      const cs = getComputedStyle(el);
      if (cs.display.includes('grid')) return (cs.gridTemplateColumns || '').split(/\s+/).filter(Boolean).length;
      if (cs.display.includes('flex')) return cs.flexDirection.startsWith('row') ? [...el.children].length : 1;
      return 1;
    };

    const navEl = document.querySelector('nav, [role="navigation"]');
    const primary = main.querySelector('button, a[class*="btn"], [role="button"], input[type="submit"]');

    const layout = {
      regions,
      // The stacking order the eye actually sees, which a CSS reorder changes and a repaint
      // does not.
      order: [...document.querySelectorAll('header, nav, main, aside, footer')]
        .filter((e) => e.checkVisibility?.())
        .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)
        .map((e) => e.tagName.toLowerCase()),
      columns: tracks(main),
      // How wide the reading measure is, in tenths of the viewport.
      measure: Math.round((main.getBoundingClientRect().width / vwNow) * 10),
      navAxis: navEl
        ? (navEl.getBoundingClientRect().width > navEl.getBoundingClientRect().height ? 'horizontal' : 'vertical')
        : null,
      primaryAction: primary ? box(primary) : null,
      density: Math.round(((document.body.innerText || '').length / Math.max(1, document.body.scrollHeight)) * 100),
      // Content running edge to edge across a wide browser is the most reliable amateur tell
      // there is, and it survives any amount of token work untouched. A dashboard may want
      // it; a page of prose never does, which is why the gate reports rather than forbids.
      fullBleed: getComputedStyle(main).maxWidth === 'none'
        && main.getBoundingClientRect().width > vwNow - 64,
    };

    return {
      styles,
      colours: [...colours],
      sizes: [...sizes],
      structure,
      anchors,
      outbound,
      content,
      layout,
      // Everything above is computed, so it is all px. The gate needs this to resolve rem
      // tokens into the same space; a page that sets html { font-size: 62.5% } would
      // otherwise read as using none of its own spacing scale.
      rootPx: parseFloat(getComputedStyle(document.documentElement).fontSize) || 16,
      geometry: { overflow, count: boxes.length },
    };
  }, PROPS);

const puppeteer = await import('puppeteer').then((m) => m.default ?? m).catch(() => {
  console.error('\n  fingerprint.mjs needs a real browser to read computed styles.\n');
  console.error('    npm install --no-save puppeteer\n');
  process.exit(2);
});

const browser = await puppeteer.launch({ headless: true });
const results = [];

for (const item of inventory.items) {
  if (!item.path) continue;
  const out = path.join(DIR, phase, item.id);
  fs.mkdirSync(out, { recursive: true });

  const page = await browser.newPage();
  await page.setViewport({ width: cfg.viewport?.width ?? 1440, height: cfg.viewport?.height ?? 900 });

  const record = { direction: {} };
  for (const dir of ['ltr', 'rtl']) {
    await page.evaluateOnNewDocument((d) => {
      document.addEventListener('DOMContentLoaded', () => { document.documentElement.dir = d; });
    }, dir);
    await page.goto(new URL(item.path, cfg.baseUrl).href, { waitUntil: 'networkidle0' });
    const shot = await capture(page);
    await page.screenshot({ path: path.join(out, `${dir}.png`), fullPage: true });

    if (dir === 'ltr') {
      record.styles = shot.styles;
      record.colours = shot.colours;
      record.sizes = shot.sizes;
      record.rootPx = shot.rootPx;
      record.anchors = shot.anchors;
      record.outbound = shot.outbound;
      record.content = shot.content;
      record.layout = shot.layout;
      // Kept for the record, no longer a pass/fail. Requiring it to match forbade adding
      // anything at all, which is the opposite of what a redesign of a bare page has to do.
      record.structureHash = createHash('sha256').update(shot.structure).digest('hex');
    }
    record.direction[dir] = { overflow: shot.geometry.overflow, collisions: 0 };
  }

  /**
   * The empty state, driven rather than hoped for.
   *
   * The most-skipped surface in any redesign, because you have to deliberately push the app
   * into it to ever see it — and a list page with no data renders as blank space, which
   * nobody can tell apart from broken.
   *
   * `emptyWhen` on the inventory row names the request to starve. Without it the state is
   * recorded as **not probed**, never as passing: a check that quietly reports success for
   * the thing it did not look at is worse than no check.
   */
  if (item.emptyWhen) {
    const probe = await browser.newPage();
    try {
      await probe.setViewport({ width: cfg.viewport?.width ?? 1440, height: cfg.viewport?.height ?? 900 });
      await probe.setRequestInterception(true);
      const match = new RegExp(item.emptyWhen);
      probe.on('request', (req) => {
        // Reads are starved; anything that writes is aborted outright. Behaviour is frozen,
        // and a probe that POSTs while nobody is watching is not a measurement.
        if (req.method() !== 'GET') return req.abort();
        if (match.test(req.url())) {
          return req.respond({ status: 200, contentType: 'application/json', body: '[]' });
        }
        return req.continue();
      });
      await probe.goto(new URL(item.path, cfg.baseUrl).href, { waitUntil: 'networkidle0' });
      await probe.screenshot({ path: path.join(out, 'empty.png'), fullPage: true });
      record.emptyState = await probe.evaluate(() => {
        const main = document.querySelector('main, [role="main"]') || document.body;
        const text = (main.innerText || '').replace(/\s+/g, ' ').trim();
        return {
          probed: true,
          text: text.length,
          hasImage: !!main.querySelector('img, svg, [role="img"]'),
          hasHeading: !!main.querySelector('h1, h2, h3'),
          actions: main.querySelectorAll('a[href], button').length,
        };
      });
    } catch (err) {
      // A probe that failed is not a page that passed.
      record.emptyState = { probed: false, why: String(err.message ?? err).slice(0, 120) };
    } finally {
      await probe.close();
    }
  } else if (record.content?.collections) {
    record.emptyState = { probed: false, why: 'no emptyWhen on this row — the empty state was never rendered' };
  }

  fs.writeFileSync(path.join(out, 'fingerprint.json'), JSON.stringify(record, null, 2) + '\n');
  results.push(`${item.id}  ${Object.keys(record.styles).length} roles`);
  await page.close();
}

await browser.close();
console.log(`\n  captured ${phase}: ${results.length} surfaces\n${results.map((r) => '    ' + r).join('\n')}\n`);
