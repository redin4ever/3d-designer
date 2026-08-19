import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  TEXTURE_PRESETS,
  TEXTURE_SLOTS,
  createTextureInspector,
  renderTextureInspector,
} from '../src/texture-inspector.js';

test('exposes the six built-in texture presets and four supported slots', () => {
  assert.deepEqual(TEXTURE_PRESETS, ['wood', 'brick', 'concrete', 'stone', 'metal', 'plaster']);
  assert.deepEqual(TEXTURE_SLOTS, ['albedo', 'normal', 'roughness', 'metallic']);
});

test('starts with an empty selection, default slot zero, and editable transform', () => {
  const inspector = createTextureInspector();
  assert.deepEqual(inspector.getState(), {
    selectedObjectIds: [],
    slot: 0,
    preset: null,
    materialId: null,
    files: { albedo: null, normal: null, roughness: null, metallic: null },
    transform: { repeat: [1, 1], rotation: 0, offset: [0, 0] },
    status: { kind: 'idle', message: '' },
  });
});

test('selection accepts one or many object ids and builds an apply command payload', () => {
  const inspector = createTextureInspector({ selectedObjectIds: ['beam_04'] });
  inspector.setSelection(['beam_04', 'beam_05']);
  inspector.setPreset('wood');
  inspector.setSlot(2);
  assert.deepEqual(inspector.buildApplyCommand(), {
    name: 'apply_texture_material',
    params: {
      object_ids: ['beam_04', 'beam_05'],
      preset: 'wood',
      material_id: null,
      slot: 2,
      files: { albedo: null, normal: null, roughness: null, metallic: null },
      transform: { repeat: [1, 1], rotation: 0, offset: [0, 0] },
    },
  });
});

test('renders reusable materials, controls, and disabled/error states as a DOM-light model', () => {
  const model = renderTextureInspector({
    selectedObjectIds: ['part-a', 'part-b'],
    materials: [{ id: 'mat-1', name: 'Warm Wood' }],
    status: { kind: 'error', message: 'Unsupported file type' },
    disabled: true,
  });
  assert.equal(model.type, 'texture-inspector');
  assert.equal(model.disabled, true);
  assert.equal(model.selectionCount, 2);
  assert.deepEqual(model.presets, TEXTURE_PRESETS);
  assert.deepEqual(model.materials, [{ id: 'mat-1', name: 'Warm Wood' }]);
  assert.deepEqual(model.fileAccept, '.png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp');
  assert.deepEqual(model.controls, ['albedo', 'normal', 'roughness', 'metallic', 'repeat', 'rotation', 'offset']);
  assert.deepEqual(model.status, { kind: 'error', message: 'Unsupported file type' });
});

test('accepts only png, jpeg, and webp channel files and preserves loading state', () => {
  const inspector = createTextureInspector();
  assert.equal(inspector.setChannelFile('albedo', { name: 'wall.webp', type: 'image/webp' }), true);
  assert.equal(inspector.setChannelFile('normal', { name: 'normal.tiff', type: 'image/tiff' }), false);
  inspector.setStatus('loading', 'Loading texture…');
  assert.equal(inspector.getState().files.albedo.name, 'wall.webp');
  assert.deepEqual(inspector.getState().status, { kind: 'loading', message: 'Loading texture…' });
});

test('updates repeat, rotation, and offset without dropping unrelated values', () => {
  const inspector = createTextureInspector();
  inspector.setTransform({ repeat: [3, 2], rotation: 45, offset: [-0.25, 0.5] });
  assert.deepEqual(inspector.getState().transform, {
    repeat: [3, 2],
    rotation: 45,
    offset: [-0.25, 0.5],
  });
});
