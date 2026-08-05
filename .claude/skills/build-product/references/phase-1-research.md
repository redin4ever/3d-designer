# Phase 1 — Research (unattended)

Two jobs, and the second matters more:

1. Learn enough about the product space to build competently.
2. **Produce the question list for Gate A.** Research that ends in facts has half-failed.
   Research that ends in "here are the 30 things only the user can decide" has succeeded.

Nobody is watching. [Rule 3](../rules/autonomy.md) applies throughout.

## Fan out

Spawn these concurrently in one message, every one **`run_in_background: false`**. Read-only
agents — none of them writes source. Use `subagent_type: Explore` for anything reading the
repo, `general-purpose` for anything using the web.

The flag is required, not implied: it defaults to **true**, and this phase's deliverable is
the synthesis of what these agents return. Background them and there is nothing left to do
but end the turn
([agent-briefs.md](agent-briefs.md#concurrency--parallel-and-background-are-not-the-same-thing)).

| Agent | Question it answers | Writes |
|---|---|---|
| `inventory` | What already exists here? Stack, conventions, dead ends, prior art in-repo. Skip on an empty directory. | `docs/research/inventory.md` |
| `landscape` | Who else builds this? For 5–8 comparable products: what they do, their core flow, their pricing shape, what users praise and complain about. | `docs/research/landscape.md` |
| `flows` | For this product category, what are the canonical user journeys, screen by screen? Where do comparable products lose people? | `docs/research/flows.md` |
| `domain` | What does this domain require that a generalist would miss? Rules, formats, jurisdictions, integrations, data the product must not get wrong. | `docs/research/domain.md` |
| `technical` | What are the real constraints? APIs and their limits, auth options, hosting shapes, anything with a cost or a rate limit. Prices and tiers, dated. | `docs/research/technical.md` |

Each agent's brief follows [agent-briefs.md](agent-briefs.md) and must end with a
**Decisions for the user** section — every point where it found two or more defensible
answers and picked none.

## Synthesise

The main agent — not a subagent — writes `docs/research/SUMMARY.md`:

- **The product in one paragraph**, in the user's words plus what research clarified
- **Comparable products table** — name, core flow, what to steal, what to avoid
- **The two or three journeys** that will make or break this product
- **Table stakes** — what every comparable product has; absence is a defect, not a choice
- **Differentiators available** — where this product could be different, each with a cost
- **Hard constraints** — things no gate answer can change
- **Open questions** — the union of every agent's "Decisions for the user", deduped,
  grouped into the Gate A wave themes, each with your recommended default

`SUMMARY.md` obeys the 250-line budget. It is the file every later phase reads; the raw
research files exist to be cited, not re-read.

## Feed the gate

Write every open question into `.pipeline/question-backlog.json` with its wave, your
recommended default, and its impact. Gate A is assembled from this file. If it holds
fewer than 25 entries, research was too shallow — go back and push on scope, journeys,
and quality bar, which are the areas that most often get assumed away.

```json
{
  "id": "Q-007",
  "wave": "journeys",
  "question": "When a proposal is viewed by a client, what should the sender find out?",
  "options": ["Opened + time spent (recommended)", "Opened only", "Nothing — no tracking"],
  "recommended": 0,
  "impact": "high",
  "source": "landscape.md — 4 of 6 competitors track; 2 market privacy as the feature"
}
```

## Also update

- `CLAUDE.md` — replace the `PIPELINE:PROJECT-SUMMARY` block with the one-paragraph
  description. Keep it to five lines.
- `docs/PIPELINE-LOG.md` — phase report.
- `.pipeline/state.json` — `phase: 2`.

## Guardrails

- Cite sources with URLs and the date fetched. An undated pricing claim is a future bug.
- Distinguish *observed* from *inferred*. "Linear uses a command palette" is observed;
  "users prefer command palettes" is inferred and must be labelled.
- Do not design the product here. Do not choose a stack here. Phase 1 gathers and asks;
  Gate A and Phase 4 decide.
- Do not write any code, config, or `package.json` in this phase.

**Do not stop here.** Write the state, then open [phase-2-design.md](phase-2-design.md) and begin it in this same turn. Phase 2 is unattended too — there is nobody to show the research to.
