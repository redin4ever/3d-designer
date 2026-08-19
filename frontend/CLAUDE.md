# frontend — local conventions

See `README.md` for what this module is and its public interface. This file is
implementation-facing.

## Status

**GREEN.** `node --test frontend/tests/` passes 180/180 (also `npm run test:frontend`), plus
`npm run test:frontend:browser` for 30 smoke tests in real Chromium via Puppeteer.
The module tests are pure logic — no browser, no WebGL, no real WebSocket. The browser
suite exists because that purity is also a blind spot: it is how a camera that could only
turn left and right shipped.

## Commands

```bash
# from the repo root
node --test frontend/tests/
npm run test:frontend

# a single file
node --test frontend/tests/viewport.test.js

# syntax-check a source file (no test harness needed)
node --check frontend/src/socket.js
```

## Known environment quirk: `tests/index.js`

On this environment's Node build (v24.18.0, Windows), `node --test <bare-directory>` in
**space-separated** form — exactly what `test:frontend` runs
(`node --test frontend/tests/`) — fails with `MODULE_NOT_FOUND` instead of recursing the
directory. Confirmed with a minimal repro outside this repo (a fresh directory,
`{"type":"module"}` `package.json`, one `tests/a.test.js`): identical failure. The
**equals**-separated form (`node --test=frontend/tests/`) recurses correctly, which
pinpoints the bug to how Node's CLI argument parser handles the space-separated form —
it falls through to plain `Module._resolveFilename` (the same resolution used for
`node <entrypoint>`), which fails on a bare directory with no `index.js`/`package.json`
`main`.

**Fix**: `frontend/tests/index.js` exists so that fallback resolution succeeds — it
imports every sibling `*.test.js` file, and because the process was started with
`--test`, their `test()` registrations still report through the active harness with
correct pass/fail counts and exit code. Verified both ways:

- Broken form + `index.js` present → works (this is what `test:frontend` relies on).
- Working form (`--test=frontend/tests/`) does **not** additionally pick up `index.js`
  as its own test file, because it does not match any default test-file naming pattern
  (`*.test.js`) — confirmed with a `console.log` planted in a same-named file in the
  repro. So there is no double-execution risk if this Node bug is ever fixed upstream.

If a future Node build fixes the space-separated form, this file becomes inert (never
independently discovered) rather than harmful — leave it in place regardless.

## Module boundaries

- Write only inside `frontend/**`. `src/contracts/wire.py`, `DESIGN.md`, and
  `package.json` are frozen surfaces read from here, never edited (Rule 5).
- `viewport.js` never imports `scene-renderer.js`, and vice versa. The only file allowed
  to import both is `main.js` — that is what keeps `viewport.js` testable with a fake
  renderer instead of a real canvas. See README's "Why `viewport.js` has no three.js".
- **Visibility is a depth buffer, not a sort.** `raster.js` rasterizes each triangle into a
  colour+depth target and keeps the nearer value per pixel. Do not reintroduce a
  back-to-front sort: the painter's algorithm has no correct answer when triangles overlap
  in depth, and which one it picks flips as the camera moves — that shipped as "triangles
  disappearing and reappearing". Three separate patches (subdividing large triangles,
  inflating fills to hide the resulting seams, stroking pieces to hide them differently and
  producing black lines) were each a symptom of the same unsound sort, and all three were
  deleted when the depth buffer landed.
- **Depth is stored as `1/w`, not view-space z.** Only `1/w` is linear in screen space under
  a perspective divide; interpolating z bends surfaces and makes coplanar geometry z-fight.
- **`camera.js` holds the orbit camera's arithmetic and `scene-renderer.js` holds the
  pixels.** That seam was cut after a user found the view would not tilt or zoom: the
  camera lived inside the one file this module's own docs exempt from `node:test`, so
  there was nothing to catch it. Anything about yaw/pitch/zoom belongs in `camera.js`,
  where it is covered; anything about drawing belongs in the renderer.
- **Every `*.test.js` must be imported by `tests/index.js`** — see the quirk above. A file
  that is not listed passes when run directly and is silently invisible to
  `npm run test:frontend`.
- **`transcript.js` is a separate module from `log.js`, not a variant of it.** The action
  log only ever receives; the transcript has to reconcile a line this browser printed
  optimistically against the server's later echo of the same line, which log.js's
  append-only counter cannot express — reconciling changes an entry that is already on
  screen. Both share the same append/cap/drop-from-the-DOM shape for the same reason:
  their containers are `aria-live`, and a rebuild re-announces the whole history.
- **The redirect composer lives in the conversation panel, not `.controls-panel`.** So
  `main.js` passes `.layout` to `attachControls`, which queries its root for each control
  individually and does not care that they now sit in two sections. The controls panel
  still comes *before* the sidebar in `index.html`'s source order even though the grid
  paints it below-left — that is what keeps the tab order `canvas → Pause → …`, which the
  browser suite asserts.
