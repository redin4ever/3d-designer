// The live 3D view's state layer (Gate A 5.1, 5.3).
//
// Split on purpose: this file owns the payload -> BufferGeometry-shaped-buffer
// translation and the scene-graph bookkeeping (which object_id maps to which renderer
// handle), and nothing here touches a canvas, WebGL context, or three.js. That is what
// lets frontend/tests/viewport.test.js exercise the translation with a plain object
// standing in for the renderer — see "Why no three.js" in frontend/CLAUDE.md. The real
// renderer (frontend/src/scene-renderer.js) implements the same four-method shape
// (createNode/updateTransform/removeNode/setHighlighted) against a 2D canvas, and
// frontend/src/main.js is the only file that wires the two together.
//
// wire.py's own comment on MeshPayload is the reason for the typed-array conversion:
// "flat lists of floats/ints ... map straight onto BufferGeometry attributes ... with no
// per-vertex object churn, which is what keeps a thousands-of-objects scene responsive."

/**
 * Convert one wire MeshPayload into typed-array buffers.
 *
 * Pure and synchronous. Throws if the payload is internally inconsistent (indices not a
 * multiple of 3, or a triangle_count that disagrees with the index buffer) rather than
 * silently building a corrupt mesh — the same "measurement over guesswork" stance the
 * rest of this product takes (Gate A 11.3).
 *
 * @param {object} mesh a wire MeshPayload: object_id, positions, indices, normals?,
 *   uvs?, materials?, groups?, triangle_count
 * @returns {{positions: Float32Array, indices: Uint32Array, normals: Float32Array|null,
 *   uvs: Float32Array|null, vertexCount: number, triangleCount: number,
 *   materials: readonly string[], groups: readonly (readonly [number, number, number])[]}}
 */
export function buildGeometryBuffers(mesh) {
  const positions = Float32Array.from(mesh.positions ?? []);
  const indices = Uint32Array.from(mesh.indices ?? []);

  if (positions.length % 3 !== 0) {
    throw new Error(
      `mesh ${mesh.object_id ?? '?'}: positions length ${positions.length} is not a multiple of 3`,
    );
  }
  if (indices.length % 3 !== 0) {
    throw new Error(
      `mesh ${mesh.object_id ?? '?'}: indices length ${indices.length} is not a multiple of 3`,
    );
  }

  const vertexCount = positions.length / 3;
  const triangleCount = indices.length / 3;

  if (typeof mesh.triangle_count === 'number' && mesh.triangle_count !== triangleCount) {
    throw new Error(
      `mesh ${mesh.object_id ?? '?'}: triangle_count ${mesh.triangle_count} does not match the ` +
        `index buffer (${triangleCount} triangles) — the payload is internally inconsistent`,
    );
  }

  return {
    positions,
    indices,
    normals: mesh.normals ? Float32Array.from(mesh.normals) : null,
    uvs: mesh.uvs ? Float32Array.from(mesh.uvs) : null,
    vertexCount,
    triangleCount,
    materials: mesh.materials ?? [],
    groups: mesh.groups ?? [],
  };
}

/** A fresh, empty viewport scene graph. */
export function createViewportState() {
  return {
    /** @type {Map<string, {handle: unknown, transform: {position: number[], quaternion: number[], scale: number[]}}>} */
    nodes: new Map(),
    /** @type {Set<string>} exactly the object_ids the last HIGHLIGHT message named */
    highlighted: new Set(),
  };
}

const IDENTITY_TRANSFORM = Object.freeze({
  position: [0, 0, 0],
  quaternion: [0, 0, 0, 1],
  scale: [1, 1, 1],
});

/**
 * Apply a MESH_UPSERT: "new or topology-changed objects, with buffers" (wire.py). This
 * is the expensive path — it always rebuilds geometry, even for an id that already has
 * a node, because a topology change means the old buffers are no longer valid. A node
 * that only moved arrives as TRANSFORM_UPDATE instead; see applyTransformUpdate.
 *
 * @param {ReturnType<typeof createViewportState>} state
 * @param {{meshes: object[]}} message
 * @param {object} renderer createNode/updateTransform/removeNode/setHighlighted
 */
