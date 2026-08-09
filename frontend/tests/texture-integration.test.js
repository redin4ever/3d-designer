import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { buildGeometryBuffers } from '../src/viewport.js';

test('viewport rejects malformed UV buffers and keeps material definitions', () => {
  assert.throws(
    () => buildGeometryBuffers({
      object_id: 'bad-uv', positions: [0, 0, 0, 1, 0, 0, 0, 1, 0],
      indices: [0, 1, 2], uvs: [0, 0], triangle_count: 1,
    }),
    /uvs length/i,
  );
  const materialDefinitions = { wood: { name: 'wood', maps: [{ channel: 'albedo', path: '/textures/wood/albedo.png' }] } };
  const geometry = buildGeometryBuffers({
    object_id: 'textured', positions: [0, 0, 0, 1, 0, 0, 0, 1, 0],
    indices: [0, 1, 2], uvs: [0, 0, 1, 0, 0, 1], triangle_count: 1,
    materials: ['wood'], material_definitions: materialDefinitions,
  });
  assert.deepEqual(geometry.materialDefinitions, materialDefinitions);
});

test('the selected-object panel visibly wires the texture inspector', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const main = readFileSync(new URL('../src/main.js', import.meta.url), 'utf8');
  const renderer = readFileSync(new URL('../src/scene-renderer.js', import.meta.url), 'utf8');
  assert.match(html, /id="texture-inspector"/);
  assert.match(html, /texture-inspector\.css/);
  assert.match(main, /attachTextureInspector/);
  assert.match(renderer, /sampleTexture/);
});
