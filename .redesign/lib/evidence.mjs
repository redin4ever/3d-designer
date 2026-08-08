/**
 * Turns captured fingerprints into a per-item verdict.
 *
 * The agent may set an item to `redesigned`. Only this module's verdict promotes it to
 * `verified`, and it does so from measurements — so "I redesigned it" is never the thing
 * being trusted.
 */

import fs from 'node:fs';
import path from 'node:path';

import { canonicalSet } from './canonical.mjs';

const read = (p) => (fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : null);

/**
 * Proportion of style declarations that differ between two fingerprints.
 *
 * Deliberately proportional, not magnitude-based: changing one value dramatically must not
 * be able to carry a page, because that is exactly the shortcut this check exists to stop.
 *
 * Measured over the *declarations*, not over the selector-keyed blocks. Keyed by selector,
 * renaming `.old-card` to `.new-card` changed every key and scored 100% changed with not one
 * value different — so a find-and-replace on class names passed the one measurement the
 * whole skill is built on. Tailwind and CSS modules rename classes constantly, which is the
 * common case rather than the adversarial one.
 *
 * A `prop:value` multiset has no such hole: it counts what the page actually looks like.
 */
const declarations = (styles) => {
  const bag = new Map();
  for (const block of Object.values(styles ?? {})) {
    if (!block || typeof block !== 'object') continue;
    for (const [prop, value] of Object.entries(block)) {
      const key = `${prop}:${value}`;
      bag.set(key, (bag.get(key) ?? 0) + 1);
    }
  }
  return bag;
};

export const distance = (before, after) => {
  const a = declarations(before);
  const b = declarations(after);
  const keys = new Set([...a.keys(), ...b.keys()]);
  if (keys.size === 0) return 0;

  // What survived, over the larger of the two pages. Counting a changed value as both a
  // removal and an addition would score "half the declarations changed" as 0.67 and slip it
  // past a 0.6 threshold — inflation in the one direction a completeness check must not
  // drift. Counts are kept, so removing three of five identical buttons registers.
  let matched = 0;
  let sizeA = 0;
  let sizeB = 0;
  for (const k of keys) {
    const x = a.get(k) ?? 0;
    const y = b.get(k) ?? 0;
    matched += Math.min(x, y);
    sizeA += x;
    sizeB += y;
  }
  const total = Math.max(sizeA, sizeB);
  return total === 0 ? 0 : 1 - matched / total;
};

/**
 * Every rendered colour/size must resolve to something the token file declares.
 *
 * Both sides are canonicalised first: the token file speaks in `#3366ff` and `0.5rem`, the
 * browser answers in `rgb(51, 102, 255)` and `8px`. Compared raw they never match, and a
 * perfectly tokenised page scored zero — see canonical.mjs.
 *
 * Values no stylesheet declares (`normal` from an unset `gap`, a UA `0px` border) are
 * dropped rather than counted as misses, since no token file could ever cover them.
 */
const tokenCoverage = (after, tokens, rootPx) => {
  const used = canonicalSet([...(after.colours ?? []), ...(after.sizes ?? [])], { rootPx });
  if (used.size === 0) return 1;
  let known = 0;
  for (const v of used) if (tokens.has(v)) known += 1;
  return known / used.size;
};

/**
 * Did anything a person relies on disappear?
 *
 * This replaces the structure-hash equality that used to guarantee safety. That check made
 * breakage impossible by making *addition* impossible too — so a bare page could never
 * become a designed one, which is the whole job. These are supersets instead: a redesign may
 * add a link, a field, a control, a way through. It may remove none of them.
 *
 * Stricter than the old check where it counts, and looser where it was only in the way.
 */
export const lost = (before, after) => {
  const out = [];
  const LABEL = {
    links: 'link(s) to somewhere in this app',
    forms: 'form target(s)',
    controls: 'named input(s)',
    testids: 'test id(s) — something asserts on these',
  };
  for (const key of Object.keys(LABEL)) {
    const had = new Set(before.anchors?.[key] ?? []);
    if (!had.size) continue;
    const has = new Set(after.anchors?.[key] ?? []);
    const gone = [...had].filter((x) => !has.has(x));
    if (gone.length) out.push(`${gone.length} ${LABEL[key]} removed: ${gone.slice(0, 3).join(', ')}`);
  }
  const wasSubmits = before.anchors?.submits ?? 0;
  if ((after.anchors?.submits ?? 0) < wasSubmits) out.push('a submit control was removed');
  return out;
};

