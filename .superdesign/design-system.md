# forge3d editor design system

## Product and job

forge3d is a live 3D authoring console for an operator supervising an AI-driven Blender
build. The viewport is the primary workspace. The operator needs to inspect parts, select
and mark them, pause the build, make precise transforms, redirect the agent, and understand
what changed without losing spatial context.

The redesign should borrow Blender's editor grammar—viewport-local tools, persistent mode
and transform context, a properties region, axis gizmos, and a status line—without copying
Blender branding or overwhelming this smaller product with every Blender control.

## Source of visual truth

Use the existing root `DESIGN.md` and generated `frontend/src/tokens.css`. Keep the current
near-black Linear-derived palette, compact system typography, four-pixel rhythm, surface
ladder, hairline separation, scarce lavender accent, and almost-shadowless depth.

Do not introduce gradients, decorative color, glossy 3D chrome, large marketing typography,
pill-shaped primary actions, or another general-purpose accent.

## Visual language

- Canvas: near black; panels rise through charcoal surfaces and one-pixel hairlines.
- Type: compact system sans for controls; mono for coordinates, object ids, status, and
  keyboard hints.
- Density: power-user compact, but pointer targets remain at least 44 CSS pixels on touch.
- Radius: four to eight pixels for editor chrome; twelve only for dialogs and large overlays.
- Emphasis: lavender is reserved for active tool, primary action, focus, and selection.
- Depth: surface steps and edge highlights, not drop shadows.
- Motion: brief state transitions only; manipulation follows the pointer without easing.
- Focus: visible two-pixel lavender ring on every interactive surface.

## Editor composition

Desktop should read as a purpose-built 3D editor:

1. A slim global bar for product identity, connection, run state, and setup.
2. A viewport-local header for mode, active tool, snapping, and view actions.
3. A narrow vertical tool shelf at the viewport's inline-start edge.
4. The canvas as the dominant, uninterrupted work surface.
5. A contextual transform/properties panel at inline-end, distinct from conversation.
6. A slim viewport status bar showing selection, active tool, axis, snap, run state, and
   connection.
7. Conversation and action history remain available as secondary supervision surfaces.

Use logical CSS properties and support both LTR and RTL. Axis meaning itself does not mirror:
world X, Y, and Z remain geometrically stable.

On narrow screens, preserve the viewport first. Tools become a compact floating shelf;
properties and conversation become explicit drawers or sheets rather than one long stack.

## Tool model

- Select/Point and Move are real active modes with `aria-pressed` state.
- Rotate and Scale may be exposed only if implemented; never present a dead active-looking
  tool.
- The active tool is visible in the shelf, viewport header, cursor, and status bar.
- Tool buttons use icons plus accessible names and tooltips; axis controls also include
  visible X/Y/Z letters so color is never the sole signal.
- Numeric transform fields remain available for precision and reflect the selected part.

## Move gizmo

For one selected part, render three axis arrows at the part's projected origin. The visible
strokes stay crisp and the hit regions are larger than the strokes. The gizmo is a display
overlay only and must never modify depth or object-id picking buffers.

Dragging an axis previews the snapped absolute destination continuously, captures the
pointer, blocks orbit/lasso for that gesture, sends one existing `move_object` operation on
release, and accepts the server transform as authoritative. Escape cancels and restores the
last authoritative transform.

When editing is unavailable, keep the gizmo visible but muted and provide the existing clear
reason plus a nearby Pause action. Never imply a local move committed when the server did not
accept it.

## Existing surfaces to preserve functionally

- Connection banner and reconnect behavior.
- Point annotation composer and attach-view flow.
- Run, rollback, cadence, marks, duplicate, delete, redirect, and Connect actions.
- Conversation transcript and action log semantics.
- Keyboard camera controls, selection controls, focus order, and native dialog behavior.

Their placement and presentation may change; their behavior and accessible names must remain
available unless a later recorded decision explicitly changes them.

## Responsive and accessibility requirements

- No horizontal page scroll at 360 CSS pixels.
- Canvas remains keyboard focusable and retains camera instructions.
- Every icon-only control has an accessible name and visible tooltip/focus state.
- Active tool, selected object, active axis, coordinate preview, and save/error state are
  available to assistive technology without announcing every pointer pixel.
- Do not rely on hover or color alone.
- Respect reduced motion.

## Implementation constraints

- Vanilla semantic HTML, CSS custom properties, and ES modules; no UI framework.
- Colors and reusable sizes come from `frontend/src/tokens.css`.
- Renderer overlays are driven by CSS-resolved tokens, never source color literals.
- Preserve the current software rasterizer, depth buffer, and object-id picking model.
