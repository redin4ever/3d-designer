# Project instructions

<!-- PIPELINE:PROJECT-SUMMARY -->
**forge3d** — live 3D authoring for AI agents, built on Blender 5.2. It computes the spatial
facts (clipping depth, gap width, manifoldness, angles, scale) and hands the model verified
numbers, takes declarative constraints instead of raw coordinates, and verifies by
re-measuring rather than by asking whether it worked. Exposed over MCP on both transports so
a consumer subscription can drive it. 17 modules, all green.
<!-- /PIPELINE:PROJECT-SUMMARY -->

## Commands

<!-- PIPELINE:COMMANDS -->
```bash
python -m pytest src -q              # backend: 609 tests + 54 conformance checks (fake AND real bpy)
node --test frontend/tests/          # frontend: 28 tests
python src/forge3d_cli.py doctor     # is the product actually wired and startable?
node .pipeline/check.mjs             # the gate — reads disk, re-runs both suites
```

`python` means `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`. The `python` on PATH
is the Windows Store alias stub and runs nothing.
<!-- /PIPELINE:COMMANDS -->

## Codebase map

<!-- PIPELINE:CODEBASE-MAP -->
| Path | What decides here |
|---|---|
| `src/contracts/` | The frozen shared surface. **Main-agent only.** |
| `src/testing/` | `FakeEngine` — a real in-memory engine, not a mock. **Main-agent only.** |
| `src/app/` | The composition root. Wires everything; owns JSON→domain coercion. **Main-agent only.** |
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
3. **`src/contracts/`, `src/testing/` and `src/app/` are main-agent only.** Sixteen modules
   compile against the first, every suite depends on the second, and the third is the one
   place allowed to know about all of them. A change there is multiplied by everything.

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
