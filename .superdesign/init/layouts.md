# Layouts

## Application shell

The application has one document shell. `frontend/index.html` defines the top status bar, a main CSS grid containing the live viewport, operator controls, and conversation/action-log sidebar, plus a native connect dialog. CSS files are linked in the document head and `frontend/src/main.js` attaches behavior after the module loads.

### frontend/index.html

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Gate A Console</title>
  <meta name="description" content="Live 3D view, action log and operator controls for a running build." />
  <!-- Without a declared icon the browser auto-requests /favicon.ico, which this static
       origin does not serve, and every single page load logs a 404 to the console. An
       empty data: URI satisfies the request without shipping an asset or a network fetch.
       Not an image file, because an SVG icon would have to hardcode a hex colour and
       every colour in this frontend comes from src/tokens.css. -->
  <link rel="icon" href="data:," />
  <link rel="stylesheet" href="src/tokens.css" />
  <link rel="stylesheet" href="src/app.css" />
  <link rel="stylesheet" href="src/chat.css" />
  <link rel="stylesheet" href="src/connect.css" />
  <link rel="stylesheet" href="src/point.css" />
</head>
<body>
  <header class="topbar">
    <h1 class="topbar-title">forge3d</h1>
    <span id="connection-status" class="status-pill" data-status="connecting" role="status" aria-live="polite">
      Connectingâ€¦
    </span>
  </header>

  <main class="layout">
    <section class="viewport-panel" aria-label="Live 3D view">
      <canvas id="viewport-canvas" tabindex="0" role="img"
          aria-label="Live 3D view of the current build. Drag to orbit, scroll to zoom. With the keyboard: arrow keys orbit, plus and minus zoom, 0 resets."></canvas>
      <!-- The in-place annotation composer (Q-07). Positioned over the canvas beside
           whatever was picked, and hidden until something is. It sits inside the viewport
           panel rather than in the sidebar because the operator chose to type where they
           are looking; `hidden` keeps it out of the tab order entirely while closed, so
           the keyboard path through the page is unchanged when nothing is selected. -->
      <form id="point-composer" class="point-composer" data-action="annotate-form" hidden>
        <p class="point-selection" id="point-selection" aria-live="polite">nothing selected</p>
        <div class="control-row">
          <label class="visually-hidden" for="annotate-text">What should the agent know about this?</label>
          <input
            id="annotate-text"
            data-field="annotate-text"
            type="text"
            autocomplete="off"
            placeholder="e.g. this one clips the tread"
            aria-describedby="point-selection"
          />
          <button type="submit" class="btn primary">Send</button>
        </div>
        <div class="control-row point-actions">
          <button type="button" class="btn" data-action="toggle-focus">Mark important</button>
          <button type="button" class="btn" data-action="attach-image" aria-pressed="false">
            Attach view
          </button>
          <button type="button" class="btn" data-action="close-composer">Close</button>
        </div>
        <p class="point-note" id="point-note"></p>
      </form>

      <div id="connection-banner" class="connection-banner">
        <p class="connection-banner-title">Not connected</p>
        <p class="connection-banner-detail" id="connection-banner-detail">
          Waiting for a build to connect. Start the viewer server and this page will pick it up
          automatically â€” no reload needed.
        </p>
      </div>
    </section>

    <!-- The controls panel sits before the sidebar in source order even though the grid
         paints it below-left: it keeps the tab order canvas â†’ run controls â†’ conversation,
         so the keyboard path through the page did not change when the chat panel landed. -->
    <section class="controls-panel" aria-label="Operator controls">
      <div class="control-group">
        <span id="run-controls-label">Run</span>
        <div class="control-row" role="group" aria-labelledby="run-controls-label">
          <button type="button" class="btn" data-action="pause">Pause</button>
          <button type="button" class="btn primary" data-action="resume">Resume</button>
        </div>
      </div>

      <div class="control-group">
        <form data-action="rollback-form">
          <label for="rollback-steps">Roll back N steps</label>
          <div class="control-row">
            <input
              id="rollback-steps"
              data-field="rollback-steps"
              type="number"
              min="1"
              step="1"
              inputmode="numeric"
              placeholder="1"
              required
            />
            <button type="submit" class="btn">Roll back</button>
          </div>
        </form>
      </div>

      <!-- Pointing and editing. Placed after Run and before Check cadence so the tab order
           runs canvas â†’ pause/resume â†’ point â†’ edit â†’ cadence â†’ conversation: the controls
           you reach for while watching come before the setting you change once. -->
      <div class="control-group">
        <span id="point-controls-label">Pointing</span>
        <div class="control-row" role="group" aria-labelledby="point-controls-label">
          <button type="button" class="btn" data-action="point-mode" aria-pressed="false">
            Point mode
          </button>
          <button type="button" class="btn" data-action="clear-focus">Clear marks</button>
        </div>
        <p class="control-hint" id="point-mode-hint">
          Off: drag turns the camera. On: click a part, or drag a loop round several.
        </p>
        <ul id="focus-list" class="focus-list" aria-live="polite" aria-label="Parts marked as important"></ul>
      </div>

      <div class="control-group" id="edit-group">
        <span id="edit-controls-label">Edit the selected part</span>
        <div class="control-row" role="group" aria-labelledby="edit-controls-label">
          <button type="button" class="btn" data-action="edit-move">Moveâ€¦</button>
          <button type="button" class="btn" data-action="edit-duplicate">Duplicate</button>
          <button type="button" class="btn" data-action="edit-delete">Delete</button>
        </div>
        <div class="control-row edit-fields">
          <label class="visually-hidden" for="edit-x">X, metres</label>
          <input id="edit-x" data-field="edit-x" type="number" step="0.1" placeholder="x" inputmode="decimal" />
          <label class="visually-hidden" for="edit-y">Y, metres</label>
          <input id="edit-y" data-field="edit-y" type="number" step="0.1" placeholder="y" inputmode="decimal" />
          <label class="visually-hidden" for="edit-z">Z, metres</label>
          <input id="edit-z" data-field="edit-z" type="number" step="0.1" placeholder="z" inputmode="decimal" />
        </div>
        <!-- Q-20: the reason is stated, and the Pause that fixes it is right here. A
             disabled control with no reason is indistinguishable from a broken one. -->
        <p class="control-hint" id="edit-blocked" role="status"></p>
        <button type="button" class="btn" data-action="pause-to-edit" hidden>Pause the build</button>
      </div>

      <div class="control-group">
        <label for="cadence-select">Check cadence</label>
        <select id="cadence-select" data-field="cadence">
          <option value="every_geometry_change">Every geometry change</option>
          <option value="phase_boundaries">Phase boundaries</option>
          <option value="on_request">On request</option>
        </select>
      </div>

      <p id="control-error" class="control-error" role="alert"></p>
    </section>

    <aside class="sidebar" aria-label="Conversation and action log">
      <section class="chat-panel" aria-labelledby="chat-heading">
        <!-- Connect sits at the right edge of the conversation panel's heading row, after
             every run control in source order â€” so the tab path through the page
             (canvas â†’ Pause â†’ â€¦ â†’ cadence â†’ Connect â†’ transcript â†’ composer) is unchanged
             for everyone who was already using it. It is dark and only one surface step
             above the panel behind it: this is setup, done once, and it must not compete
             with Send for attention on every other visit. -->
        <div class="panel-header">
          <h2 id="chat-heading" class="panel-heading">Conversation</h2>
          <button type="button" id="connect-button" class="connect-button" aria-describedby="connect-dialog-note">
            Connect
          </button>
        </div>
        <!-- aria-live="polite", not "assertive": an agent narrating a long build emits a
             line every few seconds, and assertive interrupts a screen-reader user mid-word
             every single time. Polite queues behind whatever they are already reading.
             tabindex="0" because this scrolls, and a scrollable region a keyboard cannot
             reach is a region a keyboard user cannot read the history of. -->
        <ol id="chat-transcript" class="transcript" tabindex="0" aria-live="polite" aria-label="Conversation with the agent"></ol>
        <form class="composer" data-action="redirect-form">
          <label for="redirect-text">Redirect the build, in words</label>
          <div class="control-row">
            <input
              id="redirect-text"
              data-field="redirect-text"
              type="text"
              autocomplete="off"
              aria-describedby="composer-note"
              placeholder="e.g. add a garage door on the east wall"
            />
            <button type="submit" class="btn primary">Send</button>
          </div>
          <p id="composer-note" class="composer-note">
            Sending queues your message. The agent picks it up on its next tool call â€” not the
            moment you press Enter â€” so if it is idle right now, nothing happens until it acts again.
          </p>
        </form>
      </section>

      <section class="log-panel" aria-labelledby="action-log-heading">
        <h2 id="action-log-heading" class="panel-heading">Action log</h2>
        <ul id="action-log" class="action-log" aria-live="polite"></ul>
      </section>
    </aside>
  </main>

  <!-- Everything the Connect button has to say happens in here rather than in the sidebar,
       and that is a layout decision with a reason: the conversation panel is ~340px wide and
       a few hundred tall, and a written-config result is five lines. Inline, it crushed the
       transcript to nothing â€” the operator lost the panel they actually use to a setup step
       they run once. In here it costs the panel no height at all, and the restart line gets
       the room it needs to be read.

       A native <dialog> because the four things a modal has to get right â€” focus moves in,
       Escape dismisses, the page behind goes inert, focus returns to whatever opened it â€”
       are all already implemented by the platform, and a hand-rolled one that forgets the
       last of them strands a keyboard user in a panel that is no longer on screen. -->
  <dialog id="connect-dialog" class="connect-dialog" aria-labelledby="connect-dialog-title">
    <h2 id="connect-dialog-title" class="connect-dialog-title">Connect an AI client</h2>
    <!-- Said before anything is written, because "connect" here does not mean what the word
         usually means. Also the Connect button's own aria-describedby. -->
    <p id="connect-dialog-note" class="connect-dialog-note">
      Connecting writes a config file so your AI client can launch forge3d â€” nothing connects
      from this page, and the tools appear the next time that client starts.
    </p>
    <div id="connect-dialog-body" class="connect-dialog-body" role="status" aria-live="polite"></div>
    <div class="connect-dialog-actions">
      <button type="button" class="btn" data-action="connect-cancel">Close</button>
    </div>
  </dialog>

  <script type="module" src="src/main.js"></script>
