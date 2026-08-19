// Texture inspector state and render model. DOM ownership stays with main.js so this
// controller can be used by the inspector, command palette, and agent bridge alike.

export const TEXTURE_PRESETS = [
  'wood',
  'brick',
  'concrete',
  'stone',
  'metal',
  'plaster',
];

export const TEXTURE_SLOTS = ['albedo', 'normal', 'roughness', 'metallic'];

const ACCEPTED_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp']);
const ACCEPTED_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'webp']);
const FILE_ACCEPT = '.png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp';

function copy(value) {
  return structuredClone(value);
}

function normalizeIds(ids) {
  const values = Array.isArray(ids) ? ids : ids == null ? [] : [ids];
  return [...new Set(values.filter((id) => typeof id === 'string' && id.length > 0))];
}

function normalizeTransform(transform = {}) {
  const repeat = Array.isArray(transform.repeat) ? transform.repeat : [1, 1];
  const offset = Array.isArray(transform.offset) ? transform.offset : [0, 0];
  return {
    repeat: [Number(repeat[0]) || 1, Number(repeat[1]) || 1],
    rotation: Number(transform.rotation) || 0,
    offset: [Number(offset[0]) || 0, Number(offset[1]) || 0],
  };
}

function normalizeFiles(files = {}) {
  return Object.fromEntries(TEXTURE_SLOTS.map((slot) => [slot, files[slot] ?? null]));
}

function validSlot(slot) {
  return Number.isInteger(slot) && slot >= 0 && slot < TEXTURE_SLOTS.length;
}

function validChannel(channel) {
  return TEXTURE_SLOTS.includes(channel);
}

function isAcceptedFile(file) {
  if (!file || typeof file !== 'object') return false;
  const type = typeof file.type === 'string' ? file.type.toLowerCase() : '';
  const name = typeof file.name === 'string' ? file.name.toLowerCase() : '';
  const extension = name.includes('.') ? name.split('.').pop() : '';
  return (type && ACCEPTED_TYPES.has(type)) || ACCEPTED_EXTENSIONS.has(extension);
}

function initialState(options = {}) {
  return {
    selectedObjectIds: normalizeIds(options.selectedObjectIds),
    slot: validSlot(options.slot) ? options.slot : 0,
    preset: TEXTURE_PRESETS.includes(options.preset) ? options.preset : null,
    materialId: typeof options.materialId === 'string' ? options.materialId : null,
    files: normalizeFiles(options.files),
    transform: normalizeTransform(options.transform),
    status: {
      kind: options.status?.kind ?? 'idle',
      message: options.status?.message ?? '',
    },
  };
}

