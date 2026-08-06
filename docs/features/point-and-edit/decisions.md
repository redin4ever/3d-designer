# point-and-edit — gate decisions

**2026-08-06.** One gate, 8 waves, 25 decisions. Every question below was made askable by the
Phase 1 trace: each one is anchored to a line of code that already exists, and the three
findings that shaped the whole gate were —

- **`SELECT` is already in the frozen wire protocol** (`src/contracts/wire.py:83`) and
  `buildSelectMessage` already exists in the browser (`frontend/src/controls.js:33`), but
  `src/viewer/client.py:160` throws it away as *"presentation state with nothing for the
  server to enforce or record"*. The pointing path was built to the edge of the UI and stopped.
- **Nothing in this product can move an object.** All 33 replayable operation kinds are
  construction or repair — no move, rotate, scale, delete or duplicate exists to call.
- **Nothing in the backend renders pixels.** `downscale_image` is exported and called by
  nothing; `grep ImageContent src/` is empty. The only image that can exist today is a crop
  of the browser's own software rasterizer.

Three answers went against the recommendation — **Q-07**, **Q-17** and **Q-23** — and each is
called out below, because those are the ones a later reader would otherwise assume were
defaults.

---

## Wave 1 — What pointing is for

| | Question | Options | Chosen |
|---|---|---|---|
| **Q-01** | You point at a part while the agent is mid-build. What should happen? | Queue it as context · Pause and wait · Mark it silently | **Queue it as context** |
| **Q-02** | How much should the model be told about a part you pointed at? | Everything already measured · Name and size · Just the name | **Everything already measured** |
| **Q-03** | Should the model also get a picture, or only numbers? | Both · Numbers only · Picture only | **Both — numbers plus a crop** |

Q-02 means a point carries the full `describe_object` payload — dimensions, bounds, triangle
and vertex counts, UVs, material slots, transform, and every defect `measure.inspect` finds.
The model can act without spending a call asking what it is looking at.

## Wave 2 — How you point

| | Question | Options | Chosen |
|---|---|---|---|
| **Q-04** | How do you pick a part? | Click + drag to circle · Click only · Circle only | **Click, and drag to circle** |
| **Q-05** | Drag already orbits the camera. How do the two share it? | A Point mode · Part vs empty space · Modifier key | **A Point mode you switch into** |
| **Q-06** | When parts overlap on screen, what do you get? | The nearest · Nearest + cycle · A list | **The nearest one** |

Q-05 is the conservative answer and deliberately so: nothing an operator already does changes
behaviour, and it is impossible to lose your camera angle by trying to circle something.

Q-06 plus Q-25 together decide *how* picking is implemented: an id channel written in
`raster.js`'s existing per-pixel inner loop, beside the depth value it already writes. The
part you get is the part whose pixel is under the cursor — exact by construction, not a ray
that approximately agrees with what is drawn.

## Wave 3 — Guiding with words and images

| | Question | Options | Chosen |
|---|---|---|---|
| **Q-07** | Where do you type the instruction that goes with a part? | The conversation box, part attached *(recommended)* · **A small box beside the part** · Both | **A small box that opens beside the part** |
| **Q-08** | Where does the picture come from? | A crop of your live view · The whole view · A Blender render | **A crop of your live view** |
| **Q-09** | Can you attach your own reference image? | Drag or paste · Not this version · Paste only | **Yes — drag or paste one in** |

> **Q-07 went against the recommendation.** The user chose annotation *in place* — type where
> you are looking — over the existing conversation composer. The consequence is a floating
> composer anchored to the picked part's screen position, and it must be placed so it does not
> cover the geometry being discussed. The existing composer is left exactly as it is.

Q-08 was answered against the honest cost of the alternative: a Blender render would be
prettier, but nothing in this product renders pixels today, it would be new engine work, and
it would show the model a *different angle from the one you are looking at* — which defeats
the point of pointing.

## Wave 4 — Priority

| | Question | Options | Chosen |
|---|---|---|---|
| **Q-10** | What does "important" mean to the model? | A standing instruction · A hard rule · A one-off nudge | **A standing instruction it re-reads every turn** |
| **Q-11** | How long does a mark last? | Until you clear it · Until worked on · Until the phase ends | **Until you clear it** |
| **Q-12** | Levels of importance? | Simply marked · Two levels · A number per part | **Simply marked** |
| **Q-13** | How does a marked part look? | A persistent outline · Dim everything else · A list in the panel | **A persistent coloured outline** |

