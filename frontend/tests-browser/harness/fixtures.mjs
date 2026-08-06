// Canned wire messages, shaped exactly the way src/viewer/server.py::_encode emits them:
// `json.dumps(dataclasses.asdict(message))` over contracts.wire.ServerMessage, so EVERY
// field is present on every message (`meshes`, `transforms`, `object_ids`, `text`,
// `data`), never just the ones that matter. A fixture that omits the empty fields would
// let a frontend bug that depends on their absence pass here and fail against the real
// server.

/** contracts.wire.ServerMessage with its dataclass defaults filled in, like asdict does. */
export function serverMessage(type, seq, fields = {}) {
  return {
    type,
    seq,
    meshes: [],
    transforms: [],
    object_ids: [],
    text: '',
    data: {},
    ...fields,
  };
}

/** A unit cube centred on the origin: 8 vertices, 12 triangles — a valid MeshPayload. */
export function cube(objectId) {
  return {
    object_id: objectId,
    positions: [
      -0.5, -0.5, -0.5, 0.5, -0.5, -0.5, 0.5, 0.5, -0.5, -0.5, 0.5, -0.5,
      -0.5, -0.5, 0.5, 0.5, -0.5, 0.5, 0.5, 0.5, 0.5, -0.5, 0.5, 0.5,
    ],
    indices: [
      0, 1, 2, 0, 2, 3, 4, 6, 5, 4, 7, 6, 0, 4, 5, 0, 5, 1,
      3, 2, 6, 3, 6, 7, 0, 3, 7, 0, 7, 4, 1, 5, 6, 1, 6, 2,
    ],
    normals: null,
    uvs: null,
    materials: ['shell'],
    groups: [],
    triangle_count: 12,
  };
}

const IDENTITY_QUAT = [0, 0, 0, 1];

export function transform(objectId, position) {
  return { object_id: objectId, position, quaternion: IDENTITY_QUAT, scale: [1, 1, 1] };
}

export const SCENE_OBJECT_IDS = Object.freeze(['wall.north', 'wall.south']);

/**
 * What src/viewer/server.py sends on connect: HELLO, then the full scene. Two cubes so a
 * blank canvas and a drawn one are unmistakably different when the pixels are read back.
 */
export const FULL_SCENE_GREETING = Object.freeze([
  serverMessage('hello', 0, { data: { wire_version: 1, scene_id: 'smoke', unit_scale: 1.0 } }),
  serverMessage('full_scene', 1, {
    meshes: SCENE_OBJECT_IDS.map(cube),
    transforms: [transform('wall.north', [-1.2, 0, 0]), transform('wall.south', [1.2, 0, 0])],
  }),
  serverMessage('phase', 2, { text: 'shell' }),
  serverMessage('log', 3, { text: 'created wall.north' }),
  serverMessage('log', 4, { text: 'created wall.south' }),
  serverMessage('highlight', 5, { object_ids: ['wall.south'] }),
]);

/** A connected server that has nothing to show yet — the control for the pixel check. */
export const EMPTY_GREETING = Object.freeze([
  serverMessage('hello', 0, { data: { wire_version: 1, scene_id: 'smoke-empty' } }),
  serverMessage('full_scene', 1, {}),
]);

/** Answers a REQUEST_FULL_SCENE the way the real handler does, so a resync terminates. */
export function replyToClient(message) {
  if (message?.type === 'request_full_scene') return [FULL_SCENE_GREETING[1]];
  return [];
}
