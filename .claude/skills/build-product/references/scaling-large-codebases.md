# Scaling — applying the large-codebase practices

Derived from *How Claude Code works in large codebases: best practices and where to start*
(claude.com/blog, fetched 2026-08-02). The pipeline builds a codebase that will get large,
so these are applied **while** building rather than retrofitted.

## Hierarchical CLAUDE.md

> "Keep root-level CLAUDE.md lean, focusing only on critical gotchas and pointers." Files
> "load additively as Claude traverses directories, preventing context bloat."

- Root `CLAUDE.md`: what the repo is, the rules as links, the codebase map, gotchas.
  Nothing that belongs to one package.
- **Per-package `CLAUDE.md`**, written in Phase 4.6: local conventions, and this package's
  own test and lint commands. Do not centralise commands at the root — an agent working in
  `src/features/orders/` should run only what it affects.
- Agents are started **in the subdirectory they are working on**. Claude walks up and picks
  up the root file anyway, so scoping down costs nothing and saves context.

## .claudeignore

> "Exclude generated files and third-party code via `.claudeignore` to reduce noise."

Written at bootstrap and kept current: build output, `node_modules`, lockfiles, coverage,
QA artefacts, generated token files, snapshots. Every generated artefact the pipeline
creates gets added the moment it is created — noise compounds.

## Hooks instead of reminders

> Hooks "automate consistent behaviour rather than relying on Claude to remember
> instructions" and "enforce linting and formatting deterministically."

The pipeline ships `.claude/hooks/check-file-size.mjs` on `PostToolUse` for Write/Edit —
Rule 2 enforced by a program rather than by an agent's good intentions. It is **advisory,
not blocking**, because a hook that halts a phase breaks Rule 3.

Worth adding per project once the stack is known: a formatter on `PostToolUse`, and a
`Stop` hook that proposes `CLAUDE.md` updates while the session's context is still fresh.

## Codebase maps

> "Create codebase maps in markdown when directory structure doesn't clarify
> organisation." "List top-level folders with one-line descriptions."

`docs/ARCHITECTURE.md` is written in Phase 4.1 **before** the code, and reconciled in 4.6
against what was actually built. The root `CLAUDE.md` carries the one-line-per-directory
version. Phase 5 files a defect when the map and the tree disagree — a stale map is worse
than none, because it is trusted.

## Subagents for exploration

> "Have read-only subagents map subsystems and return findings for parent agents to edit
> with full context."

This is exactly the Phase 1 and Phase 5 shape: read-only finders return structured
findings, the main agent holds the editing context. See
[agent-briefs.md](agent-briefs.md) — the BOUNDARY line is what makes it hold.

## Skills and progressive disclosure

> "Skills keep the right expertise available on-demand without bloating every session."

`SKILL.md` is an index. Each phase file is read on entry to that phase and not before.
This is why the phase files have a line budget too — a reference that must be read whole
is not progressive disclosure.

## LSP and MCP

> "LSP integrations give Claude the same navigation a developer has in their IDE" —
> symbol-level precision rather than text matching. MCP servers connect internal tools,
> docs and ticketing.

Once a stack is chosen at Gate A, enabling the language server for it is the single
highest-leverage configuration change for iteration 2 onward — rename and find-references
stop being grep. If the project has an issue tracker, wiring it via MCP lets Phase 5 file
defects where the team actually looks; ask about this in Gate A wave 10.

## Distribution

> "Plugins distribute what works." Bundle skills, hooks and MCP config into installable
> packages.

If this pipeline is used on more than one project, package `.claude/skills/build-product/`,
`.claude/rules/` and `.claude/hooks/` as a plugin rather than copying directories. Copies
diverge; the fifth project ends up with the second project's bugs.

## Review cadence

> "Review configuration every 3-6 months as models evolve. Rules that previously
> constrained older models may become unnecessary obstacles."

The rules and phase files here are calibrated to today's models. Some — file caps, the
explicit RED-commit requirement, the concurrency cap — exist because they were needed.
Re-check them periodically and delete what has become friction. Record removals in an ADR
so the reasoning is not lost and then rediscovered as a "missing" rule.

## Governance

For team use the blog's advice maps directly: one owner for this pipeline's configuration,
a small approved set of skills, and a cross-functional read of the rules before rollout.
Infrastructure first, then adoption — a team whose first run hits a broken hook does not
come back.
