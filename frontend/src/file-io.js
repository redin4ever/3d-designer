// File menu decisions and the small HTTP job client behind them. The module deliberately
// does not know about main.js or the scene renderer: the editor can inject selected ids,
// dirty state, and callbacks without making file transfers part of the wire protocol.

export const MAX_FILE_BYTES = 512 * 1024 * 1024;
export const DEFAULT_PROFILE = 'generic';
export const DEFAULT_FORMAT = 'glb';
export const FILE_ACTIONS = Object.freeze([
  'open-project',
  'save-project',
  'save-as',
  'import-model',
  'export-model',
]);

const PROJECT_EXTENSIONS = new Set(['forge3d', 'json']);
const MODEL_EXTENSIONS = new Set(['glb', 'gltf', 'obj', 'fbx', 'stl', 'ply', 'usd', 'usda', 'usdc']);
const FORMATS = new Set(['glb', 'gltf', 'obj', 'fbx', 'stl', 'ply', 'usd']);
const PROFILES = new Set(['generic', 'roblox', 'unity', 'unreal']);

function extensionOf(name) {
  const match = String(name ?? '').toLowerCase().match(/\.([a-z0-9]+)$/);
  return match?.[1] ?? '';
}

function failure(error, extra = {}) {
  return { ok: false, error, ...extra };
}

function errorText(value, fallback) {
  if (typeof value === 'string' && value) return value;
  if (value && typeof value.message === 'string') return value.message;
  return fallback;
}

/** Validate a browser File without ever accepting a path or URL string. */
export function validateLocalFile(file, { kind = 'any' } = {}) {
  if (!file || typeof file !== 'object' || typeof file.arrayBuffer !== 'function') {
    return failure('Choose a local file. Remote URLs and path strings are not supported.');
  }
  if (!Number.isFinite(file.size) || file.size < 0) return failure('The selected file has no valid size.');
  if (file.size > MAX_FILE_BYTES) return failure('Files must be 512 MB or smaller.');

  const extension = extensionOf(file.name);
  const allowed = kind === 'project'
    ? PROJECT_EXTENSIONS
    : kind === 'model'
      ? MODEL_EXTENSIONS
      : new Set([...PROJECT_EXTENSIONS, ...MODEL_EXTENSIONS]);
  if (!allowed.has(extension)) {
    return failure(`Unsupported file type .${extension || '(none)'}.`);
  }
  if (kind === 'project' && extension === 'json') {
    return { ok: true, legacy: true, extension };
  }
  return { ok: true, extension };
}

function cleanIds(ids) {
  if (!Array.isArray(ids)) return [];
  return [...new Set(ids.filter((id) => typeof id === 'string' && id.trim() !== ''))];
}

export function buildExportPayload({ selectedIds = [], profile = DEFAULT_PROFILE, format = DEFAULT_FORMAT } = {}) {
  if (!PROFILES.has(profile)) throw new Error(`Unsupported export profile "${profile}".`);
  if (!FORMATS.has(format)) throw new Error(`Unsupported export format "${format}".`);
  const objectIds = cleanIds(selectedIds);
  return {
    action: 'export-model',
    profile,
    format,
    scope: objectIds.length > 0 ? 'selection' : 'scene',
    object_ids: objectIds,
  };
}

function defaultDownload(documentImpl, href, filename) {
  if (!documentImpl?.createElement) return;
  const anchor = documentImpl.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  anchor.click?.();
}

function responsePayload(response) {
  return response.json().catch(() => ({}));
}

/**
 * Create the file job controller. All browser globals are injectable so the job lifecycle
 * can be tested without a DOM, and fetch is resolved at call time by default.
 */
