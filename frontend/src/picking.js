// Which object is under that pixel (Q-04, Q-06, Q-25).
//
// WHY THIS READS THE DEPTH BUFFER RATHER THAN CASTING A RAY.
//
// The obvious way to answer "what did the operator click on" is to build a ray through the
// cursor and intersect it with the scene. It is also a second, independent answer to a
// question the renderer already answers every frame — and two answers to "what is visible"
// disagree eventually. When they do, the operator clicks one thing and sees a different one
// highlighted, intermittently, in a way that depends on the camera angle. That is the same
// class of bug as the painter's algorithm this renderer already threw out (raster.js's
// header): an approximation right often enough to ship and wrong often enough to be maddening.
//
// So raster.js writes the object's id into an `ids` channel in the same inner loop, behind the
// same depth test, as the colour. Picking is then a single array read that returns the object
// the depth test chose. It cannot disagree with what is on screen, because it *is* what is on
// screen. That is Q-25's "instant and exact", and it costs one Int32Array write per surviving
// pixel — no traversal, no acceleration structure, nothing to rebuild when geometry changes,
// which matters because geometry changing constantly is this product's entire premise.
//
// The consequence worth knowing: you can only pick what you can see. An object fully hidden
// behind another has no pixel, and no amount of clicking selects it. That is Q-06's answer
// ("the nearest one") followed to its conclusion, and it is why pickInPath cannot return
// something occluded by the very thing you circled.

/** No object owns this pixel. Reserved — createIdIndex never allots it. */
export const NOTHING = 0;

/**
 * A stable string <-> integer map for the picking channel.
 *
 * Everything else in this product names objects with the string id from the wire protocol,
 * but a per-pixel channel has to hold a number. This is that translation, and its two
 * guarantees are what keep picking honest:
 *
 * - **Stable** — an object keeps its number for as long as it exists, so an id read this
 *   frame still resolves the next one.
 * - **Never reused** — `forget` retires a number permanently. A long build creates and
 *   deletes constantly, and recycling would let a pick that was in flight when an object was
 *   deleted resolve to whatever took its place: a click landing on the wrong object,
 *   occasionally, and never reproducibly.
 *
 * Monotonic from 1, so 0 stays free for NOTHING. At one number per object ever created, an
 * Int32Array runs out after two billion; a session that creates that many has other problems.
 */
export function createIdIndex() {
  const byObject = new Map();
  const byId = new Map();
  let next = 1;

  return {
    /** This object's number, allotting one the first time it is asked for. */
    idFor(objectId) {
      const existing = byObject.get(objectId);
      if (existing !== undefined) return existing;
      const id = next;
      next += 1;
      byObject.set(objectId, id);
      byId.set(id, objectId);
      return id;
    },

    /** The object a number names, or null if it never named one or has been forgotten. */
    objectFor(id) {
      return byId.get(id) ?? null;
    },

    /** Retire an object's number. That number is never handed out again. */
    forget(objectId) {
      const id = byObject.get(objectId);
      if (id === undefined) return;
      byObject.delete(objectId);
      byId.delete(id);
    },

    get size() {
      return byObject.size;
    },
  };
}

/**
 * The object id at one pixel, or NOTHING.
 *
 * Out of bounds is NOTHING rather than undefined: a pointer leaves the canvas mid-drag all the
 * time, and a typed-array read past the end returns undefined, which would travel onward as an
 * object id that nothing resolves and no error names.
 *
 * @param {{width: number, height: number, ids: Int32Array}} frame
 */
export function pickAt(frame, x, y) {
  const { width, height, ids } = frame;
  if (!ids) return NOTHING;
  const px = Math.floor(x);
  const py = Math.floor(y);
  if (px < 0 || py < 0 || px >= width || py >= height) return NOTHING;
  return ids[py * width + px];
}

