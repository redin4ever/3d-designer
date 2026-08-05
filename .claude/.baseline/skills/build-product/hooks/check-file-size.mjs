#!/usr/bin/env node
/**
 * Rule 2 enforcement — advisory file-size check.
 *
 * Wired to PostToolUse for Write|Edit. Reports files over budget so the agent splits them
 * during the phase rather than at review time.
 *
 * Advisory by design: it never blocks. A hook that halts an unattended phase violates
 * Rule 3 (.claude/rules/autonomy.md), which is a worse failure than an oversized file.
 *
 * Silent unless this project actually uses one of these skills. It used to fire on every
 * Write and Edit in any project the skills had merely been *installed* into — and on files
 * outside that project entirely, since a PostToolUse hook sees every edit the session makes.
 * Rule 2 is a standard a repo opts into by running a skill, not a house style to impose on
 * whatever someone happens to open next.
 */

import { readFileSync, existsSync } from 'node:fs';
import { extname, basename, join, resolve, relative, isAbsolute } from 'node:path';

const BUDGETS = {
  source: { soft: 300, hard: 1000 },
  test: { soft: 450, hard: 1500 },
  markdown: { soft: 300, hard: 600 },
};

const SOURCE_EXT = new Set([
  '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs',
  '.py', '.go', '.rs', '.rb', '.java', '.kt', '.swift', '.php', '.cs',
  '.vue', '.svelte', '.css', '.scss',
]);

const kindOf = (path) => {
  const ext = extname(path);
  if (ext === '.md' || ext === '.mdx') return 'markdown';
  if (!SOURCE_EXT.has(ext)) return null;
  return /\.(test|spec)\.|__tests__|\/tests?\//.test(path) ? 'test' : 'source';
};

/** Lines that carry logic — imports, blank lines and comment-only lines are exempt. */
const countSignificant = (text) =>
  text.split('\n').filter((raw) => {
    const line = raw.trim();
    if (line === '') return false;
    if (/^(import|export\s+\*|export\s+\{|from|using|#include|require\()/.test(line)) return false;
    if (/^(\/\/|\/\*|\*|#(?!\[)|--)/.test(line)) return false;
    return true;
  }).length;

const readHookInput = () => {
  try {
    return JSON.parse(readFileSync(0, 'utf8'));
  } catch {
    return null;
  }
};

/**
 * The working directory a skill creates when it is first run. Their presence is what
 * distinguishes "this repo is built and maintained by these skills" from "someone once
 * installed the skills here". Every one is committed at least in part, so a fresh clone of
 * a pipeline project still enforces its own rules.
 */
const IN_USE = ['.pipeline', '.feature', '.guides', '.redesign'];

const projectDir = process.env.CLAUDE_PROJECT_DIR ?? process.cwd();

/** Has any skill actually been run in this project? */
const adopted = () => IN_USE.some((dir) => existsSync(join(projectDir, dir)));

/**
 * Is this file part of the project that adopted the rule?
 *
 * The hook is wired per project but fires for every edit in the session, including files
 * in unrelated repositories. Reporting this project's budgets against another project's
 * file is noise at best, and at worst it is a rule nobody agreed to.
 */
const insideProject = (file) => {
  const rel = relative(projectDir, resolve(file));
  return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel);
};

const main = () => {
  if (!adopted()) return;

  const input = readHookInput();
  const path = input?.tool_input?.file_path ?? input?.tool_input?.path;
  if (!path) return;
  if (!insideProject(path)) return;

  const kind = kindOf(path);
  if (!kind) return;

  let text;
  try {
    text = readFileSync(path, 'utf8');
  } catch {
    return; // deleted or moved between the edit and the hook — not our problem
  }

  const lines = countSignificant(text);
  const { soft, hard } = BUDGETS[kind];
  if (lines <= soft) return;

  const name = basename(path);
  const over = lines > hard ? 'HARD CAP' : 'soft cap';
  const limit = lines > hard ? hard : soft;
  const action = lines > hard
    ? 'Split it before this phase ends — no exceptions (.claude/rules/modularity.md).'
    : 'Justify in one line or split along a responsibility seam.';

  // Must be JSON on stdout. A PostToolUse hook that exits 0 and prints plain text has
  // its stdout routed to the debug log — the agent never sees it, and the rule silently
  // stops being enforced. `additionalContext` is the documented way to reach the agent
  // without blocking, which Rule 3 forbids.
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PostToolUse',
        additionalContext:
          `[Rule 2] ${name} is ${lines} significant lines, over the ${kind} ${over} ` +
          `of ${limit}. ${action}`,
      },
    })
  );
};

main();
