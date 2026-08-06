# forge3d — what this run built

Nine phases, two gates, two build passes, ending 2026-08-06. This is the honest account.

**forge3d is live 3D authoring for AI agents, built on Blender 5.2.** It computes the spatial
facts — clipping depth, gap width, manifoldness, angles, scale — and hands the model verified
numbers instead of asking it to eyeball a render. It takes declarative constraints rather than
raw coordinates, and it verifies by re-measuring rather than by asking whether it worked.

The premise, from the Phase 1 research: VLMs score 34–56% where humans score 79–99% on spatial
benchmarks, and models land within 2× of ground truth on visual distance estimation about 37%
of the time. Constraint-based placement measures 91–95% against 37% for raw coordinates. So the
*tool* holds the spatial reasoning, and the model holds the design judgement.

## What a person can do with it

Verified by running it against real Blender 5.2.0 LTS, not by reading the code.

- **Build** — 6 primitive types, walls, floors, boolean openings, staircases, railings on
  sloped multi-segment paths, arrays along paths, LOD chains, modular kits. Dimensionally
  exact to the millimetre. A railing on a 31.7° rake produces posts plumb to 1.000000, which
  is the case a naive generator gets wrong (0.84).
- **Fix** — 8 repair operations, each proven by re-running the detector that found the defect:
  1→0 boundary holes, 3→0 duplicate vertices, 1→0 flipped faces, a 0.05 m gap → 0.000000 m.
- **Align** — 7 constraint-solver operations. 31° → 0.000000°, 50° → 90.000000°, a leaning post
  → exactly plumb.
- **Detail** — bevel, panel lines, greebles, plus a topology cleanup pass. Mean triangle aspect
  ratio on a stair tread went from 109.31 to 64.20 in the final pass, mesh still manifold.
- **Measure** — 4 metrics and 10 defect classes, each verified against geometry built to have
  exactly that one defect. Two 4 m beams yawed 45° and 1.4 m apart measure 1.314 m; a post
  driven through a deck reports "inserted 0.5 m along z, 0.1 m to separate" — two different
  numbers, correctly separate.
- **Finish** — UV unwrap and PBR bake to real PNGs, headless. Export for Roblox, Unity, Godot
  and Unreal, producing valid `.glb` in under 0.06 s, with Unity negating X where Godot does
  not, and a banner that tells a person whether the asset is safe to import.
- **Coordinate** — a single write lease, four phases (blockout → refine → detail → polish),
  role-partitioned tools, checkpoints, undo, and a phase gate that will not let an agent
  advance until the phase's acceptance queries actually pass.

All of it reachable over MCP, on both transports, by a real client: the live-client suite
completes a handshake, lists the catalogue with roles, builds geometry that is really there
afterwards, is refused by the phase gate with a named rule, follows that refusal's own
suggestion to get through, and exports a file a person can open.

## The two gates

- **[Gate A](decisions/gate-A.md)** — 12 waves, 48 decisions, before a line of code existed.
- **[Gate B](decisions/gate-B.md)** — 6 waves, 24 decisions, every one carrying evidence from
  the Phase 6 review of what had actually been built.

16 ADRs, [001–016](adr/). The five from Gate B: promotion is a hard gate with no override
(012), role binds to the lease and is checked against phase (013), export runs outside the
operation log (014), scene document v2 keeps constraints (015), and the Canvas2D renderer that
replaced three.js is now written down (016).

## What the review found, and what it changed

Phase 6 put five read-only agents on the built product; two of them drove it rather than
reading it. The finding was **"almost everything works, and almost none of it is reachable"** —
36 of 48 gate decisions built as chosen, 11 drifted with no record anywhere.

The final pass answered that. The differences that matter:

| Before | After |
|---|---|
| `export_scene` raised a raw `KeyError` through the only path an agent has | runs via its tool handler, outside the log (ADR-014) |
| `measure` and `detail` published zero MCP tools; `INSPECT` had none | 6 + 4 tools; `INSPECT` has 9 |
| No way to ask what phase you are in, or to promote | `get_phase`, `list_objects`, `describe_object`, `promote_phase` |
| Promotion passed if *anything* had happened; `measure.evaluate` had zero call sites | real acceptance queries against live geometry, no override |
| Any agent could claim any role; POLISH tools ran during blockout | role comes from the lease, checked against the phase |
| Undo was session-fatal, and re-ran raw scripts instead of restoring | rejects foreign targets, survives what it cannot replay, restores from a geometry snapshot |
| A reload silently dropped every constraint | schema v2 keeps them; a v1 file warns and names what it lost |
| The automatic check never checked neighbours, while reporting that it did | pairwise clipping via the spatial index |
| 0.006 s to build a sphere, 6.5 s to check it | 0.021 s — **306× faster**, with the pruning ratio pinned by a test |
| 1 Roblox stud = 0.28 m, uncited | verified against Roblox's own units table, and corroborated exactly by its mass row (0.28³ × 1000 = 21.952 kg) |

