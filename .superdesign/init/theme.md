# Theme

## Compact token summary

### Colors

| Token | Value |
|---|---|
| `--canvas` | `#010102` |
| `--surface-1` | `#0f1011` |
| `--surface-2` | `#141516` |
| `--surface-3` | `#18191a` |
| `--surface-4` | `#191a1b` |
| `--hairline` | `#23252a` |
| `--hairline-strong` | `#34343a` |
| `--hairline-tertiary` | `#3e3e44` |
| `--ink` | `#f7f8f8` |
| `--ink-muted` | `#d0d6e0` |
| `--muted` | `#8a8f98` |
| `--ink-tertiary` | `#62666d` |
| `--accent` | `#5e6ad2` |
| `--accent-hover` | `#828fff` |
| `--accent-focus` | `#5e69d1` |
| `--accent-pressed` | `#4a55b8` |
| `--on-accent` | `#ffffff` |
| `--brand-secure` | `#7a7fad` |
| `--marked` | `#d9a441` |
| `--marked-soft` | `rgba(217, 164, 65, 0.18)` |
| `--success` | `#27a644` |
| `--overlay` | `#000000` |

### Typography, spacing, shape, elevation

- Fonts: display/text `-apple-system, "SF Pro Display/Text", "Segoe UI", system-ui, sans-serif`; mono `ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace`.
- Type scale: body-sm `14px`, caption `12px`.
- Spacing: `4/8/12/16/24/32/48/96px` from `--space-xxs` through `--space-section`.
- Radius: `4/6/8/12/16/24px` plus pill `9999px`.
- Elevation: raised surfaces use an inset 1px ink highlight; overlays use the scrim token.
- Breakpoint: the shell changes from a 2-column viewport/sidebar grid to one column at `900px`; controls wrap below the viewport.

## Raw token source

### frontend/src/tokens.css

```css
/* GENERATED FROM DESIGN.md â€” DO NOT EDIT
 *
 * Source: DESIGN.md frontmatter (`colors`, `rounded`, `spacing`, `typography`), the
 * `linear.app` design system chosen at Gate A wave 5.2. Values are transcribed verbatim
 * from the frontmatter, mapped to semantic custom-property names so nothing outside this
 * file ever needs to know a raw hex code (frontend/tests/tokens.test.js enforces that by
 * scanning every other file in frontend/src/ for `#rrggbb`).
 *
 * To regenerate: re-read DESIGN.md's frontmatter and update the values below by hand â€”
 * this workspace has no build step and no network, so there is no `tools/generate-tokens.mjs`
 * wired up inside frontend/. See frontend/CLAUDE.md for the mapping table.
 */

:root {
  /* Surfaces â€” canvas up through the four-step lift ladder (DESIGN.md "Surface") */
  --canvas: #010102;
  --surface-1: #0f1011;
  --surface-2: #141516;
  --surface-3: #18191a;
  --surface-4: #191a1b;

  /* Hairlines â€” 1px borders and dividers (DESIGN.md "Surface") */
  --hairline: #23252a;
  --hairline-strong: #34343a;
  --hairline-tertiary: #3e3e44;

  /* Text (DESIGN.md "Text") */
  --ink: #f7f8f8;
  --ink-muted: #d0d6e0;
  --muted: #8a8f98;
  /* ^ ink-subtle in DESIGN.md; named --muted to match the register given at Gate A 5.2 */
  --ink-tertiary: #62666d;

  /* Accent â€” the one chromatic color on screen (DESIGN.md "Brand & Accent") */
  --accent: #5e6ad2;
  --accent-hover: #828fff;
  --accent-focus: #5e69d1;
  /* EXTENSION, not from DESIGN.md: its primary-hover (#828fff) measures 2.87:1
     against white ink, below the 4.5:1 WCAG AA floor for body text. A filled
     primary button needs a hover that darkens rather than lightens. 6.40:1. */
  --accent-pressed: #4a55b8;
  --on-accent: #ffffff;
  --brand-secure: #7a7fad;

  /* EXTENSION, not from DESIGN.md: the parts the operator has marked as important.
     Named --marked, not --focus: --focus-ring already means keyboard focus here, and two
     unrelated meanings under one word is how a later reader reaches for the wrong one
     (Q-13). Deliberately not --accent, which already means "the agent just changed
     this" in the live view â€” HIGHLIGHT flashes and fades, focus stays lit, and if the
     two shared a colour the operator could not tell a mark they put up from a change
     that happened to them. Amber reads as attention rather than as a state change,
     separates from --accent at a glance, and is distinguishable from it for the common
     red-green deficiencies, where two blues would not be. */
  --marked: #d9a441;
  --marked-soft: rgba(217, 164, 65, 0.18);

  /* Semantic (DESIGN.md "Semantic") */
  --success: #27a644;
  --overlay: #000000;

  /* Radius scale (DESIGN.md "Shapes") */
  --radius-xs: 4px;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-xxl: 24px;
  --radius-pill: 9999px;

  /* Spacing scale, 4px base unit (DESIGN.md "Layout") */
  --space-xxs: 4px;
  --space-xs: 8px;
  --space-sm: 12px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-xxl: 48px;
  --space-section: 96px;

  /* Type â€” cross-platform substitutes per DESIGN.md "Note on Font Substitutes"; no
     network fetch, so no @font-face â€” system stacks only. */
  --font-display: -apple-system, "SF Pro Display", "Segoe UI", system-ui, sans-serif;
  --font-text: -apple-system, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
  --font-mono: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace;

  /* Type scale (DESIGN.md "Typography"), transcribed verbatim from the frontmatter's
     `typography` block. Only the two rungs this console actually uses are mapped; add the
     rest here rather than writing a px literal into a stylesheet. */
  --text-body-sm: 14px;
  --text-caption: 12px;

  /* Elevation 2 â€” a control raised off the panel behind it (DESIGN.md "Elevation & Depth",
     level 2: surface-2 lift, 1px hairline-strong), plus that section's "subtle white edge
     highlight on the top edge of lifted panels".

     EXTENSION, not from the frontmatter: DESIGN.md describes this treatment in prose and
     has no token for it, so each raised control would otherwise re-derive it and drift.
     The lift is a surface step and a 1px top highlight rather than a drop shadow because
     DESIGN.md is explicit that this brand "resists drop shadows on dark almost entirely" â€”
     the highlight is what reads as elevation here. Built from --ink via color-mix so the
     one near-white in the system stays the only near-white in the system. */
  --surface-raised: var(--surface-2);
  --surface-raised-hover: var(--surface-3);
  --hairline-raised: var(--hairline-strong);
  --elevation-raised: inset 0 1px 0 color-mix(in srgb, var(--ink) 8%, transparent);

  /* Elevation 3 â€” dropdown menus and dialogs (DESIGN.md "Elevation & Depth", level 3),
     with the scrim that separates a modal from the page it covers. */
  --surface-overlay: var(--surface-3);
  --scrim: color-mix(in srgb, var(--overlay) 62%, transparent);

  /* Elevation 4 â€” focus ring (DESIGN.md "Elevation & Depth") */
  --focus-ring: 2px solid var(--accent-focus);
}

```


## Raw visual stylesheet sources

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