</body>
</html>

```


## Shell styling

The layout and responsive behavior are defined by these complete vanilla CSS files.

### frontend/src/app.css

```css
/* Hand-authored layout and component styles for the Gate A console. Every color here is
 * a var(--token) from tokens.css â€” never a literal hex value (frontend/tests/tokens.test.js
 * enforces this across frontend/src/). See DESIGN.md for the linear.app system this
 * implements: dense, quiet, dark, with the accent reserved for focus and the highlight.
 */

/* Dark-only design (tokens.css has no light ladder). Declaring it stops a light-preference
 * browser painting *its* scrollbars, <select> popup and number spinners over this near-black
 * page â€” those come from color-scheme, not from our CSS. */
:root {
  color-scheme: dark;
}

* {
  box-sizing: border-box;
}

html,
body {
  height: 100%;
  margin: 0;
}

body {
  background: var(--canvas);
  color: var(--ink);
  font-family: var(--font-text);
  font-size: 14px;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
}

a {
  color: inherit;
}

button,
input,
select {
  font: inherit;
  color: inherit;
}

/* A visible focus ring in the one accent color, everywhere â€” Rule: accessible controls. */
:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 2px;
  border-radius: var(--radius-xs);
}

.topbar {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  height: 56px;
  padding: 0 var(--space-lg);
  border-bottom: 1px solid var(--hairline);
  flex: 0 0 auto;
}

