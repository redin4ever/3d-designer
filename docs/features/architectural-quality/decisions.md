# Architectural quality decisions

The triggering incident was a house assembled from generic walls and rotated cubes. Its
roof panels overlapped, its stairs were oriented from an undocumented fixed axis and did
not meet the porch correctly, the scene still had failing refine checks, and the caller
reported completion anyway. The user asked for a root fix that improves future model
accuracy and restores the product's detailed, relationship-driven purpose.

## Chosen product behaviour

1. **Success:** future house builds use semantic roof and landing-stair operations, and a
   scene cannot promote while their attachment queries fail. Repairing only one scene was
   rejected.
2. **Granularity:** preserve typed middle-grain operations. Raw primitives and a monolithic
   whole-house generator were rejected.
3. **Roof scope:** add an axis-aligned gable roof first (A-023), supporting ridges along X
   or Y (A-024).
4. **Roof detail:** one call creates two roof panels, a ridge cap, front/back rake trim and
   both eave fascia boards. Rakes and fascias share full compound-miter end faces; a
   two-panel shell, point contacts and visible connector covers were rejected as unfinished.
5. **Roof intent:** footprint, eave height, pitch, thickness, overhang and trim sizes remain
   explicit parameters. Geometry is derived from them; hidden house-scale defaults are not.
6. **Stair compatibility:** keep `add_staircase` unchanged for old logs and add a distinct
   landing-connected architectural stair (A-025, A-031).
7. **Stair placement:** derive direction, total rise and total run from the bottom start
   point and the live landing bounds (A-026). The agent does not calculate the landing edge.
8. **Stair detail:** architectural stairs include treads and two side stringers. Railings
   remain the dedicated existing operation (A-027).
9. **Failure:** an unreachable, level, or degenerate landing refuses atomically with a named
   reason. No partial treads survive.
10. **Acceptance wiring:** MCP dispatch attaches typed acceptance and joinery metadata to
    the persisted `Operation`; phase promotion re-runs those queries as well as generic
    manifold, gap and clipping checks.
11. **Joinery:** intentional trim/support contact is explicit `JoineryIntent`, never inferred
    from proximity (A-028).
12. **Verification split:** measurements own topology, dimensions and attachments. The agent
    still owns whether the render is attractive, per ADR-005; the semantic operations make
    the baseline visibly complete instead of assigning a fake aesthetic score.
13. **Agent guidance:** tool descriptions explicitly direct building roofs and landing
    stairs to the semantic operations. Primitives remain available for forms without a
    typed operation.
14. **No house composite:** a whole-house call remains out of scope (A-029). It would undo
    ADR-004's middle-grain design and hide intermediate checks.
15. **Proof:** fake-engine tests verify geometry and wiring; a real-Blender smoke test/render
    verifies the visual construction path (A-030).
16. **Published workflow:** documentation names the new capabilities and says a detailed
    build continues through detail and polish rather than stopping after refine.

## Explicitly out of scope

- Hip, mansard, gambrel and curved roofs in this first pass.
- Automatic doors, windows, interiors, landscaping or a whole-house layout generator.
- Folding railings into the stair operation.
- A numeric aesthetic or realism score; ADR-005 assigns appearance to visual review.

## Question record

- **Q-01:** Prove the root fix on future builds, not only the triggering scene.
- **Q-02:** Keep typed middle-grain architectural operations.
- **Q-03:** Ship gable roofs first (A-023).
- **Q-04:** Include panels, ridge cap, rake trim and eave fascia.
- **Q-05:** Keep footprint, bearing height, pitch, thickness, overhang and trim explicit.
- **Q-06:** Support ridge axes X and Y (A-024).
- **Q-07:** Preserve legacy `add_staircase` and add a new operation (A-025).
- **Q-08:** Derive stair geometry from bottom start and live landing bounds (A-026).
- **Q-09:** Build thin treads on two side stringers.
- **Q-10:** Keep railings as the dedicated existing operation (A-027).
- **Q-11:** Refuse impossible landing relationships atomically.
- **Q-12:** Have dispatch attach operation acceptance automatically.
- **Q-13:** Re-run every active operation query during promotion.
- **Q-14:** Record intentional support intersections as `JoineryIntent` (A-028).
- **Q-15:** Measure hard geometry and visually review appearance.
- **Q-16:** Tell agents to prefer the semantic roof over rotated cubes.
- **Q-17:** Do not add a monolithic whole-house generator (A-029).
- **Q-18:** Verify with fake-engine tests and a real-Blender render (A-030).
- **Q-19:** Replay old staircase operations bit-for-bit (A-031).
- **Q-20:** Publish the semantic workflow through detail and polish.