export function applyMeshUpsert(state, message, renderer) {
  for (const meshPayload of message.meshes ?? []) {
    const objectId = meshPayload.object_id;
    const existing = state.nodes.get(objectId);
    if (existing) {
      renderer.removeNode(existing.handle);
    }
    const geometry = buildGeometryBuffers(meshPayload);
    const handle = renderer.createNode(objectId, geometry, geometry.materials, geometry.groups);
    state.nodes.set(objectId, { handle, transform: IDENTITY_TRANSFORM });
    if (state.highlighted.has(objectId)) {
      renderer.setHighlighted(handle, true);
    }
  }
}

/**
 * Apply a TRANSFORM_UPDATE: "the cheap path — node transforms only, no buffers. The
 * common case" (wire.py). Must never call renderer.createNode — that is the entire
 * reason the wire protocol has two message types instead of one.
 *
 * An update naming an object_id with no existing node is a no-op: the operator's view
 * can only ever be a beat behind the scene, and a stray transform for an id that has not
 * arrived yet (or was already removed) is not an error worth surfacing as one.
 *
 * @param {ReturnType<typeof createViewportState>} state
 * @param {{transforms: object[]}} message
 * @param {object} renderer
 */
export function applyTransformUpdate(state, message, renderer) {
  for (const transform of message.transforms ?? []) {
    const entry = state.nodes.get(transform.object_id);
    if (!entry) continue;
    const { position, quaternion, scale = [1, 1, 1] } = transform;
    renderer.updateTransform(entry.handle, position, quaternion, scale);
    entry.transform = { position, quaternion, scale };
  }
}

/**
 * Apply OBJECTS_REMOVED: drop the node and free its map entry (not just hide it) so a
 * long run does not leak renderer handles for objects that no longer exist.
 *
 * @param {ReturnType<typeof createViewportState>} state
 * @param {{object_ids: string[]}} message
 * @param {object} renderer
 */
export function applyObjectsRemoved(state, message, renderer) {
  for (const objectId of message.object_ids ?? []) {
    const entry = state.nodes.get(objectId);
    if (!entry) continue;
    renderer.removeNode(entry.handle);
    state.nodes.delete(objectId);
    state.highlighted.delete(objectId);
  }
}

/**
 * Drop every node and clear the highlight set. Used when a FULL_SCENE snapshot arrives
 * (on connect, or after a resync) — the incoming snapshot is authoritative, so anything
 * the client currently holds that is not in it must not linger as a stale ghost.
 *
 * @param {ReturnType<typeof createViewportState>} state
 * @param {object} renderer
 */
export function clearViewportState(state, renderer) {
  for (const entry of state.nodes.values()) {
    renderer.removeNode(entry.handle);
  }
  state.nodes.clear();
  state.highlighted.clear();
}

/**
 * Apply HIGHLIGHT: "what just changed, so the operator can find it without hunting"
 * (wire.py, citing Gate A 5.3). Marks exactly the given ids and clears every previously
 * highlighted id — a highlight that accumulates makes "what just changed" useless within
 * a minute of a long-running build.
 *
 * @param {ReturnType<typeof createViewportState>} state
 * @param {{object_ids: string[]}} message
 * @param {object} renderer
 */
export function applyHighlight(state, message, renderer) {
  for (const objectId of state.highlighted) {
    const entry = state.nodes.get(objectId);
    if (entry) renderer.setHighlighted(entry.handle, false);
  }

  state.highlighted = new Set(message.object_ids ?? []);

  for (const objectId of state.highlighted) {
    const entry = state.nodes.get(objectId);
    if (entry) renderer.setHighlighted(entry.handle, true);
  }
}
