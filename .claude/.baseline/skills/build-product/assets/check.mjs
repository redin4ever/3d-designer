#!/usr/bin/env node
/**
 * The build-product gate. Exit 0 means the run's own exit conditions hold.
 *
 *   node .pipeline/check.mjs [--json] [--phase 4|5]
 *
 * Until this existed, build-product was the only one of the three skills whose completion
 * was self-reported: phase-4 and phase-5 end in a list of conditions, and nothing read them.
 * It is also the skill with the longest unattended stretch and the most agents — the place
 * where a confident wrong report costs the most.
 *
 * Every check below verifies a sentence the skill already writes. It adds no new standard;
 * where the docs are quiet, so is this.
 *
 * What it deliberately cannot judge: whether the product is any good, whether the gate
 * questions were the right ones, or whether a module does what was asked rather than what
 * its tests assert. Those are the module reviewer's and the user's. A green gate here means
 * "the run did what it says it did", not "the product is right".
 *
 * Config: .pipeline/gate.json (optional — defaults are for an ordinary node project)
 *   { "backend": "npm run test:backend", "frontend": "npm run test:frontend",
 *     "skipSuites": false, "hardCaps": { "source": 1000, "test": 1500, "markdown": 600 } }
 */

import fs from 'node:fs';
import path from 'node:path';
import { execSync, execFileSync } from 'node:child_process';

import { startGate, readJson } from './lib/gate-core.mjs';

const DIR = '.pipeline';
const ROOT = process.cwd();

const gate = startGate(DIR, { setup: "run the build-product skill's Phase 0 first" });
const cfg = readJson(path.join(DIR, 'gate.json')) ?? {};
const state = gate.config('state.json');
const modules = gate.workList('modules.json', 'modules', 'modules');

const arg = (name) => {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? null : process.argv[i + 1];
};
/** Phase 4 conditions are a subset of phase 5's; default to judging everything. */
const upto = Number(arg('phase') ?? state.phase ?? 5);

const hasGit = (() => {
  try { execFileSync('git', ['rev-parse', '--git-dir'], { cwd: ROOT, stdio: 'ignore' }); return true; }
  catch { return false; }
})();

// ─── modules reached a verdict ──────────────────────────────────────────────────────
// "status advances on evidence" (rules/resilience.md) — so the gate reads the manifest
// rather than any agent's report of it. `failed` is an allowed outcome, quarantined and
// carried to the gate; what is not allowed is a module still sitting at planned or red.
const byStatus = (s) => modules.modules.filter((m) => m.status === s);
const unfinished = modules.modules.filter((m) => !['green', 'failed'].includes(m.status));
if (unfinished.length) {
  gate.fail('modules', `${unfinished.length} module(s) never reached green or failed`,
    unfinished.map((m) => ({ file: m.id, text: `status: ${m.status ?? '(none)'}` })));
}
const quarantined = byStatus('failed');
if (quarantined.length && !quarantined.every((m) => m.reason)) {
  gate.fail('modules', 'a quarantined module has no reason recorded',
    quarantined.filter((m) => !m.reason).map((m) => ({ file: m.id })));
}

// ─── every unit that started, finished ──────────────────────────────────────────────
// A `start` with no `end` is the signature of an agent that died mid-flight
// (rules/resilience.md). Silence and success are the same shape without this.
const journalPath = path.join(DIR, 'journal.jsonl');
if (fs.existsSync(journalPath)) {
  // Keyed on the unit, not on unit+attempt. Rule 6 retries a dead unit up to twice, and the
  // `end` line it documents carries no `attempt` — so keying on the pair made the *successful
  // retry* the thing left open forever: the end closed attempt 1, and attempt 2 stayed dangling.
  // Following the documentation produced a gate that could never go green after any death.
  const open = new Map();
  const ended = new Set();
  for (const line of fs.readFileSync(journalPath, 'utf8').split('\n').filter(Boolean)) {
    let e;
    try { e = JSON.parse(line); } catch { continue; }
    if (e.t === 'start') { if (!ended.has(e.unit)) open.set(e.unit, e); }
    else if (e.t === 'end') { ended.add(e.unit); open.delete(e.unit); }
  }

  // A unit whose module was quarantined is accounted for: `failed` with a reason is a legal
  // outcome three lines above, and it would be incoherent for the same death to be legal
  // there and fatal here. What stays fatal is a unit nothing mentions again.
  const quarantinedIds = new Set(quarantined.map((m) => m.id));
  const stillOpen = [...open.values()].filter((e) => {
    const id = String(e.unit ?? '').split(':').pop();
    return !quarantinedIds.has(id);
  });

  if (stillOpen.length) {
    gate.fail('journal', `${stillOpen.length} unit(s) started and never ended — treat as died, not done`,
      stillOpen.slice(0, 10).map((e) => ({ file: e.unit, text: `agent: ${e.agent ?? '?'}` })));
  }
} else {
  gate.fail('journal', `no ${DIR}/journal.jsonl — nothing recorded what ran, so nothing can be recovered`);
}