- `controls.js`'s message builders (`buildRollbackMessage` etc.) are pure and imported by
  `attachControls` in the same file, not duplicated — `main.js` only ever calls
  `attachControls`, never the builders directly.
- `socket.js`'s `classifySeq` is exported and pure specifically so it can be tested
  without a fake `WebSocket`. `SocketClient` itself is intentionally not unit-tested —
  faking a `WebSocket` well enough to test reconnect/backoff would test the fake, not the
  decision, which already lives in `classifySeq`.
- **`connect.js` is pure and `connect-ui.js` is DOM, and the split is not cosmetic.** The
  zero/one/many branch is the whole feature: an empty list rendered as a picker is a dead
  end, a list of one rendered as a picker is a step that exists because the code did not
  count, and writing the first of several unasked changes an application the user was not
  thinking about. That decision is unit-tested without a browser; `connect-ui.js` gets no
  unit test, for the same reason `attachControls` and `SocketClient` get none.
- **Connect talks HTTP, not the wire protocol.** `GET /api/clients` / `POST /api/connect`
  are served by `src/app/live.py` from the same origin as the page. Setting up an AI client
  is a one-off action, not a scene event, and putting it through `contracts/wire.py` would
  widen a frozen surface for something that is not about geometry. Same origin is also what
  keeps it a plain `fetch` with no CORS.
- **`fetch` is resolved at call time, never captured at import** (`(...args) =>
  globalThis.fetch(...args)`). That is what lets the browser suite stub it after the page has
  loaded, and calling it through a wrapper rather than passing the bare function is what
  stops Chrome throwing `Illegal invocation` on an unbound `fetch`.
- **The Connect flow renders in the `<dialog>`, never in the sidebar.** A written-config
  result is five lines; inline in a 340px panel it drove the transcript to zero height. The
  panel gains the button and nothing else — `tests-browser/connect.browser.mjs` asserts the
  chat panel's children are exactly the header row, the transcript and the composer, so a
  future "just one more status line" cannot quietly take the conversation back.
- **The picker is a native `<dialog>`, and should stay one.** Focus in, Escape out, the page
  behind inert, focus restored to the opener — four things a hand-rolled modal has to
  remember and the platform already does. Only the last one is re-implemented here, because
  it must survive the picker's own buttons being replaced by the result.
- **Browser tests for Connect live in `tests-browser/connect.browser.mjs` but are not an
  entry point.** `test:frontend:browser` names `smoke.test.js` by path and the root
  package.json is main-agent-only, so a standalone sibling test file would never run.
  `registerConnectTests({withScene, waitUntil})` is called from inside smoke.test.js's
  `describe` body — which node:test runs synchronously, so the tests land in that suite and
  share its one browser and one static server.
- Nothing under `src/` may contain a raw hex color literal outside `tokens.css` —
  `tests/tokens.test.js` scans for it. `scene-renderer.js` reads colors as opaque CSS
  strings via `getComputedStyle` and blends translucency with `ctx.globalAlpha` rather
  than hand-parsing hex to `rgba()`, specifically to avoid ever needing a hex literal in
  source.

- **Picking reads the rasterizer's id channel; it is never a ray cast.** `raster.js` writes
  the object's id into `frame.ids` in the same inner loop, and behind the same depth test, as
  the colour. A ray would be a second, independent answer to "what is visible", and two
  answers disagree eventually — when they do, the operator clicks one thing and sees another
  highlighted, intermittently, depending on camera angle. That is the same class of bug as
  the painter's algorithm this renderer already threw out. `drawTriangle`'s `id` argument is
  optional so every pre-existing caller stays untouched.
- **`SceneRenderer.setFocused` is not `setHighlighted`.** `highlighted` means "the agent just
  changed this" and `applyHighlight` clears every previous id on each HIGHLIGHT message,
  deliberately. Focus is standing state the operator put up and expects to persist. Reusing
  the one set would wipe their marks every time the agent touched anything.
- **`--marked`, not `--focus`.** `--focus-ring` already means keyboard focus in `tokens.css`,
  and two unrelated meanings under one word is how a later reader reaches for the wrong one.
- **The two snaps must agree exactly.** `edit-tools.js`'s `snapTo` and `ops/transform.py`'s
  `_snapped` round the same drag, and both round **half away from zero** — which is neither
  language's default. Python's `round` is banker's rounding and `Math.round` rounds half
  toward +Infinity, so the two disagreed on 0.25 and then, once Python was fixed, on -0.25.
  Both suites pin the same table of cases; do not "simplify" either back to a built-in.
- **`point-ui.js` is impure wiring and is not unit-tested**, for the same reason
  `attachControls` and `SocketClient` are not: every decision worth checking is already in
  `picking.js`, `annotate.js`, `capture.js` and `edit-tools.js`, which are pure and covered.
