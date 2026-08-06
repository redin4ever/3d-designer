// The crop the model is sent (Q-08, Q-23).
//
// Q-08 chose "a crop of your live view" over a fresh Blender render, and the honest reason is
// in the answer itself: nothing in this product renders pixels. `mcp_server.downscale_image`
// exists, is exported, and is called by nothing; `grep ImageContent src/` is empty. The only
// pixels that exist anywhere are the ones raster.js draws. A Blender render would be prettier
// and would show the model a *different angle from the one the operator is looking at*, which
// defeats the point of pointing.
//
// A-012: the browser crops, downscales and encodes PNG itself. `downscale_image` handles
// binary PPM only, on purpose — "adding a real codec is a gate decision, not a quiet
// addition" — and converting PNG to PPM here to feed a Python downscaler that would re-encode
// is work with no benefit. ADR-003's cost control is honoured at the same 1024 bound, one hop
// earlier.
//
// The geometry is pure and tested. The one impure step — drawing a canvas into a smaller
// canvas and calling toDataURL — is left to the integration, for the reason socket.js gives
// for not unit-testing SocketClient: faking a canvas well enough would test the fake.

/** Longest edge of the crop, in pixels. Mirrors mcp_server.images.downscale_image's default. */
export const MAX_EDGE = 1024;

/** Padding around a selection, as a fraction of its longest edge. */
const CONTEXT_PAD = 0.35;

/** Smallest crop worth sending. A click has no area, and a zero-pixel crop is a blank image. */
const MIN_CROP = 64;

/** The axis-aligned box containing a path. */
export function boundsOfPath(path) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const [x, y] of path) {
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

/**
 * The region of the view to crop, given what the operator drew.
 *
 * Padded, and clamped to the view. Both matter for the same reason: what reaches the model has
 * to be a picture a person would recognise as an answer to what was asked.
 *
 * - **Padded**, because a crop cut exactly to the object shows the part and nothing it relates
 *   to — and "this clips the tread" is a statement about two things, not one.
 * - **Clamped**, because padding a selection near the border asks the canvas for pixels that
 *   do not exist, and those read back as transparent black: a picture with a wrong dark band
 *   down one side, which the model will faithfully describe.
 *
 * @param {ReadonlyArray<readonly [number, number]>} path frame-space points (a click is one)
 * @param {{width: number, height: number}} frame
 */
export function cropRect(path, frame) {
  const bounds = boundsOfPath(path ?? []);
  if (!Number.isFinite(bounds.x)) return { x: 0, y: 0, width: frame.width, height: frame.height };

  const pad = Math.max(MIN_CROP / 2, Math.max(bounds.width, bounds.height) * CONTEXT_PAD);
  let x = Math.floor(bounds.x - pad);
  let y = Math.floor(bounds.y - pad);
  let width = Math.ceil(bounds.width + pad * 2);
  let height = Math.ceil(bounds.height + pad * 2);

  // Clamp the origin first, then the size, so a box that starts off-screen is moved back in
  // rather than silently shrunk from the far edge.
  x = Math.max(0, Math.min(x, frame.width - 1));
  y = Math.max(0, Math.min(y, frame.height - 1));
  width = Math.min(width, frame.width - x);
  height = Math.min(height, frame.height - y);

  return { x, y, width, height };
}

/**
 * The size to encode at: scaled down on the long edge to fit `maxEdge`, aspect preserved.
 *
 * Never enlarged — upscaling costs tokens and adds nothing, handing the model a bigger picture
 * of exactly the same information. Never distorted — the model is being asked about
 * proportion, and a squashed image is a wrong answer that looks like a real one. Never zero —
 * a one-pixel-tall selection is easy to draw by accident, and a zero dimension makes the
 * canvas call throw, which surfaces as the whole annotation failing to send.
 */
export function fitWithin(width, height, maxEdge = MAX_EDGE) {
  const longest = Math.max(width, height);
  if (longest <= maxEdge) return { width, height };
  const scale = maxEdge / longest;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}
