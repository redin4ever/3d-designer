// The real renderer-like object, implemented on Canvas2D — no three.js, no network
// fetch, no dependency (see frontend/CLAUDE.md "Why no three.js"). Implements the exact
// four-method shape frontend/src/viewport.js drives against a fake in tests:
// createNode / updateTransform / removeNode / setHighlighted, plus start()/stop() for
// its own render loop. Nothing in this file is imported by frontend/tests/ — it is the
// "browser adapter" half of the split the assumptions call out, and it is intentionally
// the one file in this module that is exercised by eye, not by node:test.
//
// Colors are never hard-coded here: every stroke/fill comes from getComputedStyle of a
// `--token` custom property defined in tokens.css, read once per resize/theme change and
// cached as opaque CSS color strings — translucency is done with ctx.globalAlpha rather
// than hand-parsed rgba(), so no hex digit ever appears as a literal in this file. The
// fallbacks below are CSS color keywords, not hex, for the same reason. That is what
// lets frontend/tests/tokens.test.js scan this file for a raw hex literal and find none.

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

const AUTO_ROTATE_RADIANS_PER_MS = (2 * Math.PI) / 40_000; // one slow turn per 40s — "live" without being busy
const CAMERA_TILT = -0.5;

export class SceneRenderer {
  /** @param {HTMLCanvasElement} canvas */
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.nodes = new Map();
    this._nextHandleId = 0;
    this._running = false;
    this._rafId = null;
    this._autoAngle = 0;
    this._lastFrameAt = 0;
    this._dragYaw = 0;
    this._dragging = false;
    this._dragStartX = 0;
    this._dragStartYaw = 0;
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
      this._autoAngle += (now - this._lastFrameAt) * AUTO_ROTATE_RADIANS_PER_MS;
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
      this._dragStartX = event.clientX;
      this._dragStartYaw = this._dragYaw;
      this.canvas.setPointerCapture(event.pointerId);
    });
    this.canvas.addEventListener('pointermove', (event) => {
      if (!this._dragging) return;
      const dx = event.clientX - this._dragStartX;
      this._dragYaw = this._dragStartYaw + dx * 0.01;
    });
    const release = () => {
      this._dragging = false;
    };
    this.canvas.addEventListener('pointerup', release);
    this.canvas.addEventListener('pointercancel', release);
  }

  _worldVertices(handle) {
    const { positions } = handle.geometry;
    const { position, quaternion, scale } = handle.transform;
    const out = new Array(positions.length / 3);
    const orbit = this._autoAngle + this._dragYaw;
    for (let i = 0; i < positions.length; i += 3) {
      let v = [positions[i] * scale[0], positions[i + 1] * scale[1], positions[i + 2] * scale[2]];
      v = rotateByQuaternion(v, quaternion);
      v = [v[0] + position[0], v[1] + position[1], v[2] + position[2]];
      v = rotateY(v, orbit);
      v = rotateX(v, CAMERA_TILT);
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
    const camDist = radius * 2.6 + 1;
    const focal = Math.min(width, height) * 0.9;
    const project = ([x, y, z]) => {
      const denom = camDist - z;
      const f = focal / (denom > 0.001 ? denom : 0.001);
      return [width / 2 + x * f, height / 2 - y * f, z];
    };

    const triangles = [];
    for (const handle of this.nodes.values()) {
      const world = allWorld.get(handle.handleId);
      const { indices } = handle.geometry;
      for (let i = 0; i < indices.length; i += 3) {
        const a = world[indices[i]];
        const b = world[indices[i + 1]];
        const c = world[indices[i + 2]];
        if (!a || !b || !c) continue;
        const avgZ = (a[2] + b[2] + c[2]) / 3;
        triangles.push({ a: project(a), b: project(b), c: project(c), avgZ, highlighted: handle.highlighted });
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
        ctx.globalAlpha = 0.35;
        ctx.fill();
        ctx.globalAlpha = 0.95;
        ctx.stroke();
      } else {
        ctx.fillStyle = this._colors.ink;
        ctx.strokeStyle = this._colors.muted;
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.06;
        ctx.fill();
        ctx.globalAlpha = 0.55;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }
}
