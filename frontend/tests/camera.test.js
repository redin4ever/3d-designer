import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  OrbitCamera,
  MAX_PITCH,
  MIN_ZOOM,
  MAX_ZOOM,
  clamp,
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

test('clamp is inclusive of its bounds', () => {
  assert.equal(clamp(5, 0, 5), 5);
  assert.equal(clamp(0, 0, 5), 0);
  assert.equal(clamp(-1, 0, 5), 0);
});