/** Creates a stateful controller; callers decide how to paint its render model. */
export function createTextureInspector(options = {}) {
  let state = initialState(options);
  const listeners = new Set();
  const getState = () => copy(state);
  const notify = () => listeners.forEach((listener) => listener(getState()));
  const update = (patch) => {
    state = { ...state, ...patch };
    notify();
    return getState();
  };

  return {
    getState,
    subscribe(listener) {
      if (typeof listener !== 'function') return () => {};
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setSelection(ids) {
      return update({ selectedObjectIds: normalizeIds(ids) });
    },
    setPreset(preset) {
      if (!TEXTURE_PRESETS.includes(preset)) return false;
      update({ preset, materialId: null });
      return true;
    },
    setMaterial(materialId) {
      if (materialId !== null && typeof materialId !== 'string') return false;
      update({ materialId, preset: null });
      return true;
    },
    setSlot(slot) {
      if (!validSlot(slot)) return false;
      update({ slot });
      return true;
    },
    setChannelFile(channel, file) {
      if (!validChannel(channel) || !isAcceptedFile(file)) return false;
      update({ files: { ...state.files, [channel]: file } });
      return true;
    },
    clearChannelFile(channel) {
      if (!validChannel(channel)) return false;
      update({ files: { ...state.files, [channel]: null } });
      return true;
    },
    setTransform(transform) {
      update({ transform: normalizeTransform({ ...state.transform, ...transform }) });
      return getState();
    },
    setStatus(kind, message = '') {
      const allowed = new Set(['idle', 'loading', 'error', 'disabled', 'ready']);
      update({ status: { kind: allowed.has(kind) ? kind : 'error', message: String(message) } });
      return getState();
    },
    buildApplyCommand() {
      return {
        name: 'apply_texture_material',
        params: {
          object_ids: [...state.selectedObjectIds],
          preset: state.preset,
          material_id: state.materialId,
          slot: state.slot,
          files: copy(state.files),
          transform: copy(state.transform),
        },
      };
    },
  };
}

/** Returns serializable view data; no document or browser APIs are required. */
export function renderTextureInspector(options = {}) {
  const state = options.controller?.getState ? options.controller.getState() : initialState(options);
  const materials = Array.isArray(options.materials)
    ? options.materials.filter((material) => material && typeof material.id === 'string')
    : [];
  return {
    type: 'texture-inspector',
    disabled: options.disabled === true || state.status.kind === 'disabled',
    selectionCount: state.selectedObjectIds.length,
    selectedObjectIds: [...state.selectedObjectIds],
    presets: [...TEXTURE_PRESETS],
    materials: copy(materials),
    fileAccept: FILE_ACCEPT,
    controls: [...TEXTURE_SLOTS, 'repeat', 'rotation', 'offset'],
    state,
    status: { ...state.status },
  };
}

/** Connect the pure controller to the selected-object inspector. */
export function attachTextureInspector(root, io) {
  const panel = root.querySelector('#texture-inspector');
  const controller = createTextureInspector();
  const status = panel?.querySelector('[data-texture-status]');
  const apply = panel?.querySelector('[data-action="apply-texture"]');
  const nameInput = panel?.querySelector('[data-texture-field="name"]');
  const materialSelect = panel?.querySelector('[data-texture-field="material"]');
  const fileInputs = [...(panel?.querySelectorAll('[data-texture-channel]') ?? [])];
  const encodeFile = async (file) => {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = '';
    for (let start = 0; start < bytes.length; start += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
    }
    return btoa(binary);
  };
  const refresh = () => {
    const state = controller.getState();
    const hasFiles = Object.values(state.files).some(Boolean);
    if (apply) apply.disabled = state.selectedObjectIds.length === 0 || (!state.preset && !state.materialId && !(hasFiles && nameInput?.value.trim()));
    if (status) status.textContent = state.status.message || (state.selectedObjectIds.length ? `${state.selectedObjectIds.length} part${state.selectedObjectIds.length === 1 ? '' : 's'} selected` : 'Select one or more parts, then choose a texture.');
  };
  for (const button of panel?.querySelectorAll('[data-texture-preset]') ?? []) {
    button.addEventListener('click', () => { controller.setPreset(button.dataset.texturePreset); refresh(); });
  }
  for (const input of fileInputs) {
    input.addEventListener('change', () => {
      const file = input.files?.[0];
      if (file) controller.setChannelFile(input.dataset.textureChannel, file);
      else controller.clearChannelFile(input.dataset.textureChannel);
      refresh();
    });
  }
  materialSelect?.addEventListener('change', () => { controller.setMaterial(materialSelect.value || null); refresh(); });
  nameInput?.addEventListener('input', refresh);
  const number = (name, fallback) => Number(panel?.querySelector(`[data-texture-field="${name}"]`)?.value) || fallback;
  const syncMapping = () => {
    controller.setSlot(Math.max(0, Math.trunc(number('slot', 0))));
    controller.setTransform({
      repeat: [number('repeat-x', 1), number('repeat-y', 1)],
      rotation: number('rotation', 0) * Math.PI / 180,
      offset: [number('offset-x', 0), number('offset-y', 0)],
    });
    refresh();
  };
  for (const input of panel?.querySelectorAll('.texture-transform input') ?? []) input.addEventListener('input', syncMapping);
  fetch('/api/textures').then((response) => response.json()).then((payload) => {
    for (const material of payload.materials ?? []) {
      const option = document.createElement('option');
      option.value = material.name;
      option.textContent = material.builtin ? `${material.name} (built-in)` : material.name;
      materialSelect?.append(option);
    }
  }).catch(() => {});
  apply?.addEventListener('click', async () => {
    controller.setStatus('loading', 'Importing texture…'); refresh();
    const state = controller.getState();
    const files = Object.entries(state.files).filter(([, file]) => file);
    if (files.length) {
      const maps = {};
      for (const [channel, file] of files) maps[channel] = { name: file.name, data: await encodeFile(file) };
      const response = await fetch('/api/textures', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: nameInput.value.trim(), maps, transform: state.transform }),
      });
      const payload = await response.json();
      if (!response.ok) { controller.setStatus('error', payload.error || 'Texture import failed.'); refresh(); return; }
      controller.setMaterial(payload.material.name);
    }
    const command = controller.buildApplyCommand();
    const sent = io.send({ type: 'annotate', data: { object_ids: command.params.object_ids, text: '', image: '', edit: { kind: command.name, params: command.params } } });
    controller.setStatus(sent ? 'ready' : 'error', sent ? 'Texture applied.' : 'Texture could not be sent.');
    refresh();
  });
  refresh();
  return { setSelection(ids) { controller.setSelection(ids); refresh(); }, controller };
}
