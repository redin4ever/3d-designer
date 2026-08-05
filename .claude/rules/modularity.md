# Rule 2 — Files stay small

A file that carries a lot of code cannot be reviewed by a human, reasoned about by an
agent, or edited by two agents at once. Small files are what make Rules 3 and 5 possible.

Split **before** you cross a budget. Growing a file to 1,000 lines and then refactoring is
the failure this rule exists to prevent.

## Budgets

| Unit | Soft cap | Hard cap |
|---|---|---|
| Source file | 300 lines | 1000 lines |
| Function / method | 120 lines | 400 lines |
| Function parameters | 8 | 16 (beyond that, pass one options object) |
| Exported symbols per file | 5 primary | 10 |
| Nesting depth | 4 | 7 |
| Markdown / reference file | 300 lines | 600 lines |

Counts exclude imports, type-only declarations, and comments. Test files get 1.5× the
source budget — a thorough test is not a bloated one.

Crossing a **soft** cap means: justify it in one line or split. Crossing a **hard** cap
means: split, no exceptions, no "just this once".

## How to split

Split along **responsibility seams**, never along line counts. A 900-line file cut at
line 450 produces two shallow files and one new import — that is worse than the original.

Good seams, in order of preference:

1. **A distinct decision** — validation, formatting, permission checks, retry policy
2. **A distinct actor** — what talks to the DB vs what talks to HTTP vs what decides
3. **A distinct lifecycle** — construction/config vs steady-state behaviour
4. **A distinct data shape** — one file per entity's mapping logic

Bad seams: "the first half", "the helpers", "the misc utils", "everything I wrote today".

## Shape of a module

```
src/features/<feature>/
  index.ts            # the ONLY public surface — re-exports, nothing else
  <feature>.ts        # the one deep entry point
  <thing>.ts          # one responsibility each
  <thing>.test.ts     # co-located with what it tests
  CLAUDE.md           # local conventions + this package's test/lint commands
  README.md           # what this feature is, its public interface, its invariants
```

- Nothing outside a feature may import a path deeper than its `index.ts`.
- `index.ts` contains re-exports only. If it contains logic, it is not a barrel.
- Prefer **deep modules**: a narrow interface hiding meaningful work. A file whose
  interface is as complex as its implementation should be inlined into its caller.
- No pass-through wrappers. A function that only forwards arguments is a line of noise
  and a future merge conflict.
- Shared code that two features need does not go in `utils/`. It goes in a named module
  that says what it is (`money/`, `dates/`, `retry/`).

## Enforcement

`.claude/hooks/check-file-size.mjs` runs after every Write/Edit and reports files over
budget. It is advisory — it does not block — because a build that halts mid-phase
violates Rule 3. Treat its output as work you must do before the phase ends, not later.

At the end of every implementation phase, no file may exceed a hard cap. This is checked
in Phase 5 QA and any violation is filed as a defect like any other.

## This rule applies to prose too

Skill references, docs, and ADRs follow the same budgets. A 600-line SKILL.md defeats
progressive disclosure exactly the way a 600-line source file defeats modularity.
