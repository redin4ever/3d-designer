#!/usr/bin/env node
/** One honest project gate: product suites, rendered UI, startup probe, and feature wiring. */

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = process.cwd();

function executableWorks(bin, prefix = []) {
  const result = spawnSync(bin, [...prefix, '--version'], { stdio: 'ignore' });
  return result.status === 0;
}

export function resolveBrowser({
  env = process.env,
  platform = process.platform,
  exists = existsSync,
  probe = executableWorks,
} = {}) {
  const windows = platform === 'win32';
  const candidates = [
    env.PUPPETEER_EXECUTABLE_PATH,
    env.CHROME_PATH,
    windows && env.ProgramFiles && path.join(env.ProgramFiles, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    windows && env['ProgramFiles(x86)'] && path.join(env['ProgramFiles(x86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    windows && env.LOCALAPPDATA && path.join(env.LOCALAPPDATA, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    windows && 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    !windows && 'google-chrome',
    !windows && 'chromium',
    platform === 'darwin' && '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ].filter(Boolean);

  for (const candidate of candidates) {
    const hasPath = path.isAbsolute(candidate);
    if ((hasPath && exists(candidate)) || (!hasPath && probe(candidate))) return candidate;
  }
  return null;
}

export function resolvePython({ env = process.env, exists = existsSync, probe = executableWorks } = {}) {
  const candidates = [
    env.FORGE3D_PYTHON && { bin: env.FORGE3D_PYTHON, prefix: [] },
    env.LOCALAPPDATA && {
      bin: path.join(env.LOCALAPPDATA, 'Programs', 'Python', 'Python313', 'python.exe'),
      prefix: [],
    },
    { bin: 'py', prefix: ['-3.13'] },
    { bin: 'python3.13', prefix: [] },
    { bin: 'python3', prefix: [] },
    { bin: 'python', prefix: [] },
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (path.isAbsolute(candidate.bin) && !exists(candidate.bin)) continue;
    if (probe(candidate.bin, candidate.prefix)) return candidate;
  }
  return null;
}

export function buildChecks({ python, browser } = {}) {
  const py = typeof python === 'string' ? { bin: python, prefix: [] } : python;
  return [
    {
      id: 'backend',
      label: 'backend + deterministic agent evals',
      bin: process.execPath,
      args: ['tools/run-pytest.mjs', 'src', '-q'],
      available: Boolean(py),
      unavailable: 'Python 3.13 with pytest is not available',
    },
    {
      id: 'frontend',
      label: 'frontend unit suite',
      bin: process.execPath,
      args: ['--test', 'frontend/tests/'],
      available: true,
    },
    {
      id: 'browser',
      label: 'rendered Chrome UI suite',
      bin: process.execPath,
      args: ['--test', 'frontend/tests-browser/smoke.test.js'],
      env: browser ? { PUPPETEER_EXECUTABLE_PATH: browser } : {},
      available: Boolean(browser),
      unavailable: 'Chrome, Chromium, or Edge is not available',
    },
    {
      id: 'doctor',
      label: 'startup and wiring doctor',
      bin: py?.bin,
      args: [...(py?.prefix ?? []), 'src/forge3d_cli.py', 'doctor'],
      available: Boolean(py),
      unavailable: 'Python 3.13 is not available',
    },
    {
      id: 'feature-wiring',
      label: 'feature seam and test-first gate',
      bin: process.execPath,
      args: ['.feature/check.mjs'],
      available: existsSync(path.join(ROOT, '.feature', 'check.mjs')),
      unavailable: '.feature/check.mjs is missing',
    },
  ];
}

export function overallExitCode(results) {
  if (results.some((result) => result.status === 'failed')) return 1;
  if (results.some((result) => result.status === 'unavailable')) return 2;
  return 0;
}

function runChecks({ json = false } = {}) {
  const checks = buildChecks({ python: resolvePython(), browser: resolveBrowser() });
  const results = [];
  for (const check of checks) {
    if (!check.available) {
      results.push({ id: check.id, label: check.label, status: 'unavailable', detail: check.unavailable });
      if (!json) process.stderr.write(`\nUNAVAILABLE ${check.label}: ${check.unavailable}\n`);
      continue;
    }

    if (!json) process.stdout.write(`\n== ${check.label} ==\n`);
    const run = spawnSync(check.bin, check.args, {
      cwd: ROOT,
      env: { ...process.env, ...check.env, PYTHONIOENCODING: 'utf-8' },
      encoding: json ? 'utf8' : undefined,
      stdio: json ? 'pipe' : 'inherit',
      timeout: 20 * 60 * 1000,
      maxBuffer: 64 * 1024 * 1024,
    });
    const passed = run.status === 0;
    results.push({
      id: check.id,
      label: check.label,
      status: passed ? 'passed' : 'failed',
      exitCode: run.status,
      signal: run.signal ?? null,
      ...(json && !passed ? {
        output: `${run.stdout ?? ''}${run.stderr ?? ''}`.slice(-8000),
      } : {}),
    });
  }

  const exitCode = overallExitCode(results);
  if (json) {
    process.stdout.write(`${JSON.stringify({ ok: exitCode === 0, exitCode, results }, null, 2)}\n`);
  } else {
    process.stdout.write('\nProject verification\n');
    for (const result of results) {
      process.stdout.write(`  ${result.status.toUpperCase().padEnd(11)} ${result.label}\n`);
    }
    if (exitCode === 2) {
      process.stdout.write('  Result: could not fully judge; install the unavailable prerequisite.\n');
    } else {
      process.stdout.write(`  Result: ${exitCode === 0 ? 'PASS' : 'FAIL'}\n`);
    }
  }
  return exitCode;
}

const invoked = process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (invoked) process.exit(runChecks({ json: process.argv.includes('--json') }));
