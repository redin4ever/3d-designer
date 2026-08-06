# frontend

The static browser view of a running build: a live 3D viewport, an action log, and
operator controls (pause / resume / roll back N steps / redirect in words / check
cadence) — Gate A wave 5. Its only contract with the backend is
`src/contracts/wire.py`, frozen and read-only from here (ARCHITECTURE.md: "`frontend`
depends only on the WebSocket wire-protocol contract").

No build step, no bundler, no framework, no npm dependency. Plain ES modules, loaded
directly by the browser from `index.html`.

## Running it

Open `frontend/index.html` directly in a browser, or serve the `frontend/` directory
with any static file server (`npx serve frontend`, `python -m http.server` from inside
`frontend/`, etc. — no build step either way).

- **Firefox**: ES module imports load fine straight from a `file://` URL.
- **Chrome / Chromium-based browsers**: block `type="module"` script imports from
  `file://` origins (a long-standing browser platform restriction, not something a
  no-build-step static site can work around). `index.html`'s connection banner and
  status pill are visible in the raw markup by default — not toggled visible only by
  JS — so even if `main.js` never runs, the page still shows "Not connected" rather than
  a blank screen. For guaranteed behavior in every browser, serve the directory.

By default the page connects to `ws://127.0.0.1:8766` (matching
`src/viewer/server.py`'s `serve()` defaults — the best available evidence for where a
real backend listens, not a frozen contract value). Override with a query param:
`index.html?ws=ws://host:port`.

## Layout

```
frontend/
  index.html          the shell: topbar, viewport panel, conversation, action log, controls
  src/
    tokens.css         GENERATED FROM DESIGN.md — DO NOT EDIT
    app.css            hand-authored layout/components, var(--token) only, no raw hex
    chat.css           the conversation panel's rows and composer
    main.js             entry — wires socket, viewport, log, transcript, controls to the DOM
    socket.js           WebSocket connection, the two seq rules, reconnect
    viewport.js          pure scene-graph state + payload→buffer translation
    scene-renderer.js    Canvas2D renderer — the real "renderer-like object"
    log.js               action log: append + cap
    transcript.js        the conversation: append + cap + optimistic-send reconciliation
    controls.js           client-message builders + DOM wiring
  tests/
    index.js            works around a Node CLI quirk — see CLAUDE.md
    *.test.js            node:test, one file per src module (no browser, no WebGL)
  README.md (this file)
  CLAUDE.md              local conventions, the Node quirk, module boundaries
```

## Why `viewport.js` has no three.js

three.js is not installed, there is no network to fetch it from, and the task
constraints forbid adding a dependency or fetching one over the network. So
`viewport.js` is split in two:

- **`viewport.js`** — pure. `buildGeometryBuffers` turns a wire `MeshPayload`'s flat
  float/int arrays into typed arrays; `applyMeshUpsert` / `applyTransformUpdate` /
  `applyObjectsRemoved` / `applyHighlight` / `clearViewportState` update a plain
  `{nodes: Map, highlighted: Set}` scene graph by calling four methods
  (`createNode` / `updateTransform` / `removeNode` / `setHighlighted`) on an injected
  **renderer-like object**. Tests inject a fake recording calls; nothing here touches a
  canvas or a WebGL context.
- **`scene-renderer.js`** — the real renderer-like object: a small hand-rolled
  perspective projection (quaternion rotation, painter's-algorithm triangle sort) drawn
  on a plain `<canvas>` 2D context. Not three.js, not WebGL, no dependency — and not
  covered by `node:test` for the same reason nothing in `viewport.js`'s test file needs
  a browser: it is the one file in this module meant to be checked by eye, not by
  assertion.

`main.js` is the only file that wires the two together.

## Testing

```bash
node --test frontend/tests/
```

Also runnable as `npm run test:frontend` from the repo root — 89 tests, all pure logic —
plus `npm run test:frontend:browser` for 16 smoke tests in real Chromium.

| File | Covers |
|---|---|
| `viewport.test.js` | mesh_upsert geometry shape, transform_update's cheap path (no rebuild), objects_removed, highlight semantics, clearViewportState |
| `socket.test.js` | the two seq rules — gap → resync, duplicate/out-of-order → ignore |
| `log.test.js` | append order, length cap |
| `transcript.test.js` | append order, cap (array and DOM), the three roles, missing-role default, optimistic send reconciled against the server's echo, unconfirmed lines |
| `controls.test.js` | rollback (exactly one of steps/checkpoint), redirect (rejects empty), set_cadence (one of three values) |
| `tokens.test.js` | tokens.css defines the required custom properties; no other file under `src/` contains a raw hex color |

See `CLAUDE.md` for why `tests/index.js` exists — it is not itself a test file.

## Design tokens

`src/tokens.css` is transcribed from `DESIGN.md`'s frontmatter (the `linear.app`
system chosen at Gate A 5.2) into semantic custom properties — `--canvas`,
`--surface-1`, `--hairline`, `--ink`, `--muted`, `--accent`, plus the supporting
surface/radius/spacing/type scale. Every other file under `frontend/src/` reads colors
through `var(--token)` (CSS) or `getComputedStyle(...).getPropertyValue('--token')`
(`scene-renderer.js`) — never a hex literal. `tokens.test.js` enforces this by scanning.

## Accessibility

Every control is a native `<button>`, `<input>`, `<select>`, or `<form>` — keyboard
reachable with no custom widget code. `:focus-visible` in `app.css` draws a 2px outline
in `--accent-focus` on whatever has focus. Every input has a real `<label for=...>`;
the run controls (`Pause`/`Resume`) are grouped under `role="group"` with a visible,
referenced label. The connection status pill, action log and conversation transcript all
use `aria-live` so a screen reader hears state changes without the operator needing to
hunt for them — answering the same "find it without hunting" brief as the visual
highlight (Gate A 5.3).

The transcript is `aria-live="polite"`, never `assertive`: an agent narrating a long build
emits a line every few seconds, and assertive would interrupt a screen-reader user
mid-word every single time. It carries `tabindex="0"` because it scrolls, and a scrollable
region a keyboard cannot reach is a history a keyboard user cannot read. Rows are appended
and updated in place, never rebuilt, so confirming a delivered message does not re-announce
it — the delivery marker itself is `aria-hidden`, since it is the one part of a row that
changes after the row has already been read out.

## What "sent" means in the composer

The agent does not receive a redirect when the operator presses Enter. MCP is
call/response, so the backend queues the text and hands it over in the agent's next tool
response (`contracts.wire.RedirectPayload`). That is unusual enough that a user who
misreads it concludes the product is broken, so it is stated on the page, under the field,
referenced by `aria-describedby` — not in a tooltip. The operator's line appears in the
transcript immediately and is only claimed as delivered once the server echoes it back
with `data.role: "operator"`; if the socket drops first, the line is marked
"not delivered — send it again" rather than left looking sent.
