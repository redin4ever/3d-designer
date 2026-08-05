# Project instructions

<!-- PIPELINE:PROJECT-SUMMARY -->
A tool that lets AI agents author and refine 3D models live — filling geometric gaps,
raising detail and realism past "stitched-together boxes", fixing angles and clipping,
and coordinating multiple sub-agents on one scene. Built on Blender/`bpy` as the geometry
engine. Phase 1 research pending.
<!-- /PIPELINE:PROJECT-SUMMARY -->

## Rules

These are binding. If a task instruction and a rule conflict, the rule wins.

| # | Rule | File |
|---|---|---|
| 1 | Gate questions carry UX choices | [.claude/rules/questions.md](.claude/rules/questions.md) |
| 2 | Files stay small | [.claude/rules/modularity.md](.claude/rules/modularity.md) |
| 3 | Never block between gates | [.claude/rules/autonomy.md](.claude/rules/autonomy.md) |
| 4 | Tests first | [.claude/rules/testing.md](.claude/rules/testing.md) |
| 5 | Agents own disjoint files | [.claude/rules/collaboration.md](.claude/rules/collaboration.md) |
| 6 | Assume every agent dies | [.claude/rules/resilience.md](.claude/rules/resilience.md) |

## Pipeline state

`.pipeline/state.json` is the source of truth for where the build stands.
`docs/PIPELINE-LOG.md` is the human-readable history.

## Environment facts (verified 2026-08-05)

- Node **v24.18.0**, git **2.55.0** available.
- **Python is NOT installed** — `python3.exe` is the Windows Store alias stub only.
- **Blender is NOT installed** on this machine and not on `PATH`.
- Platform: Windows 11 Pro, PowerShell primary shell (also a Git Bash tool).

Anything requiring a real Blender or CPython runtime must degrade gracefully or be
gated behind an explicit availability check. Test suites must not require Blender.
