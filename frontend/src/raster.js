// A depth-buffered software rasterizer.
//
// WHY THIS EXISTS, and what it replaces.
//
// The renderer used to draw with `ctx.fill()` per triangle, ordered back-to-front by each
// triangle's average depth — the painter's algorithm. That is not a visibility algorithm.
// It is an approximation that happens to work when triangles are small, separated, and
// never overlap in depth, and it has no correct answer otherwise:
//
//   * Two triangles whose depth ranges overlap have no valid ordering at all. Average depth
//     picks one, and which one it picks flips as the camera moves — so a surface in front
//     gets painted over by one behind it, vanishes, and comes back a frame later. That is
//     exactly the reported symptom: triangles disappearing and reappearing while moving the
//     camera.
//   * Three triangles can form a cycle where A occludes B occludes C occludes A. No
//     ordering exists. A sort cannot express the answer.
//   * A large triangle spanning the scene sorts by an average that describes none of it.
//
// Every patch for those is a patch for a symptom. Subdividing large triangles narrowed
// their depth ranges; inflating fills hid the seams subdivision created; stroking each
// piece to hide the seams painted the shared band twice and produced black lines. Three
// fixes, each caused by the last, all downstream of a sort that cannot be made correct.
//
// What real renderers do — every GPU since the 1990s, and software renderers before them —
// is resolve visibility **per pixel** instead of per triangle. Keep a depth value for each
// pixel; when a triangle covers that pixel, compare and keep the nearer one. Draw order
// stops mattering entirely, which is why the sort, the subdivision and the inflation are
// all gone: an algorithm that is correct needs no tie-breaking.
//
// The other classical answers were considered. A BSP tree (Doom, Quake) gives a provably
// correct back-to-front order for any camera, but it must be rebuilt whenever geometry
// changes — and geometry changing constantly is the entire point of this product. Newell's
// algorithm splits triangles at their depth conflicts, which is the same idea as a BSP with
// worse constants. A depth buffer needs no precomputation and does not care what moved.
//
// PERSPECTIVE. Depth is stored as 1/w (`invW`), not as view-space z. Screen-space linear
// interpolation of z is wrong under a perspective divide — it bends surfaces and makes
// coplanar geometry z-fight in bands. 1/w *is* linear in screen space, which is why every
// hardware pipeline interpolates it and compares that. Nearer is larger.

/**
 * A colour+depth+id target. Plain typed arrays, so this is testable with no canvas at all.
 *
 * `ids` is the picking channel — which object owns each pixel — written in the same inner
 * loop and behind the same depth test as the colour. Picking therefore returns the object the
 * depth test already chose, instead of a second opinion from a ray cast. See picking.js for
 * why two answers to "what is visible" is worse than one.
 */
export function createFrame(width, height) {
  return {
    width,
    height,
    color: new Uint8ClampedArray(width * height * 4),
    depth: new Float32Array(width * height), // 1/w, 0 = nothing drawn (infinitely far)
    ids: new Int32Array(width * height), // 0 = no object here (picking.NOTHING)
  };
}

/** Fill the whole frame with a background colour and reset every depth and id. */
export function clearFrame(frame, [r, g, b]) {
  const { color, depth, ids } = frame;
  for (let i = 0; i < depth.length; i += 1) {
    const o = i * 4;
    color[o] = r;
    color[o + 1] = g;
    color[o + 2] = b;
    color[o + 3] = 255;
    depth[i] = 0;
    // Cleared with the depth, never separately. An id left behind keeps a deleted object
    // pickable in the space it used to occupy until something is drawn over it.
    if (ids) ids[i] = 0;
  }
}

/**
 * Rasterize one triangle with a depth test.
 *
 * Vertices are `[screenX, screenY, invW]`. Flat-shaded: one colour for the whole triangle,
 * which is all this renderer needs and keeps the inner loop to a compare and four writes.
 *
 * Returns the number of pixels actually written, which is what makes the depth test
 * testable — "the far triangle wrote nothing" is the assertion that matters.
 *
 * `id` is optional and defaults to 0 ("no object here"). This renderer also draws things that
 * are not scene objects, and keeping it optional is what lets every existing caller and every
 * existing test in raster.test.js stay exactly as it was.
 */
