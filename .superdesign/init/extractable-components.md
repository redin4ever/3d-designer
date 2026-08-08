# Extractable Components

These are the reusable DraftComponent candidates present in the current vanilla frontend. There are no framework components; each candidate is a semantic DOM fragment owned by the named module or static shell.

## Layout components

### AppShell
- Source: `frontend/index.html`
- Category: layout
- Description: Full single-page forge3d editor shell with status bar, viewport, controls, sidebar, and connect dialog.
- Extractable props: none required; the shell is currently hardcoded.
- Hardcoded: forge3d title, panel labels, DOM IDs, linked CSS files, canvas, dialog, and all copy.

### ViewportPanel
- Source: `frontend/index.html`, behavior in `frontend/src/scene-renderer.js` and `frontend/src/point-ui.js`
- Category: layout
- Description: Live canvas surface with connection banner and contextual point annotation composer.
- Extractable props: none currently; future candidates are `wsUrl` and `showConnectionBanner`.
- Hardcoded: canvas ID/ARIA description, orbit instructions, connection copy, annotation labels, and button text.

### Sidebar
- Source: `frontend/index.html`
- Category: layout
- Description: Conversation and action-log column.
- Extractable props: none currently; future candidates are `showConnect` and `showActionLog`.
- Hardcoded: headings, connect dialog trigger, transcript/composer IDs, and action log.

## Basic / interaction components

### PointComposer
- Source: `frontend/index.html`, behavior in `frontend/src/point-ui.js` and `frontend/src/annotate.js`
- Category: basic
- Description: Contextual annotation form for the selected part, including mark-important and attach-view actions.
- Extractable props: `selectedObjectId` (string, current selection); `canAttachImage` (boolean, future visibility flag).
- Hardcoded: input placeholder, Send/Mark important/Attach view/Close labels, and token-based CSS classes.

### OperatorControls
- Source: `frontend/index.html`, behavior in `frontend/src/controls.js`
- Category: basic
- Description: Run-state, rollback, point mode, focus, edit, and cadence controls.
- Extractable props: `connected` (boolean), `runState` (string), `selectedObjectId` (string), `cadence` (string).
- Hardcoded: action labels, field IDs, cadence option labels, and control grouping.

### Transcript
- Source: `frontend/src/transcript.js`
- Category: basic
- Description: Incremental accessible conversation list with role/state markers.
- Extractable props: `maxMessages` (number, default 200); `entries` (state data).
- Hardcoded: You/Agent/System role labels and operator delivery-state copy.

### ActionLog
- Source: `frontend/src/log.js`
- Category: basic
- Description: Capped append-only accessible list of build events.
- Extractable props: `maxEntries` (number, default 500); `entries` (state data).
- Hardcoded: row structure and kind data attributes.

### ConnectDialog
- Source: `frontend/index.html`, behavior in `frontend/src/connect-ui.js`
- Category: basic
- Description: Native modal for selecting/configuring an AI client, including Codex support.
- Extractable props: `clients` (array, current client catalog); `busy` (boolean); `resultTone` (string).
- Hardcoded: dialog title, setup explanation, Close button, and status-region IDs.

### CanvasSelectionFeedback
- Source: `frontend/src/scene-renderer.js`, `frontend/src/point-outline.js`
- Category: basic
- Description: Hover and selection fill/outline feedback over visible object IDs in the software-rendered canvas.
- Extractable props: `hoveredId`, `selectedId`, `focusedIds`, `outlineColor`.
- Hardcoded: renderer color priority and screen-space outline behavior.

## Extraction notes

- Keep the current hardcoded copy and token classes when extracting; only state/navigation/visibility values should become props.
- Do not extract `camera.js`, `raster.js`, `picking.js`, or `socket.js` as visual DraftComponents; they are rendering/input/transport utilities.

