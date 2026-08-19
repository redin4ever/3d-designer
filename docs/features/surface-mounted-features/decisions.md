# Surface-mounted features — decisions

Gate date: 2026-08-14. The first 24 recommendations were accepted implicitly when the
user supplied one additional factory defect rather than an exception. Q-25 records the
user's words verbatim; Q-26 and Q-27 are reversible assumptions A-034 and A-035.

| ID | Decision |
|---|---|
| Q-01 | Separate `add_roof_window` and `add_wall_sign` semantic operations. |
| Q-02 | Misalignment is a hard failure and blocks phase promotion. |
| Q-03 | Preserve generic primitives/raw execution; direct architectural work to semantic tools. |
| Q-04 | Repair both the app and the existing factory artifact. |
| Q-05 | Roof windows are surface-mounted framed skylights, not boolean roof cuts. |
| Q-06 | Roof-window placement is relative to the host face, not world coordinates. |
| Q-07 | Support any sufficiently planar upward roof face. |
| Q-08 | Reject an oversized roof window atomically rather than silently resizing it. |
| Q-09 | Facade signs use raised mesh lettering. |
| Q-10 | The caller supplies a point the sign should face toward; camera state is irrelevant. |
| Q-11 | Signs center horizontally on the selected face at an explicit world height. |
| Q-12 | Text that does not fit is rejected with the available width. |
| Q-13 | Text becomes portable mesh geometry for GLB export. |
| Q-14 | Roof windows and signs are REFINE tools. |
| Q-15 | Geometry has deterministic ids; material assignment remains a separate operation. |
| Q-16 | Every new operation is atomic. |
| Q-17 | Glass, frame, text, and rib segment ids are predictable. |
| Q-18 | Parallel surface normals count as aligned regardless of sign. |
| Q-19 | Surface alignment tolerance is 1 degree. |
| Q-20 | Host contact tolerance is 1 mm. |
| Q-21 | Inspect agents get a direct `measure_surface_angle` tool. |
| Q-22 | Phase promotion verifies both surface angle and host contact. |
| Q-23 | Text creation is backend-neutral; FakeEngine supplies deterministic conservative bounds. |
| Q-24 | `add_primitive` remains backward compatible. |
| Q-25 | Facade ribs may never cross garage doors or other wall openings. |
| Q-26 | A rib crossing an opening is split into solid-wall segments (A-034). |
| Q-27 | Ribs keep 50 mm clearance and omit segments shorter than 100 mm (A-035). |

## User note

> take into account there is issue in the lines you added in the front as some of them collide with the garages.
