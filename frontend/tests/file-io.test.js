import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fileIo from '../src/file-io.js';

import {
  MAX_FILE_BYTES,
  buildExportPayload,
  createFileController,
  attachFileMenu,
  validateLocalFile,
} from '../src/file-io.js';

test('file errors recursively extract readable text and never stringify as object Object', () => {
  assert.equal(typeof fileIo.formatFileError, 'function');
  assert.equal(
    fileIo.formatFileError?.({ error: { message: 'Pause the build before opening this project.' } }),
    'Pause the build before opening this project.',
  );
  assert.equal(
    fileIo.formatFileError?.({ code: 'project_invalid', details: ['Missing scene.json', 'Invalid package'] }),
    'Missing scene.json; Invalid package',
  );
  assert.equal(fileIo.formatFileError?.({ unexpected: true }), 'File operation failed.');
  assert.notEqual(fileIo.formatFileError?.({ unexpected: true }), '[object Object]');
});

function file(name, bytes = 4, type = 'application/octet-stream') {
  return {
    name,
    size: bytes,
    type,
    arrayBuffer: async () => new Uint8Array(bytes).buffer,
  };
}

function response(payload, ok = true, status = 200) {
  return { ok, status, json: async () => payload, blob: async () => payload };
}

test('local file validation rejects URLs, text values, unsupported extensions, and files over 512 MB', () => {
  assert.equal(MAX_FILE_BYTES, 512 * 1024 * 1024);
  assert.equal(validateLocalFile(file('model.glb')).ok, true);
  assert.equal(validateLocalFile(file('scene.forge3d')).ok, true);
  assert.equal(validateLocalFile('https://example.test/model.glb').ok, false);
  assert.equal(validateLocalFile(file('scene.txt', 2, 'text/plain')).ok, false);
  assert.equal(validateLocalFile(file('model.exe')).ok, false);
  assert.equal(validateLocalFile(file('huge.glb', MAX_FILE_BYTES + 1)).ok, false);
});

test('export defaults to the whole scene and requires explicit selection scope', () => {
  assert.deepEqual(
    buildExportPayload({ selectedIds: ['beam_04', 'beam_04', 'post_02'], scope: 'selection', format: 'gltf' }),
    {
      action: 'export-model',
      profile: 'generic',
      format: 'gltf',
      scope: 'selection',
      object_ids: ['beam_04', 'post_02'],
    },
  );
  assert.deepEqual(buildExportPayload({ selectedIds: [], profile: 'generic', format: 'glb' }), {
    action: 'export-model',
    profile: 'generic',
    format: 'glb',
    scope: 'scene',
    object_ids: [],
  });
  assert.deepEqual(buildExportPayload({ selectedIds: ['selected-but-not-requested'], format: 'glb' }), {
    action: 'export-model',
    profile: 'generic',
    format: 'glb',
    scope: 'scene',
    object_ids: [],
  });
});

test('controller uploads local files as binary and sends the requested import action', async () => {
  const calls = [];
  const controller = createFileController({
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return url === '/api/file-io/jobs'
        ? response({ job_id: 'job-1' })
        : response({ status: 'complete' });
    },
    pollInterval: 0,
  });

  const result = await controller.importModel(
    file('chair.glb', 8, 'model/gltf-binary'),
    { sourceUp: 'Y', unitScale: 0.01, flatten: false },
  );

  assert.equal(result.ok, true);
  assert.equal(calls[0].url, '/api/file-io/jobs');
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(calls[0].init.headers['x-forge3d-action'], 'import-model');
  assert.equal(calls[0].init.headers['x-forge3d-filename'], 'chair.glb');
  assert.equal(calls[0].init.headers['x-forge3d-source-up'], 'Y');
  assert.equal(calls[0].init.headers['x-forge3d-unit-scale'], '0.01');
  assert.equal(calls[0].init.headers['x-forge3d-flatten'], 'false');
  assert.ok(calls[0].init.body instanceof ArrayBuffer);
});

test('export posts generic profile and polls until a Blob download is available', async () => {
  const calls = [];
  const clicked = [];
  const revoked = [];
  const controller = createFileController({
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (url === '/api/file-io/jobs') return response({ job_id: 'job-2' });
      if (url === '/api/file-io/jobs/job-2') return response({ status: 'complete', download_url: '/downloads/job-2.glb' });
      if (url === '/downloads/job-2.glb') return response(new Blob(['mesh']));
      throw new Error(`unexpected URL ${url}`);
    },
    urlImpl: {
      createObjectURL: () => 'blob:job-2',
      revokeObjectURL: (url) => revoked.push(url),
    },
    downloadImpl: (href, filename) => clicked.push({ href, filename }),
    pollInterval: 0,
  });

  const result = await controller.exportModel({ selectedIds: ['part-1'], scope: 'selection', format: 'glb' });

  assert.equal(result.ok, true);
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    action: 'export-model', profile: 'generic', format: 'glb', scope: 'selection', object_ids: ['part-1'],
  });
  assert.deepEqual(clicked, [{ href: 'blob:job-2', filename: 'scene.glb' }]);
  assert.deepEqual(revoked, ['blob:job-2']);
});

