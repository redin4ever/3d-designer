// Read the viewport canvas back as pixels.
//
// The whole reason this file exists: `scene-renderer.js` is the one frontend module with
// no node:test coverage (frontend/README.md calls it "checked by eye, not by assertion"),
// and "the canvas element exists" proves nothing — a canvas sized to zero, a renderer
// whose rAF loop never starts, or a colour token that never resolves all leave a canvas
// element in the DOM and nothing on screen. Counting distinct colours is the cheapest
// assertion that tells those apart from a scene that actually drew.

const PROBE_TIMEOUT_MS = 15_000;

/**
 * @param {import('puppeteer').Page} page
 * @returns {Promise<{width: number, height: number, cssWidth: number, cssHeight: number,
 *   distinctColors: number, modalShare: number, nonModalPixels: number,
 *   modalColor: string, totalPixels: number}>}
 */
export async function probeCanvas(page) {
  return page.evaluate(() => {
    const canvas = document.getElementById('viewport-canvas');
    const empty = {
      width: 0,
      height: 0,
      cssWidth: 0,
      cssHeight: 0,
      distinctColors: 0,
      modalShare: 1,
      nonModalPixels: 0,
      modalColor: 'none',
      totalPixels: 0,
    };
    if (!canvas) return empty;
    const rect = canvas.getBoundingClientRect();
    if (canvas.width === 0 || canvas.height === 0) {
      return { ...empty, cssWidth: rect.width, cssHeight: rect.height };
    }

    const ctx = canvas.getContext('2d');
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const counts = new Map();
    for (let i = 0; i < data.length; i += 4) {
      const key = (data[i] << 24) | (data[i + 1] << 16) | (data[i + 2] << 8) | data[i + 3];
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    let modalKey = 0;
    let modalCount = 0;
    for (const [key, count] of counts) {
      if (count > modalCount) {
        modalCount = count;
        modalKey = key;
      }
    }
    const total = data.length / 4;
    const channel = (shift) => (modalKey >> shift) & 0xff;
    return {
      width: canvas.width,
      height: canvas.height,
      cssWidth: rect.width,
      cssHeight: rect.height,
      distinctColors: counts.size,
      modalShare: modalCount / total,
      nonModalPixels: total - modalCount,
      modalColor: `rgba(${channel(24)},${channel(16)},${channel(8)},${modalKey & 0xff})`,
      totalPixels: total,
    };
  });
}

/**
 * Wait until at least `minPixels` differ from the canvas's dominant colour, i.e. until
 * something has genuinely been drawn on top of the cleared background. Polls a condition
 * rather than sleeping past a frame, because the renderer's rAF loop and the WebSocket's
 * first FULL_SCENE race by design.
 */
export async function waitForCanvasDrawn(page, minPixels) {
  await page.waitForFunction(
    (floor) => {
      const canvas = document.getElementById('viewport-canvas');
      if (!canvas || canvas.width === 0 || canvas.height === 0) return false;
      const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
      const counts = new Map();
      for (let i = 0; i < data.length; i += 4) {
        const key = (data[i] << 24) | (data[i + 1] << 16) | (data[i + 2] << 8) | data[i + 3];
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      let modal = 0;
      for (const count of counts.values()) if (count > modal) modal = count;
      return data.length / 4 - modal >= floor;
    },
    { timeout: PROBE_TIMEOUT_MS, polling: 100 },
    minPixels,
  );
}
