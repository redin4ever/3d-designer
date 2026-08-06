// The real renderer-like object, implemented on Canvas2D — no three.js, no network
// fetch, no dependency (see frontend/CLAUDE.md "Why no three.js"). Implements the exact
// four-method shape frontend/src/viewport.js drives against a fake in tests:
// createNode / updateTransform / removeNode / setHighlighted, plus start()/stop() for
// its own render loop.
//
// Most of this file is a browser adapter and is exercised by eye. The camera is NOT: it
// lives in ./camera.js and is covered by frontend/tests/camera.test.js. That split exists
// because this file's "exercised by eye" exemption used to include the camera, and a user
// found what eyes miss — the view turned left and right and would not tilt or zoom, since
// `pointermove` read only `clientX`, the tilt was the module constant below, and nothing
// listened for `wheel` at all.
//
// Colors are never hard-coded here: every stroke/fill comes from getComputedStyle of a
// `--token` custom property defined in tokens.css, read once per resize/theme change and
// cached as opaque CSS color strings — translucency is done with ctx.globalAlpha rather
// than hand-parsed rgba(), so no hex digit ever appears as a literal in this file. The
// fallbacks below are CSS color keywords, not hex, for the same reason. That is what
// lets frontend/tests/tokens.test.js scan this file for a raw hex literal and find none.

import {
  OrbitCamera,
  shadeFactor,
  subdivideForDepth,
  triangleNormal,
  zUpToYUp,
} from './camera.js';