.topbar-title {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 15px;
  letter-spacing: -0.2px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xxs);
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  background: var(--surface-2);
  color: var(--ink-muted);
  font-size: 12px;
  font-family: var(--font-mono);
}

.status-pill::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full, 9999px);
  background: var(--ink-tertiary);
}

.status-pill[data-status='open'] {
  color: var(--ink);
}
.status-pill[data-status='open']::before {
  background: var(--success);
}

.status-pill[data-status='connecting']::before {
  background: var(--accent);
}

.status-pill[data-status='closed']::before {
  background: var(--ink-tertiary);
}

.layout {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 340px;
  grid-template-rows: 1fr auto;
  grid-template-areas:
    'viewport sidebar'
    'controls sidebar';
}

@media (max-width: 768px) {
  .layout {
    grid-template-columns: 1fr;
    grid-template-areas:
      'viewport'
      'controls'
      'sidebar';
  }
}

.viewport-panel {
  grid-area: viewport;
  position: relative;
  background: var(--surface-1);
  border-right: 1px solid var(--hairline);
  min-height: 240px;
}

#viewport-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.connection-banner {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: var(--space-sm);
  background: color-mix(in srgb, var(--canvas) 88%, transparent);
  text-align: center;
  padding: var(--space-lg);
}

.connection-banner[hidden] {
  display: none;
}

.connection-banner-title {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 500;
}

.connection-banner-detail {
  color: var(--muted);
  max-width: 40ch;
  font-size: 13px;
}

.sidebar {
  grid-area: sidebar;
  border-left: 1px solid var(--hairline);
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--surface-1);
}

