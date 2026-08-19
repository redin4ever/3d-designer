# Profiled-shape design accuracy decisions

No answers were provided at the decision gate, so the documented recommended choices below are
reversible assumptions A-045 through A-052.

| ID | Decision | Chosen outcome |
|---|---|---|
| Q-01 | Primary job | Replace primitive stacking for silhouette-critical hard-surface forms. |
| Q-02 | Audience | Connected agents and local Python asset generators use the same operation. |
| Q-03 | Tool grain | One reusable `add_profiled_solid` tool covers extrusion and lofting. |
| Q-04 | First regression | Rebuild the forge anvil and extraction hood. |
| Q-05 | Phase | Expose construction during REFINE. |
| Q-06 | Shape representation | Ordered local 2D profiles at ordered offsets along one world axis. |
| Q-07 | Supported axes | X, Y and Z with the same right-handed winding contract. |
| Q-08 | Minimum stations | Two; identical profiles are an extrusion and changing profiles are a loft. |
| Q-09 | Profile class | Closed convex profiles first. |
| Q-10 | Correspondence | Every station has the same vertex count and index correspondence. |
| Q-11 | Station order | Strictly increasing offsets; no implicit sorting. |
| Q-12 | Invalid input | Reject atomically with a named rule and actionable station/point index. |
| Q-13 | Silent correction | Never resize, reorder or reverse caller geometry silently. |
| Q-14 | End treatment | Cap both ends so the result is a closed solid. |
| Q-15 | Bevel | Explicit non-negative width; zero means no edge treatment. |
| Q-16 | Output granularity | One deterministic mesh per call; assemblies remain separate objects. |
| Q-17 | Materials | Assigned afterward through existing material operations. |
| Q-18 | Verification | Gate positive volume and structural topology; pin bounds in geometry tests. |
| Q-19 | Aesthetic QA | Render inspection remains explicit; geometry does not claim artistic judgment. |
| Q-20 | Existing primitives | Preserve all primitive behavior and replay compatibility. |
| Q-21 | Visible catalogue | Add one REFINE tool and deliberately update both count ledgers. |
| Q-22 | Documentation | Show forge, architectural and furniture examples to keep the tool general. |
| Q-23 | Export | Preserve separate editable parts in BLEND and GLB by default. |
| Q-24 | Quality target | Historically plausible silhouettes with game-ready section density. |
| Q-25 | Completion evidence | Unit, wiring, real-Blender, full-suite, feature-gate and visual render evidence. |