Q-10 is the decisive one, and it is the reason focus cannot simply reuse `add_operator_note`.
Operator notes are **drained and cleared on delivery** (`reporting.py:187-188`) — correct for a
one-off redirect, fatal for "focus on this", which would be forgotten by the third action.
Focus is standing state that is re-read every turn until cleared.

Q-13 has the matching constraint on the browser side: the marks cannot live in
`viewport.js`'s `state.highlighted`, because `applyHighlight` clears every previously
highlighted id on each `HIGHLIGHT` message — deliberately, so *what just changed* stays
meaningful. Reusing it would wipe the operator's marks every time the agent touched anything.

## Wave 5 — The editing tools

| | Question | Options | Chosen |
|---|---|---|---|
| **Q-14** | Which edits can you make yourself? *(multi-select)* | move/rotate/scale · delete/duplicate · hide/show · rename/material | **All four** |
| **Q-15** | How do you drive a move or rotate? | Handles + numbers · Numbers only · Handles only | **Drag handles in the view, with numbers beside them** |
| **Q-16** | Should dragging snap? | Grid, switchable · To nearby parts · No snapping | **Snap to a grid, and you can turn it off** |

Q-15 matches the product's own premise — it computes verified numbers rather than asking
whether something looked right — so the number is never hidden behind the handle.

## Wave 6 — You versus the agent

| | Question | Options | Chosen |
|---|---|---|---|
| **Q-17** | Who wins when you edit mid-action? | Your edit lands after its action *(recommended)* · Agent pauses for you · **You press Pause first** | **You have to press Pause first** |
| **Q-18** | Is the agent told when you move something? | Yes, always · A summary · No | **Yes, always** |
| **Q-19** | Do your edits and the agent's share an undo history? | One shared history · Separate Ctrl+Z · Both | **One shared history** |

> **Q-17 went against the recommendation**, and it is the single most simplifying answer in the
> gate. Manual editing is only reachable while the run is paused, so the manual path **never
> contends for the write lock at all** — the entire class of two-writer races stops existing
> rather than being handled. Q-20 is what keeps that from feeling like a mystery.

Q-19 is why manual edits must be real logged `Operation`s rather than direct engine writes:
replay, checkpoints and roll-back-N-steps come for free, and two timelines describing one
scene becomes impossible.

## Wave 7 — When things go wrong

| | Question | Options | Chosen |
|---|---|---|---|
| **Q-20** | You reach for a handle while the run is going. | Greyed out + a Pause button · Auto-pause · No handles | **Handles greyed out, with a Pause button right there** |
| **Q-21** | You drag a part into a broken placement. | Let it, then say what broke · Warn during drag · Refuse | **Lets you, then tells you what broke** |
| **Q-22** | The connection drops mid-move. | Revert and say so · Hold and re-send · Freeze | **The move reverts, and it says so** |

Q-21 routes a manual mistake through exactly the same measurement and reporting path as one
of the agent's — measured, named, with the number. Q-22 refuses the one failure this product
is most arranged against: a view showing a position that exists only in the browser.

## Wave 8 — Reach and limits

| | Question | Options | Chosen |
|---|---|---|---|
| **Q-23** | How big is the crop sent to the model? | ~512px *(recommended)* · **Up to 1024px** · Choose per send | **Full — up to 1024px** |
| **Q-24** | Can you point using only the keyboard? | Tab + space · Mouse only · Keyboard picking only | **Yes — tab through parts, space to pick** |
| **Q-25** | What should the effort go into? | Pointing feeling exact · The model visibly acting · A real editor feel | **Pointing feeling instant and exact** |

> **Q-23 went against the recommendation** — detail over per-point token cost. 1024 is also
> `downscale_image`'s own documented default `max_edge`, so the two now agree rather than one
> silently overriding the other.

Q-24 keeps the canvas consistent with itself: it is already keyboard-operable for orbit and
zoom, so pointing not being would have made this the one thing on the page needing a mouse.

Q-25 sets the build order. Pixel-exact picking is unit 1 and gets the most care, because
everything else in the feature is built on top of "the part you got is the part you meant".