.panel-heading {
  padding: var(--space-md) var(--space-lg) var(--space-xs);
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--ink-subtle, var(--muted));
}

/* The sidebar holds two stacked panels: the conversation on top (where the operator is
 * looking) and the machine action log below it. Both scroll independently; neither may
 * push the other off the screen, which is what min-height: 0 on each is for. */
.chat-panel,
.log-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-panel {
  flex: 3 1 0;
  border-bottom: 1px solid var(--hairline);
}

.log-panel {
  flex: 2 1 0;
}

/* Stacked layout: the sidebar's grid row is content-height there, not 1fr, so a zero
 * flex-basis has nothing to divide and collapses both panels onto each other. Size them
 * by content instead and let the page scroll. Placed after the rules above because a
 * media query adds no specificity â€” source order is what decides this one. */
@media (max-width: 768px) {
  .chat-panel,
  .log-panel {
    flex: 0 0 auto;
  }
}

.action-log {
  list-style: none;
  margin: 0;
  padding: 0 var(--space-lg) var(--space-lg);
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
  font-family: var(--font-mono);
  font-size: var(--text-caption);
}

.log-row {
  padding: var(--space-xs) 0;
  border-bottom: 1px solid var(--hairline);
  color: var(--ink-muted);
}

.log-row[data-kind='error'] {
  color: var(--accent-hover);
}

.log-row[data-kind='highlight'] {
  color: var(--ink);
}

.controls-panel {
  grid-area: controls;
  border-top: 1px solid var(--hairline);
  padding: var(--space-md) var(--space-lg);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
  align-items: flex-end;
  background: var(--surface-1);
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-xxs);
}

.control-group label {
  font-size: 12px;
  color: var(--muted);
}

.control-row {
  display: flex;
  gap: var(--space-xs);
}

button.btn {
  background: var(--surface-2);
  color: var(--ink);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  padding: 8px 14px;
  font-weight: 500;
  cursor: pointer;
}

button.btn:hover {
  border-color: var(--hairline-strong);
}

button.btn.primary {
  background: var(--accent);
  color: var(--on-accent);
  border-color: transparent;
}

button.btn.primary:hover {
  /* The lighter --accent-hover against white ink measures 2.87:1, below the 4.5:1 AA
     floor for body text â€” the default state is already only 4.70:1, so lightening the
     background on hover pushed it under. Darkening instead keeps the hover legible and
     still reads as a state change. */
  background: var(--accent-pressed);
}

input[type='text'],
input[type='number'],
select {
  background: var(--surface-1);
  color: var(--ink);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  padding: 8px 12px;
  min-width: 0;
}

input[type='text']:focus,
input[type='number']:focus,
select:focus {
  border-color: var(--hairline-strong);
}

.control-error {
  color: var(--accent-hover);
  font-size: 12px;
  min-height: 1em;
}

```

### frontend/src/chat.css

```css
/* The conversation panel â€” the transcript rows and the composer beneath them.
 *
 * Split out of app.css (which holds the page layout and the operator controls) along a
 * component seam: this is one panel with one job, and app.css was already at its Rule 2
 * budget. Same rule applies here as everywhere under frontend/src/ â€” every colour, size
 * and space is a var(--token) from tokens.css, never a literal.
 */

.transcript {
  list-style: none;
  margin: 0;
  padding: 0 var(--space-lg) var(--space-sm);
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.transcript-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-xxs);
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  background: var(--surface-2);
  /* An instruction can be a sentence and an object id can be one long token; neither may
     push the sidebar sideways (the narrow-viewport smoke test asserts exactly that). */
  overflow-wrap: anywhere;
}

/* Operator and agent must be separable at a glance â€” that is what makes this a
   transcript rather than a second log. Tinted and indented one way, plain the other. */
.transcript-row[data-role='operator'] {
  background: color-mix(in srgb, var(--accent) 22%, var(--surface-2));
  border-color: var(--accent-focus);
  margin-left: var(--space-lg);
}

.transcript-row[data-role='agent'] {
  background: var(--surface-3);
  margin-right: var(--space-lg);
}

.transcript-row[data-role='system'] {
  background: transparent;
  border-color: transparent;
  padding-left: 0;
  padding-right: 0;
}

.transcript-who {
  font-family: var(--font-display);
  font-size: var(--text-caption);
  font-weight: 500;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--muted);
}

.transcript-row[data-role='operator'] .transcript-who {
  color: var(--ink-muted);
}

