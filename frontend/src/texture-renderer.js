/** Pure texture helpers used by the canvas renderer. */

export function normalizeModulo(value, modulus) {
  return value;
}

export function transformUv(uv, transform = {}) {
  return [...uv];
}

export function sampleRgba(texture, uv, options = {}) {
  return [0, 0, 0, 0];
}

export function perspectiveCorrectUv(vertices, barycentric) {
  return [
    vertices[0].uv[0] * barycentric[0] + vertices[1].uv[0] * barycentric[1] + vertices[2].uv[0] * barycentric[2],
    vertices[0].uv[1] * barycentric[0] + vertices[1].uv[1] * barycentric[1] + vertices[2].uv[1] * barycentric[2],
  ];
}

export function resolveMaterialGroup(groups, triangleIndex) {
  return null;
}

export function createTextureCache(options = {}) {
  const entries = new Map();
  return {
    async load(source) {
      return entries.get(source) ?? options.fallback ?? [0, 0, 0, 0];
    },
    get(source) {
      return entries.get(source) ?? options.fallback ?? [0, 0, 0, 0];
    },
    clear() {
      entries.clear();
    },
  };
}
