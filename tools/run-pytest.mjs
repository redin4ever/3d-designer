/**
 * Run pytest with a Python that actually exists.
 *
 * `npm run test:backend` used to be plain `python -m pytest`, which fails on Windows
 * because `python` on PATH is the Microsoft Store alias stub — it opens the Store instead
 * of running anything. The documented command did not work on the machine it was
 * documented for, and the gate (which runs it) reported the backend suite as not green
 * while `pytest` itself was passing.
 *
 * This tries the interpreters that are actually likely to be there, in order, and uses the
 * first one that can import pytest. No hardcoded user path.
 */

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const candidates = [
  // Explicit override always wins.
  process.env.FORGE3D_PYTHON,

  // A per-user CPython install — where `bpy` has to live, since it is version-locked.
  process.env.LOCALAPPDATA &&
    join(process.env.LOCALAPPDATA, 'Programs', 'Python', 'Python313', 'python.exe'),

  // The Windows launcher, pinned: `py` alone can select an interpreter without bpy.
  'py -3.13',

  'python3.13',
  'python3',
  'python',
].filter(Boolean);

function works(command) {
  const [bin, ...prefix] = command.split(' ');
  if (bin.includes('\\') || bin.includes('/')) {
    if (!existsSync(bin)) return null;
  }
  const probe = spawnSync(bin, [...prefix, '-c', 'import pytest'], { stdio: 'ignore' });
  return probe.status === 0 ? [bin, prefix] : null;
}

let chosen = null;
for (const candidate of candidates) {
  chosen = works(candidate);
  if (chosen) {
    if (candidate !== candidates[0]) process.stderr.write(`using ${candidate}\n`);
    break;
  }
}

if (!chosen) {
  process.stderr.write(
    'No Python with pytest was found.\n' +
      `Tried: ${candidates.join(', ')}\n` +
      'Install Python 3.13 (bpy is locked to exactly 3.13) and `pip install pytest`,\n' +
      'or set FORGE3D_PYTHON to the interpreter you want used.\n',
  );
  process.exit(1);
}

const [bin, prefix] = chosen;
const args = [...prefix, '-m', 'pytest', ...process.argv.slice(2)];
const run = spawnSync(bin, args, {
  stdio: 'inherit',
  // cp1252 cannot encode the em dashes and box-drawing characters in this suite's output.
  env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
});
process.exit(run.status ?? 1);
