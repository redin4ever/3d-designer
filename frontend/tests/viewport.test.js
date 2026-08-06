// Contract: frontend/src/viewport.js — payload-to-BufferGeometry translation, and the
// cheap transform path the wire protocol distinguishes from a full mesh rebuild.
//
// No WebGL and no three.js here — buildGeometryBuffers is pure, and the renderer is a
// fake object satisfying the same createNode/updateTransform/removeNode/setHighlighted
// shape the real Canvas2D renderer (frontend/src/scene-renderer.js) implements. See
// frontend/CLAUDE.md "Why no three.js" for why this split exists.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildGeometryBuffers,
  createViewportState,
  applyMeshUpsert,
  applyTransformUpdate,
  applyObjectsRemoved,
  applyHighlight,
  clearViewportState,
} from '../src/viewport.js';

function quadMesh(objectId = 'quad-1') {
  return {
    object_id: objectId,
    positions: [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], // 4 vertices
    indices: [0, 1, 2, 0, 2, 3], // 2 triangles
    normals: null,
    uvs: null,
    materials: ['mat-a'],
    groups: [],
    triangle_count: 2,
  };
}

function moveTransform(objectId) {
  return { object_id: objectId, position: [1, 2, 3], quaternion: [0, 0, 0, 1], scale: [2, 2, 2] };
}

function makeFakeRenderer() {
  const calls = { createNode: [], updateTransform: [], removeNode: [], setHighlighted: [] };
  let nextHandleId = 0;
  return {
    calls,
    createNode(objectId, geometry, materials, groups) {
      const handle = { id: objectId, handleId: nextHandleId++, geometry, materials, groups, highlighted: false };
      calls.createNode.push({ objectId, geometry, materials, groups });
      return handle;
    },
    updateTransform(handle, position, quaternion, scale) {
      calls.updateTransform.push({ handle, position, quaternion, scale });
      handle.transform = { position, quaternion, scale };
    },
    removeNode(handle) {
      calls.removeNode.push(handle);
    },
    setHighlighted(handle, on) {
      calls.setHighlighted.push({ handle, on });
      handle.highlighted = on;
    },
  };
}

test('mesh_upsert builds geometry with positions.length === 3×vertexCount and indices.length === 3×triangleCount', () => {
  const geo = buildGeometryBuffers(quadMesh());
  assert.equal(geo.positions.length, 3 * 4, 'positions must hold exactly 3 floats per vertex');
  assert.equal(geo.indices.length, 3 * 2, 'indices must hold exactly 3 entries per triangle');
  assert.ok(geo.positions instanceof Float32Array, 'positions must be a typed array (maps straight onto BufferGeometry, no per-vertex churn)');
  assert.ok(geo.indices instanceof Uint32Array, 'indices must be a typed array');
});

test('buildGeometryBuffers rejects a triangle_count that disagrees with the index buffer', () => {
  const bad = quadMesh();
  bad.triangle_count = 99;
  assert.throws(() => buildGeometryBuffers(bad), /triangle_count/);
});

test('transform_update moves an existing node without rebuilding its buffers', () => {
  const state = createViewportState();
  const renderer = makeFakeRenderer();

  applyMeshUpsert(state, { meshes: [quadMesh('quad-1')] }, renderer);
  assert.equal(renderer.calls.createNode.length, 1, 'mesh_upsert must build geometry exactly once');
  const geometryAfterCreate = renderer.calls.createNode[0].geometry;
  const handleAfterCreate = state.nodes.get('quad-1').handle;

  applyTransformUpdate(state, { transforms: [moveTransform('quad-1')] }, renderer);

  assert.equal(
    renderer.calls.createNode.length,
    1,
    'a transform_update must never rebuild buffers — that is the cheap path the protocol distinguishes from mesh_upsert',
  );
  assert.equal(renderer.calls.updateTransform.length, 1);
  const call = renderer.calls.updateTransform[0];
  assert.strictEqual(call.handle, handleAfterCreate, 'the same node handle must be reused');
  assert.strictEqual(call.handle.geometry, geometryAfterCreate, 'the same geometry buffers must be reused, not rebuilt');
  assert.deepEqual(call.position, [1, 2, 3]);
  assert.deepEqual(call.quaternion, [0, 0, 0, 1]);
  assert.deepEqual(call.scale, [2, 2, 2]);
});

