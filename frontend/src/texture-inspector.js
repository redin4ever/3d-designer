// Texture inspector contract stub. The controller is intentionally DOM-light so the
// main editor can render it into any inspector surface without coupling state to markup.

export const TEXTURE_PRESETS = [
  'wood',
  'brick',
  'concrete',
  'stone',
  'metal',
  'plaster',
];

export const TEXTURE_SLOTS = ['albedo', 'normal', 'roughness', 'metallic'];

export function createTextureInspector() {
  throw new Error('texture inspector not implemented');
}

export function renderTextureInspector() {
  throw new Error('texture inspector not implemented');
}
