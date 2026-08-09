/** Pure texture helpers used by the canvas renderer. */

export function normalizeModulo(value, modulus) {
  if (!Number.isFinite(value) || !Number.isFinite(modulus) || modulus <= 0) return 0;
  return ((value % modulus) + modulus) % modulus;
}

export function transformUv(uv, transform = {}) {
  const repeat = transform.repeat ?? [1, 1];
  const rotation = transform.rotation ?? 0;
  const offset = transform.offset ?? [0, 0];
  const x = uv[0] * repeat[0];
  const y = uv[1] * repeat[1];
  const cosine = Math.cos(rotation);
  const sine = Math.sin(rotation);
  return [
    normalizeModulo(x * cosine - y * sine + offset[0], 1),
    normalizeModulo(x * sine + y * cosine + offset[1], 1),
  ];
}

export function sampleRgba(texture, uv, options = {}) {
  const fallback = options.fallback ?? [0, 0, 0, 255];
  if (!texture || !texture.width || !texture.height || !texture.data) return [...fallback];
  const [u, v] = transformUv(uv, options);
  const x = Math.min(texture.width - 1, Math.floor(u * texture.width));
  const y = Math.min(texture.height - 1, Math.floor(v * texture.height));
  const offset = (y * texture.width + x) * 4;
  return Array.from(texture.data.slice(offset, offset + 4));
}

export function perspectiveCorrectUv(vertices, barycentric) {
  const denominator = vertices.reduce((sum, vertex, index) => sum + barycentric[index] * vertex.invW, 0);
  if (!denominator) return [0, 0];
  return [0, 1].map((axis) => vertices.reduce(
    (sum, vertex, index) => sum + barycentric[index] * vertex.uv[axis] * vertex.invW,
    0,
  ) / denominator);
}

export function resolveMaterialGroup(groups, triangleIndex) {
  return groups?.find((group) => (
    triangleIndex >= group.start && triangleIndex < group.start + group.count
  )) ?? null;
}

export function createTextureCache(options = {}) {
  const entries = new Map();
  const pending = new Map();
  const fallback = options.fallback ?? [0, 0, 0, 255];
  return {
    async load(source) {
      if (entries.has(source)) return entries.get(source);
      if (!pending.has(source)) {
        const request = Promise.resolve()
          .then(() => options.loadImage?.(source))
          .then((value) => {
            const result = value ?? fallback;
            entries.set(source, result);
            pending.delete(source);
            return result;
          })
          .catch(() => {
            pending.delete(source);
            entries.set(source, fallback);
            return fallback;
          });
        pending.set(source, request);
      }
      return pending.get(source);
    },
    get(source) {
      return entries.get(source) ?? fallback;
    },
    clear() {
      entries.clear();
      pending.clear();
    },
  };
}
