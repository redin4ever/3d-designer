# Product robustness

Forge3D now has one dependable launch-to-export path: the viewer reconnects itself, agent
readiness is detected without an unsafe config write, controls and inspectors remain
contained at the supported 529px minimum, and scene file work crosses onto Blender's owner
thread before touching `bpy`.

## What changed

- The top bar uses one responsive flex layout. Tall transform and texture inspectors scroll
  internally, advanced texture mapping is collapsible, and rendered tests check bounding
  boxes at desktop and narrow widths.
- Agent clients are detected on page startup and whenever the tab becomes visible again.
  Configuration remains an explicit action and reports restart-required truthfully.
- Open/import pauses an active build and stays paused. File jobs serialize on workers while
  Blender operations are dispatched to the owner thread. Export defaults to the whole scene
  and selection export is explicit.
- MCP discovery shows one complete specialist role plus orientation tools instead of every
  cross-phase schema. `set_tool_focus` switches roles, server instructions require measured
  verification, `get_phase` returns operator focus and next actions, and raw execution is an
  explicit `--raw` opt-in.
- `.pipeline/check.mjs` is the single whole-project command. It runs backend/evals, frontend,
  rendered Chrome tests, the startup doctor, and the feature wiring gate while distinguishing
  unavailable prerequisites from product failures.

## Compatibility and safety

Semantic tool calls and phase authorization remain compatible; discovery focus changes only
what an agent has to choose among. External Codex, Claude, and Cursor configuration is never
rewritten automatically. Raw execution remains unrestricted after explicit opt-in, so it is
disabled by default.

## Verification

Run `node .pipeline/check.mjs`. Exit 0 means every product and wiring check passed, exit 1
means a product failure, and exit 2 means the environment lacked a required prerequisite.
