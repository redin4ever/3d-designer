#!/usr/bin/env node
/**
 * The redesign gate. Exit 0 means the redesign is complete; anything else means it is not.
 *
 *   node .redesign/check.mjs [--json]
 *
 * The agent running the redesign may not declare the work finished while this exits
 * non-zero. It writes `verified` into the inventory itself, from measurements — that field
 * is not the agent's to set.
 *
 * Config: .redesign/config.json
 *   { "root": "src", "tokenFile": "src/styles/tokens.css", "threshold": 0.6,
 *     "testCommand": "npm test", "typeScale": ["var(", "clamp("], "exclude": [],
 *     "coverageFloor": 0.9, "rootPx": 16 }
 */

import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';
import { createHash } from 'node:crypto';

import { sourceFiles, scan, quarantineImporters, RAW_COLOUR, PHYSICAL_DIRECTION, LIBRARY_PALETTE, offScaleSize } from './lib/scan.mjs';
import { judge } from './lib/evidence.mjs';
import { canonical } from './lib/canonical.mjs';
import { startGate, readJson } from './lib/gate-core.mjs';

const DIR = '.redesign';

const gate = startGate(DIR, { setup: "run the redesign skill's Phase 0 first" });
const cfg = gate.config();
const fail = (...a) => gate.fail(...a);

// ─── tokens declared ────────────────────────────────────────────────────────────────
const tokenText = fs.existsSync(cfg.tokenFile) ? fs.readFileSync(cfg.tokenFile, 'utf8') : '';
if (!tokenText) fail('tokens', `token file missing: ${cfg.tokenFile}`);