/**
 * Whether a point falls inside a closed polygon, by ray casting.
 *
 * A lasso drawn by hand is not convex, so a convex-hull approximation would quietly select
 * things the operator deliberately drew around — which is most of what a lasso is for.
 *
 * @param {ReadonlyArray<readonly [number, number]>} path
 */
export function pointInPolygon(path, x, y) {
  if (!path || path.length < 3) return false;
  let inside = false;
  for (let i = 0, j = path.length - 1; i < path.length; j = i, i += 1) {
    const [xi, yi] = path[i];
    const [xj, yj] = path[j];
    // Half-open comparison on y: a vertex exactly level with the ray is counted by one of its
    // two edges and not both, which is what stops a point level with a vertex being reported
    // outside a polygon it is plainly inside.
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

/**
 * Every visible object with at least `minPixels` pixels inside a closed path (Q-04).
 *
 * Scans the path's bounding box rather than the whole frame, so circling a small region costs
 * what that region costs. A full-frame scan at a real canvas size is half a million
 * point-in-polygon tests per drag frame, and the lasso is redrawn on every pointer move.
 *
 * A path with fewer than three points selects nothing. A click registers as a one-point drag,
 * and treating a zero-area path as "everything inside it" would make a stray click select the
 * whole scene.
 *
 * @param {{width: number, height: number, ids: Int32Array}} frame
 * @param {ReadonlyArray<readonly [number, number]>} path
 * @param {{minPixels?: number}} [options] raise `minPixels` to ignore objects the loop only
 *   grazed. The default of 1 is the forgiving reading — you circled roughly, you get what you
 *   drew around.
 * @returns {number[]} ids, in the order first met scanning top-left to bottom-right
 */
export function pickInPath(frame, path, options = {}) {
  const { minPixels = 1 } = options;
  if (!path || path.length < 3) return [];

  const { width, height, ids } = frame;
  if (!ids) return [];

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const [px, py] of path) {
    if (px < minX) minX = px;
    if (px > maxX) maxX = px;
    if (py < minY) minY = py;
    if (py > maxY) maxY = py;
  }

  const x0 = Math.max(0, Math.floor(minX));
  const x1 = Math.min(width - 1, Math.ceil(maxX));
  const y0 = Math.max(0, Math.floor(minY));
  const y1 = Math.min(height - 1, Math.ceil(maxY));
  if (x0 > x1 || y0 > y1) return [];

  const counts = new Map();
  for (let y = y0; y <= y1; y += 1) {
    const row = y * width;
    for (let x = x0; x <= x1; x += 1) {
      const id = ids[row + x];
      if (id === NOTHING) continue;
      if (!pointInPolygon(path, x + 0.5, y + 0.5)) continue;
      counts.set(id, (counts.get(id) ?? 0) + 1);
    }
  }

  const picked = [];
  for (const [id, count] of counts) {
    if (count >= minPixels) picked.push(id);
  }
  return picked;
}

/**
 * A pointer position, in frame pixels.
 *
 * The canvas backing store is sized in device pixels and laid out in CSS pixels, and on a 2x
 * display those differ by a factor of two. Scaling by the ratio between the two — rather than
 * reading `devicePixelRatio`, which changes mid-session when a window is dragged between
 * monitors — keeps this correct with nothing to keep in sync.
 *
 * The result may fall outside the frame, and deliberately: `pickAt` reads that as NOTHING, so
 * a pointer leaving the canvas needs no special case at the call site.
 *
 * @param {{width: number, height: number}} frame
 * @param {{left: number, top: number, width: number, height: number}} rect
 *   the canvas's `getBoundingClientRect()`
 * @returns {[number, number]}
 */
export function cssToFrame(frame, rect, clientX, clientY) {
  const scaleX = rect.width === 0 ? 0 : frame.width / rect.width;
  const scaleY = rect.height === 0 ? 0 : frame.height / rect.height;
  return [(clientX - rect.left) * scaleX, (clientY - rect.top) * scaleY];
}