.transcript-text {
  font-size: var(--text-body-sm);
  color: var(--ink);
  white-space: pre-wrap;
}

.transcript-row[data-role='system'] .transcript-text {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--muted);
}

/* The delivery marker. aria-hidden in the DOM, so this is the only channel it has. */
.transcript-state {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--muted);
}

.transcript-state:empty {
  display: none;
}

.transcript-row[data-state='unconfirmed'] .transcript-state {
  color: var(--accent-hover);
}

.composer {
  padding: var(--space-xs) var(--space-lg) var(--space-md);
  border-top: 1px solid var(--hairline);
  display: flex;
  flex-direction: column;
  gap: var(--space-xxs);
}

.composer .control-row {
  width: 100%;
}

.composer input[type='text'] {
  flex: 1 1 auto;
}

/* Always visible, directly under the field it describes, and referenced from it by
   aria-describedby. What "sent" means here is unusual enough that a user who misreads it
   concludes the product is broken, so it cannot live in a tooltip. */
.composer-note {
  margin: var(--space-xxs) 0 0;
  font-size: var(--text-caption);
  line-height: 1.4;
  color: var(--muted);
}

```

### frontend/src/connect.css

```css
/* The Connect button, its result line, and the client picker.
 *
 * Split from chat.css rather than added to it (Rule 2, responsibility seam): chat.css is
 * the conversation â€” transcript rows and the composer â€” and this is one control that talks
 * to the HTTP origin instead of the socket, plus a modal that is not part of the panel at
 * all. Same rule as everywhere under frontend/src/: every colour, radius and space is a
 * var(--token) from tokens.css.
 */

/* The heading row the button shares with "Conversation". The button sits at the right edge
 * of the panel it belongs to, which is also the far right of the page. */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  padding-right: var(--space-lg);
  flex: 0 0 auto;
}

/* Dark, and close to the panel it sits on rather than contrasting with it: this is setup,
 * not the thing the page is for, so it must be findable without competing with Send. The
 * lift is DESIGN.md's elevation 2 â€” one step up the surface ladder, a stronger hairline,
 * and the faint top edge highlight â€” not a shadow and not a colour. */
.connect-button {
  flex: 0 0 auto;
  background: var(--surface-raised);
  color: var(--ink-muted);
  border: 1px solid var(--hairline-raised);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-raised);
  padding: var(--space-xxs) var(--space-sm);
  font-family: var(--font-display);
  font-size: var(--text-caption);
  font-weight: 500;
  cursor: pointer;
}

.connect-button:hover {
  background: var(--surface-raised-hover);
  color: var(--ink);
}

.connect-button[aria-busy='true'] {
  color: var(--muted);
  cursor: progress;
}

/* The dialog carries the whole flow â€” the picker, the empty-machine message and the result
 * â€” because the conversation panel has no height to spare for any of them. A native
 * <dialog>: Escape, focus-in and focus-restore come from the platform rather than from code
 * that has to remember all three. */
.connect-dialog {
  background: var(--surface-overlay);
  color: var(--ink);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--elevation-raised);
  padding: var(--space-lg);
  /* A layout measure, like .layout's sidebar width in app.css â€” not a design token. */
  width: min(420px, calc(100vw - var(--space-xl)));
  max-width: 100%;
}

.connect-dialog::backdrop {
  background: var(--scrim);
}

.connect-dialog-title {
  margin: 0 0 var(--space-xxs);
  font-family: var(--font-display);
  font-size: var(--text-body-sm);
  font-weight: 500;
}

.connect-dialog-note {
  margin: 0 0 var(--space-md);
  font-size: var(--text-caption);
  line-height: 1.4;
  color: var(--muted);
}

/* A result runs to five lines including the restart warning, and a picker to three rows.
 * Capped and scrollable so neither can grow past a short window and push the way out
 * off-screen â€” a dialog whose Close button you cannot reach is a trap. */
.connect-dialog-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-xxs);
  margin-bottom: var(--space-md);
  max-height: 60vh;
  overflow-y: auto;
  font-size: var(--text-caption);
  line-height: 1.4;
  color: var(--muted);
}

.connect-dialog-body:empty {
  display: none;
}

.connect-result-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--text-body-sm);
  font-weight: 500;
  color: var(--ink);
}

.connect-dialog-body[data-tone='error'] .connect-result-title {
  color: var(--accent-hover);
}

.connect-result-line {
  margin: 0;
}

/* The restart instruction. Every client here reads its MCP config once, at start-up, so a
 * user who skims this line sees no tools at all and concludes the button did nothing. */
