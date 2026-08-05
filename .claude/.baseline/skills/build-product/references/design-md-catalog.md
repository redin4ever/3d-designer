# DESIGN.md catalogue

`DESIGN.md` is a design-system file agents read before generating UI: YAML frontmatter of
tokens (colours, typography, spacing, radius) plus prose on philosophy, components,
do's and don'ts. It lives at the repo root under that exact name.

## Fetch

```
https://raw.githubusercontent.com/VoltAgent/awesome-design-md/main/design-md/<slug>/DESIGN.md
```

Slugs are exact, including dots — `linear.app`, not `linear`. Verified working; a 404
means a wrong slug, not a missing file. To re-list slugs if this file goes stale:

```bash
curl -s https://api.github.com/repos/voltagent/awesome-design-md/contents/design-md \
  | grep '"name"' | sed 's/.*: "//; s/",//'
```

Each folder also holds `preview.html` and `preview-dark.html` (same URL pattern) — useful
if you want to render a candidate rather than describe it.

## Slugs by register

Pick by **register**, not by brand affection. The register is what the product feels like
to use; the brand is incidental.

| Register | Use when the product is | Slugs |
|---|---|---|
| Dense professional tool | A workspace people live in daily | `linear.app` `notion` `raycast` `warp` `cursor` `superhuman` |
| Developer platform | Docs, dashboards, APIs, consoles | `vercel` `supabase` `clickhouse` `sentry` `resend` `mintlify` `posthog` `hashicorp` `opencode.ai` |
| Trust and money | Payments, banking, anything with a balance | `stripe` `wise` `revolut` `coinbase` `mastercard` `kraken` `binance` |
| Warm consumer | Booking, marketplace, lifestyle, community | `airbnb` `pinterest` `spotify` `starbucks` `uber` `cal` |
| Commerce | Storefronts, catalogues, checkout | `shopify` `nike` `airtable` |
| Editorial | Content-led, reading-first, marketing | `theverge` `wired` `meta` `apple` |
| Creative tool | Canvas, editor, anything visual | `figma` `framer` `webflow` `miro` `lovable` `clay` |
| AI product | Chat, agents, model surfaces | `claude` `cohere` `mistral.ai` `elevenlabs` `runwayml` `replicate` `ollama` `x.ai` `minimax` `together.ai` |
| Enterprise | Big-org software, procurement, IT | `ibm` `slack` `intercom` `mongodb` `nvidia` `hp` `vodafone` |
| High-drama | Launch pages, hardware, anything cinematic | `tesla` `spacex` `ferrari` `lamborghini` `bugatti` `bmw` `bmw-m` `playstation` `renault` |
| Deliberately retro | A period look, on purpose only | `dell-1996` `nintendo-2001` |

Not placed above but available: `composio` `expo` `sanity` `voltagent` `zapier`.
Verified full list (74): airbnb, airtable, apple, binance, bmw, bmw-m, bugatti, cal,
claude, clay, clickhouse, cohere, coinbase, composio, cursor, dell-1996, elevenlabs, expo,
ferrari, figma, framer, hashicorp, hp, ibm, intercom, kraken, lamborghini, linear.app,
lovable, mastercard, meta, minimax, mintlify, miro, mistral.ai, mongodb, nike,
nintendo-2001, notion, nvidia, ollama, opencode.ai, pinterest, playstation, posthog,
raycast, renault, replicate, resend, revolut, runwayml, sanity, sentry, shopify, slack,
spacex, spotify, starbucks, stripe, supabase, superhuman, tesla, theverge, together.ai,
uber, vercel, vodafone, voltagent, warp, webflow, wired, wise, x.ai, zapier.
Re-check with the curl above before trusting this list.

## Frontmatter shape

```yaml
---
name: Linear-design-analysis
description: "…the intent of the system, in prose…"
colors:
  primary: "#5e6ad2"      # plus on-primary, hover, focus
  ink: "#f7f8f8"          # plus muted, subtle, tertiary
  canvas: "#010102"       # plus surface-1..4
  hairline: "#23252a"
  semantic-success: "#27a644"
typography:
  display-xl: { fontFamily, fontSize, fontWeight, lineHeight, letterSpacing }
  headline: …
  body: …
spacing: …
radius: …
---
```

Prose sections: visual theme, colour roles, typography rules, component styling, layout
principles, depth and elevation, do's and don'ts, responsive behaviour, agent prompt guide.

## Turning it into enforced tokens

A `DESIGN.md` that is only read is decoration. In Phase 4:

1. **Generate** the token file from the frontmatter — `src/styles/tokens.css` or the
   stack's equivalent. Header comment: `GENERATED FROM DESIGN.md — DO NOT EDIT`.
   Regeneration must be lossless, so no hand-tuning it afterwards.
2. Semantic names only in components — `var(--surface-1)`, never `#0f1011`, never
   `var(--linear-charcoal)`. Components must not know the brand.
3. **Lint** raw hex, raw px font sizes, and off-scale spacing outside the token file into
   an error. This is the rule that keeps the system alive.
4. `docs/DESIGN-USAGE.md` records what the DESIGN.md does not: focus rings, disabled
   states, dense-table density, chart colours, and any deviation with its reason.

## Other sources

- `https://getdesign.md/<slug>/design-md` — browsable catalogue, same corpus
- `https://designmd.app/library` — 461 systems including style-based (Swiss, brutalist,
  art nouveau) rather than brand-based; use when the product wants a *style*, not a peer
- Hand-authored is legitimate for a strong existing brand — same section structure, and
  say so at the gate rather than pretending a catalogue entry fits.
