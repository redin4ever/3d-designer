# Rule 1 — Questions carry user-experience choices

The user is reachable only at a gate. A gate is expensive and rare, so it must extract
everything that would otherwise be guessed. Under-asking is the failure mode, not over-asking.

## What a good question is

Ask about **what the user of the product will experience**, not about what you will type.

| Ask this | Not this |
|---|---|
| "When someone submits the form and it fails, what should they see?" | "Should errors be typed or untyped?" |
| "Should a first-time visitor land on a demo, or on a sign-up wall?" | "Do we need auth middleware?" |
| "How much should the page move — still, subtle, or expressive?" | "Should we install Framer Motion?" |

Every wave must contain **at least one** question of the left-hand kind. A wave made
entirely of stack and library questions is a failed wave — rewrite it before sending.

Technical questions are allowed, but only when the answer changes something the user can
perceive (speed, offline behaviour, cost, privacy, where their data lives). Phrase them
by that consequence, not by the technology.

## The wave protocol

`AskUserQuestion` accepts **1–4 questions per call, 2–4 options each**. So a gate is not
one call — it is a sequence of waves. Run them back to back with no work in between.

- Target **6–10 waves** at Gate A — it carries **every** pre-build question, so 25–40
  decisions there. Gate B runs 4–6 waves, drawn only from the Phase 6 review research.
- Each wave is thematically coherent. Do not mix "who is this for" with "which database".
- Later waves may depend on earlier answers — that is the point of sequencing them.
- Stop a gate only when no remaining unknown would change more than one module's public
  interface. Everything smaller is an assumption you are allowed to make.

Wave ordering that works (Gate A):

1. Product and audience — who, what job, what "good" looks like
2. Scope — what is in the first version, what is explicitly out
3. Core user journeys — the two or three flows that must feel excellent
4. Interaction and feedback — empty, loading, error, success, undo
5. Visual direction — the DESIGN.md shortlist, density, motion, dark mode
6. Content and data — what objects exist, what the user can see and edit
7. Accounts and access — sign-in, roles, sharing, what a stranger can see
8. Quality bar — devices, browsers, accessibility target, speed budget
9. Stack and hosting — framed as cost, control, and deploy friction
10. Ways of working — repo layout, review flow, how many agents build in parallel

Gate B ordering is in [phase-7-gate-b.md](../references/phase-7-gate-b.md).
There are exactly two gates. Gate A must say so, and Gate B must say it is the last one —
a user who does not know the budget cannot spend it.

## Writing the options

- **2–4 options.** If you have five, two of them are the same answer.
- Options are **mutually exclusive** unless `multiSelect: true`. Use multiSelect for
  "which of these do you want" backlog picking; never for either/or design decisions.
- The **first option is your recommendation**, labelled `(Recommended)`, and it must be
  the option you would have silently chosen under Rule 3. This is what makes the gate
  safe: a user who answers nothing but the first option still gets a coherent product.
- `description` states the consequence, not the mechanism. "Visitors can try it before
  giving an email — more people reach the product, fewer of them are qualified leads."
- Never offer an "Other" option; the harness adds one.

## Use previews for anything visual or structural

Single-select questions support a `preview` field rendered as a monospace block. Use it
whenever the choice is something the user should *see* rather than read:

- Layout and navigation shape — ASCII wireframes of each option
- The DESIGN.md shortlist — palette swatch hexes, type scale, radius, a sample button
- Flow variants — step-by-step of each path
- Data shape — a sample record

Two options that read identically in prose usually differ obviously as previews. If you
cannot draw the difference, the question is probably not worth asking.

## Recording answers

Every gate produces, before the next phase starts:

- `docs/decisions/gate-<A|B-n>.md` — question, chosen option, verbatim user notes, date.
- One ADR in `docs/adr/` per decision that constrains architecture. Later phases must
  not re-litigate an ADR; they may only supersede it with a new one.
- `docs/ASSUMPTIONS.md` — every decision you took *without* asking, with its blast radius
  and how to reverse it. This file is read aloud at the top of the next gate.

If a later agent finds itself wanting to ask something, it does not ask. It appends the
question to `.pipeline/question-backlog.json` and that becomes wave material for the next
gate. See [Rule 3](autonomy.md).