export function drawTriangle(frame, a, b, c, [r, g, b_, ], id = 0) {
  const { width, height, color, depth, ids } = frame;

  // Signed area via the cross product. Zero means degenerate — a triangle seen exactly
  // edge-on covers no pixels, and dividing by it would produce NaN barycentrics that
  // compare false and silently skip, or worse, compare true and write garbage.
  const area = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]);
  if (area === 0 || !Number.isFinite(area)) return 0;

  // No back-face culling: this renderer draws open shells and unclosed meshes, where a
  // back face is the only thing between the viewer and the inside of an object. Winding is
  // normalised instead, so the barycentric signs work for either orientation.
  const sign = area < 0 ? -1 : 1;
  const invArea = 1 / (area * sign);

  const minX = Math.max(0, Math.floor(Math.min(a[0], b[0], c[0])));
  const maxX = Math.min(width - 1, Math.ceil(Math.max(a[0], b[0], c[0])));
  const minY = Math.max(0, Math.floor(Math.min(a[1], b[1], c[1])));
  const maxY = Math.min(height - 1, Math.ceil(Math.max(a[1], b[1], c[1])));
  if (minX > maxX || minY > maxY) return 0;

  let written = 0;
  for (let y = minY; y <= maxY; y += 1) {
    const py = y + 0.5;
    for (let x = minX; x <= maxX; x += 1) {
      const px = x + 0.5;

      // Edge functions. All three non-negative (after the winding normalisation) means the
      // sample point is inside.
      const w0 = ((b[0] - a[0]) * (py - a[1]) - (px - a[0]) * (b[1] - a[1])) * sign;
      if (w0 < 0) continue;
      const w1 = ((c[0] - b[0]) * (py - b[1]) - (px - b[0]) * (c[1] - b[1])) * sign;
      if (w1 < 0) continue;
      const w2 = ((a[0] - c[0]) * (py - c[1]) - (px - c[0]) * (a[1] - c[1])) * sign;
      if (w2 < 0) continue;

      // w1 weights a, w2 weights b, w0 weights c — the edge opposite each vertex.
      const invW = (w1 * a[2] + w2 * b[2] + w0 * c[2]) * invArea;

      const idx = y * width + x;
      if (invW <= depth[idx]) continue; // something nearer is already here

      depth[idx] = invW;
      // Inside the depth test, deliberately. Writing the id unconditionally would make the
      // last-drawn object pickable straight through everything in front of it.
      if (ids) ids[idx] = id;
      const o = idx * 4;
      color[o] = r;
      color[o + 1] = g;
      color[o + 2] = b_;
      color[o + 3] = 255;
      written += 1;
    }
  }
  return written;
}

/** Rasterize a UV-mapped triangle while preserving the same depth and picking channels. */
export function drawTexturedTriangle(frame, a, b, c, sample, id = 0, shade = 1) {
  const { width, height, color, depth, ids } = frame;
  const area = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]);
  if (area === 0 || !Number.isFinite(area)) return 0;
  const sign = area < 0 ? -1 : 1;
  const invArea = 1 / (area * sign);
  const minX = Math.max(0, Math.floor(Math.min(a[0], b[0], c[0])));
  const maxX = Math.min(width - 1, Math.ceil(Math.max(a[0], b[0], c[0])));
  const minY = Math.max(0, Math.floor(Math.min(a[1], b[1], c[1])));
  const maxY = Math.min(height - 1, Math.ceil(Math.max(a[1], b[1], c[1])));
  let written = 0;
  for (let y = minY; y <= maxY; y += 1) {
    for (let x = minX; x <= maxX; x += 1) {
      const px = x + 0.5;
      const py = y + 0.5;
      const w0 = ((b[0] - a[0]) * (py - a[1]) - (px - a[0]) * (b[1] - a[1])) * sign;
      const w1 = ((c[0] - b[0]) * (py - b[1]) - (px - b[0]) * (c[1] - b[1])) * sign;
      const w2 = ((a[0] - c[0]) * (py - c[1]) - (px - c[0]) * (a[1] - c[1])) * sign;
      if (w0 < 0 || w1 < 0 || w2 < 0) continue;
      const bary = [w1 * invArea, w2 * invArea, w0 * invArea];
      const invW = bary[0] * a[2] + bary[1] * b[2] + bary[2] * c[2];
      const idx = y * width + x;
      if (invW <= depth[idx]) continue;
      const u = (bary[0] * a[3] * a[2] + bary[1] * b[3] * b[2] + bary[2] * c[3] * c[2]) / invW;
      const v = (bary[0] * a[4] * a[2] + bary[1] * b[4] * b[2] + bary[2] * c[4] * c[2]) / invW;
      const rgba = sample([u, v]);
      depth[idx] = invW;
      if (ids) ids[idx] = id;
      const o = idx * 4;
      color[o] = rgba[0] * shade;
      color[o + 1] = rgba[1] * shade;
      color[o + 2] = rgba[2] * shade;
      color[o + 3] = rgba[3] ?? 255;
      written += 1;
    }
  }
  return written;
}
