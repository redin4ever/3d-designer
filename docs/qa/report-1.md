# QA report — pass 1

Ten finders across two suites, plus an 80-agent module review with adversarial verification
of every severe finding. This is what they found and what was done about it.

## The headline

**Five independent finders reported the same P0**: `Orchestrator.perform()` never forwarded
the caller's write lease to `Scene.apply()`, so every mutating call through the real agent
path raised `LockContention` against the lease it had *just verified*. The entire
agent-facing pipeline — every construction, repair, alignment, detail and export operation —
failed 100% of the time through `dispatch`.

It survived every module suite because both `FakeScene` doubles implemented
`apply(self, op)` with no lock check at all, matching an incomplete `ScenePort` rather than
the real `Scene`. **A test double that agrees with the wrong side of a contract is the most
expensive artefact in this codebase**, and this is the third time it has produced a P0 here.

## Fixed this pass

| # | What was wrong | Why nothing caught it |
|---|---|---|
| P0 | `perform()` never forwarded the lease — every mutating call failed | both `FakeScene` doubles implemented no locking |
| P0 | `perform()` emitted hardcoded `0.0` measurements; B-000 was marked closed but the wiring was never done | the test asserted only `measurements != ()` |
| P0 | `promote()` logged a `phase_promotion` operation no handler could execute — the phase machine could not advance | the doubles accepted any operation kind |
| P0 | export scaled each mesh in place but left its position in metres — two-object scenes landed 3.57× wrong for Roblox, 100× for Unreal; `mirror_x` flipped meshes without moving them | every export test used one object |
| P0 | `MESH_UPSERT` carries a transform the browser never applied — every object rendered at the world origin, and a positioned object snapped back there on its next topology change | `FULL_SCENE` did it correctly two lines above; nothing compared them |
| P1 | `uv.seams`, `align.position` and `constraints.anchors` each carried a `1e-12` degenerate guard where `normalized()` raises below `EPSILON` (1e-4) — a sliver between the two passes the guard and trips the call it guards | `detail/edges.py` hit exactly this and was fixed; the three duplicated copies never received it |
| P1 | `npm run test:backend` ran `python -m pytest`; `python` on PATH is the Windows Store stub, so the documented command never worked and the gate read the suite as not green | nobody ran the npm script |

Each fix carries a regression test named after the failure. The four end-to-end ones in
`src/app/app_test.py` drive the **real** `Orchestrator` against the **real** `Scene` — the
only arrangement that could have caught the lock bug.

## Confirmed and not yet fixed

These survived adversarial verification. They are real; they are queued rather than done.

**`find_clipping` reports the wrong magnitude** (`src/measure/intersections.py:80`). It uses
the minimum per-axis AABB overlap, which is a minimum-translation distance, not socket
depth. For anything thinner than it is deep — every post, dowel, tenon and peg — the number
collapses to the object's cross-section. A post driven 500 mm through a deck reports
`0.1m`. An agent told to fix it moves 0.1 m and is still 0.4 m buried. Worse, a
`JoineryIntent` declaring a 150 mm socket silences it entirely, because 0.1 ≤ 0.15.

The verifier confirmed it and corrected the severity: the wrong-number half is live and
unconditional, but the silent-pass half needs a caller to author a `JoineryIntent`, and
nothing in the wired product produces one yet.

**`distance` and `gap_width` are AABB-only** (`src/measure/metrics.py:64`). Two 4 m beams
yawed 45° and 1.4 m apart report `distance=0.0` and `gap_width=0.0`, while `find_clipping`
simultaneously reports a 0.1 m interpenetration between parts that never touch. Every test
uses an unrotated cube. ADR-005 gives measurement authority over the agent, so the agent
will move correct geometry to fix a defect that does not exist.

**Partial application leaves orphan geometry.** A handler that creates objects and then
raises leaves them live in the engine with no log entry. `add_railing` failing on its third
`create_mesh` left 29 orphaned parts and an empty log. They then appear in the live view as
geometry with no history, and vanish on the next save/load.

**A dead writer wedges the lock permanently.** Lease expiry is measured against
`document.head`, but `head` only advances through `apply`, which only the dead lease's
holder can call. Five acquire attempts from another agent failed forever.

**Raw execution cannot create the snapshot barrier `SECURITY.md` promises.** Nothing in the
production wiring computes a `snapshot_path`, so an opaque operation either raises or
records a barrier that cannot be restored from. Undo across it re-executes the arbitrary
script instead of restoring — a non-deterministic script produced provably different
geometry after undo+redo while reporting `FULL_RESYNC` as though it were a clean restore.

**`snapshot()` drops loose vertices on real Blender** — it walks `mesh.polygons`, so a
vertex referenced by no face is invisible. `measure.find_loose_or_duplicate`'s loose-vertex
detection is dead code against real geometry while working correctly against the fake.

**Object creation is not O(1)** — 3.16 ms/op at ~100 objects rising to 54.52 ms/op at ~900,
a 17× degradation from a `view_layer.update()` per object. At the stated thousands-of-objects
target this is the binding constraint.

**Primary-button hover fails WCAG AA** at 2.87:1 (`#ffffff` on `#828fff`).
**`DESIGN.md`'s typography scale never reached `tokens.css`**, so `app.css` hardcodes
off-scale px sizes. There is no `<main>` landmark and no `<h1>`.

## What I could not make pass, and will not fake

