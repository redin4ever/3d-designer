import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const load = (name) => readFile(new URL(`../src/${name}`, import.meta.url), 'utf8');

function rule(css, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, 's'));
  assert.ok(match, `missing ${selector} rule`);
  return match[1];
}

test('top-bar commands participate in layout instead of competing fixed offsets', async () => {
  const [app, connect] = await Promise.all([load('app.css'), load('connect.css')]);
  const panel = rule(app, '.controls-panel');
  const run = rule(app, '.run-group');
  const agent = rule(connect, '.connect-button');

  assert.match(panel, /display:\s*(grid|flex)/, 'the command bar needs one shared layout context');
  assert.doesNotMatch(run, /position:\s*absolute/, 'run controls cannot reserve space only by offset');
  assert.doesNotMatch(agent, /position:\s*fixed/, 'agent state must share the command-bar layout');
});

test('selected-object content owns scrolling and texture markup has matching selectors', async () => {
  const [point, texture] = await Promise.all([load('point.css'), load('texture-inspector.css')]);
  const body = rule(point, '.transform-body');

  assert.match(body, /overflow-y:\s*auto/, 'long inspectors must scroll rather than cross into chat or logs');
  for (const selector of ['.texture-presets', '.texture-maps', '.texture-transform']) {
    assert.ok(texture.includes(selector), `${selector} is rendered but has no stylesheet contract`);
  }
});
