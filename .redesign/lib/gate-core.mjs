/**
 * The part every completion gate has in common.
 *
 * A gate is the only thing that can say a skill's work is finished, so the ways it can be
 * wrong are worth writing once. Two of them have already happened here:
 *
 *   - An absent or empty work list read as a finished one. The redesign gate fell back to
 *     `{ items: [] }`, checked nothing, printed "complete", exited 0 — and then wrote the
 *     empty list back over the real one, so every later run agreed with it.
 *   - A missing config produced a stack trace rather than the sentence that fixes it.
 *
 * Both are encoded here, so a new gate cannot reintroduce them by omission.
 *
 * Deliberately thin. The interesting half of every gate is its own checks, and this holds
 * none of them — only loading, failure collection, reporting and exit codes. If you find
 * yourself adding a domain concept, it belongs in the gate, not here.
 *
 * CANONICAL COPY: plugins/_shared/gate-core.mjs. The copies under each skill's assets/lib/
 * are vendored, because skills install into separate directories and cannot import across
 * them. `npm run sync-shared` copies it out; `test/shared-drift.test.mjs` fails if they
 * diverge, which is what makes "single source" true rather than aspirational.
 */

import fs from 'node:fs';
import path from 'node:path';

/** Reads JSON, or the fallback. Never throws — a malformed file is the caller's decision. */
export const readJson = (p, fallback = null) => {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return fallback; }
};

/**
 * Exit codes, which are the gate's actual interface:
 *   0  finished
 *   1  not finished, and the report says why
 *   2  cannot judge — nothing was checked, so no verdict is claimed either way
 *
 * 2 matters. It is the difference between "your work is incomplete" and "I was not able to
 * look", and collapsing them into 1 is how a run starts treating a broken setup as a
 * quality problem.
 */
export const EXIT = { ok: 0, failed: 1, cannotJudge: 2 };

/**
 * @param {string} dir the skill's working directory, e.g. `.guides`
 * @param {{ setup: string }} opts what to tell someone whose setup is missing
 */
export const startGate = (dir, { setup }) => {
  const failures = [];
  const json = process.argv.includes('--json');

  const cannotJudge = (message, hint) => {
    console.error(`\n  ${message}\n  ${hint ?? setup}\n`);
    process.exit(EXIT.cannotJudge);
  };

  return {
    dir,
    json,
    failures,

    /** Collect a failure. `items` are the specific offenders, printed under the summary. */
    fail(check, detail, items = []) {
      failures.push({ check, detail, items });
    },

    /** The gate's own config. Absent is not a failure — it is "I cannot judge". */
    config(file = 'config.json') {
      return readJson(path.join(dir, file)) ?? cannotJudge(`no ${dir}/${file}`);
    },

    /**
     * The generated work list. An empty one is *never* success: there is nothing to have
     * finished. This is the guard that exists because a gate once printed "complete" for it.
     */
    workList(file, key, { label = key, hint } = {}) {
      const data = readJson(path.join(dir, file));
      if (!data) cannotJudge(`no ${dir}/${file}`, hint);
      if (!Array.isArray(data[key]) || data[key].length === 0) {
        cannotJudge(`${dir}/${file} lists no ${label} — nothing to verify, so nothing can be complete.`, hint);
      }
      return data;
    },

    /**
     * Print and exit. `headline` is the one line someone reads first, so it carries the
     * count that matters rather than a verdict they can already see from the exit code.
     */
    finish({ headline, done, extra = {} }) {
      if (json) {
        console.log(JSON.stringify({ ok: failures.length === 0, ...extra, failures }, null, 2));
      } else {
        console.log(`\n  ${headline}\n`);
        for (const f of failures) {
          console.log(`  ✗ ${f.check}: ${f.detail}`);
          for (const i of f.items) {
            console.log(`      ${i.file ?? ''}${i.line ? `:${i.line}` : ''}  ${i.text ?? ''}`);
          }
          if (f.items.length) console.log('');
        }
        if (failures.length) {
          console.log(`  ${failures.length} check(s) failing. Not finished.\n`);
        } else {
          // `done` may be several lines. A gate can pass while naming what it did not check,
          // and flattening that into one cheerful sentence is the overclaim these gates exist
          // to avoid — a skipped replay must not read like a full pass.
          const lines = Array.isArray(done) ? done : [done];
          console.log(`  ✓ ${lines[0]}`);
          for (const l of lines.slice(1)) console.log(`    ${l}`);
          console.log('');
        }
      }
      process.exit(failures.length === 0 ? EXIT.ok : EXIT.failed);
    },
  };
};
