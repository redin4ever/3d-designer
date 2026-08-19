# Codex Connect and pointing-highlight decisions

The user accepted every recommended option on 2026-08-08.

Official OpenAI documentation establishes the integration baseline: Codex stores MCP
configuration in `~/.codex/config.toml` by default, supports project-scoped
`.codex/config.toml`, and shares the host configuration across Codex CLI, the IDE
extension, and ChatGPT desktop:
<https://developers.openai.com/codex/mcp/>.

## Q-01 — Codex scope

Options: global `~/.codex/config.toml` (recommended), or project-only
`.codex/config.toml`.

Chosen: global `~/.codex/config.toml`. One Connect action makes forge3d available to
Codex across projects and across the local Codex clients that share this configuration.

## Q-02 — Codex setup

Options: safely merge the forge3d tables into TOML (recommended), or invoke
`codex mcp add`.

Chosen: safe TOML merge. Connect remains independent of the CLI executable being on
`PATH`, preserves unrelated settings, and refuses malformed TOML instead of replacing it.

## Q-03 — Connect picker

Options: one `Codex` entry (recommended), or separate CLI, IDE-extension, and desktop
entries.

Chosen: one `Codex` entry. Its note explains that the resulting configuration is shared.

## Q-04 — Point feedback

Options: highlight on hover and persist after click/lasso (recommended), hover only, or
selection only.

Chosen: hover immediately in point mode; clicked and lassoed parts remain highlighted
until the selection is cleared or point mode is left.

## Q-05 — Point appearance

Options: brighter accent fill that restores the prior state afterward (recommended), an
outline, or the same colour as an agent change.

Chosen: the existing brighter accent-hover colour. Point feedback is separate state and
temporarily takes priority over marks and change highlights; clearing it reveals the
previous state unchanged.

## Q-06 — CLI parity

Options: support both the button and `forge3d connect codex` (recommended), or the button
only.

Chosen: both surfaces. They describe and write the same server command.