// ─── tests came first ───────────────────────────────────────────────────────────────
// phase-4 calls the RED commit "the evidence the tests were real". This is where it is
// read: a module whose tests arrived after its implementation was not built test-first,
// whatever the suite reports now.
if (hasGit && upto >= 5) {
  // Read the subjects and match here rather than with --grep: git's --grep is POSIX regex,
  // where the parens in `test(orders):` mean something different than they do in JS, and
  // the check silently matched nothing.
  // Compared by position in the log, not by timestamp. `%ct` is second-resolution, so two
  // commits made in the same second look simultaneous — and commit dates can be rewritten
  // anyway. Order is what "before" actually means here.
  let subjects = [];
  try {
    subjects = execFileSync('git', ['log', '--format=%s'], { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })
      .split('\n').filter(Boolean);          // newest first
  } catch { subjects = []; }

  /**
   * Index of the newest `<type>(<module>):` commit — lower is newer. -1 if absent.
   *
   * The scope is required. It used to be optional, which broke the check both ways: one
   * unscoped `test:` commit matched *every* module, so a cross-cutting test commit reported
   * every module as built implementation-first; and an unscoped `feat:` at the tip matched a
   * module that genuinely had no test commit, so a module built implementation-first passed.
   * A check that can be defeated by a commit message is not evidence of anything.
   */
  const newestIndex = (type, id) => {
    const re = new RegExp(`^${type}\\(${id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\)\\s*:`);
    return subjects.findIndex((s) => re.test(s));
  };

  const late = [];
  for (const m of byStatus('green')) {
    const red = newestIndex('test', m.id);
    const green = newestIndex('feat', m.id);
    if (red === -1) late.push({ file: m.id, text: 'no test: commit — cannot show the tests could fail' });
    else if (green !== -1 && red < green) late.push({ file: m.id, text: 'tests committed after the implementation' });
  }
  if (late.length) {
    gate.fail('tests-first', `${late.length} module(s) have no evidence the tests could ever have failed`, late);
  }
}

// ─── nothing over a hard cap ────────────────────────────────────────────────────────
// rules/modularity.md: "At the end of every implementation phase, no file may exceed a
// hard cap." The hook that reports this during a phase is advisory by design, so the
// end-of-phase half has to live somewhere that can fail.
const CAPS = { source: 1000, test: 1500, markdown: 600, ...(cfg.hardCaps ?? {}) };
const SKIP = new Set(['node_modules', '.git', 'dist', 'build', '.next', 'coverage', '.pipeline']);
const KIND = (f) => {
  if (/\.(md|mdx)$/.test(f)) return 'markdown';
  if (/\.(test|spec)\.[jt]sx?$/.test(f)) return 'test';
  return /\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|rb|java|kt|swift|php|cs|vue|svelte|css|scss)$/.test(f) ? 'source' : null;
};
const over = [];
const walk = (d) => {
  let entries;
  try { entries = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
  for (const e of entries) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) { if (!SKIP.has(e.name)) walk(p); continue; }
    const kind = KIND(e.name);
    if (!kind) continue;
    const lines = fs.readFileSync(p, 'utf8').split('\n').length;
    if (lines > CAPS[kind]) over.push({ file: path.relative(ROOT, p), text: `${lines} lines, cap ${CAPS[kind]}` });
  }
};
walk(ROOT);
if (over.length) {
  gate.fail('file-size', `${over.length} file(s) over a hard cap (rules/modularity.md)`, over.slice(0, 15));
}

// ─── the decisions are on disk ──────────────────────────────────────────────────────
// A build is meant to be reconstructable from its decisions rather than from the
// conversation. Gate B only exists on pass 2.
const required = [
  ['docs/decisions/gate-A.md', 'every pre-build decision, with the user\'s verbatim notes'],
  ['docs/ASSUMPTIONS.md', 'what was decided without the user'],
  [`${DIR}/question-backlog.json`, 'what is queued for the next gate'],
];
if (state.pass >= 2) required.push(['docs/decisions/gate-B.md', "the last gate's decisions"]);
// `status: finished` only — NOT `final`. `final: true` is set at the *start* of the last
// pass (phase-7-gate-b.md), and the summary is written at its *end*, after both gate
// invocations. Requiring it on `final` made every gate of the final pass fail on a file that
// by definition does not exist yet: the run could not finish because it had not finished.
if (state.status === 'finished') {
  required.push(['docs/PIPELINE-SUMMARY.md', 'what the run produced']);
}
const missing = required.filter(([f]) => !fs.existsSync(path.join(ROOT, f)));
if (missing.length) {
  gate.fail('record', `${missing.length} required record(s) missing`,
    missing.map(([file, why]) => ({ file, text: why })));
}

// ─── both suites ────────────────────────────────────────────────────────────────────
// Last, because it is the slow one, and a run that fails everything above does not need
// to wait for it to be told so.
if (!cfg.skipSuites && upto >= 5) {
  for (const [name, cmd] of [['backend', cfg.backend ?? 'npm run test:backend'],
    ['frontend', cfg.frontend ?? 'npm run test:frontend']]) {
    try {
      execSync(cmd, { cwd: ROOT, stdio: 'pipe', maxBuffer: 64 * 1024 * 1024, timeout: (cfg.testTimeoutSec ?? 900) * 1000 });
    } catch (err) {
      gate.fail('suites', err.signal === 'SIGTERM' || err.code === 'ETIMEDOUT'
        ? `${name} suite did not finish in ${cfg.testTimeoutSec ?? 900}s — watch mode? ${cmd}`
        : `${name} suite is not green: ${cmd}`);
    }
  }
}

const green = byStatus('green').length;
gate.finish({
  headline: `build-product gate — ${green}/${modules.modules.length} module(s) green`
    + (quarantined.length ? `, ${quarantined.length} quarantined` : '')
    + `  ·  phase ${state.phase ?? '?'}, pass ${state.pass ?? '?'}`,
  done: 'the run did what it says it did',
  extra: { green, quarantined: quarantined.length, total: modules.modules.length },
});
