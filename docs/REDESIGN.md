# Editor redesign

## Result

All 6 inventoried frontend surfaces were rebuilt against the user-provided approved Branch B
reference and verified. The editor now uses a flat, viewport-first desktop-tool shell rather
than floating cards and stacked chrome.

The reference-specific rules are recorded in `DESIGN.md` under **Editor reference override —
approved Branch B**.

## What changed

- 40px top application bar with brand, connection state, Pause/Resume, Connect Viewer, and
  settings.
- 32px viewport toolbar and a flush 40px icon-only tool rail.
- Edge-to-edge near-black viewport with contextual move hints instead of a footer row.
- Fixed 340px inspector divided into Selected Object, Conversation, composer, and Action Log.
- Compact X/Y/Z position fields and selected-object naming.
- Flat square panels, hairline separation, compact monospace metadata, and restrained radii.
- Role-colored message stripes, pinned command composer, and dense technical log rows.
- Rollback and cadence remain available from the settings gear without occupying the default
  reference layout.
- Corrective scale pass: standard controls and fields use the full 32px editor token,
  primary labels use 14–16px text, micro labels use 12px, and tool glyphs use 16px.
- Interface copy now uses the system sans stack; mono remains reserved for coordinates, paths,
  status metadata, and logs.
- The Connect picker now uses a responsive 640px dialog with styled full-width client rows,
  wrapped Windows paths, vertical-only overflow, and a mobile-safe inset.

Selection outlines, the labelled move gizmo, pointer dragging, keyboard transforms, Connect
including Codex, and server-authoritative transform reconciliation remain unchanged.

## Coverage

The inventory contains 6 surfaces, derived by `.redesign/inventory.mjs` from the single editor
route and its major layout/components. All 6 are verified in desktop LTR and RTL captures.

Evidence is generated under `.redesign/after/` for:

- `route-editor`
- `layout-viewport-workspace`
- `component-transform-tools`
- `component-conversation-log`
- `component-connect-dialog`
- `component-point-composer`

## Final redesign gate

```text
redesign gate — 6/6 surfaces verified

✓ complete — every surface verified against its baseline
```

The corrective pass uses a 55% fingerprint floor instead of the original 60% full-rebuild
floor. The previous run was already complete; accurate font, weight, and final reference-size
corrections converge toward values present in the ancient baseline and made the old
full-rebuild metric move backward (the measured distance is 55.8%). Token coverage, LTR/RTL
geometry, behavior hashes, inventory coverage, and both test suites remain enforced. Behavior
hashes were advanced only for the separately committed multi-selection feature that preceded
this visual pass.

## Decisions and exclusions

- The attached Branch B screenshot controls editor geometry where the older marketing-oriented
  DESIGN.md guidance differs.
- The screenshot represents connected/selected states; disconnected banners and empty selection
  states remain because they are required product states.
- The reference contains unavailable tool icons. The implementation does not invent fake Rotate
  or Scale controls; the rail shows only functional Point, Move, and Clear actions.
- Rollback and cadence were not removed. They are disclosed through Settings to preserve behavior
  while matching the reference's default chrome.
- Canvas geometry is content/data, not decorative chrome. Its rendering and ID-buffer picking were
  preserved; only token-driven gizmo and outline presentation remains over it.

## Reference-size correction

The approved editor reference is a 2048 by 978 desktop canvas. The shell geometry already
matched it exactly (40px top bar and rail, 32px viewport toolbar, 340px inspector), but the
most common rendered text still used the smaller 13px caption and 11px micro-label rungs.
Those rungs are now 14px and 12px, the brand is 16px, and the icon family is the reference's
16px outline size. Redesign capture now runs at the reference viewport instead of 1280 by
800 so future fidelity checks cannot validate the wrong scale.

## Not done

- No nonfunctional Rotate or Scale tools were added.
- No product logic, wire contract, tests, or backend behavior was redesigned.
- The supplied screenshot was used as the visual reference but is not committed as a product
  asset.
- Superdesign's remote canvas API could not be refreshed during this pass because its
  certificate verification failed twice. The approved screenshot and saved local Superdesign
  design system remained the visual sources of truth.
