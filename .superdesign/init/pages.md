# Pages

## /

**Entry:** `frontend/index.html`

**Boot:** `frontend/src/main.js`

**Rendered structure:** topbar/status → live canvas viewport with connection banner and in-place annotation composer → operator controls (run, rollback, point/focus, edit, cadence) → conversation sidebar with connect button/dialog, transcript composer, and action log.

**Styles:** `frontend/src/tokens.css`, `frontend/src/app.css`, `frontend/src/chat.css`, `frontend/src/connect.css`, `frontend/src/point.css`.

**Complete JavaScript dependency tree:**

- `frontend/src/main.js`
  - `frontend/src/socket.js`
  - `frontend/src/viewport.js`
  - `frontend/src/scene-renderer.js`
  - `frontend/src/log.js`
  - `frontend/src/transcript.js`
  - `frontend/src/controls.js`
    - `frontend/src/socket.js`
  - `frontend/src/point-ui.js`
    - `frontend/src/annotate.js`
      - `frontend/src/socket.js`
    - `frontend/src/capture.js`
    - `frontend/src/edit-tools.js`
      - `frontend/src/socket.js`
    - `frontend/src/picking.js`
  - `frontend/src/connect-ui.js`
    - `frontend/src/connect.js`


**HTML and CSS dependencies:**

- `frontend/index.html`
  - `frontend/src/tokens.css`
  - `frontend/src/app.css`
  - `frontend/src/chat.css`
  - `frontend/src/connect.css`
  - `frontend/src/point.css`
  - `frontend/src/main.js`

**Interaction ownership:**

- `main.js`: composition root, socket lifecycle, server-message dispatch, renderer/state wiring.
- `viewport.js`: scene-facing viewport state and visible object/highlight state updates.
- `scene-renderer.js`: canvas rasterization, camera controls, hover/selection outline presentation.
- `point-ui.js`: point mode, canvas picking, selected/hovered state, annotation composer, focus marks, edit gating.
- `controls.js`: pause/resume, rollback, redirect, cadence controls.
- `connect-ui.js` / `connect.js`: client picker and connection setup result dialog.
- `transcript.js` / `log.js`: incremental accessible conversation and action-log rendering.

