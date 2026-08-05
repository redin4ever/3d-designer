#!/usr/bin/env node
/**
 * Keep an unattended run going — for every skill in this family, not just the pipeline.
 *
 * Wired to the `Stop` event. When a skill's state file says a run is mid-flight and not at
 * a gate, this asks Claude to carry on instead of handing control back to somebody who is
 * not there.
 *
 * (The filename says `pipeline` for one reason only: existing installs have it wired into
 * settings.json under that name, and renaming it would leave those pointing at a file that
 * no longer exists — a hook that errors on every turn end. The contents are general.)
 *
 * ## What this can and cannot do
 *
 * It can nudge **once per turn**, and that is a ceiling, not a tuning choice:
 *
 *   "Never block when `stop_hook_active` is `true`." — the Stop hook documentation
 *
 * and the harness has no infinite-loop backstop of its own; it relies on hooks respecting
 * that flag. So a Stop hook is a safety net, never the engine that drives a run through
 * nine phases. What drives the run is the skill saying, at every phase exit, which file to
 * open next — this only catches the turn where that failed.
 *
 * Anyone tempted to "fix" the one-nudge limit by blocking through `stop_hook_active` should
 * read that line again. A trapped session is far worse than a paused one.
 *
 * ## Why a run stops when it should not
 *
 * Usually not a lapse of will. It is spawning a wave of agents with `run_in_background:
 * true`, which hands the turn away and leaves literally nothing to do but wait. Prose
 * cannot fix a situation where stopping is the only legal move, so the nudge names that
 * case explicitly.
 *
 * Fails open on everything uncertain: no state file, unreadable JSON, an unrecognised
 * phase, a gate, a finished run, or three nudges already spent in this phase.
 *
 * CANONICAL COPY: plugins/_shared/pipeline-continue.mjs — vendored into each skill's
 * hooks/ by `npm run sync-shared`, and `test/shared-drift.test.mjs` fails if they diverge.
 */

import fs from 'node:fs';
import path from 'node:path';

/** Let the turn end. Every uncertain path leads here. */
const allow = () => process.exit(0);

/** Ask Claude to continue, and say what with. */
const keepGoing = (reason) => {
  process.stdout.write(JSON.stringify({ decision: 'block', reason }));
  process.exit(0);
};

const readStdin = () =>
  new Promise((resolve) => {
    let raw = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => { raw += c; });
    process.stdin.on('end', () => resolve(raw));
    process.stdin.on('error', () => resolve(''));
    setTimeout(() => resolve(raw), 2000).unref?.();
  });

/**
 * Every skill that runs unattended, and the phases where stopping is the whole point.
 *
 * A skill appears here only if it writes `<dir>/state.json` with a `phase`. Three of these
 * did not, which is why three of the four skills had no protection at all: the hook was
 * build-product's, keyed to `.pipeline/`, and nothing else was ever looked at.
 */
