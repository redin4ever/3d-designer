# Blender-style editor tools and move gizmo

The editor now uses a viewport-first layout inspired by Blender's working grammar: global
run controls stay in a slim strip, object tools live on a compact viewport shelf, exact
coordinates live in a Transform panel, and conversation/history remain in a secondary dock.
The styling is forge3d's own dark token system rather than a Blender skin.

## Move workflow

- Select one part, choose **Move** or press **G**, then drag the labelled X, Y, or Z arrow.
- Dragging previews the snapped position locally. Pointer release sends one existing
  `move_object` edit, so intermediate pointer events do not pollute undo history.
- Press **G**, then **X**, **Y**, or **Z** for keyboard movement. Arrow keys adjust the value,
  **Enter** commits, and **Escape** restores the authoritative transform.
- Editing remains available only while connected and paused. Rejection, disconnect, or
  resync rolls optimistic movement back to server state and reports the reason.
- Snap defaults to 0.1 m and can be toggled. Frame Selection and Reset View remain beside
  the viewport.

## Rendering and picking

`gizmo.js` projects world axes and hit-tests larger invisible screen-space targets.
`scene-renderer.js` draws the familiar labelled red X, green Y, and blue Z arrows after the
software frame is copied to Canvas2D. The overlay therefore never writes depth or object IDs;
part hover and selection still come only from the renderer's frame ID buffer.

## Accessibility and responsive behavior

The controls retain visible focus, 44 px coarse-pointer targets, text labels in addition to
axis color, a live movement status, keyboard cancellation, and logical CSS properties for
LTR/RTL mirroring. At narrow widths the viewport stays dominant while the dock stacks below.

## Verification

Pure tests cover projection, hit targets, snapping, lifecycle, cancellation, and server
reconciliation. Real-browser journeys cover pointer dragging, a complete keyboard move,
selection framing, snapping, visible hover/selection outlines, focus order, and narrow-screen
overflow. The redesign gate captures desktop LTR and RTL evidence for every inventoried
surface.

