# Project instructions

<!-- PIPELINE:PROJECT-SUMMARY -->
**forge3d** — live 3D authoring for AI agents, built on Blender 5.2. It computes the spatial
facts (clipping depth, gap width, manifoldness, angles, scale) and hands the model verified
numbers, takes declarative constraints instead of raw coordinates, and verifies by
re-measuring rather than by asking whether it worked. Exposed over MCP on both transports so
a consumer subscription can drive it. 17 modules, all green.
<!-- /PIPELINE:PROJECT-SUMMARY -->

## Sub-agents

The only permitted sub-agent is **Luna** (`luna`); do not spawn or delegate to any
other sub-agent, model, or agent identity. Luna may do anything in the repository,
including editing shared contracts, configuration, tests, and any module, running
commands, and crossing ownership boundaries. The usual main-agent-only and
file-ownership restrictions do not limit Luna. If Luna is unavailable, the main agent
continues without substituting a different sub-agent. `AGENTS.md` is the companion
agent-instructions file.

## Commands

<!-- PIPELINE:COMMANDS -->
```bash
node tools/run-pytest.mjs src -q                 # backend + deterministic agent evals
node --test frontend/tests/                      # frontend unit suite
node --test frontend/tests-browser/smoke.test.js # rendered UI (set PUPPETEER_EXECUTABLE_PATH if needed)
node .pipeline/check.mjs                         # complete gate, including doctor + feature wiring
```

The runners discover Python 3.13 and Chrome/Edge from explicit environment overrides and
standard install locations. Missing prerequisites are reported as `UNAVAILABLE` with exit
code 2; product failures use exit code 1, so a missing browser can never look like a pass.
<!-- /PIPELINE:COMMANDS -->

## Codebase map

<!-- PIPELINE:CODEBASE-MAP -->
| Path | What decides here |
|---|---|
| `src/contracts/` | The frozen shared surface. Main-agent or Luna. |
| `src/testing/` | `FakeEngine` — a real in-memory engine, not a mock. Main-agent or Luna. |
| `src/app/` | The composition root. Wires everything; owns JSON→domain coercion. Main-agent or Luna. |
| `src/engine/` | **The only module that may `import bpy`.** |
| `src/spatial/` | Maintained BVH, broad-phase proximity. |
| `src/measure/` | 7 metrics, 10 defect classes. Pure — never mutates. |
| `src/constraints/` | The 12-type vocabulary, solved to transforms. |
| `src/ops/` `src/align/` `src/gaps/` `src/detail/` `src/uv/` | The operation library. |
| `src/scene/` | The operation log, replay, undo, checkpoints. |
| `src/orchestration/` | Phases, the single write lock, conflicts, cadence. |
| `src/export/` | Per-engine profiles. Roblox primary. |
| `src/raw/` | Unrestricted execution (ADR-009). |
| `src/viewer/` `frontend/` | The live view. |
| `src/mcp_server/` | Both transports, role-partitioned registry. |

Full detail and the reasoning behind each seam: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
<!-- /PIPELINE:CODEBASE-MAP -->

## The three things to know before changing anything

1. **`src/engine/` is the only module that may `import bpy`.** Everything else speaks
   `contracts.EngineProtocol`. That is why the decision layer tests in a tenth of a second
   without Blender, and why a Blender version bump touches one module instead of fifteen —
   Blender ships breaking API changes with no deprecation policy.
2. **Tests come first.** No implementation before a test that fails for the right reason. A
   test failing with `ImportError` has not been verified. Never edit a test to make an
   implementation pass — if a test looks wrong, it is usually describing a requirement you
   have not read yet.
3. **`src/contracts/`, `src/testing/` and `src/app/` may be changed by the main agent or
   Luna.** Sixteen modules compile against the first, every suite depends on the second,
   and the third is the one place allowed to know about all of them. A change there is
   multiplied by everything.

## Rules

Binding. If a task instruction and a rule conflict, the rule wins.

| # | Rule | File |
|---|---|---|
| 1 | Gate questions carry UX choices | [.claude/rules/questions.md](.claude/rules/questions.md) |
| 2 | Files stay small | [.claude/rules/modularity.md](.claude/rules/modularity.md) |
| 3 | Never block between gates | [.claude/rules/autonomy.md](.claude/rules/autonomy.md) |
| 4 | Tests first | [.claude/rules/testing.md](.claude/rules/testing.md) |
| 5 | Agents own disjoint files | [.claude/rules/collaboration.md](.claude/rules/collaboration.md) |
| 6 | Assume every agent dies | [.claude/rules/resilience.md](.claude/rules/resilience.md) |

## Environment facts (verified 2026-08-06)

- **Blender 5.2.0 LTS** installed; `bpy` 5.2.0 imports **in-process**.
- **Python 3.13.14** at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`.
- `mcp`, `websockets`, `starlette`, `uvicorn`, `pytest` installed.
- Node v24.18.0, git 2.55.0.
- Platform: Windows 11, PowerShell primary (a Git Bash tool also exists).

Contrary to an early research note: `bpy`-as-a-module **does** have window access in this
build, so unwrap, bake and glTF export run in-process rather than needing the subprocess
fallback. Blender 5.2's boolean solver enum is `FLOAT`/`EXACT`/`MANIFOLD`, not `FAST`.

## Pipeline state

`.pipeline/state.json` is the source of truth for where the build stands.
`docs/PIPELINE-LOG.md` is the human-readable history.
