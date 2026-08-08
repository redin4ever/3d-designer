import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  OrbitCamera,
  MAX_PITCH,
  MIN_ZOOM,
  MAX_ZOOM,
  clamp,
  zUpToYUp,
  shadeFactor,
  triangleNormal,
  DEFAULT_PITCH,
  clipTriangleNear,
} from '../src/camera.js';

// These describe a bug a user hit in a real browser and no test could have caught, because
// the camera lived inside the one file its own header exempted from node:test. Dragging up
// and down did nothing; the wheel did nothing.

test('dragging up and down actually tilts the camera', () => {
  const cam = new OrbitCamera();
  const before = cam.pitch;

  cam.drag(0, -80);

  assert.notEqual(cam.pitch, before, 'a vertical drag left the pitch untouched');
});

test('the model follows the cursor — dragging down is not inverted', () => {
  // Reported from a real browser after the first attempt shipped the opposite sign. Direct
  // manipulation: drag down and the far side of the object comes up over the top toward
  // you, as if your finger were on it. Moving the camera instead reads as inverted.
  const down = new OrbitCamera();
  const up = new OrbitCamera();

  down.drag(0, 60);
  up.drag(0, -60);

  assert.ok(down.pitch > up.pitch, 'vertical drag is inverted');
});

test('dragging left and right still turns the camera', () => {
  const cam = new OrbitCamera();
  cam.drag(50, 0);
  assert.ok(cam.yaw > 0, 'the axis that already worked must keep working');
});

test('a diagonal drag moves both axes, not just the one that used to work', () => {
  const cam = new OrbitCamera();
  const yaw0 = cam.yaw;
  const pitch0 = cam.pitch;

  cam.drag(40, 40);

  assert.notEqual(cam.yaw, yaw0);
  assert.notEqual(cam.pitch, pitch0);
});

test('the camera never reaches the pole, however hard you drag', () => {
  const cam = new OrbitCamera();
  cam.drag(0, -100_000);
  assert.ok(cam.pitch <= MAX_PITCH, 'flipped over the top');
  cam.drag(0, 100_000);
  assert.ok(cam.pitch >= -MAX_PITCH, 'flipped under the bottom');
});

test('the wheel zooms, and scroll-up zooms in', () => {
  const cam = new OrbitCamera();
  const framed = cam.distanceFor(10);

  cam.zoomByWheel(-100); // one notch up

  assert.ok(
    cam.distanceFor(10) < framed,
    'scroll-up must move the camera closer — every 3D tool works this way',
  );
});

test('scroll-down zooms out', () => {
  const cam = new OrbitCamera();
  const framed = cam.distanceFor(10);
  cam.zoomByWheel(100);
  assert.ok(cam.distanceFor(10) > framed);
});

test('zooming in and back out returns exactly where it started', () => {
  const cam = new OrbitCamera();
  const start = cam.distanceFor(7.5);

  cam.zoomByWheel(-100);
  cam.zoomByWheel(100);

  assert.ok(
    Math.abs(cam.distanceFor(7.5) - start) < 1e-9,
    'zoom must be multiplicative, or a user drifts away from their framing',
  );
});

test('zoom is bounded at both ends', () => {
  const cam = new OrbitCamera();
  cam.zoomByWheel(-100_000);
  assert.ok(cam.zoom >= MIN_ZOOM, 'zoomed through the scene and out the other side');
  cam.zoomByWheel(100_000);
  assert.ok(cam.zoom <= MAX_ZOOM, 'zoomed until the scene became a dot');
});

test('keyboard zoom moves the same way the wheel does', () => {
  const wheel = new OrbitCamera();
  const keys = new OrbitCamera();

  wheel.zoomByWheel(-100);
  keys.zoomBySteps(-1);

  assert.ok(
    Math.abs(wheel.zoom - keys.zoom) < 1e-9,
    'a keyboard user must get the same camera as a mouse user, not an approximation',
  );
});

