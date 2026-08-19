# point-and-edit

Point at a part in the live view so the model gets measured facts and a picture of it, mark
parts so it keeps paying attention to them, and change simple things yourself without a model
round trip.

25 decisions at one gate ([decisions.md](decisions.md)). 23 seams: **13 wired, 10 declined
with a reason**. 9 units, all green.

## What it does

| | |
|---|---|
| **Point** | Point mode, then click a part or drag a loop round several. Picking reads the id the rasterizer wrote under the same depth test as the colour, so what you get is what is under the cursor — not a ray's second opinion about it. |
| **Say** | A composer opens beside what you picked. It sends the parts, your words, and optionally a crop of exactly what you are looking at. Paste an image to say "more like this". |
| **Prioritise** | Mark parts as important. They stay marked until you clear them, and the agent is re-told about them on **every** report rather than once. |
| **Edit** | Move, rotate, scale, delete, duplicate, rename and set-material — as ordinary logged operations, so undo, replay, checkpoints and roll-back-N all reach them. |

## The three findings that shaped it

- **`SELECT` was already in the frozen wire protocol** and `buildSelectMessage` already
  existed in the browser, but `viewer/client.py` discarded it as *"presentation state with
  nothing for the server to enforce or record"*. The path had been built to the edge of the UI
  and stopped.
- **Nothing in this product could move an object.** All 33 replayable operation kinds were
  construction or repair.
- **Nothing in the backend renders pixels.** `downscale_image` was exported and called by
  nothing. The only image that can exist is a crop of the browser's own rasterizer, which is
  why Q-08's answer is also the only honest one.

## Two things the trace missed, found by the suite

- **`src/app/wire_contract_test.py`** asserts the Python and JavaScript message-type enums
  agree, and broke the moment `ANNOTATE`/`SET_FOCUS`/`FOCUS` were added. The test was right
  and `frontend/src/socket.js` was incomplete.
- **`perform()` refuses while paused**, and Q-17 made pausing the *precondition* for editing.
  Without `apply_operator_edit` the manual tools could never have worked at all: the thing you
  must do to use them was also the thing refusing them.

## Two real defects the tests caught

- **The two snaps disagreed, twice.** Python's `round` is banker's rounding, so `0.25` on a
  0.1 grid gave 0.3 in the browser and 0.2 on the backend. Fixing that exposed the mirror
  case: `Math.round(-2.5)` is -2, so `-0.25` then gave -0.2 and -0.3. Either way a part sits
  where you put it and jumps one grid step on commit, only on halves — the shape of a bug
  reported as "the snapping is broken sometimes" and never reproduced. Both now round away
  from zero and both suites pin the same table.
- **Three number inputs held the whole grid wider than a 360px viewport**, because a number
  input carries an intrinsic width that `flex: 1` does not override. Caught by the browser
  suite's no-horizontal-scroll test — exactly the blind spot that suite exists for, since the
  module tests are pure logic and could never have seen it.

## Known gap — reported, not hidden

**`integration` was not built test-first.** The DOM wiring landed and the browser tests
followed it. The gate says so and I have not worked around it. The decisions underneath were
all covered test-first — `picking`, `annotate`, `capture` and `edit-tools` are pure modules
with 63 tests between them, written red first — but the wiring itself is a Rule 4 violation.
`node .feature/check.mjs` exits non-zero on this one item and nothing else.

## Noticed but not done

- `src/contracts/operations.py` is 417 significant lines and `src/orchestration/reporting.py`
  is 307, both over the 300 soft cap. Both were already over before this feature and both are
  under the 1000 hard cap. Splitting `operations.py` would mean amending the package's
  documented acyclic import order — a wider change than this feature warrants.
- The draggable-arrow gap is closed by
  [Blender-style editor tools and move gizmo](../blender-tools-gizmo/FEATURE.md). Numeric entry
  remains available beside the on-canvas X/Y/Z arrows, with shared snapping and one committed
  move per drag.
- Rotate and scale have operations, tools and message builders but no control in the panel
  yet — only move, duplicate and delete are exposed.
- `_handle_select` is still a no-op. That is now a decision (see `seams.json`), not a gap.