- **A number input has an intrinsic width that `flex: 1` does not override.** The edit fields
  need `min-width` plus `width: 0`, or three of them hold the whole grid wider than a 360px
  viewport — which the browser suite's no-horizontal-scroll test catches, and did.

## Wire protocol assumptions

`frontend` depends only on `src/contracts/wire.py` (ARCHITECTURE.md), not on
`src/viewer`'s current implementation, which is free to still be a stub. Where wire.py
doesn't pin something down, these were read from `src/viewer/server.py` /
`src/viewer/bridge.py` as the best available evidence and are reversible if wrong:

- **Wire encoding**: `src/viewer/server.py::_encode` uses
  `json.dumps(dataclasses.asdict(message), default=str)`. `asdict()` keeps dataclass
  field names verbatim, so JSON keys match `wire.py` exactly
  (`object_id`, `triangle_count`, `object_ids`, `data`, …); tuples serialize as JSON
  arrays; `StrEnum` members (`ServerMessage.type`, `ClientMessage.type`) serialize as
  their plain string value, not `{"value": ...}`.
- **Default socket target**: `ws://127.0.0.1:8766`, no path — matches
  `src/viewer/server.py::serve`'s `host`/`port` defaults and its raw
  `websockets.serve(handler, host, port)` (no route path). Overridable with
  `?ws=ws://host:port` since this is a default, not a contract value.
- **`HIGHLIGHT` and `OBJECTS_REMOVED` both carry ids in `ServerMessage.object_ids`** —
  the field the two message types already share in `wire.py`'s field list — not nested
  under `data`.
- **A `TRANSFORM_UPDATE` for an unknown `object_id` is a silent no-op**, not an error.
  `wire.py` doesn't specify ordering guarantees between a mesh's arrival and a transform
  for it; treating an unmatched transform as informational rather than fatal is the
  reversible choice (`viewport.test.js`'s "no-op, not a crash" case pins this down).
- **`LOG.data.role` is `operator` / `agent` / `system`**, and a `LOG` with no role is
  treated as `system` — older backends send exactly that, and a missing role must never
  make a message disappear. Every `LOG` goes to the conversation transcript; only
  system-role and role-less ones *also* go to the action log, so an agent's reply is not
  duplicated into the machine record.
- **The action log only appends for discrete narrative events** (`LOG`, `PHASE`,
  `RUN_STATE`, `PROBLEMS`, `CONFLICT`, `EXPORT_REPORT`, `ERROR`, `HIGHLIGHT`, connection
  status) — not for every `MESH_UPSERT`/`TRANSFORM_UPDATE`, which show up in the live 3D
  view instead. Gate A 11.4 scenes run to thousands of objects; logging every geometry
  message would defeat the log's own cap (`log.js`'s `DEFAULT_MAX_ENTRIES`) within
  seconds of a real run.
- **`RollbackTarget.checkpoint` has no picker UI** in `index.html` — only a "roll back N
  steps" number input, matching Gate A 5.4's chosen answer verbatim ("Pause, roll back N
  steps, redirect in words"). `buildRollbackMessage({checkpoint})` is still implemented
  and tested for programmatic/future use; wire.py has no checkpoint-listing message type
  to populate a picker from yet.

## Style

Plain ES modules (`import`/`export`), no TypeScript, no JSDoc build step — the `@param`
comments are for editor hover-help only. Every exported function in `viewport.js`,
`socket.js`, `log.js`, and `controls.js` carries a docstring stating the product-level
consequence of it being wrong, matching the house convention in
`src/orchestration/CLAUDE.md`. Test files mirror source files one-to-one
(`viewport.js` ↔ `viewport.test.js`, etc.) except `scene-renderer.js`, `main.js` and
`connect-ui.js`, which are the three files with no pure logic to unit-test (see README).

`tokens.css` also gained an elevation group for the Connect button and its dialog:
`--surface-raised`, `--surface-raised-hover`, `--hairline-raised`, `--elevation-raised`
(levels 2), and `--surface-overlay`, `--scrim` (level 3). These are an **extension** —
DESIGN.md's "Elevation & Depth" describes the treatment in prose and its frontmatter has no
token for it. They alias the existing surface ladder rather than introducing values, and
`--elevation-raised` is a 1px inset top highlight built from `--ink` via `color-mix`, not a
drop shadow: DESIGN.md is explicit that this brand "resists drop shadows on dark almost
entirely", so on this page a lift is a surface step plus an edge, and there is no new colour
in the system.

`tokens.css` gained two `--text-*` type-scale rungs (`--text-body-sm`, `--text-caption`),
transcribed verbatim from DESIGN.md's `typography` frontmatter. New CSS
reads sizes from those rather than writing a px literal; the older declarations in
`app.css` still carry literals and are left alone rather than reformatted (Rule 5: no
drive-by cleanups).