export function createFileController(options = {}) {
  const fetchImpl = options.fetchImpl ?? ((...args) => globalThis.fetch(...args));
  const urlImpl = options.urlImpl ?? globalThis.URL;
  const documentImpl = options.documentImpl ?? globalThis.document;
  const sleepImpl = options.sleepImpl ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const pollInterval = Math.max(0, Number(options.pollInterval ?? 250));
  const downloadImpl = options.downloadImpl ?? ((href, filename) => defaultDownload(documentImpl, href, filename));
  const onStatus = options.onStatus ?? (() => {});
  const isDirty = options.isDirty ?? (() => false);
  const confirmUnsaved = options.confirmUnsaved ?? (async () => 'cancel');
  let state = { action: null, phase: 'idle', status: 'idle', progress: 0, message: '' };
  let currentJob = null;

  const emit = (patch) => {
    state = { ...state, ...patch };
    onStatus({ ...state });
  };

  async function request(url, init) {
    let response;
    try {
      response = await fetchImpl(url, init);
    } catch (error) {
      return failure(`Could not reach the file service: ${error?.message ?? String(error)}`);
    }
    const payload = await responsePayload(response);
    if (!response.ok) return failure(errorText(payload.error, `File service answered ${response.status}.`), { payload });
    return { ok: true, ...payload };
  }

  async function downloadResult(payload) {
    if (!payload.download_url) return;
    const response = await fetchImpl(payload.download_url);
    if (!response.ok) return failure(`Could not download ${payload.filename ?? 'the generated file'}.`);
    const blob = await response.blob();
    const href = urlImpl?.createObjectURL?.(blob);
    if (!href) return failure('The browser could not create a download link.');
    const filename = payload.filename ?? (payload.format ? `scene.${payload.format}` : 'scene.forge3d');
    try {
      downloadImpl(href, filename);
    } finally {
      urlImpl?.revokeObjectURL?.(href);
    }
  }

  async function poll(job, action, shouldDownload) {
    for (;;) {
      const result = await request(`/api/file-io/jobs/${encodeURIComponent(job.id)}`);
      if (!result.ok) {
        emit({ action, phase: 'error', status: 'error', message: result.error });
        return result;
      }
      const status = String(result.status ?? 'running').toLowerCase();
      const progress = Number.isFinite(result.progress) ? Math.max(0, Math.min(1, result.progress)) : state.progress;
      if (status === 'complete' || status === 'completed' || status === 'done') {
        if (job.cancelRequested) {
          emit({ action, phase: 'cancelled', status: 'cancelled', progress, message: 'Cancelled.' });
          return { ok: true, status: 'cancelled' };
        }
        emit({ action, phase: 'complete', status: 'complete', progress: 1, message: result.message ?? 'Complete.' });
        const downloaded = shouldDownload
          ? await downloadResult({ ...result, filename: result.filename ?? job.filename, format: result.format ?? job.format })
          : null;
        if (downloaded?.ok === false) return downloaded;
        return { ok: true, ...result };
      }
      if (status === 'cancelled' || status === 'canceled') {
        emit({ action, phase: 'cancelled', status: 'cancelled', progress, message: result.message ?? 'Cancelled.' });
        return { ok: true, ...result, status: 'cancelled' };
      }
      if (status === 'failed' || status === 'error') {
        const message = errorText(result.error, result.message ?? 'File job failed.');
        emit({ action, phase: 'error', status: 'error', progress, message });
        return failure(message, { ...result });
      }
      emit({ action, phase: 'progress', status, progress, message: result.message ?? '' });
      if (job.cancelRequested) {
        emit({ action, phase: 'cancelled', status: 'cancelled', progress, message: 'Cancelled.' });
        return { ok: true, status: 'cancelled' };
      }
      await sleepImpl(pollInterval);
    }
  }

  async function start(action, { payload = {}, file = null, download = false, headers = {} } = {}) {
    if (!FILE_ACTIONS.includes(action)) return failure(`Unsupported file action "${action}".`);
    let init;
    if (file) {
      const checked = validateLocalFile(file, { kind: action === 'import-model' ? 'model' : 'project' });
      if (!checked.ok) return checked;
      let binary;
      try {
        binary = await file.arrayBuffer();
      } catch (error) {
        return failure(`Could not read ${file.name}: ${error?.message ?? String(error)}`);
      }
      init = {
        method: 'POST',
        headers: {
          'content-type': file.type || 'application/octet-stream',
          'x-forge3d-action': action,
          'x-forge3d-filename': file.name,
          'x-forge3d-size': String(file.size),
          ...headers,
        },
        body: binary,
      };
    } else {
      init = {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action, ...payload }),
      };
    }

    emit({ action, phase: 'starting', status: 'starting', progress: 0, message: 'Starting…' });
    const started = await request('/api/file-io/jobs', init);
    if (!started.ok) {
      emit({ action, phase: 'error', status: 'error', message: started.error });
      return started;
    }
    const id = started.job_id ?? started.id;
    if (!id) {
      emit({ action, phase: 'complete', status: 'complete', progress: 1, message: 'Complete.' });
      if (download) await downloadResult(started);
      return { ok: true, ...started };
    }
    const job = {
      id,
      cancelRequested: false,
      format: payload.format,
      filename: payload.filename ?? (action === 'export-model' && payload.format ? `scene.${payload.format}` : undefined),
    };
    currentJob = job;
    try {
      return await poll(job, action, download);
    } finally {
      if (currentJob === job) currentJob = null;
    }
  }

  async function gate(action) {
    if (!isDirty() || !['open-project', 'import-model'].includes(action)) return { ok: true };
    const decision = await confirmUnsaved(action);
    if (decision === 'discard') return { ok: true };
    if (decision === 'save') {
      const saved = await saveProject({ internal: true });
      return saved.ok ? { ok: true } : saved;
    }
    return { ok: true, cancelled: true };
  }

  async function openProject(file) {
    const gateResult = await gate('open-project');
    if (gateResult.cancelled) return { ok: true, status: 'cancelled' };
    if (!gateResult.ok) return gateResult;
    return start('open-project', { file });
  }

  async function importModel(file, { sourceUp = 'AUTO', unitScale = 1, flatten = true } = {}) {
    const gateResult = await gate('import-model');
    if (gateResult.cancelled) return { ok: true, status: 'cancelled' };
    if (!gateResult.ok) return gateResult;
    return start('import-model', {
      file,
      headers: {
        'x-forge3d-source-up': String(sourceUp).toUpperCase(),
        'x-forge3d-unit-scale': String(unitScale),
        'x-forge3d-flatten': String(Boolean(flatten)),
      },
    });
  }

  async function saveProject({ filename = 'scene.forge3d', internal = false } = {}) {
    return start('save-project', { payload: { filename }, download: true, internal });
  }

  async function saveAs({ filename = 'scene.forge3d' } = {}) {
    return start('save-as', { payload: { filename }, download: true });
  }

  async function exportModel({ selectedIds = [], profile = DEFAULT_PROFILE, format = DEFAULT_FORMAT } = {}) {
    let payload;
    try {
      payload = buildExportPayload({ selectedIds, profile, format });
    } catch (error) {
      return failure(error?.message ?? String(error));
    }
    return start('export-model', { payload, download: true });
  }

  async function cancel() {
    if (!currentJob) return failure('There is no file operation to cancel.');
    const job = currentJob;
    job.cancelRequested = true;
    const result = await request(`/api/file-io/jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' });
    emit({ phase: 'cancelling', status: 'cancelling', message: 'Cancelling…' });
    return result.ok ? { ok: true, status: 'cancelled' } : result;
  }

  function shortcutAction(event) {
    if (!event || !(event.ctrlKey || event.metaKey) || event.altKey) return null;
    const key = String(event.key ?? '').toLowerCase();
    const action = key === 'o' && !event.shiftKey
      ? 'open-project'
      : key === 's' && event.shiftKey
        ? 'save-as'
        : key === 's'
          ? 'save-project'
          : null;
    if (action) event.preventDefault?.();
    return action;
  }

  return {
    openProject,
    saveProject,
    saveAs,
    importModel,
    exportModel,
    cancel,
    shortcutAction,
    getState: () => ({ ...state }),
  };
}

function setVisible(node, visible) {
  if (!node) return;
  node.hidden = !visible;
  node.setAttribute('aria-hidden', String(!visible));
}

function actionMethod(controller, action, context) {
  if (action === 'open-project') return controller.openProject(context.file);
  if (action === 'save-project') return controller.saveProject({ filename: context.filename });
  if (action === 'save-as') return controller.saveAs({ filename: context.filename });
  if (action === 'import-model') return controller.importModel(context.file, context);
  return controller.exportModel(context);
}

/** Attach the File menu, native file picker, dialog, and keyboard shortcuts. */
export function attachFileMenu(root, options = {}) {
  if (!root?.querySelector) return null;
  const documentImpl = options.documentImpl ?? root.ownerDocument ?? globalThis.document;
  const menuButton = root.querySelector('[data-action="file-menu"], #file-menu-button');
  const menu = root.querySelector('[data-file-menu-panel]');
  const dialog = root.querySelector('[data-file-dialog], #file-io-dialog');
  const fileInput = root.querySelector('[data-file-input]');
  const statusNode = root.querySelector('[data-file-status]');
  const progressNode = root.querySelector('[data-file-progress]');
  const filenameInput = root.querySelector('[data-file-filename]');
  const profileInput = root.querySelector('[data-file-profile]');
  const formatInput = root.querySelector('[data-file-format]');
  const unsavedNode = root.querySelector('[data-file-unsaved]');
  const sourceUpInput = root.querySelector('[data-file-source-up]');
  const unitScaleInput = root.querySelector('[data-file-unit-scale]');
  const flattenInput = root.querySelector('[data-file-flatten]');
  const controller = options.controller ?? createFileController({
    ...options,
    documentImpl,
    onStatus: (status) => {
      statusNode && (statusNode.textContent = status.message || status.phase);
      progressNode && (progressNode.value = Math.round((status.progress ?? 0) * 100));
      statusNode?.setAttribute('data-phase', status.phase);
      options.onStatus?.(status);
    },
    confirmUnsaved: options.confirmUnsaved ?? (() => new Promise((resolve) => {
      if (!unsavedNode) return resolve('cancel');
      setVisible(unsavedNode, true);
      const finish = (choice) => {
        setVisible(unsavedNode, false);
        resolve(choice);
      };
      unsavedNode.querySelector('[data-file-unsaved-save]')?.addEventListener('click', () => finish('save'), { once: true });
      unsavedNode.querySelector('[data-file-unsaved-discard]')?.addEventListener('click', () => finish('discard'), { once: true });
      unsavedNode.querySelector('[data-file-unsaved-cancel]')?.addEventListener('click', () => finish('cancel'), { once: true });
    })),
  });
  let activeAction = null;

  const showDialog = (action) => {
    activeAction = action;
    const title = dialog?.querySelector('[data-file-dialog-title]');
    if (title) title.textContent = action.replaceAll('-', ' ');
    if (fileInput) {
      fileInput.value = '';
      fileInput.accept = action === 'import-model' ? '.glb,.gltf,.obj,.fbx,.stl,.ply,.usd,.usda,.usdc' : '.forge3d,.json';
    }
    if (dialog?.showModal && !dialog.open) dialog.showModal();
    if ((action === 'open-project' || action === 'import-model') && fileInput) {
      if (fileInput.showPicker) fileInput.showPicker();
      else fileInput.click();
    }
  };

  const submit = async () => {
    if (!activeAction) return;
    const context = {
      file: fileInput?.files?.[0] ?? null,
      filename: filenameInput?.value?.trim() || 'scene.forge3d',
      profile: profileInput?.value || DEFAULT_PROFILE,
      format: formatInput?.value || DEFAULT_FORMAT,
      selectedIds: options.selectedIds?.() ?? [],
      sourceUp: sourceUpInput?.value || 'AUTO',
      unitScale: Number(unitScaleInput?.value || 1),
      flatten: flattenInput?.checked ?? true,
    };
    if ((activeAction === 'open-project' || activeAction === 'import-model') && !context.file) {
      if (statusNode) statusNode.textContent = 'Choose a local file first.';
      return;
    }
    const result = await actionMethod(controller, activeAction, context);
    options.onResult?.(result, activeAction);
    if (result?.ok && result.status !== 'cancelled') dialog?.close?.();
  };

  menuButton?.addEventListener('click', () => {
    const next = menu?.hidden ?? true;
    setVisible(menu, next);
    menuButton.setAttribute('aria-expanded', String(next));
  });
  menu?.querySelectorAll('[data-file-action]').forEach((item) => {
    item.addEventListener('click', () => {
      setVisible(menu, false);
      menuButton?.setAttribute('aria-expanded', 'false');
      showDialog(item.dataset.fileAction);
    });
  });
  root.querySelector('[data-file-confirm]')?.addEventListener('click', submit);
  root.querySelector('[data-file-cancel]')?.addEventListener('click', () => controller.cancel());
  root.querySelector('[data-file-close]')?.addEventListener('click', () => dialog?.close?.());
  root.addEventListener('keydown', (event) => {
    const action = controller.shortcutAction(event);
    if (action) showDialog(action);
  });
  return { controller, open: showDialog, submit };
}
