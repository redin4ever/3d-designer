# Rule 5 — Agents own disjoint files

Many agents build in this codebase at once, and humans work in it too. Parallelism is
only safe behind two things: **frozen contracts** and **non-overlapping file ownership**.

## Contracts freeze before fan-out

Before any parallel implementation starts, the shared surface is written and frozen:

- Types, schemas and event shapes live in one place (`packages/contracts/` or `src/contracts/`)
- Every module's public interface is declared in `.pipeline/modules.json` *before* it is built
- Contracts are owned by the **main agent only**. No subagent edits them.

If an agent needs a contract change mid-phase, it does not edit it. It records the need
in `.pipeline/contract-requests.json` and implements against the current contract with an
adapter. The main agent reconciles requests between waves.

This is the whole reason parallel agents work: they are not coordinating, they are
compiling against the same frozen surface.

## The ownership manifest

`.pipeline/modules.json` is the authority on who may write where:

```json
{
  "iteration": 1,
  "modules": [
    {
      "id": "orders",
      "owner": "agent:orders",
      "paths": ["src/features/orders/**"],
      "publicInterface": "src/features/orders/index.ts",
      "dependsOn": ["contracts", "db"],
      "status": "red"
    }
  ]
}
```

Rules:

- An agent writes **only** inside its own `paths`. Reading anything is always allowed.
- Two modules' `paths` must not intersect. If they want to, they are one module.
- Shared files — root config, lockfiles, CI, `contracts/`, `CLAUDE.md`, migrations —
  are **main-agent only**. A subagent that needs one files a request.
- `status` moves `planned → red → green → refactored`. The main agent integrates only
  modules at `green` or better.

## Isolation

- Agents whose paths are genuinely disjoint run in the shared tree — cheap and fine.
- Agents that must touch overlapping ground, or that run long enough to collide with a
  human, run with `isolation: "worktree"` and are merged by the main agent.
- Never run two writing agents in the same worktree.

## Commits

- Conventional commits, scoped to the module: `feat(orders): reject cancel after refund`
- Small and frequent. One commit per RED/GREEN/REFACTOR step, not one per phase.
- Never commit generated artefacts, screenshots, coverage output, or `.pipeline/` scratch.
- Never `--no-verify`, never force-push a shared branch, never commit on the default
  branch — branch first.

## Working alongside humans

- Before a phase starts, check for uncommitted local changes. If the tree is dirty, work
  in a worktree and say so in the phase report.
- Do not reformat, re-lint, or rename files outside the module you own. Drive-by cleanups
  are how an agent turns a 30-line diff into an unreviewable one.
- Every module ships a `README.md` (what it is, its interface, its invariants) and a
  `CLAUDE.md` (local conventions, its own test and lint commands). A human or agent
  arriving at that directory should need nothing above it to start work.