test('an unzoomed camera frames the scene exactly as it did before zoom existed', () => {
  const cam = new OrbitCamera();
  // radius * 2.6 + 1 is what scene-renderer computed per frame; adding zoom must not
  // silently re-frame every existing view.
  assert.equal(cam.distanceFor(10), 10 * 2.6 + 1);
});

test('reset returns to the default view', () => {
  const cam = new OrbitCamera();
  cam.drag(300, 200);
  cam.zoomByWheel(-300);

  cam.reset();

  assert.equal(cam.yaw, 0);
  assert.equal(cam.zoom, 1);
  assert.equal(cam.distanceFor(4), 4 * 2.6 + 1);
});

test('frame selection changes the orbit target and reset returns to the scene origin', () => {
  const camera = new OrbitCamera();

  camera.focusOn([4, -2, 1]);
  assert.deepEqual(camera.target, [4, -2, 1]);

  camera.reset();
  assert.deepEqual(camera.target, [0, 0, 0]);
});

test('clamp is inclusive of its bounds', () => {
  assert.equal(clamp(5, 0, 5), 5);
  assert.equal(clamp(0, 0, 5), 0);
  assert.equal(clamp(-1, 0, 5), 0);
});

// --- world orientation -------------------------------------------------------------
// A user opened the live view and the 8x8 m deck was standing on its edge like a wall.

test('world up becomes view up', () => {
  const [, y] = zUpToYUp([0, 0, 1]); // straight up in Blender
  assert.equal(y, 1, 'Blender is Z-up and this renderer draws Y-up');
});

test('a floor is wide and flat in view space, not tall and thin', () => {
  // The deck: 8m in world X and Y, 0.2m thick in world Z.
  const corners = [
    [-4, -4, 0], [4, -4, 0], [4, 4, 0], [-4, 4, 0],
    [-4, -4, 0.2], [4, 4, 0.2],
  ].map(zUpToYUp);

  const xs = corners.map((p) => p[0]);
  const ys = corners.map((p) => p[1]);
  const spreadX = Math.max(...xs) - Math.min(...xs);
  const spreadY = Math.max(...ys) - Math.min(...ys);

  assert.ok(spreadX > spreadY * 10, `a floor must be flat on screen, got ${spreadX} x ${spreadY}`);
});

test('the conversion does not mirror the scene front to back', () => {
  // World +Y is away from the viewer in Blender's front view, so it must map to view -Z.
  // The opposite sign looks plausible and puts every object's far side in front of its
  // near side once the painter's sort runs.
  const [, , z] = zUpToYUp([0, 1, 0]);
  assert.ok(z < 0, 'front-to-back is mirrored');
});

test('the conversion leaves left and right alone', () => {
  assert.deepEqual(zUpToYUp([3, 0, 0]), [3, 0, -0]);
});

// --- shading -----------------------------------------------------------------------

test('shading gives different faces different values', () => {
  const up = shadeFactor([0, 1, 0]);
  const side = shadeFactor([1, 0, 0]);
  assert.notEqual(up, side, 'every face the same value makes a mesh an unreadable blob');
});

test('shading never returns fully black', () => {
  // A face perpendicular to the light must still be visible, or objects grow holes.
  assert.ok(shadeFactor([0, 0, 0]) > 0.2);
  for (const n of [[1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, -1, -1]]) {
    assert.ok(shadeFactor(n) > 0.2, `${n} shaded too dark`);
    assert.ok(shadeFactor(n) <= 1);
  }
});

test('a face turned away is lit like one turned toward', () => {
  // No back-face culling here, so an unlit back face reads as a hole in the object.
  assert.equal(shadeFactor([0, 1, 0]), shadeFactor([0, -1, 0]));
});

test('the triangle normal is perpendicular to the triangle', () => {
  const n = triangleNormal([0, 0, 0], [1, 0, 0], [0, 1, 0]);
  assert.equal(n[0], 0);
  assert.equal(n[1], 0);
  assert.notEqual(n[2], 0);
});