function readColor(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function rotateY([x, y, z], angle) {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return [x * c + z * s, y, -x * s + z * c];
}

function rotateX([x, y, z], angle) {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return [x, y * c - z * s, y * s + z * c];
}

/** Standard v' = v + 2w(q×v) + 2q×(q×v), the per-node orientation from TRANSFORM_UPDATE. */
function rotateByQuaternion([x, y, z], [qx, qy, qz, qw]) {
  const c1x = qy * z - qz * y;
  const c1y = qz * x - qx * z;
  const c1z = qx * y - qy * x;
  const c2x = qy * c1z - qz * c1y;
  const c2y = qz * c1x - qx * c1z;
  const c2z = qx * c1y - qy * c1x;
  return [x + 2 * qw * c1x + 2 * c2x, y + 2 * qw * c1y + 2 * c2y, z + 2 * qw * c1z + 2 * c2z];
}

// The view no longer turns on its own. It used to rotate one slow turn per 40s as a
// "this is live" cue, which is a cue nobody asked for and which makes a model you are
// trying to look at drift out from under you. Liveness is the action log's job.

export class SceneRenderer {
  /** @param {HTMLCanvasElement} canvas */
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.nodes = new Map();
    this._nextHandleId = 0;
    this._running = false;
    this._rafId = null;
    this._lastFrameAt = 0;
    this.camera = new OrbitCamera();
    this._dragging = false;
    this._lastPointerX = 0;
    this._lastPointerY = 0;
    this._colors = { ink: 'white', muted: 'gray', accent: 'slateblue', canvas: 'black' };
    this._bindPointer();
    this._resizeObserver = new ResizeObserver(() => this._resize());
    this._resizeObserver.observe(canvas);
    this._resize();
  }

  refreshTheme() {
    this._colors = {
      ink: readColor('--ink', this._colors.ink),
      muted: readColor('--muted', this._colors.muted),
      accent: readColor('--accent', this._colors.accent),
      canvas: readColor('--canvas', this._colors.canvas),
    };
  }

  createNode(objectId, geometry, materials, groups) {
    const handle = {
      id: objectId,
      handleId: this._nextHandleId++,
      geometry,
      materials,
      groups,
      highlighted: false,
      transform: { position: [0, 0, 0], quaternion: [0, 0, 0, 1], scale: [1, 1, 1] },
    };
    this.nodes.set(handle.handleId, handle);
    return handle;
  }

  updateTransform(handle, position, quaternion, scale) {
    handle.transform = { position, quaternion, scale };
  }

  removeNode(handle) {
    this.nodes.delete(handle.handleId);
  }

  setHighlighted(handle, on) {
    handle.highlighted = on;
  }

  start() {
    if (this._running) return;
    this.refreshTheme();
    this._running = true;
    this._lastFrameAt = performance.now();
    const tick = (now) => {
      if (!this._running) return;
      this._lastFrameAt = now;
      this._draw();
      this._rafId = requestAnimationFrame(tick);
    };
    this._rafId = requestAnimationFrame(tick);
  }

  stop() {
    this._running = false;
    if (this._rafId) cancelAnimationFrame(this._rafId);
    this._rafId = null;
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(1, Math.round(rect.width * dpr));
    this.canvas.height = Math.max(1, Math.round(rect.height * dpr));
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  _bindPointer() {
    this.canvas.addEventListener('pointerdown', (event) => {
      this._dragging = true;
      this._lastPointerX = event.clientX;
      this._lastPointerY = event.clientY;
      this.canvas.setPointerCapture(event.pointerId);
    });

    // Incremental deltas rather than "current minus drag-start", because the pitch clamp
    // makes the camera's state not a pure function of total displacement: drag past the
    // pole and back and an absolute mapping teleports the view.
    this.canvas.addEventListener('pointermove', (event) => {
      if (!this._dragging) return;
      this.camera.drag(event.clientX - this._lastPointerX, event.clientY - this._lastPointerY);
      this._lastPointerX = event.clientX;
      this._lastPointerY = event.clientY;
    });

    const release = () => {
      this._dragging = false;
    };
    this.canvas.addEventListener('pointerup', release);
    this.canvas.addEventListener('pointercancel', release);

    // `passive: false` and preventDefault, or the wheel zooms the model *and* scrolls the
    // page under it. Only over the canvas; the log beside it must still scroll normally.
    this.canvas.addEventListener(
      'wheel',
      (event) => {
        event.preventDefault();
        this.camera.zoomByWheel(event.deltaY);
      },
      { passive: false },
    );

    // A canvas is not focusable by default, so a keyboard user could reach the controls
    // beside the view and never the view itself. index.html gives it tabindex="0".
    this.canvas.addEventListener('keydown', (event) => {
      const step = event.shiftKey ? 40 : 12;
      const keys = {
        ArrowLeft: () => this.camera.drag(-step, 0),
        ArrowRight: () => this.camera.drag(step, 0),
        ArrowUp: () => this.camera.drag(0, -step),
        ArrowDown: () => this.camera.drag(0, step),
        '+': () => this.camera.zoomBySteps(-1),
        '=': () => this.camera.zoomBySteps(-1),
        '-': () => this.camera.zoomBySteps(1),
        _: () => this.camera.zoomBySteps(1),
        '0': () => this.camera.reset(),
      };
      const action = keys[event.key];
      if (!action) return;
      event.preventDefault();
      action();
    });
  }

  _worldVertices(handle) {
    const { positions } = handle.geometry;
    const { position, quaternion, scale } = handle.transform;
    const out = new Array(positions.length / 3);
    const orbit = this.camera.yaw;
    for (let i = 0; i < positions.length; i += 3) {
      let v = [positions[i] * scale[0], positions[i + 1] * scale[1], positions[i + 2] * scale[2]];
      v = rotateByQuaternion(v, quaternion);
      v = [v[0] + position[0], v[1] + position[1], v[2] + position[2]];
      // World space is Blender's, which is Z-up. Everything below this line — the orbit,
      // the projection, the painter's sort — assumes Y-up. Without the conversion an 8x8m
      // deck rendered as a wall standing on its edge, which is what the live view showed
      // the first time it had geometry in it.
      v = zUpToYUp(v);
      v = rotateY(v, orbit);
      v = rotateX(v, this.camera.pitch);
      out[i / 3] = v;
    }
    return out;
  }

  _draw() {
    const { ctx, canvas } = this;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    ctx.globalAlpha = 1;
    ctx.fillStyle = this._colors.canvas;
    ctx.fillRect(0, 0, width, height);

    if (this.nodes.size === 0) return;

    let radius = 1;
    const allWorld = new Map();
    for (const handle of this.nodes.values()) {
      const world = this._worldVertices(handle);
      allWorld.set(handle.handleId, world);
      for (const [x, y, z] of world) {
        radius = Math.max(radius, Math.hypot(x, y, z));
      }
    }
    const camDist = this.camera.distanceFor(radius);
    const focal = Math.min(width, height) * 0.9;
    const project = ([x, y, z]) => {
      const denom = camDist - z;
      const f = focal / (denom > 0.001 ? denom : 0.001);
      return [width / 2 + x * f, height / 2 - y * f, z];
    };

    // How much depth one triangle may span before the painter's sort stops being able to
    // order it correctly against its neighbours. Scaled to the scene so it means the same
    // thing for a doorknob and for a city block.
    const maxDepthSpan = radius * 0.12;

    const triangles = [];
    for (const handle of this.nodes.values()) {
      const world = allWorld.get(handle.handleId);
      const { indices } = handle.geometry;
      for (let i = 0; i < indices.length; i += 3) {
        const a = world[indices[i]];
        const b = world[indices[i + 1]];
        const c = world[indices[i + 2]];
        if (!a || !b || !c) continue;

        // Shade from the original triangle, not the pieces: subdivision is a depth-sorting
        // device and must not change how the surface is lit, or a floor would come out
        // patchy exactly where it happened to be split.
        const shade = shadeFactor(triangleNormal(a, b, c));

        const pieces = subdivideForDepth(a, b, c, maxDepthSpan);
        // Outline only a triangle that was NOT split. Stroking every piece would draw the
        // subdivision grid across the floor — a wireframe of an implementation detail.
        const outline = pieces.length === 1;

        for (const [pa, pb, pc] of pieces) {
          triangles.push({
            a: project(pa),
            b: project(pb),
            c: project(pc),
            avgZ: (pa[2] + pb[2] + pc[2]) / 3,
            shade,
            outline,
            highlighted: handle.highlighted,
          });
        }
      }
    }
    triangles.sort((t1, t2) => t1.avgZ - t2.avgZ); // painter's algorithm: far first

    for (const tri of triangles) {
      ctx.beginPath();
      ctx.moveTo(tri.a[0], tri.a[1]);
      ctx.lineTo(tri.b[0], tri.b[1]);
      ctx.lineTo(tri.c[0], tri.c[1]);
      ctx.closePath();
      if (tri.highlighted) {
        // The one accent-colored thing on screen: the latest change, unmistakably.
        ctx.fillStyle = this._colors.accent;
        ctx.strokeStyle = this._colors.accent;
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = tri.shade;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.stroke();
      } else {
        // Solid, shaded surfaces — not a 6%-alpha wireframe.
        //
        // The old fill was `globalAlpha = 0.06`, which meant every object was effectively
        // see-through: a staircase behind a deck showed straight through it, and the whole
        // scene read as a tangle of lines with no sense of which surface was in front. The
        // painter's sort was already doing the work; nothing was using it.
        //
        // Alpha rather than a computed colour because this file must not contain a colour
        // literal — `tests/tokens.test.js` scans it, and every colour comes from a CSS
        // custom property read through `getComputedStyle`. Compositing the token against
        // the canvas background at the shade factor is how a flat token becomes a lit
        // surface without ever naming a hex value here.
        ctx.fillStyle = this._colors.muted;
        ctx.globalAlpha = 1;
        ctx.fill();
        ctx.fillStyle = this._colors.canvas;
        ctx.globalAlpha = 1 - tri.shade;
        ctx.fill();

        if (tri.outline) {
          ctx.strokeStyle = this._colors.ink;
          ctx.lineWidth = 1;
          ctx.globalAlpha = 0.25;
          ctx.stroke();
        } else {
          // A subdivided piece gets no outline, but it does need its own edge painted in
          // its own colour: canvas antialiases each fill independently, so two abutting
          // triangles leave a hairline of background between them and a floor comes out
          // visibly cracked along every split.
          ctx.strokeStyle = this._colors.muted;
          ctx.lineWidth = 1;
          ctx.globalAlpha = 1;
          ctx.stroke();
          ctx.strokeStyle = this._colors.canvas;
          ctx.globalAlpha = 1 - tri.shade;
          ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = 1;
  }
}
