// Browser coverage for the file-flow hooks. This module is intentionally not an entrypoint:
// smoke.test.js can import and register it once main.js adds the File menu to the page.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { FULL_SCENE_GREETING } from './harness/fixtures.mjs';
import { waitForConnected } from './harness/open-page.mjs';

/** Register file-menu tests into the existing browser smoke suite. */
export function registerFileIoTests({ withScene, waitUntil }) {
  test('File menu exposes native project/model actions and keeps the dialog named', async () => {
    const session = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(session);
      const view = await session.page.evaluate(() => {
        const button = document.querySelector('[data-action="file-menu"], #file-menu-button');
        const dialog = document.querySelector('[data-file-dialog], #file-io-dialog');
        return {
          button: Boolean(button),
          dialog: Boolean(dialog),
          labelled: Boolean(dialog?.getAttribute('aria-label') || dialog?.getAttribute('aria-labelledby')),
          actions: [...document.querySelectorAll('[data-file-action]')].map((node) => node.dataset.fileAction),
          exportScope: document.querySelector('[data-file-scope]')?.value ?? null,
        };
      });
      assert.ok(view.button, 'the File menu button is missing');
      assert.ok(view.dialog, 'the file dialog is missing');
      assert.ok(view.labelled, 'the native dialog needs an accessible name');
      assert.deepEqual(view.actions, ['open-project', 'save-project', 'save-as', 'import-model', 'export-model']);
      assert.equal(view.exportScope, 'scene', 'Export must not silently switch to the current selection');
    } finally {
      await session.dispose();
    }
  });

  test('File dialog only shows controls that apply to the active operation', async () => {
    const session = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(session);
      await session.page.evaluate(() => {
        document.querySelector('[data-file-input]').showPicker = () => {};
      });

      const readFields = () => session.page.evaluate(() => {
        const visible = (selector) => {
          const node = document.querySelector(selector);
          return Boolean(node && !node.hidden && getComputedStyle(node).display !== 'none');
        };
        const field = (id) => ({
          label: visible(`label[for="${id}"]`),
          control: visible(`#${id}`),
        });
        return {
          localFile: field('file-io-input'),
          filename: field('file-io-filename'),
          profile: field('file-io-profile'),
          scope: field('file-io-scope'),
          format: field('file-io-format'),
          importSettings: visible('[data-file-import-settings]'),
        };
      });

      await session.page.click('[data-action="file-menu"]');
      await session.page.click('[data-file-action="import-model"]');
      assert.deepEqual(await readFields(), {
        localFile: { label: true, control: true },
        filename: { label: false, control: false },
        profile: { label: false, control: false },
        scope: { label: false, control: false },
        format: { label: false, control: false },
        importSettings: true,
      });

      await session.page.keyboard.press('Escape');
      await session.page.click('[data-action="file-menu"]');
      await session.page.click('[data-file-action="export-model"]');
      assert.deepEqual(await readFields(), {
        localFile: { label: false, control: false },
        filename: { label: true, control: true },
        profile: { label: true, control: true },
        scope: { label: true, control: true },
        format: { label: true, control: true },
        importSettings: false,
      });
    } finally {
      await session.dispose();
    }
  });

  test('Ctrl+O opens the project picker and Ctrl+Shift+S opens Save As', async () => {
    const session = await withScene(FULL_SCENE_GREETING);
    try {
      await waitForConnected(session);
      await session.page.keyboard.down('Control');
      await session.page.keyboard.press('o');
      await session.page.keyboard.up('Control');
      await waitUntil(
        () => session.page.evaluate(() => document.querySelector('#file-io-dialog')?.open === true),
        'the Open Project dialog',
      );
      await session.page.keyboard.press('Escape');
      await session.page.keyboard.down('Control');
      await session.page.keyboard.down('Shift');
      await session.page.keyboard.press('s');
      await session.page.keyboard.up('Shift');
      await session.page.keyboard.up('Control');
      const title = await waitUntil(
        () => session.page.$eval('[data-file-dialog-title]', (node) => node.textContent.trim()).catch(() => ''),
        'the Save As dialog title',
      );
      assert.match(title, /save as/i);
    } finally {
      await session.dispose();
    }
  });
}
