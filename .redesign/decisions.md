# Branch B redesign decisions

The user selected **Branch B — viewport-first floating Blender-inspired workspace** on
2026-08-08 after reviewing the faithful baseline and two Superdesign branches.

- Logo: keep the `forge3d` text wordmark monochrome in the current ink colour; no logo asset exists.
- Density: compact editor density with forty-pixel minimum interactive targets.
- Structure: slim global bar, compact viewport header, left quick shelf, collapsible right dock,
  and a narrow viewport status bar.
- Destructive actions: keep Duplicate and Delete inside Transform context, separated from Move.
- Direction: LTR is primary; RTL must remain robust through logical properties. Coordinates and
  technical numerals remain Latin and in X/Y/Z order.
- Difference threshold: deliberately unrecognisable beside the former two-column-plus-bottom-strip
  layout while preserving every existing action, state, label meaning, ID, and protocol.
- Substance: add only headings, labels, instructions, and empty/error states that describe
  existing behavior. Invent no claims, statistics, prices, testimonials, or capabilities.
- Assets: there are no product images, charts, maps, or raster logos to recolour or regenerate.
- Interaction: one selected part gets labelled X/Y/Z Move arrows, live snapped preview, one final
  commit, Escape rollback, Frame Selection, Reset View, and a switchable 0.1 m snap.
- Nonfunctional Rotate and Scale tools remain hidden.

Verbatim selection: “do B”. The preceding “recommended” accepted the 25 decisions recorded in
`docs/features/blender-tools-gizmo/decisions.md`.
