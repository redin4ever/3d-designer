import assert from 'node:assert/strict';

import { waitForCanvasDrawn } from './harness/canvas-probe.mjs';
import { serverMessage } from './harness/fixtures.mjs';

async function selectVisiblePart(page, waitUntil) {
  await waitForCanvasDrawn(page, 500);
  await page.click('[data-action="point-mode"]');
  const point = await page.evaluate(() => {
    const canvas = document.getElementById('viewport-canvas');
    const context = canvas.getContext('2d');
    const image = context.getImageData(0, 0, canvas.width, canvas.height);
    const rect = canvas.getBoundingClientRect();
    const at = (x, y) => {
      const i = (y * canvas.width + x) * 4;
      return [...image.data.slice(i, i + 4)].join(',');
    };
    const background = at(0, 0);
    for (let y = 2; y < canvas.height - 2; y += 1) {
      for (let x = 2; x < canvas.width - 2; x += 1) {
        if (at(x, y) === background) continue;
        return {
          clientX: rect.left + ((x + 0.5) * rect.width) / canvas.width,
          clientY: rect.top + ((y + 0.5) * rect.height) / canvas.height,
        };
      }
    }
    return null;
  });
  assert.ok(point, 'could not find a rendered part to select');
  await page.mouse.click(point.clientX, point.clientY);
  await waitUntil(
    () => page.$eval('#point-composer', (element) => element.hidden === false),
    'a part to become selected',
  );
}

async function axisStroke(page, token) {
  return page.evaluate((tokenName) => {
    const canvas = document.getElementById('viewport-canvas');
    const context = canvas.getContext('2d');
    const image = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const probe = document.createElement('canvas').getContext('2d');
    probe.canvas.width = 1;
    probe.canvas.height = 1;
    probe.fillStyle = getComputedStyle(document.documentElement).getPropertyValue(tokenName).trim();
    probe.fillRect(0, 0, 1, 1);
    const target = probe.getImageData(0, 0, 1, 1).data;
    const points = [];
    for (let y = 0; y < canvas.height; y += 1) {
      for (let x = 0; x < canvas.width; x += 1) {
        const i = (y * canvas.width + x) * 4;
        if (image[i] === target[0] && image[i + 1] === target[1] && image[i + 2] === target[2]) {
          points.push([x, y]);
        }
      }
    }
    if (points.length < 5) return null;
    const cx = points.reduce((sum, [x]) => sum + x, 0) / points.length;
    const cy = points.reduce((sum, [, y]) => sum + y, 0) / points.length;
    let xx = 0;
    let xy = 0;
    let yy = 0;
    for (const [x, y] of points) {
      xx += (x - cx) ** 2;
      xy += (x - cx) * (y - cy);
      yy += (y - cy) ** 2;
    }
    const angle = 0.5 * Math.atan2(2 * xy, xx - yy);
    const rect = canvas.getBoundingClientRect();
    return {
      count: points.length,
      x: rect.left + (cx * rect.width) / canvas.width,
      y: rect.top + (cy * rect.height) / canvas.height,
      dx: Math.cos(angle) * 36 * rect.width / canvas.width,
      dy: Math.sin(angle) * 36 * rect.height / canvas.height,
    };
  }, token);
}

