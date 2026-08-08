// The real renderer-like object, implemented on Canvas2D — no three.js, no network
// fetch, no dependency (see frontend/CLAUDE.md "Why no three.js"). Implements the exact
// four-method shape frontend/src/viewport.js drives against a fake in tests:
// createNode / updateTransform / removeNode / setHighlighted, plus the operator's
// hovered/selected/focused emphasis and start()/stop() for its own render loop.
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

import { OrbitCamera, clipTriangleNear, shadeFactor, triangleNormal, zUpToYUp } from './camera.js';
import { paintIdOutline } from './point-outline.js';
import { clearFrame, createFrame, drawTriangle } from './raster.js';
import { createIdIndex } from './picking.js';

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
    // Named CSS colours as the pre-theme fallback, never hex: tests/tokens.test.js scans
    // every source file for a hex literal outside tokens.css and fails on one.
    this._colors = {
      ink: 'white',
      muted: 'gray',
      accent: 'slateblue',
      pointed: 'mediumslateblue',
      canvas: 'black',
      marked: 'gold',
    };
    this._frame = null;
    this._image = null;
    this._rgbCache = new Map();
    // Picking reads the id the depth test chose, so the renderer is the one place that
    // can assign these — see picking.js for why this is not a ray cast.
    this.ids = createIdIndex();
    this._focused = new Set();
    this._hovered = new Set();
    this._selected = new Set();
    this._probeCtx = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
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
      pointed: readColor('--accent-hover', this._colors.pointed),
      marked: readColor('--marked', this._colors.marked),
      canvas: readColor('--canvas', this._colors.canvas),
    };
    this._rgbCache.clear(); // the tokens just changed; the resolved bytes are stale
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
    // Retire the picking id with the node. Reusing it would let a pick that was in
    // flight when the object was deleted resolve to whatever took its place.
    this.ids.forget(handle.id);
    this._hovered.delete(handle.id);
    this._selected.delete(handle.id);
    this._focused.delete(handle.id);
  }

  setHighlighted(handle, on) {
    handle.highlighted = on;
  }

  /**
   * The parts the operator marked as important (Q-13).
   *
   * Kept separate from `highlighted`, deliberately. HIGHLIGHT means 'the agent just
   * changed this' and clears every previous id on each message — reusing it would wipe
   * the operator's marks every time the agent touched anything, which is the one thing
   * a standing mark must not do.
   */
  setFocused(objectIds) {
    this._focused = new Set(objectIds ?? []);
  }

  /** The visible part currently under the point cursor; cleared as soon as it leaves. */
  setHovered(objectIds) {
    this._hovered = new Set(objectIds ?? []);
  }

  /** Click, lasso and keyboard selections that stay visible until explicitly cleared. */
  setSelected(objectIds) {
    this._selected = new Set(objectIds ?? []);
  }

  /** The current colour+depth+id frame, for picking. Null before the first draw. */
  get frame() {
    return this._frame;
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

  /** Resolve a CSS colour string to [r, g, b] without ever naming one in this file.

   * The rasterizer writes bytes, so it needs numbers; `tests/tokens.test.js` scans this file
   * and forbids a colour literal. Letting the browser resolve the token through a 1x1
   * canvas keeps both true — the value still comes from `tokens.css`, and nothing here
   * hard-codes it.
   */
  _rgb(cssColor) {
    const cached = this._rgbCache.get(cssColor);
    if (cached) return cached;
    const probe = this._probeCtx;
    probe.clearRect(0, 0, 1, 1);
    probe.fillStyle = cssColor;
    probe.fillRect(0, 0, 1, 1);
    const [r, g, b] = probe.getImageData(0, 0, 1, 1).data;
    const rgb = [r, g, b];
    this._rgbCache.set(cssColor, rgb);
    return rgb;
  }

  /** Mix `rgb` toward the background by `1 - shade`, the flat-shading composite. */
  _shaded(rgb, background, shade) {
    return [
      rgb[0] * shade + background[0] * (1 - shade),
      rgb[1] * shade + background[1] * (1 - shade),
      rgb[2] * shade + background[2] * (1 - shade),
    ];
  }

  _draw() {
    const { ctx, canvas } = this;
    const width = canvas.width;
    const height = canvas.height;
    if (width === 0 || height === 0) return;

    const background = this._rgb(this._colors.canvas);
    const surface = this._rgb(this._colors.muted);
    const accent = this._rgb(this._colors.accent);
    const pointed = this._rgb(this._colors.pointed);
    const marked = this._rgb(this._colors.marked);
    const ink = this._rgb(this._colors.ink);

    if (!this._frame || this._frame.width !== width || this._frame.height !== height) {
      this._frame = createFrame(width, height);
      this._image = ctx.createImageData(width, height);
    }
    const frame = this._frame;
    clearFrame(frame, background);

    if (this.nodes.size === 0) {
      this._image.data.set(frame.color);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.putImageData(this._image, 0, 0);
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return;
    }

    let radius = 1;
    const allWorld = new Map();
    const pointedIds = new Set();
    for (const handle of this.nodes.values()) {
      const world = this._worldVertices(handle);
      allWorld.set(handle.handleId, world);
      for (const [x, y, z] of world) {
        radius = Math.max(radius, Math.hypot(x, y, z));
      }
    }

    const camDist = this.camera.distanceFor(radius);
    // Backing-store pixels, not CSS pixels: the rasterizer writes into the backing store
    // directly, so a 2x display would otherwise render a half-size image into a full-size
    // buffer.
    const focal = Math.min(width, height) * 0.9;

    // Anything at or past `camDist` in view depth is level with or behind the eye, where
    // the perspective divide has no answer. Clipped, never clamped.
    const nearPlane = camDist - Math.max(camDist * 0.02, 1e-4);

    // Depth is 1/w, which is what the rasterizer interpolates: 1/w is linear in screen
    // space under a perspective divide and view-space z is not.
    const project = ([x, y, z]) => {
      const invW = 1 / (camDist - z);
      const f = focal * invW;
      return [width / 2 + x * f, height / 2 - y * f, invW];
    };

    for (const handle of this.nodes.values()) {
      const world = allWorld.get(handle.handleId);
      const { indices } = handle.geometry;
      // Point feedback reads first while it is active, then reveals the exact standing
      // state underneath when cleared. Focus is persistent operator intent; a change
      // highlight is the last thing the agent touched and may be replaced at any moment.
      const isPointed = this._selected.has(handle.id) || this._hovered.has(handle.id);
      const focused = this._focused.has(handle.id);
      const base = isPointed ? pointed : focused ? marked : handle.highlighted ? accent : surface;
      const id = this.ids.idFor(handle.id);
      if (isPointed) pointedIds.add(id);

      for (let i = 0; i < indices.length; i += 3) {
        const a = world[indices[i]];
        const b = world[indices[i + 1]];
        const c = world[indices[i + 2]];
        if (!a || !b || !c) continue;

        const shade = shadeFactor(triangleNormal(a, b, c));
        const rgb = this._shaded(base, background, shade);

        // No sort, no subdivision, no seam inflation. The depth buffer decides visibility
        // per pixel, so draw order does not matter and none of those are needed.
        for (const [ca, cb, cc] of clipTriangleNear(a, b, c, nearPlane)) {
          drawTriangle(frame, project(ca), project(cb), project(cc), rgb, id);
        }
      }
    }

    this._image.data.set(frame.color);
    // Fill colour alone can disappear into flat shading. Draw an unshaded, DPR-aware halo
    // around the visible silhouette so hover and committed selection read at a glance.
    const dpr = window.devicePixelRatio || 1;
    paintIdOutline(
      this._image.data,
      frame.ids,
      width,
      height,
      pointedIds,
      ink,
      Math.max(2, Math.round(dpr * 2)),
    );
    // putImageData ignores the current transform, so the DPR scale set in _resize would
    // double-apply. Reset around it and restore afterwards for anything drawing in CSS
    // pixels later.
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.putImageData(this._image, 0, 0);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
}
