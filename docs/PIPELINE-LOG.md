# Pipeline log

What ran, what was decided, what was assumed, what is queued. This is the record the user
reads instead of having watched.

## Phase 0 — Bootstrap (2026-08-05)

**Ran:** created `.pipeline/`, `docs/{adr,decisions,research,qa}/`; installed all 6 rules
into `.claude/rules/` and both hooks into `.claude/hooks/` wired via `.claude/settings.json`
(`check-file-size.mjs` on PostToolUse, `pipeline-continue.mjs` on Stop); copied the gate
(`.pipeline/check.mjs` + `lib/`); seeded `CLAUDE.md`, `.gitignore`, `.claudeignore`,
`docs/ASSUMPTIONS.md`; `git init` + first commit.

**Idea as given:** a tool/app that lets AI models author 3D models live — assisting with
blank/gap filling, pushing design detail and realism beyond "stitched-together cubes",
handling angle adjustment and part clipping (e.g. railings), with multi-agent / sub-agent
task assignment, aimed at raising model accuracy, detail attention and spatial awareness.
Blender/`bpy` named as an acceptable starting point.

**Environment facts found:** Node v24.18.0 and git 2.55.0 present. Python **not** installed
(Store alias stub only). Blender **not** installed, not on PATH. Recorded in `CLAUDE.md`;
this is a hard constraint on how the product can be tested here.

**Decided:** nothing about the product. Phase 0 makes no design choices.

**Queued for Gate A:** nothing yet — Phase 1 populates the backlog.

**Repo now:** empty of source, fully instrumented, `state.json` at `phase: 1, pass: 1`.
