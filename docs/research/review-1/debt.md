# The bill

## Method

Read `docs/ASSUMPTIONS.md` (10 entries), `.pipeline/backlog.json` (61 items),
`.pipeline/contract-requests.json` (8 requests), `docs/qa/report-1.md` (both rounds),
`docs/PIPELINE-LOG.md`, `.pipeline/modules.json`, `.pipeline/state.json`, and
`.claude/rules/modularity.md`. Cross-checked every claim against the current tree (`src/`,
`frontend/`) rather than trusting the documents: ran an AST pass over all `src/**/*.py` for
file/function size and nesting, `wc -l` over every source and test file, targeted `grep` for
duplication, TODO/FIXME/debug prints/commented-out code, and read the flagged files
directly. Verified `mcp`, `websockets`, `starlette` are actually importable in this
environment (`python -c "import ..."`) rather than trusting module docs' claims about them.
Read `git log --oneline` (29 commits) to confirm the QA report's RED-commit claims rather
than re-deriving them. Did not run any test suite - per constraints, this is a static audit
of what exists, not a re-verification of what was already run. State at time of writing:
`phase: 6, pass: 1`, `next: "Phase 6 review research, then Gate B"` - Gate B has not
happened yet, so every item in `ASSUMPTIONS.md` flagged "queued for Gate B" is still,
definitionally, open.

## Open assumptions

| id | still true? | blast radius | cost to resolve |
|---|---|---|---|
| A-001 in-process `bpy`, Python core | **True**, load-bearing everywhere (`src/engine/session.py:88` `BlenderEngine()` direct). Its own text says reversal cost is "high after Phase 4" - Phase 4 is done, so that clause has now silently flipped from advisory to binding. | Whole server. | N/A to resolve; cost is that reversing it is no longer cheap - worth one line in HANDOVER that the window closed. |
| A-002 checks report, don't block | **True**, wired (`src/orchestration/reporting.py`, ADR-005). | Check layer + operation loop. | None - confirm at Gate B. |
| A-003 no collision meshes/atlasing | **True** - B-030, B-031 unbuilt, P3. | Export module only. | None. |
| A-004 sequencing by priority | **True** - rigging (B-029) got least depth, matches stated order. | `docs/HANDOVER.md` content. | None - this review is part of paying it. |
| A-005 HTTP binds loopback | **True** in code (`src/mcp_server/transports.py:29,119`), but the non-default path is untested - see coverage gaps. | One config line, now also a test gap. | Small: add a bound-to-0.0.0.0 test with a fake SDK. |
| A-006 12-type constraint vocabulary | **True**, all 12 present (`src/contracts/constraints.py:44-77`). "Queued for Gate B: evidence of which constraints agents actually reached for" - **no such evidence exists**; no agent has run against this outside tests. | Solver + every placement call. | Cannot be resolved without a real run; flag as unresolvable pre-Gate-B. |
| A-007 checkpoint/log retention | **True** as designed (`src/scene/persistence.py`, `src/scene/history_test.py`), never contradicted, never stress-tested past unit scope. | Scene doc schema. | None to resolve; untested at scale (see coverage gaps). |
| A-008 1 Roblox stud = 0.28 m | **Still unverified.** `src/contracts/export_profiles.py:98` carries the constant with no citation or verification comment anywhere in the tree - explicitly flagged "needs verification... not acceptance on the strength of this note" and that never happened. | Roblox profile only, but it is the **primary** profile per Gate A. | Small - one web check against Roblox's own docs, one constant, one regression test. |
| A-009 pytest + Puppeteer | **Contradicted.** `package.json:15` declares `puppeteer`, but it is not installed (`node_modules` has no puppeteer binary) and QA round 1+2 both record "Puppeteer is not installed; the frontend is exercised as ES modules" - nothing has ever verified real rendering, layout, or keyboard behaviour in a browser. | Whole frontend suite's credibility. | Medium - `npm install`, write the actual browser suite; first real run may surface new defects (see coverage gaps). |
| A-010 scene doc is JSON | **True** (`src/scene/persistence.py`). | Persistence layer. | None. |

## Open backlog, by priority