/**
 * How much of the ARRANGEMENT moved, as distinct from the paint.
 *
 * "Different, not adjusted" was measured only over style declarations, so a page could clear
 * the threshold with new colours and type while every box stayed exactly where it was — and
 * it still read as the old product. Layout is where a redesign is actually felt: which way
 * the nav runs, how many columns, how wide the measure, where the primary action sits, what
 * order the regions come in.
 */
export const layoutDistance = (before, after) => {
  const a = before.layout;
  const b = after.layout;
  if (!a || !b) return null;                     // captured before this existed

  const facts = [];
  const add = (name, x, y) => facts.push([name, JSON.stringify(x ?? null) !== JSON.stringify(y ?? null)]);

  add('order', a.order, b.order);
  add('columns', a.columns, b.columns);
  add('measure', a.measure, b.measure);
  add('navAxis', a.navAxis, b.navAxis);
  add('primaryAction', a.primaryAction, b.primaryAction);
  add('density', a.density, b.density);
  for (const region of new Set([...Object.keys(a.regions ?? {}), ...Object.keys(b.regions ?? {})])) {
    add(`region:${region}`, a.regions?.[region], b.regions?.[region]);
  }

  const moved = facts.filter(([, changed]) => changed).length;
  return { moved, total: facts.length, ratio: facts.length ? moved / facts.length : 0 };
};

/**
 * Is there anything on this page yet?
 *
 * A page can be perfectly tokenised and still be a wall of unlabelled inputs with no heading,
 * no guidance and no way onward. Counted, not judged — so the gate can say "this is still
 * empty" instead of calling it verified because the colours are right.
 */
export const bareness = (content) => {
  if (!content) return null;
  const missing = [];
  const fields = content.fields ?? 0;

  if (!content.headings?.h1) missing.push('no heading');
  if ((content.text ?? 0) < 200) missing.push('almost no text');
  if (!content.images) missing.push('no imagery of any kind');
  if (!content.onward) missing.push('nothing to click onward to');
  if ((content.landmarks?.length ?? 0) < 2) missing.push('no landmark structure');

  // A *visible* label, not merely an accessible name. `aria-label` satisfies a screen reader
  // and adds no text to the page, so a form can score fully labelled and look exactly as
  // bare as it did. Fall back to the older field when a capture predates this.
  const visible = content.fieldsVisiblyLabelled ?? content.fieldsLabelled ?? 0;
  if (fields > 0 && visible < fields) missing.push(`${fields - visible} field(s) with no visible label`);

  // Grouping is what turns a wall of inputs into a form somebody designed. Only asked of
  // pages long enough to need it — a login form must not be pushed into fieldsets.
  if (fields > 6 && (content.fieldsGrouped ?? 0) / fields < 0.9) {
    missing.push('fields are not grouped under headings');
  }

  if (content.titleIsScaffold) missing.push('the document title is still the scaffold\'s');
  if (content.formsWithoutExit) missing.push(`${content.formsWithoutExit} form(s) with no way out but submit`);

  return { missing, bare: missing.length >= 3 };
};

/**
 * @returns {{status:'verified'|'pending', evidence:object, reasons:string[]}}
 */