const RUNS = [
  {
    dir: '.pipeline',
    skill: 'build-product',
    gates: new Set([3, 7]),
    /** Written once, at the end, and never removed — true exactly when the run is over. */
    done: 'docs/PIPELINE-SUMMARY.md',
    next: {
      0: 'read references/pipeline-state.md and begin Phase 1',
      1: 'open references/phase-2-design.md and begin Phase 2',
      2: 'open references/phase-3-gate-a.md and run the Gate A waves',
      4: 'open references/phase-5-qa.md and begin Phase 5',
      5: 'open references/phase-6-review.md and begin Phase 6 (on pass 2, write docs/PIPELINE-SUMMARY.md and end the run)',
      6: 'open references/phase-7-gate-b.md and run the Gate B waves',
      8: 'finish the second build-and-QA pass, then write docs/PIPELINE-SUMMARY.md',
    },
  },
  {
    dir: '.feature',
    skill: 'add-feature',
    gates: new Set([2]),
    next: {
      0: 'open references/phase-1-trace.md and begin the trace',
      1: 'open references/phase-2-questions.md and run the question waves',
      3: 'open references/phase-4-build.md and build the units',
      4: 'open references/phase-5-verify.md and run node .feature/check.mjs',
      5: 'fix what the gate named and run it again, until it exits 0',
    },
  },
  {
    dir: '.redesign',
    skill: 'redesign',
    gates: new Set([2]),
    next: {
      0: 'open references/phase-1-inventory.md and generate the inventory',
      1: 'open references/phase-2-gate.md and run the gate waves',
      3: 'open references/phase-4-sweep.md and sweep the next inventory item',
      4: 'open references/phase-5-direction.md and do the direction pass',
      5: 'open references/phase-6-verify.md and run node .redesign/check.mjs',
      6: 'fix what the gate named and run it again, until it exits 0',
    },
  },
  {
    dir: '.guides',
    skill: 'codebase-guides',
    gates: new Set(),                       // no gate: this skill never asks anything
    next: {
      0: 'open references/scale.md and scope the areas',
      1: 'open references/evidence.md and trace the next area',
      5: 'open references/probes.md and prove each recipe',
      6: 'run node .guides/check.mjs and fix what it names',
      7: 'open references/wiring.md and wire the guides into CLAUDE.md',
    },
  },
];

/** A run that is over, waiting on a person, or stopped for a reason the rules allow. */
const DONE = new Set([
  'finished', 'complete', 'completed', 'done', 'ended',
  'awaiting-user', 'awaiting-gate', 'escalated', 'blocked', 'failed', 'aborted',
]);

/** Three nudges per phase, then let it go — something is wrong that this cannot fix. */
const LIMIT = 3;

const bump = (dir, phase) => {
  const file = path.join(dir, 'continue-guard.json');
  let seen = { phase: null, n: 0 };
  try { seen = JSON.parse(fs.readFileSync(file, 'utf8')); } catch { /* first time */ }
  const n = seen.phase === phase ? Number(seen.n) + 1 : 1;
  try { fs.writeFileSync(file, JSON.stringify({ phase, n }) + '\n'); } catch { /* best effort */ }
  return n;
};

/** The first skill with a run in progress here. Null when none of them is running. */
const findRun = (root) => {
  for (const run of RUNS) {
    const dir = path.join(root, run.dir);
    let state;
    try { state = JSON.parse(fs.readFileSync(path.join(dir, 'state.json'), 'utf8')); } catch { continue; }
    const phase = Number(state.phase);
    if (!Number.isFinite(phase)) continue;
    yieldable: {
      if (run.gates.has(phase)) break yieldable;                       // a gate: stopping is correct
      if (DONE.has(String(state.status ?? '').toLowerCase())) break yieldable;
      if (run.done && fs.existsSync(path.join(root, run.done))) break yieldable;
      return { run, dir, phase, state };
    }
  }
  return null;
};

try {
  const input = JSON.parse((await readStdin()) || '{}');

  // Documented contract: never block while a previous block is still being worked through.
  // The harness has no loop breaker of its own, so this flag is the only one there is.
  if (input.stop_hook_active) allow();

  const root = input.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const found = findRun(root);
  if (!found) allow();

  const { run, dir, phase } = found;
  const n = bump(dir, phase);
  if (n > LIMIT) allow();                        // nudged enough; never trap anyone

  keepGoing(
    `${run.skill}: phase ${phase} is unattended — ${run.dir}/state.json says the run is `
    + `mid-flight and no gate has been reached. Nobody is waiting to read a phase report.\n\n`
    + `Next: ${run.next[phase] ?? `read ${run.dir}/state.json and continue from the recorded phase`}.\n\n`
    + `If you stopped because a wave of agents is running in the background, that is the bug: `
    + `respawn it with run_in_background: false so the wave returns into this turn. `
    + `Concurrency comes from many tool calls in one message, not from backgrounding.\n\n`
    + `If continuing would be unsafe or irreversible, that is an escalation — set `
    + `"status": "escalated" in ${run.dir}/state.json and say so plainly. (Nudge ${n}/${LIMIT}.)`
  );
} catch {
  allow();
}
