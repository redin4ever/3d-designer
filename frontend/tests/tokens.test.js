// Contract: frontend/src/tokens.css is the ONLY place a raw hex color may appear under
// frontend/src/. "A design system that is only read is decoration" — this test is what
// makes the linear.app register (DESIGN.md) enforced rather than aspirational.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, relative } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_DIR = join(HERE, '..', 'src');
const HEX_PATTERN = /#[0-9a-fA-F]{3,8}\b/g;

function listFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) out.push(...listFiles(full));
    else out.push(full);
  }
  return out;
}

test('tokens.css is marked generated and defines the required semantic custom properties', () => {
  const css = readFileSync(join(SRC_DIR, 'tokens.css'), 'utf8');
  assert.match(css, /GENERATED FROM DESIGN\.md — DO NOT EDIT/);
  for (const name of ['--canvas', '--surface-1', '--hairline', '--ink', '--muted', '--accent']) {
    assert.match(css, new RegExp(`${name}\\s*:\\s*#[0-9a-fA-F]{6}`), `tokens.css must define ${name}`);
  }
});

test('no file in frontend/src/ other than tokens.css contains a raw hex color', () => {
  const offenders = [];
  for (const file of listFiles(SRC_DIR)) {
    if (file.endsWith('tokens.css')) continue;
    const contents = readFileSync(file, 'utf8');
    const matches = contents.match(HEX_PATTERN);
    if (matches) offenders.push(`${relative(SRC_DIR, file)}: ${matches.join(', ')}`);
  }
  assert.deepEqual(offenders, [], 'design values must be read from tokens.css custom properties, never hard-coded');
});
