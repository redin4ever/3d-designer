# Phase 2 — Design (unattended)

**The user picks the design system. You do not.**

Your job in this phase is to make their choice easy and informed — never to make it for
them. The visual system is the most visible, most personal decision in the product, and an
agent's taste is not a substitute for the user's. Phase 2 prepares; Gate A decides.

The catalogue and fetch URLs are in [design-md-catalog.md](design-md-catalog.md).

## First: has the user already supplied one?

Check, in this order, and **skip the rest of this phase** on the first hit:

1. A `DESIGN.md` already at the repo root → use it. Do not shortlist, do not second-guess
   it, do not offer alternatives at the gate.
2. A design given at invocation — `/build-product "<idea>" --design <slug|path|url>`:
   - a catalogue slug → fetch it
   - a local path → copy it to root `DESIGN.md`
   - a URL → fetch it; verify it parses as a DESIGN.md before accepting
3. A design named anywhere in the user's own words when they started the run ("make it
   look like Linear", "use our brand file at `brand/tokens.md`") → take it at face value.

Record the source in `.pipeline/state.json`:
`"design": { "slug": "linear.app", "source": "catalogue" | "user-provided" | "authored" }`.

Then validate it parses (frontmatter with `colors`, `typography`, `spacing`) and move on.
If a user-provided file is thin — say, colours but no type scale — do **not** replace it.
Use it, note the gaps in `docs/DESIGN-USAGE.md`, and ask about only the missing parts at
the gate.

## Otherwise: prepare the user's choice

Decide the product's **register** from `docs/research/SUMMARY.md` — dense professional
tool, consumer surface, marketplace, editorial, creative tool, something playful. Register
is what the product feels like to use; brand is incidental.

Then pull **3 candidates** from that register, deliberately spread apart:

- one **safe** fit — the obvious match for the category
- one **sharper** fit — more opinionated, more memorable, more risk
- one **contrast** — a different register that would reframe the product if chosen

Three, because a fourth splits the vote without adding information. Never three variations
of the same dark developer aesthetic — that is a shortlist with one real option in it.

These are **candidates, not a recommendation you are steering toward.** The gate question
must also let the user go outside them (see below), and if they do, that is a success of
the phase, not a failure.

Download all three raw to `.pipeline/design-candidates/<slug>.md` and verify each parsed.
A 404 or an HTML body means a wrong slug — check the catalogue rather than inventing one.

**Do not write root `DESIGN.md`.** It is written only after the user chooses at Gate A.
If all three fetches fail, record it in `ASSUMPTIONS.md`, bring the failure to the gate,
and let the user decide whether to name their own or have you author a minimal one.

## Build the previews

`AskUserQuestion` renders `preview` as monospace, and this is where it earns its keep — the
user should *see* the options, not read adjectives about them. One block per candidate,
same layout for all three so they compare at a glance:

```
LINEAR ─ near-black product surface

canvas   #010102   surface #0f1011   hairline #23252a
ink      #f7f8f8   muted   #8a8f98   accent   #5e6ad2

Display  56px / 600 / -1.8px tracking
Body     16px / 400 / 1.5

┌──────────────────────────────┐   radius 8px
│  Ship faster                 │   ┌────────────┐
│  Dense, technical, quiet.    │   │ Get started│  accent fill
└──────────────────────────────┘   └────────────┘

Feels like: engineering craft, low ceremony, dark by default
Costs you: hard to make warm or playful later
```

Always include the **"costs you"** line. A design option presented with no downside is a
recommendation wearing a question's clothes.

Also prepare, for the gate: the register's **full slug list** from the catalogue, so a user
who dislikes all three can name any of the 74 without you narrowing again.

## The gate question (assembled here, asked at Gate A wave 5)

The question must offer, at minimum:

1. Candidate A (safe) — with preview
2. Candidate B (sharper) — with preview
3. Candidate C (contrast) — with preview

and the message accompanying the wave must tell the user, in one line, that they can also
name any other system from the catalogue, point at a file or URL of their own, or ask for
one to be authored from a brand they describe. Their `Other` free-text answer is a valid
and expected outcome — handle it, do not re-ask.

Queue follow-up visual questions for the same wave: density, motion, dark mode, and how
much personality the copy should carry. Those are UX choices the DESIGN.md does not settle.

## After the user chooses (runs at the start of Phase 4)

1. Copy the chosen file to root `DESIGN.md` — the convention agents look for.
2. **Generate** the token file (`src/styles/tokens.css` or the stack's equivalent) from the
   frontmatter, headed `GENERATED FROM DESIGN.md — DO NOT EDIT`. Regeneration must be
   lossless, so no hand-tuning afterwards.
3. `docs/DESIGN-USAGE.md` — which token to reach for when, plus everything the DESIGN.md
   leaves open (focus rings, disabled states, table density, chart colours).
4. Add the lint rule that fails on a raw colour, font size, or off-scale spacing anywhere
   outside the token file. Without it, `DESIGN.md` is decoration within a week.

## Write

- `.pipeline/design-candidates/` — the fetched files plus `previews.md`
- `.pipeline/question-backlog.json` — the wave 5 questions
- `docs/PIPELINE-LOG.md`, `.pipeline/state.json` → `phase: 3`

**Do not stop here.** Write the state, then open [phase-3-gate-a.md](phase-3-gate-a.md) and begin it in this same turn. Gate A is where the turn legitimately ends, and not before.
