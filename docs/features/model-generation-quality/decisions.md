# Model-generation quality — decisions

Gate date: 2026-08-18. The user explicitly identified incoherent top plates, under-designed
striking faces, and poor fit, and authorized reusable generation tools. The details below use the
reversible defaults recorded in A-036 through A-043.

| ID | Decision |
|---|---|
| Q-01 | Success is a fitted assembly whose structural load path reads without explanation. |
| Q-02 | Both connected agents and local scripts receive the improvement. |
| Q-03 | Add a middle-grain `add_impact_head` operation, not a whole weapon generator. |
| Q-04 | The first guaranteed family is a symmetrical dual-strike industrial hammer/maul. |
| Q-05 | Exclude decorative claws, floating fins, and parts with no mechanical role. |
| Q-06 | Expose the operation during REFINE. |
| Q-07 | Export the constructor through the public `ops` barrel. |
| Q-08 | Use one inset top cap with a consistent reveal. |
| Q-09 | Derive front and rear cheek plates from the body profile. |
| Q-10 | Connect each face through a socketed shoulder, collar, face, and outer rim. |
| Q-11 | Connect the handle through a centered underside socket and collar. |
| Q-12 | Reject impossible nesting atomically before geometry creation. |
| Q-13 | Never silently resize requested dimensions. |
| Q-14 | Persist broken-fit checks and block phase promotion when they fail. |
| Q-15 | Make every visible proportion explicit. |
| Q-16 | Keep structural and armor parts separately addressable. |
| Q-17 | Assign materials afterward through deterministic ids. |
| Q-18 | Verify top/body and both cheek/body contacts. |
| Q-19 | Verify shoulders/body, collars/faces, and handle socket/body contacts. |
| Q-20 | Record intended socket depth as explicit joinery. |
| Q-21 | Preserve primitive behavior and existing replay. |
| Q-22 | Pin live-app reachability in integration tests. |
| Q-23 | Rebuild the existing hammer head through the operation and remove incoherent decoration. |
| Q-24 | Require real-Blender BLEND/GLB/PNG regeneration and visual inspection. |

## User note

> the way the plates are placed and how they look isnt well. im talking about the top of the
> hammer also its striking points (hammer sides) look very lacking and make no-sense design wise
> they arent well designed. they also arent well fitted.
