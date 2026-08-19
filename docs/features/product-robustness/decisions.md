# Product robustness decisions

The user asked Forge3D to be "robust and easily usable" and "able to create great 3d
designs", specifically naming UI crossover, automatic agent connection, unreliable file
import/export, and weak agent accuracy and attention to detail.

The traced external-write question was surfaced to the user. No permission to silently modify
Codex, Claude, or Cursor files was provided, so the safe recommended choices below are recorded
as reversible assumptions in [`docs/ASSUMPTIONS.md`](../../ASSUMPTIONS.md). They preserve the
full requested outcome while avoiding an unapproved side effect outside this repository.

| ID | Question | Chosen decision | Alternatives considered | Basis |
|---|---|---|---|---|
| Q-01 | What must feel better? | Dependable launch-to-export collaboration with verified designs. | Fix isolated symptoms only. | A-053 |
| Q-02 | Primary user? | One local desktop user with one live MCP agent. | Cloud or multi-writer collaboration. | A-053 |
| Q-03 | Required scope? | Connection, UI containment, files, agent focus/evals, and project gate. | Defer one or more reported areas. | A-053 |
| Q-04 | Out of scope? | Cloud accounts, multi-writer editing, new formats, replacing Blender. | Expand the platform during repair. | A-053 |
| Q-05 | Narrow top bar? | One responsive layout; collapse secondary content before overlap. | Independent fixed offsets or horizontal clipping. | A-054 |
| Q-06 | Connection location? | Compact top-bar state with accessible detail dialog. | Floating overlay or settings-only state. | A-054 |
| Q-07 | Minimum viewport? | Keep the existing 529px rendered contract. | Raise the minimum or claim mobile support. | A-054 |
| Q-08 | Sidebar allocation? | Flexible chat; bounded, collapsible inspector and log sections. | Fixed undersized rows or unbounded panels. | A-055 |
| Q-09 | Tall inspector? | Internal scrolling with actions reachable. | Clip content or cover adjacent panels. | A-055 |
| Q-10 | Texture density? | Essential state visible; advanced mapping grouped/collapsible. | Show everything at once or hide all texture state. | A-055 |
| Q-11 | Startup connection? | Reconnect viewer and detect/report agents automatically. | Wait for a Connect click. | A-056 |
| Q-12 | External config writes? | Require an explicit Configure action. | Silently rewrite every detected client. | A-056 |
| Q-13 | After configuration? | Report restart-required until reload, with refresh/retry. | Claim connected after writing the file. | A-056 |
| Q-14 | Open/import while running? | Explain, pause, serialize, and remain paused. | Submit a doomed job or resume into a replaced scene. | A-057 |
| Q-15 | Default export scope? | Whole scene; explicit selection-only when offered. | Implicit current selection. | A-057 |
| Q-16 | Guaranteed formats? | Real round trips for `.forge3d` and GLB; validation for all advertised formats. | Mock-only coverage or every format in slow CI. | A-058 |
| Q-17 | Long file work? | Async user-facing jobs, owner-thread Blender execution. | Block the UI or run `bpy` on workers. | A-058 |
| Q-18 | File proof? | API, browser-state, and real-Blender round-trip evidence. | Menu-label tests only. | A-058 |
| Q-19 | Agent tool visibility? | Phase-focused catalogue; raw execution explicit opt-in. | Flat 52-tool list or silent arbitrary cap. | A-059 |
| Q-20 | Mandatory agent loop? | Orient, build semantically, inspect, measure, repair, promote. | Prompt-free discovery or narrative-only advice. | A-060 |
| Q-21 | Orientation response? | Phase, focused tools, failures, operator focus, next actions. | Phase name alone. | A-060 |
| Q-22 | Detail evaluation? | Score representative complete workflows. | Infer accuracy from tool count or prompt text. | A-061 |
| Q-23 | Existing-client compatibility? | Preserve calls/authorization; focus discovery; raw opt-in. | Remove tools or weaken authorization. | A-059 |
| Q-24 | Project gate? | Run backend, frontend, wiring, evals, and honest prerequisite probes. | Stale documented command or silent skips. | A-061 |
| Q-25 | Completion evidence? | Green suites plus live files, rendered containment, truthful connection, focused MCP and gate. | Treat narrow unit tests as completion. | A-061 |
