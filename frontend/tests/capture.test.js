import { test } from 'node:test';
import assert from 'node:assert/strict';

import { MAX_EDGE, boundsOfPath, cropRect, fitWithin } from '../src/capture.js';

// The crop the model is sent (Q-08: a crop of your live view; Q-23: up to 1024px). The
// geometry is pure and tested here; the one impure line — drawing a canvas into a smaller
// canvas and calling toDataURL — is left to the integration, the same way SocketClient is
// (faking a canvas well enough to test it would test the fake).

test('the crop is 1024 on the long edge, as chosen', () => {
  // Q-23 went against the recommendation: detail over per-point token cost. 1024 is also
  // downscale_image's own documented default, so the two agree rather than one silently
  // overriding the other.
  assert.equal(MAX_EDGE, 1024);
});

test('a lasso becomes the box that contains it', () => {
  const bounds = boundsOfPath([[10, 20], [40, 5], [25, 60]]);

  assert.deepEqual(bounds, { x: 10, y: 5, width: 30, height: 55 });
});

test('a single click still produces a crop worth looking at', () => {
  // A click is a one-point path with zero area. Cropping to zero pixels would hand the model
  // a blank image and nothing anywhere would say why it was useless.
  const rect = cropRect([[100, 100]], { width: 800, height: 600 });

  assert.ok(rect.width > 0 && rect.height > 0);
  assert.ok(rect.width >= 64, 'the crop is too small to show context around the part');
});

test('the crop keeps some context around what was circled', () => {
  // A crop cut exactly to the object shows the model the part and nothing it relates to —
  // and "this clips the tread" is a statement about two things, not one.
  const tight = { width: 800, height: 600 };
  const rect = cropRect([[400, 300], [440, 340]], tight);

  assert.ok(rect.width > 40, 'no padding around the selection');
});

test('a crop never runs off the edge of the view', () => {
  // Padding a selection near the border would otherwise ask the canvas for pixels that do
  // not exist, which reads back as transparent black — a picture with a wrong dark band.
  const rect = cropRect([[2, 2], [10, 10]], { width: 800, height: 600 });

  assert.ok(rect.x >= 0 && rect.y >= 0);
  assert.ok(rect.x + rect.width <= 800);
  assert.ok(rect.y + rect.height <= 600);
});

test('a crop of the whole view is not padded past the view', () => {
  const rect = cropRect([[0, 0], [800, 600]], { width: 800, height: 600 });

  assert.deepEqual(rect, { x: 0, y: 0, width: 800, height: 600 });
});

test('an image already within budget is not enlarged', () => {
  // Upscaling costs tokens and adds no detail — it hands the model a bigger picture of
  // exactly the same information.
  assert.deepEqual(fitWithin(400, 300, 1024), { width: 400, height: 300 });
});

test('an oversized crop is scaled down on its long edge, keeping its shape', () => {
  // A distorted crop is worse than a small one: the model is being asked about proportion,
  // and a squashed image is a wrong answer that looks like a real one.
  const fitted = fitWithin(2048, 1024, 1024);

  assert.equal(fitted.width, 1024);
  assert.equal(fitted.height, 512);
});

test('a very thin crop never scales to zero pixels', () => {
  // A one-pixel-tall selection is easy to draw by accident. A zero dimension makes the
  // canvas call throw, which would surface as the whole annotation failing to send.
  const fitted = fitWithin(4000, 3, 1024);

  assert.ok(fitted.height >= 1);
});
