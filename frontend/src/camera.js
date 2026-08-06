// The orbit camera's state and arithmetic, with no canvas and no DOM.
//
// This lives apart from scene-renderer.js for one reason: that file's own header says it is
// "exercised by eye, not by node:test", and being exercised by eye is how it shipped a
// camera you could only turn left and right. Dragging up did nothing and the wheel did
// nothing, because `pointermove` read `clientX` and never `clientY`, the tilt was a module
// constant, and there was no `wheel` listener at all. None of that is a drawing concern —
// it is arithmetic on three numbers, and arithmetic can be tested.
//
// So the split is: everything here is pure and covered by frontend/tests/camera.test.js;
// what stays in scene-renderer.js is genuinely about pixels.

/** Never let the camera reach the pole. */
export const MAX_PITCH = Math.PI / 2 - 0.05;

/** Zoom bounds, as a multiplier on the auto-framed distance. */
export const MIN_ZOOM = 0.15;
export const MAX_ZOOM = 6;

/** Radians per pixel dragged. Same feel on both axes so a diagonal drag goes diagonally. */
export const DRAG_SENSITIVITY = 0.01;

/**
 * The opening view: slightly above the scene, looking down.
 *
 * Positive is above. The old fixed tilt was -0.5, which was chosen when the renderer was
 * projecting a Z-up world as if it were Y-up — with that bug fixed, the same number puts the
 * camera *under* the floor, so an opaque deck hides everything standing on it. The sign is
 * the whole content of this constant, and `defaultViewLooksDownOnTheGround` pins it.
 */
export const DEFAULT_PITCH = 0.5;

/** One wheel notch. Multiplicative, so zooming in and back out returns where it started. */
export const WHEEL_STEP = 1.1;

export function clamp(value, low, high) {
  return value < low ? low : value > high ? high : value;
}

export class OrbitCamera {
  constructor({ pitch = DEFAULT_PITCH } = {}) {
    this.yaw = 0;
    this.pitch = clamp(pitch, -MAX_PITCH, MAX_PITCH);
    this.zoom = 1;
  }

  /** Apply a drag in pixels. `dy` is the half that did not work at all. */
  drag(dx, dy) {
    this.yaw += dx * DRAG_SENSITIVITY;
    // Direct manipulation: the model follows the cursor. Drag down and the far side of the
    // object comes up over the top toward you, the way it would if you had a finger on it.
    // The opposite sign — the camera moving instead of the model — reads as inverted to
    // anyone who has used a 3D viewport, and it was wrong here on the first attempt.
    this.pitch = clamp(this.pitch + dy * DRAG_SENSITIVITY, -MAX_PITCH, MAX_PITCH);
  }

  /**
   * Zoom by wheel notches. Negative `deltaY` is scroll-up, which every 3D tool in
   * existence treats as zoom *in* — so the multiplier has to invert it.
   */
  zoomByWheel(deltaY) {
    const notches = deltaY / 100;
    this.zoom = clamp(this.zoom * WHEEL_STEP ** notches, MIN_ZOOM, MAX_ZOOM);
  }

  /** Discrete zoom, for keyboard and buttons. `steps` > 0 zooms out. */
  zoomBySteps(steps) {
    this.zoom = clamp(this.zoom * WHEEL_STEP ** steps, MIN_ZOOM, MAX_ZOOM);
  }

  reset() {
    this.yaw = 0;
    this.pitch = DEFAULT_PITCH;
    this.zoom = 1;
  }

  /**
   * Camera distance for a scene of the given bounding radius.
   *
   * The framing (`radius * 2.6 + 1`) is what the renderer already computed per frame, kept
   * exactly so an unzoomed view is pixel-identical to before. Zoom scales it.
   */
  distanceFor(radius) {
    return (radius * 2.6 + 1) * this.zoom;
  }
}

/**
 * Blender's world is **Z-up**; this renderer projects as if **Y** were up. Without this
 * conversion the whole scene is drawn rotated 90° about X — an 8x8 m floor, which is wide
 * in world X and Y and thin in world Z, comes out as a tall thin wall. That is exactly what
 * `forge3d run` showed the first time it had geometry in it: a deck standing on its edge.
 *
 * Right-handed both sides: world +Z (up) becomes view +Y (up), and world +Y (away from the
 * viewer in Blender's front view) becomes view -Z. Getting the sign of that third component
 * wrong mirrors the scene front-to-back, which looks plausible and puts the far side of
 * every object in front of the near side under the painter's sort.
 */
export function zUpToYUp([x, y, z]) {
  return [x, z, -y];
}

/**
 * Lambert shading from a face normal, as a 0..1 factor.
 *
 * Flat grey fills with no shading make a mesh unreadable — every face the same value, so a
 * staircase is a grey blob and only its edges say anything. This is the cheapest thing that
 * makes form legible, and it needs no light rig: a fixed headlight-ish direction, and the
 * absolute value of the dot product so a triangle facing away is lit like one facing toward
 * (this renderer has no back-face culling, and an unlit back face reads as a hole).
 */
export function shadeFactor(normal, { ambient = 0.35, light = [0.4, 0.75, 0.5] } = {}) {
  const [nx, ny, nz] = normal;
  const len = Math.hypot(nx, ny, nz);
  if (!len) return ambient;
  const [lx, ly, lz] = light;
  const llen = Math.hypot(lx, ly, lz) || 1;
  const dot = Math.abs((nx * lx + ny * ly + nz * lz) / (len * llen));
  return clamp(ambient + (1 - ambient) * dot, 0, 1);
}