**The single most important thing the final pass found**: the write lock — the safety property
the entire multi-agent design rests on — had never been tested against real OS concurrency, and
when it was, it was broken. Eight threads racing behind a barrier produced **three simultaneous
holders of the "only" write lock**, because `acquire` was an unsynchronised check-then-write.
A second race made `find_conflicts` raise a bare `KeyError` out of a read-only method, refusing
168 readers in one run. Both are fixed and pinned by tests that use real threads, never sleeps.
That is what Gate B 6.2 asked to be excellent, and it is why it was worth asking.

## Suites

```
backend   1036 tests, against both the in-memory engine and real Blender 5.2   exit 0
frontend    31 module tests                                                    exit 0
browser     10 tests in real Chromium                                          exit 0
doctor    Blender 5.2.0 LTS, MCP SDK 2.0, websockets — 43 tools, 9 roles       exit 0
```

## Known issues

Full detail, with repros, in **[HANDOVER.md](HANDOVER.md)**. **27 of the 28 scoped final-pass
items are done.** What is left:

1. **F-019 is partial.** `src/engine/scale_test.py` follows the object-creation curve past the
   ~900 objects either earlier pass had measured, against a stated target of thousands. The
   figures in it were not independently re-run at the close — treat the ceiling it asserts as a
   regression guard, not a published benchmark. Re-run it before quoting numbers.
2. **No operation declares joinery for the joints it creates** (B-00K). An agent *can* now
   declare one — `find_clipping` takes a `joinery` parameter — but a staircase plus railing
   still reports its deliberate sockets as defects unless the agent knows to say so.
3. **A render tool, collision meshes and texture atlasing** were chosen by the user at Gate B
   and then cut by the user for budget. They are wanted, not declined.
4. **Rigging and organic sculpting have zero code**, deliberately and for stated reasons.

The final pass ran in three rounds and survived two interruptions. Round 2 was stopped at the
user's request; `ops` and `frontend` had completed and were kept, `engine` was finished by
hand, and `viewer` was reverted rather than shipped with eleven failing tests. Round 3
recovered the units that never ran, and was itself interrupted by a machine restart that
killed one unit **between an atomic write and its rename** — the crashed temp file was
recovered and the unit finished by hand from the tests it had already written.

## Assumptions still open

Nine of ten resolved or confirmed at Gate B. One is not, and could not be:

**A-006 — which of the 12 constraint types agents actually reach for.** The vocabulary is built,
solved and correct. No agent has used any of it outside a test file, so there is no evidence,
and the pipeline had no way to generate any. It needs one real session with a real agent, which
is the first thing to do after this run.

## What the next person should do first

1. **Run one real session end to end** — a real agent, connected over MCP, building a small
   scene, promoting through all four phases, exporting for Roblox, with the browser open. Every
   piece of that now works and is tested; what has never happened is all of it at once, driven
   by a model rather than a test. It will settle A-006 and it will find more than any test
   written in advance — that has been true of every layer in this project that got its first
   real exercise.
2. **Then re-run `src/engine/scale_test.py` and read the curve**, before quoting any number
   about scale.
3. **Then decide about joinery** (B-00K): an agent can declare it now, but no operation
   declares its own. That is the last thing standing between a staircase-plus-railing and a
   clean defect report.

Everything else is in [HANDOVER.md](HANDOVER.md), priority-ordered.

## What I would not do

The gate's tests-first check is red and was not made green. Ten modules have RED commits under
combined scopes the matcher cannot parse, six have none at all, and `app`'s tests were committed
after its implementation. Teaching the matcher to read combined scopes was offered at Gate B and
not chosen. **No retroactive commits were fabricated.** Fabricating a sequence that did not happen
is precisely the failure this check exists to catch, and a green gate bought that way is worth
less than a red one that tells the truth — including as evidence about how much to trust the
next run's gate.