`backlog.json` has 61 entries: 27 marked `"fixed"` (all QA-round defects, verified against
the QA report - not re-litigated here), 1 `"done"`, 3 explicitly `"open"`, and **30 with no
`status` field at all**. Cross-referencing those 30 against `.pipeline/modules.json` (all 17
modules `"green"`) shows 24 of them (B-001-B-021, B-023-B-025, B-027) are the original
feature items and are in fact **built** - the field was simply never written. That is itself
listed under Leftovers. The genuinely open work is:

**Defects (P2):**
- **Q-017** `.pipeline/backlog.json:3-10` - 10 modules have RED commits the gate's
  per-module matcher can't parse (combined scopes like `b63166d`); 6 modules
  (`gaps,align,uv,mcp,viewer,frontend`) have no RED commit at all; `app`'s tests were
  committed after its implementation. QA declined to fabricate retroactive commits. Cost to
  resolve: either teach the gate's matcher combined scopes (small, mechanical) or accept
  this as a known process gap and say so in HANDOVER (free). Not a code defect - a
  process-evidence gap.

**Design questions (P2), not defects:**
- **B-00K** `backlog.json:204-211` - `add_railing` declares no `JoineryIntent` for the parts
  it deliberately embeds, so a stair+railing throws 94 clipping warnings an agent must
  dismiss by hand. Cost: small (one function, `src/ops/railing.py`, needs a decision on
  whether operations should self-declare joinery - that's the actual open question).
- **B-00L** `backlog.json:213-219` - real Blender bevel produces mean triangle aspect ratio
  ~116, edge-length CoV ~1.6 on a simple tread. Correctly measured, badly produced. Cost:
  medium - bevel parameter tuning or a cleanup pass in `src/detail/edges.py`.

**Missing features, deferred by design (P3), not started:**
- **B-029** rigging/organic sculpting - "thin coverage" was the plan; there is in fact
  **zero** coverage. No `src/rig/` or equivalent exists.
- **B-030** collision meshes, **B-031** texture atlasing - offered at Gate A, not selected,
  not built. Both additive; cost to add is a new export post-process each, medium.

## Coverage gaps - what has never been run

- **The MCP SDK server path.** `src/mcp_server/transports.py:97` `serve_stdio` and `:112`
  `serve_http` call a real `mcp.server.Server`, but no test drives a real client against
  them - `transports_test.py` only checks the absence-error and the loopback-warning log
  line. The SDK **is** importable in this environment (`import mcp` resolves to
  `site-packages/mcp`, confirmed directly) but nobody has run `forge3d serve` and connected
  a client to it. Cost to close: medium - needs a scripted client, one afternoon.
- **The viewer's live socket loop.** `src/viewer/server.py`'s `serve()` - same story;
  `websockets` and `starlette` are also both actually installed (confirmed directly,
  contradicting `src/viewer/CLAUDE.md:57-58`'s "not installed in this environment"), but no
  test opens a real socket and pushes a frame. Cost: medium.
- **A real browser.** No Puppeteer install (see A-009). Nothing has ever verified the
  three.js canvas renders, that CSS/layout matches `DESIGN.md`, or that a keyboard user can
  drive the controls. Cost: medium-large - first real run is likely to find new defects, per
  the pattern already established twice this project (contract review found 15, test audits
  found 6, composition root found 3 - every integration layer that got its first real
  exercise found bugs no unit suite could).
- **The engine's subprocess fallback.** `src/engine/session.py:88-105` -
  `create_engine(prefer_subprocess=True)` is a bare `raise NotImplementedError`, honestly
  labelled. Nothing shells out to `blender.exe`. Given the Phase-4 finding that in-process
  `bpy` has window access in this build (`docs/PIPELINE-LOG.md:236-239`), it is not even
  clear this path is still needed - see Decisions.
- **Real concurrency on the write lock.** `src/orchestration/locking_test.py` and every
  other lock test call `acquire`/`apply` sequentially in one process/thread - grepped for
  `threading.Thread(`/`.start()` across the whole lock-contention test surface: zero hits.
  The "single writer, many readers" property - the safety guarantee the entire multi-agent
  design rests on (B-016) and the exact thing a real deployment needs, since it is meant to
  serve genuinely concurrent agent connections - has never been tested against genuine OS
  concurrency, only simulated in-order calls.
- **Anything above ~1000 objects.** The 17x-then-fixed object-creation curve
  (`docs/qa/report-1.md:75-77,159-161`) was measured to ~900 objects before and 900 after
  the fix (0.78 ms/op). The stated target is "thousands"; the curve was never followed past
  900 either time.
- **A-008's stud conversion**, never checked against source. **A-006's "which constraints
  agents actually use"**, never observable because no agent has used any of them outside a
  test file.
- **`serve_http` bound to a non-loopback host with a real SDK present** -
  `test_serve_http_on_a_non_loopback_host_logs_a_warning_naming_adr_009` only checks the log
  line fires before the (missing-SDK) `RuntimeError`; nothing has ever actually bound
  `0.0.0.0` and confirmed a remote connection can, per ADR-009, do exactly what the warning
  says it can.

## Files and functions over budget

Against `.claude/rules/modularity.md` (300 soft/1000 hard for source, 450 soft/1500 hard for
tests at 1.5x, 120/400 for functions). No file is anywhere near a **hard** cap - the largest
is 530 lines, half the hard limit. Seven files cross their **soft** cap with no written
justification found in-file or in the owning module's `CLAUDE.md`:

| file | lines | cap | justified? |
|---|---|---|---|
| `src/contracts/contracts_test.py` | 530 | 450 (test) | no |
| `src/contracts/operations.py` | 408 | 300 | no |
| `src/testing/fake_engine.py` | 392 | 300 | no |
| `src/contracts/geometry.py` | 345 | 300 | no |
| `src/contracts/measurement.py` | 325 | 300 | no |
| `src/contracts/engine.py` | 319 | 300 | no |
| `src/app/handlers.py` | 310 | 300 | no |

Cost to resolve: small per file (one line of justification, e.g. "frozen shared surface,
splitting fragments the import order" - which is in fact the real reason for the four
`contracts/` files per that module's own `CLAUDE.md` acyclic-import-order note) or an actual
split. Given all seven sit only marginally over (3-33%) and five of seven are in
`contracts/`, where `CLAUDE.md` already states splitting is disfavoured (a change there is
"multiplied by all [sixteen modules]"), the honest read is these are justified in spirit but
not in the one required line - a five-minute fix, not a restructuring.

Three functions cross the 120-line soft cap for functions, none the 400 hard cap:
`src/scene/document.py:32` `apply` (130 lines), `src/app/handlers.py:181` `build_handlers`
(130 lines), `src/ops/_acceptance.py:17` `acceptance_for` (121 lines). No nesting-depth hard
violations survived manual review (an AST depth pass flagged `src/ops/validation.py:104`,
but that function is a flat `elif` chain the Python AST represents as nested `orelse` blocks
- not a real depth-7 structure; discounted after reading it).

## Duplication that will drift

- **`_triangle_normal`, four independent copies**, one already caused a real crash
  (B-00H/Q-006, fixed): `src/align/position.py:41`, `src/constraints/anchors.py:78`,
  `src/detail/edges.py:162`, `src/uv/seams.py:71`. All four now use `EPSILON` correctly, but
  **they still disagree on the degenerate case's return value**: three return `None`
  (align, detail, uv); `constraints/anchors.py:82-83` returns `Vec3(0.0, 0.0, 0.0)` and
  layers a *second*, undocumented magic threshold (`_face_groups` at
  `src/constraints/anchors.py:95` re-checks `n.length() < 1e-9`, not `EPSILON`). Nothing
  breaks today because each caller matches its own copy, but "fix the anchors copy to also
  return `None`, like the others" is exactly the kind of drive-by consistency edit that
  would silently reintroduce a bug at `:95`. Cost to close for good: small - one shared
  function in `contracts` or a documented, tested exception (same pattern used for
  `rotation_aligning` below).
- **`sample_polyline`/`arc_length_to`/`tangent_at`/`rotation_from_up_to`, duplicated
  between `src/engine/_curve.py` and `src/testing/mesh_helpers.py`** (deliberate, per both
  modules' docstrings - production code may not depend on `src/testing/`). **They have
  already diverged**: `src/testing/mesh_helpers.py:51-52` guards `sample_polyline` with
  `if spacing <= 0: raise ValueError(...)` internally; `src/engine/_curve.py`'s copy
  (starting `:20`) has no such guard. Both current callers (`src/engine/modifiers.py:153`
  and `src/testing/fake_engine.py:290`) happen to check `spacing <= 0` before calling, so
  nothing breaks today - but `_curve.py`'s `sample_polyline` is not safe to call directly:
  `spacing <= 0` makes the `while t <= length + 1e-9: ... t += spacing` loop either not
  advance or run forever. Cost to close: small - add the same guard to `_curve.py`, or
  better, delete it from both copies and require every caller to check (already true) with
  a one-line comment explaining why.
- **`rotation_aligning`/`perpendicular_in_plane`, duplicated between
  `src/align/_geom.py:57,76` and `src/constraints/_geom.py:56,78`** - explicitly documented
  as deliberate in both files' module docstrings, formulas confirmed byte-identical by
  direct comparison, no drift found. Lower risk than the two above because the duplication
  itself is the visible, load-bearing decision (Rule 5 barrel boundary), not an accident -
  but still two copies of closed-form math with no shared regression test proving they stay
  identical if one is ever tweaked. Cost to harden: small - one cross-module property test
  asserting the two produce the same quaternion for a shared set of inputs.
- **Two independent tool registries claiming to be the same thing.**
  `src/orchestration/_tool_registry.py:32-77` (`TOOLS_BY_ROLE`) is a hand-written table of
  **fictional** tool names/schemas (`_EMPTY_SCHEMA` for every entry) that `Orchestrator.
  tools_for()` serves. `src/mcp_server/registry.py:79` (`build_registry`) is the real
  registry, dynamically assembled from every module's actual `*_SPECS`. These do not agree
  (`_tool_registry.py` has `"close_gap"`; the real gaps registry names it
  `close_visual_gap` per `backlog.json:210,258`) and nothing checks that they ever should.
  `grep` confirms `tools_for` is called nowhere in `src/app/` - the composition root never
  wires it to anything real. This is not "duplication that will drift," it already has: one
  side is disconnected from reality and only exercised by its own tests
  (`src/orchestration/phases_test.py:87-109`), which therefore prove nothing about what an
  agent actually sees. See Decisions.

## Stale documentation

- **`src/mcp_server/CLAUDE.md:86-100,142-145` and `src/mcp_server/README.md:107-130`**
  describe the `mcp`/`mcp_server` package-name collision as **live and blocking** -
  "needs a decision at a gate... before `serve_stdio`/`serve_http` can be exercised" - while
  `src/mcp_server/transports.py:54-59`'s own docstring says the rename "fixed it at the
  composition root; verified against a real install," matching `backlog.json`'s B-00A and
  B-00E (both `"fixed"`). Same file, same module, three documents in outright
  contradiction. Both files also assert the SDK "is not installed in this environment,"
  which is false (confirmed importable directly). Cost: small, ~30 minutes - rewrite both
  sections to describe the fix, not the problem it replaced.
- **`src/viewer/CLAUDE.md:57-58`** - "`websockets`/`starlette`... are **not installed in
  this environment**." Both are installed (confirmed directly); QA's own doctor output says
  "websockets [...] present." The instruction to keep the import lazy is still correct
  practice, but the stated reason is now wrong. Cost: trivial, one sentence.
- **`docs/ARCHITECTURE.md:34,43`** - lists `subprocess fallback` as a real, working part of
  `engine/`'s surface and calls `uv/` its "Primary user," but `docs/PIPELINE-LOG.md:236-239`
  records that this was a corrected research assumption: in-process `bpy` has window access
  in this build, so unwrap/bake/glTF export run in-process and the fallback is unused
  (confirmed: `src/uv/README.md`/`CLAUDE.md` make no mention of subprocess at all - only the
  top-level architecture doc still does). Cost: trivial, two lines.
- **`src/orchestration/README.md:117-119`** ("Contract gaps" item 1) - "`src/scene` is
  listed `"planned"` in `.pipeline/modules.json`." It is `"green"` (confirmed directly), has
  been since Phase 4. The underlying crash this flagged (`ScenePort.document` method vs.
  property) was fixed per B-00C, but the doc still frames `scene` as unbuilt.
  `contract-requests.json:13-16`'s matching entry (`status: "open"`) is the same staleness
  one level up - the acute bug is fixed, the "reconcile `ScenePort` into `src/contracts/`"
  request itself is still genuinely unresolved (`ScenePort` still lives only in
  `src/orchestration/scene_port.py`), so this one is partially stale, not fully.
- **`contract-requests.json:33-36`** (engine, "open-blocker-for-detail-integration",
  `edge_indices` tuple-vs-int disagreement) - resolved per B-00G;
  `src/engine/modifiers.py:40` `_resolve_edges` now accepts both forms with the contract
  (`Sequence[int]`) as primary. Request should read `resolved`, not `open`.
  `contract-requests.json:22-25` (orchestration, `tools_for` registry injection,
  `"open-blocks-mcp"`) is also stale in a different way: `mcp` shipped and is green without
  ever using this injection point, so "blocks-mcp" is now false - see the dead-registry
  finding above instead.

## Leftovers

- **30 of 61 backlog items carry no `status` field.** 24 of those (B-001 through B-021,
  B-023-B-025, B-027) are actually built and green per `.pipeline/modules.json` - the field
  was simply never set to `"done"`. Three more (B-029-B-031) are genuinely not built. A
  reader of `backlog.json` alone, without cross-referencing `modules.json`, would believe
  roughly half the product does not exist. Cost: trivial - a script pass setting `"done"` on
  the 24 confirmed-green items.
- No TODO/FIXME/XXX/HACK markers anywhere in `src/` or `frontend/` (checked). No
  commented-out code blocks (checked via a heuristic AST/regex scan, hand-verified the five
  hits it produced - all were ordinary prose comments, not code). No debug `print`/
  `console.log` outside `src/forge3d_cli.py`'s intentional CLI output. No `.bak`/`.orig`/
  scratch files anywhere in the tree. This module set is unusually clean on this axis.
- **`Orchestrator.tools_for()`'s fictional tool table** (`src/orchestration/
  _tool_registry.py`) is itself a leftover in the "known-broken, never connected" sense -
  see Duplication and Decisions.

## Decisions for the user

1. **The engine's subprocess fallback (`prefer_subprocess=True`) is an honest stub that
   raises.** Given Phase 4 found in-process `bpy` already has window access, is there a
   real capability left that needs it (headless server deployment without a display?), or
   should the flag be deleted along with `docs/ARCHITECTURE.md`'s stale reference to it?
   Finish it, ship the raise as a documented known-gap, or cut the flag entirely.

2. **`Orchestrator.tools_for()` returns a fictional tool table nothing in the product
   calls.** Either wire it to the real `mcp_server.registry.build_registry()` output (so it
   stops being a second source of truth that can't agree with the first), or delete it and
   its tests as dead code left over from before `mcp_server` shipped its own registry. Right
   now it is neither finished nor removed, and it looks load-bearing from the outside.

3. **A-008 (Roblox stud = 0.28 m) is still an unverified guess sitting in the primary,
   user-named export profile.** This is a one-search, one-constant fix. Given it is the
   profile the user said they would actually use, this is the cheapest, highest-consequence
   item on this whole list to close before shipping - recommend doing it now rather than
   carrying it to Gate B.

4. **Nothing has ever driven the MCP server, the viewer socket, or a real browser
   end-to-end**, and the multi-agent write lock has only ever been exercised by sequential
   calls in one process, never real concurrency. These are the four capabilities the
   product is actually *for* (a connected agent, a watching operator, real simultaneous
   sub-agents) and none has a single real run behind it. Ship as a known-untested risk with
   this stated explicitly in `HANDOVER.md`, or spend the next pass on exactly these four
   before anything else - they are more valuable to prove than any new feature.

5. **Q-017 (tests-first git evidence) is a process-integrity finding, not a code defect.**
   Teach the gate to parse combined-scope commits (mechanical, small) or accept and document
   that six modules' RED-phase discipline is unverifiable after the fact. Either is fine;
   silently dropping it is not - it is evidence about how much to trust the *next* pass's
   own gate.