export const judge = (item, { dir, tokens, threshold, coverageFloor = 0.9, rootPx = 16, layoutFloor = 0.25 }) => {
  const reasons = [];
  const before = read(path.join(dir, 'baseline', item.id, 'fingerprint.json'));
  const after = read(path.join(dir, 'after', item.id, 'fingerprint.json'));

  // Surfaces a browser cannot be pointed at, and marks a fingerprint cannot describe.
  //
  // These have no `path`, so the capture step skips them — and then they could never be
  // verified, so an inventory containing one could never reach exit 0. The kinds that most
  // need saying out loud (an email, a print stylesheet, an icon set) were the ones that
  // made the gate unreachable.
  //
  // They are judged from the source side instead, and the report says so rather than
  // implying a render was inspected. `sourceFiles` is what the agent already records; the
  // negative checks in check.mjs cover those files like any other.
  const SOURCE_ONLY = new Set(['email', 'print', 'image', 'icon-set']);
  const sourceOnly = SOURCE_ONLY.has(item.kind) || item.renders === 'canvas' || !item.path;

  if (sourceOnly) {
    const evidence = { judged: 'source-only', why: item.kind ?? (item.renders === 'canvas' ? 'canvas' : 'no path to render') };
    if (!(item.sourceFiles ?? []).length) {
      return {
        status: 'pending',
        evidence,
        reasons: ['nothing to judge — a surface with no path needs sourceFiles naming what it is made of'],
      };
    }
    if (item.kind === 'image' && !item.disposition) {
      return { status: 'pending', evidence, reasons: ['no disposition — restyle, regenerate, or keep with a reason'] };
    }
    if (item.disposition === 'keep' && !item.reason) {
      return { status: 'pending', evidence, reasons: ['kept, with no reason recorded'] };
    }
    evidence.sourceFiles = item.sourceFiles.length;
    return { status: 'verified', evidence, reasons: [] };
  }

  if (!before) reasons.push('no baseline captured — cannot prove it changed');
  if (!after) reasons.push('not re-captured after the sweep');

  const evidence = {};
  if (before && after) {
    evidence.distance = Number(distance(before.styles ?? {}, after.styles ?? {}).toFixed(3));
    if (evidence.distance < threshold) {
      reasons.push(`only ${(evidence.distance * 100).toFixed(0)}% of declarations changed, threshold ${(threshold * 100).toFixed(0)}% — adjusted, not redesigned`);
    }

    // The page tells us its own root size when it was captured; config is the fallback.
    evidence.tokenCoverage = Number(tokenCoverage(after, tokens, after.rootPx ?? rootPx).toFixed(3));
    if (evidence.tokenCoverage < coverageFloor) {
      reasons.push(`${((1 - evidence.tokenCoverage) * 100).toFixed(0)}% of rendered values are not tokens (floor ${(coverageFloor * 100).toFixed(0)}%)`);
    }

    // Nothing a person relies on may disappear. Additions are the point.
    const gone = lost(before, after);
    if (gone.length) reasons.push(...gone);

    // The arrangement has to move, not just the paint.
    const moved = layoutDistance(before, after);
    if (moved) {
      evidence.layout = `${moved.moved}/${moved.total}`;
      if (moved.ratio < (layoutFloor ?? 0.25)) {
        reasons.push(`only ${moved.moved} of ${moved.total} layout facts changed — the page was repainted, not rearranged`);
      }
    }

    // A page that started bare has to stop being bare. Restyling an empty page produces a
    // well-tokenised empty page, which is the complaint this exists to answer.
    const was = bareness(before.content);
    const now = bareness(after.content);
    if (was?.bare && now) {
      evidence.substance = { before: was.missing.length, after: now.missing.length };
      // `bareOnPurpose` is the user's answer at the gate, not the agent's escape hatch: a
      // deliberately minimal login or confirmation page is finished, not empty. It is set
      // from Wave 6, and it is the only thing that excuses a page staying bare.
      if (now.bare && !item.bareOnPurpose) {
        reasons.push(`still bare — ${now.missing.join(', ')}. A redesign of an empty page has to put something on it.`);
      }
    }
    if (now && !was?.bare && now.missing.includes('no heading')) {
      reasons.push('no heading on the page');
    }

    // Content running edge to edge is the most reliable amateur tell there is, and it
    // survives any amount of token work untouched. Recorded rather than failed: a dashboard
    // or a data table legitimately goes full width, and only the item's kind knows which
    // this is. It shows in the report so somebody looks.
    if (after.layout?.fullBleed) evidence.fullBleed = true;

    /**
     * The empty state, which is where a working page most looks broken.
     *
     * Three outcomes, and they are deliberately three rather than two: probed and designed,
     * probed and blank, and never probed. Collapsing the third into a pass is the failure
     * this whole family of gates is arranged against — "no findings" and "the finder never
     * ran" have to be distinguishable.
     */
    const empty = after.emptyState;
    if (empty?.probed) {
      const bad = [];
      if (empty.text < 20) bad.push('renders as blank space');
      if (!empty.hasHeading) bad.push('no heading saying what would live here');
      if (!empty.actions) bad.push('no action that would create the first one');
      evidence.emptyState = bad.length ? bad.join('; ') : 'designed';
      if (bad.length) reasons.push(`the empty state ${bad.join(', ')}`);
    } else if (empty) {
      // Reported, not failed: naming `emptyWhen` for every collection is work the user may
      // reasonably not have done, and failing on it would push people to delete the row.
      evidence.emptyState = `not probed — ${empty.why}`;
    }

    for (const [d, geo] of Object.entries(after.direction ?? {})) {
      if (geo.overflow) reasons.push(`overflows in dir="${d}"`);
      if (geo.collisions) reasons.push(`${geo.collisions} overlapping elements in dir="${d}"`);
    }
    evidence.direction = Object.keys(after.direction ?? {});
  }

  return { status: reasons.length === 0 ? 'verified' : 'pending', evidence, reasons };
};
