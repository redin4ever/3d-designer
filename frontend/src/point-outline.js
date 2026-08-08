/**
 * Paint a screen-space outline around visible pixels owned by `targetIds`.
 *
 * The picking buffer stays untouched: this is a presentation pass over the ImageData copy,
 * so the outline cannot make the background or a neighbouring part clickable.
 */
export function paintIdOutline(image, ids, width, height, targetIds, rgb, radius = 1) {
  const targets = targetIds instanceof Set ? targetIds : new Set(targetIds ?? []);
  if (targets.size === 0 || width < 1 || height < 1) return 0;

  const edgePixels = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      const id = ids[index];
      if (!targets.has(id)) continue;
      if (
        x === 0 ||
        y === 0 ||
        x === width - 1 ||
        y === height - 1 ||
        ids[index - 1] !== id ||
        ids[index + 1] !== id ||
        ids[index - width] !== id ||
        ids[index + width] !== id
      ) {
        edgePixels.push([x, y]);
      }
    }
  }

  const thickness = Math.max(1, Math.floor(radius));
  const painted = new Uint8Array(width * height);
  let count = 0;
  for (const [edgeX, edgeY] of edgePixels) {
    for (let dy = -thickness; dy <= thickness; dy += 1) {
      for (let dx = -thickness; dx <= thickness; dx += 1) {
        if (dx * dx + dy * dy > thickness * thickness) continue;
        const x = edgeX + dx;
        const y = edgeY + dy;
        if (x < 0 || y < 0 || x >= width || y >= height) continue;
        const index = y * width + x;
        const offset = index * 4;
        image[offset] = rgb[0];
        image[offset + 1] = rgb[1];
        image[offset + 2] = rgb[2];
        image[offset + 3] = 255;
        if (!painted[index]) {
          painted[index] = 1;
          count += 1;
        }
      }
    }
  }
  return count;
}