**The gate's tests-first check fails for all 17 modules.** The honest picture is in three
parts:

- Ten modules (`engine`, `spatial`, `measure`, `raw`, `constraints`, `detail`, `ops`,
  `scene`, `export`, `orchestration`) **do** have RED commits — `b63166d`, `5f205eb`,
  `4f780e6` — but with combined scopes like `test(engine,spatial,measure,raw):`, which the
  gate's per-module matcher cannot read. The evidence exists; the gate cannot see it.
- Six modules (`gaps`, `align`, `uv`, `mcp`, `viewer`, `frontend`) genuinely have **no**
  RED commit. They were built RED-then-GREEN inside a single agent pass, which the agents
  reported verifying, but there is no git-level proof the tests ever failed first.
- `app`'s tests were committed **after** its implementation.

I am not creating retroactive commits to turn this green. Fabricating a sequence that did
not happen is precisely the failure this check exists to catch, and a green gate bought that
way is worth less than a red one that tells the truth.

## What was not tested

- **The MCP SDK's server code path.** `serve_stdio`/`serve_http` are reviewed but never
  driven — that needs a real client on the other end.
- **The viewer's live socket loop.** Same reason.
- **A real browser.** Puppeteer is not installed; the frontend is exercised as ES modules,
  so nothing verifies rendering, layout, or actual keyboard behaviour in a browser.
- **Anything above ~1000 objects.** The 17× creation slowdown was measured to ~900; the
  stated target is thousands and the curve was not followed further.

## Suites

```
backend   609 tests + 54 conformance checks run twice (fake and real Blender)   exit 0
frontend  29 tests                                                             exit 0
doctor    Blender 5.2.0 LTS, MCP SDK, websockets all present                    exit 0
gate      17/17 modules green; tests-first check failing, see above
```

---

# Fix round 2 — everything above that could be fixed, was

Fifteen of the seventeen findings are closed, each with a regression test named after the
failure it prevents. The three that remain are P2 design questions, not defects I chose to
leave.

## Closed since the first pass

**`find_clipping` reported the wrong number.** It conflated two quantities: the minimum
translation that separates a pair (*how far to move*) and the depth along the axis a part is
inserted (*what a socket declares*). Neither `min` nor `max` answers it — two flush cubes
offset 30 mm insert along their *smallest* overlap, a driven post along its *largest*.
`_geom.insertion_depth` picks the shallowest axis that is a genuine partial penetration,
which is right for both, and `JoineryIntent` can now name the axis outright. The defect line
carries all three overlaps and a suggestion that tells the agent exactly what to declare.

**`distance` and `gap_width` measured bounding boxes.** Now measured against real triangles
(vertex-to-face and edge-to-edge, AABB-pruned), with an honest flag when a pair is too large
to sweep exactly. Two 45°-yawed beams 1.4 m apart no longer report as touching.

**A dead writer wedged the lock forever.** Expiry was measured against `document.head`,
which only advances when an operation is applied — which only the current holder can do. The
clock now advances on acquire attempts, so a waiting agent advances it by waiting.

**A failed operation left orphan geometry.** `scene.apply`'s own docstring promised the
engine would be exactly as observable after a failure as before it, and did not deliver.
The exception still propagates unchanged; what the failed attempt created is now removed
first.

**Raw execution recorded a barrier pointing at nothing.** `perform` now captures the scene
before an opaque operation runs — the only moment the pre-execution state still exists.
`SECURITY.md`'s claim is now true.

**Loose vertices were invisible on real Blender.** `snapshot` walked only `mesh.polygons`,
so `find_loose_or_duplicate`'s loose-vertex detection was dead code against Blender while
working against the fake.

**Object creation was O(n²).** A `view_layer.update()` per object re-evaluated the whole
dependency graph. Composing `matrix_world` directly: **0.78 ms/op at 900 objects, down from
54.52** — 70× faster, and near-flat instead of quadratic.

**Accessibility.** Primary-button hover raised from 2.87:1 to 6.40:1 against a 4.5:1 floor;
added a `<main>` landmark and an `<h1>`; the action log appends instead of rebuilding every
row inside an `aria-live` region.

**Ten module docs announced "RED by design"** for modules that are fully green.

## Still open, and why

**Q-017 — tests-first git evidence.** Ten modules have RED commits under combined scopes the
gate's matcher cannot read; six have none; `app` committed tests after implementation. I am
not fabricating retroactive commits. A green gate bought that way is worth less than a red
one that tells the truth, and this check exists precisely to catch it.

**B-00K — a railing declares no joinery for the parts it deliberately embeds.** A
stair-plus-railing reports 94 clipping warnings, most of them balusters correctly socketing
into treads. The measurement is right; the question is whether an operation should
auto-declare its own joints, or whether that is the agent's call. That is a design decision,
not a bug, and it belongs at a gate. The defect suggestion now names the exact
`JoineryIntent` to declare, which makes it actionable in the meantime.

**B-00L — real bevels produce poor topology.** Mean triangle aspect ratio ~116 and edge-length
CoV ~1.6 on a simple tread. The tool measures and reports this correctly; the bevel
parameters or a cleanup pass need work.

## Suites after round 2

```
backend   620 tests + 57 conformance checks run twice (fake and real Blender)   exit 0
frontend  31 tests                                                             exit 0
doctor    Blender 5.2.0 LTS, MCP SDK, websockets                                exit 0
gate      17/17 modules green; tests-first still failing, see Q-017
```
