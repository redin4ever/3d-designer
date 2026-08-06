# Security

**This tool provides no security boundary against a connected agent.** That is a decision,
not an oversight, and this page states it plainly rather than burying it.

## What a connected agent can do

An agent that can reach this server can:

- **Run arbitrary Python** in the tool's process, via the `raw_execute` tool (`src/raw/`).
  There is no sandbox, no allowlist, and no AST inspection.
- **Read and write any file the user can.** There is no path restriction.

Both were chosen explicitly at Gate A, with the risk stated in the question at the time. The
precedent was named: the de-facto standard agent–Blender bridge exposes exactly this design
and carries an open CVSS 9.0 remote-code-execution issue as a result. See
[ADR-009](adr/ADR-009-unrestricted-execution-local-trust.md).

## Why that is a defensible choice here

The trust boundary is **one user's own machine and their own agents**:

- Gate A 7.1 — runs locally, not hosted.
- Gate A 7.3 — the codebase stays private and is never distributed.

There is no multi-tenant surface and no third party whose data is at stake. An agent running
here already has whatever access the user running it has, and `raw_execute` grants nothing
the user could not do themselves. Sandboxing a tool whose whole purpose is to let an agent
drive Blender would be security theatre against a threat model that does not apply.

**If either of those two facts stops being true, this page is wrong and ADR-009 needs
revisiting before anything ships.**

## The sharp edge: the HTTP transport

`stdio` is only reachable by a process the user launched. **An HTTP listener is reachable by
anything that can route to it.**

- It binds `127.0.0.1` by default.
- Binding elsewhere requires an explicit `--host`, and logs a warning naming ADR-009.
- There is **no authentication layer**. Anything that reaches the port has unrestricted code
  execution and full filesystem access.

Do not bind this to a non-loopback address on a shared or untrusted network. If you need
remote access, put it behind something that authenticates — an SSH tunnel is the simple
answer.

## What *is* defended

The absence of a sandbox is deliberate; these are not:

- **Every raw call is recorded** in the operation log as an opaque edit and creates an undo
  barrier with a real snapshot. Nothing runs invisibly, and you can always get back.
- **Raw execution takes the same write lock** as any other mutation, so it cannot race a
  concurrent agent.
- **It is switchable off.** `build_app(include_raw=False)` or `forge3d serve --no-raw`
  removes the tool from the registry entirely.
- **It is `ADMIN`-role only.** It is never visible to the `INSPECT` role, which is what lets
  many read-only sub-agents run concurrently — a mutating tool there would break that
  guarantee. `contracts.ToolSpec` enforces this at construction, so the combination cannot
  be created even by accident.
- **A failing script returns a named error**, never a bare traceback, and reports what it
  created before it failed. Partial application is real and the report does not pretend
  otherwise.

## Dependencies

`bpy` is GPL-3.0. Distribution is what triggers copyleft; Gate A 7.3 keeps this private and
undistributed, so no obligation attaches. **If that changes, the licensing question in
[ADR-001](adr/ADR-001-blender-as-geometry-engine.md) and
[technical.md](research/technical.md) must be answered before shipping** — the `import bpy`
case in particular is genuinely unsettled, and Blender's own guidance is to consult a
lawyer.

## Reporting

This is a private, single-user tool. If it stops being one, add a real reporting path here
and revisit every line above.
