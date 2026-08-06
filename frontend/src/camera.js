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

/** One wheel notch. Multiplicative, so zooming in and back out returns where it started. */
export const WHEEL_STEP = 1.1;

export function clamp(value, low, high) {
  return value < low ? low : value > high ? high : value;
}

export class OrbitCamera {
  constructor({ pitch = -0.5 } = {}) {
    this.yaw = 0;
    /** Starts at the old fixed CAMERA_TILT, so the default view is unchanged. */
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
    this.pitch = -0.5;
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