export function registerGizmoTests({ test, withScene, waitUntil, greeting }) {
  test('Move exposes labelled accessible axes without changing the picking channel', async () => {
    const session = await withScene(greeting);
    try {
      await selectVisiblePart(session.page, waitUntil);
      session.wire.broadcast(serverMessage('run_state', 6, { text: 'paused' }));
      await session.page.click('[data-action="move-tool"]');

      const controls = await waitUntil(
        () => session.page.evaluate(() => {
          const axes = [...document.querySelectorAll('[data-action="move-axis"]')];
          return axes.length === 3 ? axes.map((axis) => ({
            name: axis.getAttribute('aria-label'),
            size: Math.min(axis.getBoundingClientRect().width, axis.getBoundingClientRect().height),
          })) : null;
        }),
        'three keyboard-accessible move axes',
      );
      assert.deepEqual(controls.map(({ name }) => name), [
        'Move selected part along X axis',
        'Move selected part along Y axis',
        'Move selected part along Z axis',
      ]);
      assert.ok(controls.every(({ size }) => size >= 40), 'axis equivalents need touch-sized targets');

      for (const token of ['--axis-x', '--axis-y', '--axis-z']) {
        const stroke = await waitUntil(() => axisStroke(session.page, token), `${token} arrow pixels`);
        assert.ok(stroke.count >= 5, `${token} is not visibly drawn`);
      }

      const selectedBefore = await session.page.$eval('#point-selection', (element) => element.textContent);
      await session.page.click('[data-action="point-mode"]');
      assert.equal(
        await session.page.$eval('#point-selection', (element) => element.textContent),
        selectedBefore,
        'switching tools lost the selected part instead of preserving it',
      );
    } finally {
      await session.dispose();
    }
  });

  test('dragging a move arrow previews locally and sends one final existing move operation', async () => {
    const session = await withScene(greeting);
    try {
      await selectVisiblePart(session.page, waitUntil);
      session.wire.broadcast(serverMessage('run_state', 6, { text: 'paused' }));
      await session.page.click('[data-action="move-tool"]');
      const x = await waitUntil(() => axisStroke(session.page, '--axis-x'), 'the X move arrow');

      await session.page.mouse.move(x.x, x.y);
      await session.page.mouse.down();
      await session.page.mouse.move(x.x + x.dx, x.y + x.dy, { steps: 4 });
      await session.page.mouse.up();

      const edits = await waitUntil(() => {
        const found = session.wire.received.filter((message) => message.data?.edit?.kind === 'move_object');
        return found.length ? found : null;
      }, 'one move_object message');
      assert.equal(edits.length, 1, 'pointermove events must not create intermediate history entries');
      assert.equal(edits[0].type, 'annotate');
      assert.equal(edits[0].data.edit.params.snap, 0.1);
      assert.equal(edits[0].data.edit.params.translation.length, 3);
      assert.match(
        await session.page.$eval('#move-status', (element) => element.textContent),
        /saving|awaiting|saved/i,
      );
    } finally {
      await session.dispose();
    }
  });

  test('a second axis drag starts immediately without waiting for the first transform echo', async () => {
    const session = await withScene(greeting);
    try {
      await selectVisiblePart(session.page, waitUntil);
      session.wire.broadcast(serverMessage('run_state', 6, { text: 'paused' }));
      await session.page.click('[data-action="move-tool"]');

      for (const token of ['--axis-x', '--axis-y']) {
        const axis = await waitUntil(() => axisStroke(session.page, token), `${token} move arrow`);
        await session.page.mouse.move(axis.x, axis.y);
        await session.page.mouse.down();
        await session.page.mouse.move(axis.x + axis.dx, axis.y + axis.dy, { steps: 4 });
        await session.page.mouse.up();
      }

      const edits = await waitUntil(() => {
        const found = session.wire.received.filter((message) => message.data?.edit?.kind === 'move_object');
        return found.length === 2 ? found : null;
      }, 'two consecutive move_object messages');
      assert.equal(edits.length, 2);
      assert.notDeepEqual(edits[0].data.edit.params.translation, edits[1].data.edit.params.translation);
    } finally {
      await session.dispose();
    }
  });

  test('G then an axis supports a snapped keyboard move, Enter commit, and Escape cancel', async () => {
    const session = await withScene(greeting);
    try {
      await selectVisiblePart(session.page, waitUntil);
      session.wire.broadcast(serverMessage('run_state', 6, { text: 'paused' }));
      await session.page.focus('#viewport-canvas');
      await session.page.keyboard.press('g');
      await session.page.keyboard.press('x');
      await session.page.keyboard.press('ArrowRight');
      await session.page.keyboard.press('Enter');
      await waitUntil(
        () => session.wire.received.some((message) => message.data?.edit?.kind === 'move_object'),
        'keyboard move commit',
      );
      assert.equal(
        session.wire.received.filter((message) => message.data?.edit?.kind === 'move_object').length,
        1,
      );

      await session.page.keyboard.press('g');
      await session.page.keyboard.press('y');
      await session.page.keyboard.press('ArrowRight');
      await session.page.keyboard.press('Escape');
      assert.equal(
        session.wire.received.filter((message) => message.data?.edit?.kind === 'move_object').length,
        1,
        'Escape sent a cancelled keyboard move',
      );
    } finally {
      await session.dispose();
    }
  });

  test('Frame Selection, Reset View, and switchable snapping stay within viewport reach', async () => {
    const session = await withScene(greeting);
    try {
      await selectVisiblePart(session.page, waitUntil);
      session.wire.broadcast(serverMessage('run_state', 6, { text: 'paused' }));
      const before = await session.page.$eval('#viewport-canvas', (canvas) =>
        canvas.toDataURL());
      await session.page.click('[data-action="frame-selection"]');
      await waitUntil(async () => {
        const current = await session.page.$eval('#viewport-canvas', (canvas) => canvas.toDataURL());
        return current !== before ? current : null;
      }, 'Frame Selection to change the view');
      await session.page.click('[data-action="reset-view"]');

      const snapBefore = await session.page.$eval('[data-action="snap-toggle"]', (button) => button.getAttribute('aria-pressed'));
      await session.page.click('[data-action="snap-toggle"]');
      const snapAfter = await session.page.$eval('[data-action="snap-toggle"]', (button) => button.getAttribute('aria-pressed'));
      assert.equal(snapBefore, 'true');
      assert.equal(snapAfter, 'false');

      await session.page.focus('#viewport-canvas');
      await session.page.keyboard.press('g');
      await session.page.keyboard.press('x');
      await session.page.keyboard.press('ArrowRight');
      await session.page.keyboard.press('Enter');
      const edit = await waitUntil(() =>
        session.wire.received.find((message) => message.data?.edit?.kind === 'move_object'),
      'an unsnapped keyboard move');
      assert.equal(edit.data.edit.params.snap, 0);
    } finally {
      await session.dispose();
    }
  });
}
