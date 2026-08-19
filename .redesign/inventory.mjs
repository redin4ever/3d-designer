import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const root = process.cwd();
const sha = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
const visualFiles = [
  'frontend/index.html',
  'frontend/src/tokens.css',
  'frontend/src/app.css',
  'frontend/src/chat.css',
  'frontend/src/connect.css',
  'frontend/src/point.css',
].filter((file) => fs.existsSync(path.join(root, file)));

const item = (id, kind, sourceFiles, states, elements) => ({
  id,
  kind,
  path: '/index.html',
  sourceFiles,
  states,
  elements,
  status: 'pending',
  evidence: null,
});

const inventory = {
  generatedAt: sha,
  scope: 'all frontend surfaces',
  items: [
    item('route-editor', 'route', visualFiles, ['connected', 'disconnected', 'running', 'paused', 'error'],
      ['header', 'main', 'button', 'input', 'select', 'status', 'empty-state']),
    item('layout-viewport-workspace', 'layout', ['frontend/index.html', 'frontend/src/app.css'],
      ['default', 'narrow', 'rtl'], ['toolbar', 'canvas', 'sidebar', 'status']),
    item('component-transform-tools', 'component', ['frontend/index.html', 'frontend/src/point.css'],
      ['no-selection', 'selected', 'blocked', 'moving', 'pending', 'rejected'], ['button', 'input', 'help']),
    item('component-conversation-log', 'component', ['frontend/index.html', 'frontend/src/chat.css'],
      ['empty', 'populated', 'pending', 'unconfirmed'], ['list', 'row', 'composer', 'status']),
    item('component-connect-dialog', 'component', ['frontend/index.html', 'frontend/src/connect.css'],
      ['closed', 'loading', 'empty', 'picker', 'success', 'error'], ['dialog', 'button', 'list', 'status']),
    item('component-point-composer', 'component', ['frontend/index.html', 'frontend/src/point.css'],
      ['hidden', 'selected', 'attachment', 'sent', 'error'], ['form', 'input', 'button', 'status']),
  ],
};

fs.writeFileSync(path.join(root, '.redesign', 'inventory.json'), `${JSON.stringify(inventory, null, 2)}\n`);

const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
  const absolute = path.join(dir, entry.name);
  return entry.isDirectory() ? walk(absolute) : [absolute];
});
const testRoots = ['frontend/tests', 'frontend/tests-browser'];
const tests = Object.fromEntries(testRoots.flatMap((dir) => walk(path.join(root, dir)))
  .filter((file) => /\.(?:js|mjs)$/.test(file))
  .map((file) => {
    const relative = path.relative(root, file).replaceAll('\\', '/');
    const hash = createHash('sha256').update(fs.readFileSync(file)).digest('hex');
    return [relative, hash];
  }));
fs.writeFileSync(path.join(root, '.redesign', 'behaviour.json'), `${JSON.stringify({
  tests,
  commands: ['npm run test:frontend', 'npm run test:frontend:browser'],
  browserEnvironment: 'PUPPETEER_EXECUTABLE_PATH=C:/Program Files/Google/Chrome/Application/chrome.exe',
  baseline: 'Both suites passed before the visual sweep.',
}, null, 2)}\n`);

console.log(`generated ${inventory.items.length} surfaces and froze ${Object.keys(tests).length} test/support files at ${sha}`);