test('transform_update for an unknown object_id is a no-op, not a crash', () => {
  const state = createViewportState();
  const renderer = makeFakeRenderer();
  assert.doesNotThrow(() => applyTransformUpdate(state, { transforms: [moveTransform('ghost')] }, renderer));
  assert.equal(renderer.calls.updateTransform.length, 0);
});

test('objects_removed drops the node and frees its entry', () => {
  const state = createViewportState();
  const renderer = makeFakeRenderer();
  applyMeshUpsert(state, { meshes: [quadMesh('quad-1')] }, renderer);
  const handle = state.nodes.get('quad-1').handle;

  applyObjectsRemoved(state, { object_ids: ['quad-1'] }, renderer);

  assert.equal(state.nodes.has('quad-1'), false, 'the entry must be freed, not merely marked');
  assert.equal(renderer.calls.removeNode.length, 1);
  assert.strictEqual(renderer.calls.removeNode[0], handle);
});

test('highlight marks exactly the ids in the payload and clears the previous highlight', () => {
  const state = createViewportState();
  const renderer = makeFakeRenderer();
  applyMeshUpsert(state, { meshes: [quadMesh('a'), quadMesh('b'), quadMesh('c')] }, renderer);

  applyHighlight(state, { object_ids: ['a'] }, renderer);
  assert.deepEqual([...state.highlighted], ['a']);

  applyHighlight(state, { object_ids: ['b', 'c'] }, renderer);
  assert.deepEqual([...state.highlighted].sort(), ['b', 'c']);
  assert.equal(state.highlighted.has('a'), false, 'a highlight that accumulates makes "what just changed" useless');

  const offIds = renderer.calls.setHighlighted.filter((c) => c.on === false).map((c) => c.handle.id);
  const onIds = renderer.calls.setHighlighted.filter((c) => c.on === true).map((c) => c.handle.id);
  assert.ok(offIds.includes('a'), 'the previous highlight must be explicitly cleared on the renderer');
  assert.ok(onIds.includes('b') && onIds.includes('c'));
});

test('clearViewportState drops every node and the highlight, for a full_scene resync', () => {
  const state = createViewportState();
  const renderer = makeFakeRenderer();
  applyMeshUpsert(state, { meshes: [quadMesh('a'), quadMesh('b')] }, renderer);
  applyHighlight(state, { object_ids: ['a'] }, renderer);

  clearViewportState(state, renderer);

  assert.equal(state.nodes.size, 0);
  assert.equal(state.highlighted.size, 0);
  assert.equal(renderer.calls.removeNode.length, 2);
});

test('a mesh_upsert places the object where the server said, not at the origin', () => {
  // The server sends `transforms` on every mesh_upsert. applyMeshUpsert creates nodes at
  // the identity transform, so without applying them too, every new object renders at the
  // world origin and an already-positioned object snaps back there on its next topology
  // change — silently, with nothing logged. This is the "watch a build happen live"
  // journey being visibly wrong while every other test passes.
  const state = createViewportState();
  const moved = [];
  const renderer = {
    createNode: (id) => ({ id }),
    updateTransform: (handle, position) => moved.push([handle.id, position]),
    removeNode() {},
    setHighlighted() {},
  };
  const message = {
    type: 'mesh_upsert',
    seq: 3,
    meshes: [{
      object_id: 'wall-7',
      positions: [0, 0, 0, 1, 0, 0, 1, 1, 0],
      indices: [0, 1, 2],
      materials: ['m'],
      groups: [],
      triangle_count: 1,
    }],
    transforms: [{
      object_id: 'wall-7',
      position: [42, 0, 17],
      quaternion: [0, 0, 0, 1],
      scale: [1, 1, 1],
    }],
    object_ids: ['wall-7'],
  };

  applyMeshUpsert(state, message, renderer);
  applyTransformUpdate(state, { transforms: message.transforms }, renderer);

  assert.deepStrictEqual(
    state.nodes.get('wall-7').transform.position,
    [42, 0, 17],
    'the server-sent position was discarded; the object is at the origin',
  );
  assert.ok(moved.length > 0, 'updateTransform was never called for an upserted mesh');
});
