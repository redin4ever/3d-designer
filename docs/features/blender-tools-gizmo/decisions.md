# Blender-style editor tools and move gizmo — gate decisions

**2026-08-08.** The user accepted every recommended option across eight decision waves. The
feature keeps the existing connected-and-paused editing contract and wire protocol while
reorganizing the editor around a viewport-first, Blender-inspired interaction model.

## Wave 1 — Editor purpose

- **Q-01:** The live viewport dominates the editor.
- **Q-02:** Success means selecting and moving a part accurately and confidently.
- **Q-03:** Borrow Blender's editor grammar, density, and spatial conventions without cloning
  Blender's brand or abandoning forge3d's dark visual system.

## Wave 2 — Tool scope

- **Q-04:** Expose Select/Point, Move, and Annotate as the immediate object tools.
- **Q-05:** Hide Rotate and Scale until they are functional; do not ship dead affordances.
- **Q-06:** Preserve exact XYZ entry in a contextual transform-properties panel.

## Wave 3 — Placement

- **Q-07:** Put object tools in a compact vertical shelf attached to the viewport's left edge.
- **Q-08:** Add a slim viewport header for mode, selection context, view actions, and snapping.
- **Q-09:** Keep run, cadence, rollback, connection, and global status outside the object shelf.
- **Q-10:** Keep conversation and action history as a secondary dock beside the dominant view.

## Wave 4 — Move interaction

- **Q-11:** Support one selected part in the first gizmo release. Explain why Move is
  unavailable when selection state is incompatible.
- **Q-12:** Render labeled red X, green Y, and blue Z arrows, with labels and shape carrying
  meaning in addition to colour.
- **Q-13:** Dragging an axis produces a live local preview snapped to the active grid.
- **Q-14:** Send one absolute `move_object` operation on release; intermediate pointer updates
  never create history entries.
- **Q-15:** Escape cancels the interaction and restores the last authoritative position.

## Wave 5 — Precision and keyboard

- **Q-16:** Translation snap defaults to 0.1 metres and is switchable.
- **Q-17:** `G` starts Move, `X`/`Y`/`Z` constrain the axis, Enter commits, and Escape cancels.
- **Q-18:** Include Frame Selection, Reset View, snap toggle/value, and concise tooltips.

## Wave 6 — States and authority

- **Q-19:** Manual editing remains available only while connected and paused.
- **Q-20:** Unavailable tools remain visible but disabled, with a nearby Pause cue when running.
- **Q-21:** A rejection or disconnect rolls an optimistic preview back and reports a clear
  error/status. Server state remains authoritative.

## Wave 7 — Accessibility

- **Q-22:** Interactive targets are at least 44 CSS pixels; thin arrows receive larger invisible
  screen-space hit regions.
- **Q-23:** Movement and save/error state appears in the viewport status bar and a polite live
  region; colour is never the only signal.

## Wave 8 — Responsive and content rules

- **Q-24:** On narrow screens the tool shelf compacts while properties and conversation become
  drawers or sheets, preserving a usable viewport.
- **Q-25:** Build LTR-first with logical properties for robust RTL, keep coordinate numerals
  stable, preserve existing behavior and terminology, and invent no product claims or content.

## Approved implementation contract

The move gizmo has state independent from hover, selection, focus, and change highlighting.
It captures the initiating pointer before orbit or lasso can claim the gesture, projects world
axes to screen space for hit testing and movement, previews reversibly, and commits through the
existing annotation/edit transport. The gizmo overlay must not write to the renderer's depth or
object-ID buffers, so pointing remains pixel-exact.