/** Face normal of a triangle, unnormalised length being fine for `shadeFactor`. */
export function triangleNormal(a, b, c) {
  const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
  return [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
}

/**
 * Split a triangle until no piece spans more depth than `maxExtent`, returning the pieces.
 *
 * The painter's algorithm sorts whole triangles by their average depth and draws far ones
 * first. That is only sound when a triangle is small relative to the depth differences it
 * has to resolve — and an 8x8 m floor is two triangles spanning the entire scene. Their
 * average depth lands mid-scene, so the near half of the floor sorts *in front of* a
 * staircase standing on it and paints straight over it. A user watching from an angle sees
 * the deck slicing through the railing, which is exactly what was reported.
 *
 * Subdividing at the edge midpoints is the cheap correct-enough answer for a Canvas2D
 * renderer with no depth buffer: it costs nothing on the small triangles that make up most
 * of a mesh, and it turns the handful of huge ones into pieces whose depth ordering the
 * sort can actually get right. It is not a general solution — genuinely interpenetrating
 * triangles still need splitting along their intersection, which is a BSP, not this — but
 * those are a defect the product reports rather than geometry it is asked to draw.
 *
 * `maxDepth` bounds the recursion so a triangle seen almost edge-on cannot subdivide
 * forever: 4^5 = 1024 pieces is already far past the point of visible improvement.
 */
export function subdivideForDepth(a, b, c, maxExtent, maxDepth = 5) {
  const extent = Math.max(a[2], b[2], c[2]) - Math.min(a[2], b[2], c[2]);
  if (maxDepth <= 0 || extent <= maxExtent) return [[a, b, c]];

  const mid = (p, q) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2];
  const ab = mid(a, b);
  const bc = mid(b, c);
  const ca = mid(c, a);

  return [
    ...subdivideForDepth(a, ab, ca, maxExtent, maxDepth - 1),
    ...subdivideForDepth(ab, b, bc, maxExtent, maxDepth - 1),
    ...subdivideForDepth(ca, bc, c, maxExtent, maxDepth - 1),
    ...subdivideForDepth(ab, bc, ca, maxExtent, maxDepth - 1),
  ];
}

/**
 * Grow a projected triangle outward from its centroid by roughly `pixels`.
 *
 * Canvas antialiases every fill independently, so two triangles sharing an edge each cover
 * about half the boundary pixel and the background shows through as a hairline. Across a
 * subdivided floor that is a visible grid of cracks.
 *
 * The obvious fix — stroking each piece in its own colour to cover the seam — is what
 * produced the black lines a user reported: a stroke straddles the path, so the shared band
 * gets painted by *both* neighbours, and any colour composited twice comes out darker than
 * the surface it was meant to match. Overlapping the fills has no such double-count. Where
 * two triangles genuinely meet at an object's edge the overlap is sub-pixel and invisible.
 */
export function inflateTriangle(a, b, c, pixels = 0.5) {
  const cx = (a[0] + b[0] + c[0]) / 3;
  const cy = (a[1] + b[1] + c[1]) / 3;
  const push = (p) => {
    const dx = p[0] - cx;
    const dy = p[1] - cy;
    const len = Math.hypot(dx, dy);
    if (len < 1e-9) return [p[0], p[1]];
    const k = (len + pixels) / len;
    return [cx + dx * k, cy + dy * k];
  };
  return [push(a), push(b), push(c)];
}

/**
 * Clip a triangle against the camera's near plane, returning 0, 1 or 2 triangles.
 *
 * `z` here is depth in view space, and the projection divides by `camDist - z`. A vertex at
 * or past `camDist` is level with or behind the eye: the divisor collapses to zero, and the
 * old code clamped it to 0.001, which flings that vertex thousands of pixels away and turns
 * its triangle into a huge sliver. Rotate or zoom a little and the vertex crosses back, and
 * the triangle snaps to something sane again — which is exactly the reported symptom,
 * triangles disappearing and reappearing while moving the camera.
 *
 * It is reachable because zoom scales the camera distance: at the closest zoom the camera
 * sits inside the scene's bounding radius, so geometry genuinely does pass behind it.
 * Clamping hides that; clipping handles it. Keeping the part in front and cutting the rest
 * at the plane is the whole of it.
 *
 * The four-vertex case really does need two triangles — dropping one is a hole in the
 * surface at exactly the moment the camera is closest to it.
 */
export function clipTriangleNear(a, b, c, limit) {
  const inside = (p) => p[2] < limit;
  const kept = [a, b, c].filter(inside);
  if (kept.length === 3) return [[a, b, c]];
  if (kept.length === 0) return [];

  const cross = (p, q) => {
    // Interpolate every component, not just z: the crossing point has to be on the edge.
    const t = (limit - p[2]) / (q[2] - p[2]);
    return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, limit];
  };

  const poly = [];
  const verts = [a, b, c];
  for (let i = 0; i < 3; i += 1) {
    const current = verts[i];
    const next = verts[(i + 1) % 3];
    if (inside(current)) poly.push(current);
    if (inside(current) !== inside(next)) poly.push(cross(current, next));
  }

  if (poly.length < 3) return [];
  if (poly.length === 3) return [[poly[0], poly[1], poly[2]]];
  return [
    [poly[0], poly[1], poly[2]],
    [poly[0], poly[2], poly[3]],
  ];
}