test('the default view looks down on the ground, not up at it from underneath', () => {
  // With an opaque deck, a camera below the floor hides everything standing on it — which
  // is exactly what the live view showed once surfaces stopped being 6%-alpha wireframe.
  // The old -0.5 tilt was chosen while the renderer was drawing a Z-up world as Y-up; with
  // that fixed, the same number points the camera at the underside.
  const cam = new OrbitCamera();
  assert.ok(cam.pitch > 0, 'the opening view is under the floor');
});

test('the ground plane recedes upward on screen from the default view', () => {
  // The real check behind the sign: on a floor, the far edge must sit higher on screen than
  // the near edge. Reproduces the renderer's own transform for two points on the ground.
  const cam = new OrbitCamera();
  const project = (world) => {
    const [x, y, z] = zUpToYUp(world);
    // rotateX by the camera pitch, as scene-renderer does
    const c = Math.cos(cam.pitch);
    const s = Math.sin(cam.pitch);
    return { screenUp: y * c - z * s, depth: y * s + z * c };
  };

  const far = project([0, 4, 0]);   // +Y is away from the viewer in Blender's front view
  const near = project([0, -4, 0]);

  assert.ok(far.screenUp > near.screenUp, 'the ground is being viewed from below');
});

// --- near plane --------------------------------------------------------------------
// "i can see triangles dissapearing and reaapearing when moving my camera". The projection
// divides by (camDist - z); a vertex past camDist is behind the eye, and clamping that
// divisor flung it off screen instead of clipping the triangle.

test('a triangle fully in front of the camera is untouched', () => {
  const out = clipTriangleNear([0, 0, 0], [1, 0, 0], [0, 1, 0], 5);
  assert.equal(out.length, 1);
  assert.deepEqual(out[0], [[0, 0, 0], [1, 0, 0], [0, 1, 0]]);
});

test('a triangle fully behind the camera is dropped, not flung across the screen', () => {
  const out = clipTriangleNear([0, 0, 9], [1, 0, 9], [0, 1, 9], 5);
  assert.deepEqual(out, [], 'geometry behind the eye must not be drawn at all');
});

test('one vertex behind the camera leaves a quad, which needs two triangles', () => {
  // Dropping one of them is a hole in the surface at exactly the moment the camera is
  // closest to it — which reads as a triangle that vanished.
  const out = clipTriangleNear([0, 0, 0], [10, 0, 0], [0, 0, 10], 5);
  assert.equal(out.length, 2, `expected a quad split in two, got ${out.length}`);
});

test('two vertices behind the camera leave a single triangle', () => {
  const out = clipTriangleNear([0, 0, 0], [10, 0, 10], [0, 10, 10], 5);
  assert.equal(out.length, 1);
});

test('every clipped vertex is in front of the near plane', () => {
  for (const tri of clipTriangleNear([0, 0, 0], [10, 0, 0], [0, 0, 10], 5)) {
    for (const v of tri) {
      assert.ok(v[2] <= 5 + 1e-9, `a clipped vertex is still behind the eye at z=${v[2]}`);
    }
  }
});

test('the cut lands exactly on the plane, not somewhere near it', () => {
  const out = clipTriangleNear([0, 0, 0], [0, 0, 10], [10, 0, 0], 4);
  const onPlane = out.flat().filter((v) => Math.abs(v[2] - 4) < 1e-9);
  assert.ok(onPlane.length >= 2, 'the crossing points are not on the near plane');
});

test('clipping interpolates x and y, not just depth', () => {
  // A crossing point that keeps the original x/y is not on the edge, so the surface bends.
  const [tri] = clipTriangleNear([0, 0, 0], [10, 0, 10], [0, 10, 0], 5);
  const cut = tri.find((v) => Math.abs(v[2] - 5) < 1e-9);
  assert.ok(cut, 'no crossing point produced');
  assert.ok(cut[0] > 0 && cut[0] < 10, `x was not interpolated: ${cut[0]}`);
});
