# Modifier multi-selection and repeat movement

Ctrl or Alt selection gestures toggle visible parts into or out of the current selection,
and a released gizmo drag can be followed immediately by a drag on another axis.

## How it is wired in

- Selection state: `frontend/src/annotate.js:36` — plain gestures replace; modifier
  gestures toggle.
- Pointer input: `frontend/src/point-ui.js:172` — Ctrl and Alt are carried from pointer
  release into click and lasso selection.
- Inspector safety: `frontend/src/point-ui.js:122` — several selected parts show a count;
  single-object move, frame, position, duplicate, and delete controls remain disabled.
- Move lifecycle: `frontend/src/move-gizmo.js:47` — release returns the pointer session to
  idle while pending absolute edits retain rollback state.
- Browser coverage: `frontend/tests-browser/smoke.test.js:836` and
  `frontend/tests-browser/gizmo.browser.mjs:153`.

## Decisions

See [decisions.md](decisions.md).

## Assumptions still standing

A-017 — chained optimistic moves keep the latest confirmed transform as their rollback
point. Reversal is local to the pointer lifecycle.

## Noticed but not done

Batch transform, duplicate, and delete operations need explicit backend contracts before
multi-selection can safely use them.

## Known gaps

None.