.connect-result-critical {
  color: var(--ink);
  font-weight: 500;
}

/* A Windows config path is one long unbreakable token; left alone it widens the dialog past
 * the viewport and takes the page's horizontal scroll with it. */
.connect-result-path,
.connect-choice-path {
  margin: 0;
  font-family: var(--font-mono);
  color: var(--ink-muted);
  overflow-wrap: anywhere;
}

.connect-choices {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.connect-choice {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-xxs);
  text-align: left;
  background: var(--surface-raised);
  color: var(--ink);
  border: 1px solid var(--hairline-raised);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-raised);
  padding: var(--space-xs) var(--space-sm);
  cursor: pointer;
}

.connect-choice:hover {
  background: var(--surface-raised-hover);
  border-color: var(--hairline-tertiary);
}

.connect-choice-label {
  font-size: var(--text-body-sm);
  font-weight: 500;
}

.connect-choice-path {
  font-size: var(--text-caption);
  color: var(--muted);
}

.connect-dialog-actions {
  display: flex;
  justify-content: flex-end;
}

```

### frontend/src/point.css

```css
/* Pointing, priority and the edit tools (Q-05, Q-07, Q-13, Q-15, Q-20).
   Every colour and size comes from tokens.css â€” tests/tokens.test.js fails on a hex
   literal anywhere under src/ except that file. */

/* The in-place annotation composer (Q-07). Absolute inside .viewport-panel, which is the
   positioning context; anchored bottom-left rather than following the cursor, because a
   panel that moves to wherever you clicked covers the thing you clicked about half the
   time, and you cannot predict where to look for it. */
.point-composer {
  position: absolute;
  left: var(--space-sm);
  bottom: var(--space-sm);
  z-index: 2;
  max-width: min(28rem, calc(100% - var(--space-lg)));
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-sm);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  box-shadow: var(--elevation-raised);
}

.point-composer[hidden] {
  display: none;
}

.point-selection {
  margin: 0;
  font-size: var(--text-caption);
  color: var(--marked);
}

.point-actions {
  flex-wrap: wrap;
}

.point-note {
  margin: 0;
  font-size: var(--text-caption);
  color: var(--muted);
}

.point-note:empty {
  display: none;
}

/* A part the operator marked. Distinct from the agent's change-highlight in both colour
   and behaviour: this stays lit until taken down, that one flashes and fades (Q-13). */
.focus-list {
  list-style: none;
  margin: var(--space-xs) 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xxs);
}

.focus-list:empty {
  display: none;
}

.focus-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xxs);
  padding: 0 var(--space-xs);
  border: 1px solid var(--marked);
  border-radius: var(--radius-sm);
  background: var(--marked-soft);
  color: var(--ink);
  font-size: var(--text-caption);
  line-height: 1.8;
}

.focus-chip button {
  border: 0;
  background: none;
  color: inherit;
  cursor: pointer;
  font: inherit;
  padding: 0;
}

.control-hint {
  margin: var(--space-xxs) 0 0;
  font-size: var(--text-caption);
  color: var(--muted);
}

.control-hint:empty {
  display: none;
}

/* A number input carries an intrinsic width from its default `size`, which no amount of
   `flex: 1` overrides â€” `min-width: 0` is what lets three of them share a narrow panel
   instead of forcing the whole grid wider than the viewport. Wrapping is the backstop at
   the narrowest sizes. */
.edit-fields {
  flex-wrap: wrap;
}

.edit-fields input {
  min-width: 3.5rem;
  width: 0;
  flex: 1 1 3.5rem;
}

/* Same intrinsic-width problem, same fix: the composer's text input would otherwise hold
   the viewport panel open at its own preferred width. */
.point-composer input[type='text'] {
  min-width: 0;
  flex: 1 1 6rem;
}

/* Q-20: greyed out with the reason beside them, never hidden. A control you cannot see is
   a feature you do not know exists; one you can see and cannot use teaches you the rule. */
#edit-group[data-blocked='true'] .btn,
#edit-group[data-blocked='true'] input {
  opacity: 0.45;
  pointer-events: none;
}

/* Point mode changes what dragging means, so it changes the cursor â€” the only always-
   visible signal of which mode you are in (Q-05). */
.viewport-panel[data-point-mode='on'] canvas {
  cursor: crosshair;
}

/* The lasso, drawn as an overlay rather than into the frame: the rasterizer's output is
   what picking reads, and painting a loop into it would make the loop itself pickable. */
.lasso {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

```