// Declared values, in every form a stylesheet writes them — then canonicalised into the
// same space as the captured computed values, which are always rgb()/px.
// The same colour functions RAW_COLOUR knows. When this list was shorter than that one, a
// token file written in oklch() — which is what most current systems emit — declared nothing
// this half of the gate could see, scored 0% coverage, and could never pass.
const DECLARED = /(?<![\w-])(#[0-9a-fA-F]{3,8}|-?\d*\.?\d+(?:px|rem|em))(?![\w-])|(?:rgba?|hsla?|hwb|oklab|oklch)\s*\([^)]*\)/g;
const tokens = new Set(
  [...tokenText.matchAll(DECLARED)]
    .map((m) => canonical(m[1] ?? m[0], { rootPx: cfg.rootPx ?? 16 }))
    .filter(Boolean)
);

// ─── negative checks ────────────────────────────────────────────────────────────────
const files = sourceFiles(cfg.root ?? 'src');
const ignore = [cfg.tokenFile, ...(cfg.exclude ?? [])];

const raw = scan(files, [RAW_COLOUR, offScaleSize(cfg.typeScale ?? ['var('])], { ignore });
if (raw.length) fail('no-raw-values', `${raw.length} raw values outside the token file`, raw.slice(0, 15));

const physical = scan(files, [PHYSICAL_DIRECTION], { ignore });
if (physical.length) fail('direction', `${physical.length} physical direction properties`, physical.slice(0, 15));

// Charts and maps keep their old colours without a single colour appearing in the diff,
// because what they name is a palette rather than a value. See LIBRARY_PALETTE.
const borrowed = scan(files, [LIBRARY_PALETTE], { ignore });
if (borrowed.length) {
  fail('library-palette', `${borrowed.length} chart palette(s) or basemap(s) still chosen by a library`, borrowed.slice(0, 15));
}

const quarantined = readJson(path.join(DIR, 'quarantine.json'), { files: [] }).files ?? [];
const stillImported = quarantineImporters(files, quarantined);
if (stillImported.length) fail('quarantine', `${stillImported.length} imports of rival themes`, stillImported.slice(0, 15));

// ─── behaviour freeze ───────────────────────────────────────────────────────────────
const frozen = readJson(path.join(DIR, 'behaviour.json'), { tests: {} });
const drifted = Object.entries(frozen.tests ?? {}).filter(([f, h]) => {
  if (!fs.existsSync(f)) return true;
  return createHash('sha256').update(fs.readFileSync(f)).digest('hex') !== h;
});
if (drifted.length) {
  fail('behaviour-freeze', 'test files changed — a redesign must not change behaviour', drifted.map(([f]) => ({ file: f })));
}
if (cfg.testCommand) {
  // A chatty suite that passes must not be reported as red: with the default 1MB buffer,
  // execSync throws ENOBUFS on output volume alone. And a watch-mode command would
  // otherwise wedge the gate — which, unattended, is indistinguishable from a hang.
  try {
    execSync(cfg.testCommand, {
      stdio: 'pipe',
      maxBuffer: 64 * 1024 * 1024,
      timeout: (cfg.testTimeoutSec ?? 600) * 1000,
    });
  } catch (err) {
    fail('behaviour-freeze', err.signal === 'SIGTERM' || err.code === 'ETIMEDOUT'
      ? `suite did not finish within ${cfg.testTimeoutSec ?? 600}s — is it in watch mode? ${cfg.testCommand}`
      : `suite is not green: ${cfg.testCommand}`);
  }
}

// ─── is the evidence current? ───────────────────────────────────────────────────────
// Every verdict below comes out of after/<id>/fingerprint.json, never out of the source.
// So a capture older than the last edit is the gate judging work it has not seen: you fix a
// page, re-run, and the verdict does not move. That reads as "my fix did nothing" and is the
// quietest failure available here, which is why it is checked rather than trusted.
const newestSource = files.reduce((t, f) => {
  try { return Math.max(t, fs.statSync(f).mtimeMs); } catch { return t; }
}, 0);

const staleCaptures = [];
for (const dir of ['after']) {
  const base = path.join(DIR, dir);
  if (!fs.existsSync(base)) continue;
  for (const id of fs.readdirSync(base)) {
    const f = path.join(base, id, 'fingerprint.json');
    if (!fs.existsSync(f)) continue;
    if (fs.statSync(f).mtimeMs < newestSource) staleCaptures.push({ file: `${dir}/${id}`, text: 'captured before your latest edit' });
  }
}
if (staleCaptures.length) {
  fail('stale-capture',
    `${staleCaptures.length} capture(s) predate the source — re-run "node ${DIR}/fingerprint.mjs after" before judging`,
    staleCaptures.slice(0, 10));
}

// ─── coverage, from evidence ────────────────────────────────────────────────────────
// `workList` refuses an absent or empty inventory rather than reading it as finished — the
// guard lives in gate-core because this gate once printed "complete" for an empty one, then
// wrote that empty list back over the real one so every later run agreed.
const inventory = gate.workList('inventory.json', 'items', { label: 'surfaces' });

// The inventory cannot be shortened.
//
// The skill claims this in four places ("generated; you cannot shorten it", "regenerated,
// not merged, on every check run"). None of it was true: the gate read the file as given, so
// deleting the row for a page you had not done took the gate from "1 of 2 not verified" to
// "1/1 verified ✓". The one work-list guarantee the skill repeats most was the one it did
// not have.
//
// Regenerating here would mean re-walking the router from inside the gate. Recording the
// roster instead costs one file and catches the same thing: ids may be added, never dropped.
const rosterPath = path.join(DIR, 'roster.json');
const ids = inventory.items.map((i) => i.id).filter(Boolean);
const roster = readJson(rosterPath);

if (!roster) {
  fs.writeFileSync(rosterPath, JSON.stringify({ ids, note: 'ids seen by the gate; rows may be added, never removed' }, null, 2) + '\n');
} else {
  const dropped = (roster.ids ?? []).filter((id) => !ids.includes(id));
  if (dropped.length) {
    fail('inventory', `${dropped.length} surface(s) disappeared from the inventory`,
      dropped.slice(0, 15).map((id) => ({ file: id, text: 'was in the work list and is not now' })));
  }
  const added = ids.filter((id) => !(roster.ids ?? []).includes(id));
  if (added.length) {
    fs.writeFileSync(rosterPath, JSON.stringify({ ids: [...new Set([...(roster.ids ?? []), ...ids])], note: roster.note }, null, 2) + '\n');
  }
}

const unverified = [];
for (const item of inventory.items) {
  const { status, evidence, reasons } = judge(item, {
    dir: DIR, tokens, threshold: cfg.threshold ?? 0.6,
    coverageFloor: cfg.coverageFloor ?? 0.9, rootPx: cfg.rootPx ?? 16,
  });
  item.status = status;              // the gate owns this field, not the agent
  item.evidence = { ...evidence, reasons };
  if (status !== 'verified') unverified.push({ file: item.path ?? item.id, text: reasons[0] });
}
fs.writeFileSync(path.join(DIR, 'inventory.json'), JSON.stringify(inventory, null, 2) + '\n');

if (unverified.length) {
  fail('coverage', `${unverified.length} of ${inventory.items.length} surfaces not verified`, unverified.slice(0, 20));
}

// ─── can you get there from here? ───────────────────────────────────────────────────
// The skill restyled pages one at a time and never once looked at how they connect. A
// beautifully redesigned page nothing links to is work nobody will find, and a page with no
// way onward is a dead end however good it looks. Both are computable from the captures
// already taken — every page records where it can send you.
const captured = (id) => readJson(path.join(DIR, 'after', id, 'fingerprint.json'));
const reachable = new Set();
for (const item of inventory.items) {
  for (const link of captured(item.id)?.outbound ?? []) {
    reachable.add(link.split(' ')[1]);                  // "region path name"
  }
}

if (reachable.size) {
  const norm = (p) => String(p ?? '').split('?')[0].replace(/\/\d+(?=\/|$)/g, '/:id').replace(/\/$/, '') || '/';
  const shots = inventory.items.map((i) => [i, captured(i.id)]).filter(([, s]) => s);

  // Chrome is computed, not hand-listed. A link on nearly every page is the shell, wherever
  // its markup puts it — keying off <nav> alone missed sidebars built from plain divs and
  // counted them as this page's own onward links.
  const seen = new Map();
  for (const [, shot] of shots) {
    for (const target of new Set((shot.outbound ?? []).map((l) => l.split(' ')[1]))) {
      seen.set(target, (seen.get(target) ?? 0) + 1);
    }
  }
  const chrome = new Set([...seen.entries()]
    .filter(([, n]) => shots.length >= 3 && n / shots.length >= 0.8)
    .map(([t]) => t));

  const routes = new Set(inventory.items.filter((i) => i.path).map((i) => norm(i.path)));
  const declared = new Set((cfg.entryPoints ?? []).map(norm));

  const orphans = [];
  const deadEnds = [];
  const unlabelledNav = [];
  const noWayUp = [];

  for (const [item, shot] of shots) {
    if (!item.path) continue;
    const here = norm(item.path);
    const targets = new Set((shot.outbound ?? []).map((l) => l.split(' ')[1]));

    // A route nothing links to. Declared entry points are excused in config; anything else
    // needs a `reachedBy` on the row saying how you get there — a POST redirect, a role, a
    // mailed link. A silent ignore list would hide the ones that matter.
    //
    // An anonymous crawl cannot see behind a login, so on an app with auth the honest fix is
    // to crawl per role rather than to widen the exclusions. The message says so.
    if (here !== '/' && !reachable.has(here) && !declared.has(here) && !item.reachedBy) {
      orphans.push({ file: item.path, text: 'nothing links here — add a link, or set reachedBy / config.entryPoints with the reason' });
    }

    // A form IS somewhere to go: submitting it is the onward action. Without this every
    // form page in the product reads as a dead end, which would make the check noise.
    const onwardLinks = [...targets].filter((t) => !chrome.has(t) && t !== here).length;
    const canAct = (shot.anchors?.submits ?? 0) > 0 || (shot.anchors?.forms ?? []).length > 0;
    if (!onwardLinks && !canAct) {
      deadEnds.push({ file: item.path, text: 'nothing to do or follow from here that is not the site shell' });
    }

    if (shot.content?.navCurrent === false && (shot.outbound ?? []).some((l) => l.startsWith('nav '))) {
      unlabelledNav.push({ file: item.path, text: 'the nav does not show where you are' });
    }

    // Somewhere deep with no way up. Purely structural: the ancestors it checks are routes
    // that exist in the inventory, so a flat URL scheme simply reports nothing rather than
    // reporting wrongly.
    const parts = here.split('/').filter(Boolean);
    if (parts.length >= 2) {
      const ancestors = parts.slice(0, -1).map((_, i) => `/${parts.slice(0, i + 1).join('/')}`).filter((a) => routes.has(a));
      if (ancestors.length && !ancestors.some((a) => targets.has(a))) {
        noWayUp.push({ file: item.path, text: `no link up to ${ancestors[ancestors.length - 1]}` });
      }
    }
  }

  if (orphans.length) fail('wayfinding', `${orphans.length} route(s) nothing links to`, orphans.slice(0, 12));
  if (deadEnds.length) fail('wayfinding', `${deadEnds.length} page(s) are dead ends`, deadEnds.slice(0, 12));
  if (noWayUp.length) fail('wayfinding', `${noWayUp.length} deep page(s) with no way back up`, noWayUp.slice(0, 12));
  if (unlabelledNav.length) {
    fail('wayfinding', `${unlabelledNav.length} page(s) where the nav does not mark the current item`, unlabelledNav.slice(0, 12));
  }
}

// ─── report ─────────────────────────────────────────────────────────────────────────
const verified = inventory.items.length - unverified.length;
// Surfaces with no page to render — emails, print, images, icon sets, canvas charts — are
// judged from source. Saying "verified against its baseline" for those would claim a render
// nobody looked at, which is the overclaim these gates exist to avoid.
const sourceOnly = inventory.items.filter((i) => i.evidence?.judged === 'source-only').length;

gate.finish({
  headline: `redesign gate — ${verified}/${inventory.items.length} surfaces verified`
    + (sourceOnly ? `, ${sourceOnly} judged from source` : ''),
  done: sourceOnly
    ? [
      `complete — ${verified - sourceOnly} surface(s) verified against their baseline.`,
      `${sourceOnly} had no page to render (email, print, image, icon set, canvas) and were`,
      'judged from source only: their files were checked, their pixels were not.',
    ]
    : 'complete — every surface verified against its baseline',
  extra: { verified, sourceOnly, total: inventory.items.length },
});