test('job progress is reported and cancellation stops polling', async () => {
  const statuses = [];
  const calls = [];
  let resolvePoll;
  const controller = createFileController({
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (url === '/api/file-io/jobs') return response({ job_id: 'job-3' });
      if (url.endsWith('/cancel')) return response({ status: 'cancelled' });
      if (url.endsWith('/job-3')) {
        await new Promise((resolve) => { resolvePoll = resolve; });
        return response({ status: 'running', progress: 0.25, message: 'Importing' });
      }
      throw new Error(`unexpected URL ${url}`);
    },
    pollInterval: 0,
    onStatus: (status) => statuses.push(status),
  });

  const pending = controller.importModel(file('scene.gltf'));
  await new Promise((resolve) => setTimeout(resolve, 0));
  const cancelled = await controller.cancel();
  resolvePoll?.();
  const result = await pending;

  assert.equal(cancelled.ok, true);
  assert.equal(result.status, 'cancelled');
  assert.ok(statuses.some((status) => status.progress === 0.25));
  assert.ok(calls.some(({ url, init }) => url.endsWith('/cancel') && init.method === 'POST'));
});

test('structured file-job failures stay readable instead of becoming object text', async () => {
  const statuses = [];
  const controller = createFileController({
    fetchImpl: async (url) => url === '/api/file-io/jobs'
      ? response({ job_id: 'job-error' })
      : response({
        status: 'failed',
        error: {
          code: 'run_must_be_paused',
          message: 'Pause the build before you open a project.',
          details: ['The running agent may still be changing geometry.'],
        },
      }),
    pollInterval: 0,
    onStatus: (status) => statuses.push(status),
  });

  const result = await controller.openProject(file('scene.forge3d'));

  assert.equal(result.ok, false);
  assert.equal(result.error, 'Pause the build before you open a project.');
  assert.equal(typeof result.error, 'string');
  assert.equal(statuses.at(-1).message, 'Pause the build before you open a project.');
});

test('dirty Open and Import honor Save, Discard, and Cancel', async () => {
  const actions = [];
  const fetchImpl = async (url, init) => {
    actions.push({ url, init });
    if (url === '/api/file-io/jobs') return response({ job_id: `${actions.length}` });
    if (url.includes('/downloads/')) return response(new Blob(['project']));
    return response({ status: 'complete', download_url: '/downloads/project.forge3d' });
  };
  const outcomes = ['save', 'discard', 'cancel'];
  const controller = createFileController({
    fetchImpl,
    pollInterval: 0,
    isDirty: () => true,
    confirmUnsaved: async () => outcomes.shift(),
  });

  assert.equal((await controller.openProject(file('one.forge3d'))).ok, true);
  assert.equal((await controller.importModel(file('two.glb'))).ok, true);
  assert.equal((await controller.openProject(file('three.forge3d'))).status, 'cancelled');
  assert.equal(actions.filter(({ url }) => url === '/api/file-io/jobs').length, 3);
});

test('shortcut decisions are Ctrl+O, Ctrl+S, and Ctrl+Shift+S', () => {
  const controller = createFileController();
  const events = [
    { key: 'o', ctrlKey: true, preventDefault() { this.prevented = true; } },
    { key: 's', ctrlKey: true, preventDefault() { this.prevented = true; } },
    { key: 's', ctrlKey: true, shiftKey: true, preventDefault() { this.prevented = true; } },
  ];
  assert.deepEqual(events.map((event) => controller.shortcutAction(event)), [
    'open-project', 'save-project', 'save-as',
  ]);
  events.forEach((event) => assert.equal(event.prevented, true));
});

test('save and export status is delivered to the dialog and callback', async () => {
  const statuses = [];
  const controller = createFileController({
    fetchImpl: async (url) => {
      if (url === '/api/file-io/jobs') return response({ job_id: 'job-4' });
      if (url === '/downloads/out.glb') return response(new Blob(['mesh']));
      return response({ status: 'complete', download_url: '/downloads/out.glb' });
    },
    urlImpl: {
      createObjectURL: () => 'blob:out',
      revokeObjectURL: () => {},
    },
    pollInterval: 0,
    onStatus: (status) => statuses.push(status),
  });
  const result = await controller.saveProject({ filename: 'house.forge3d' });
  assert.equal(result.ok, true);
  assert.ok(statuses.some((status) => status.phase === 'complete'));
});

test('DOM attachment is optional-element safe and still returns a controller', () => {
  const root = {
    ownerDocument: {},
    querySelector: () => null,
    addEventListener: () => {},
  };
  const attached = attachFileMenu(root, { fetchImpl: async () => response({}) });
  assert.ok(attached?.controller);
});
