# Codex Connect support and visible pointing highlight

The Connect button now configures Codex, and point mode visibly identifies the part under
the pointer and keeps click, lasso, and keyboard selections highlighted until cleared.

## How it is wired in

- Codex registry: `src/app/connect.py` — one `Codex` client backed by the global
  `~/.codex/config.toml` shared by local Codex surfaces (Q-01, Q-03).
- Codex writer: `src/app/codex_config.py` — validates the full TOML document, preserves
  unrelated text, and replaces only forge3d's MCP tables (Q-02).
- Connect picker: `frontend/tests-browser/connect.browser.mjs` — a real browser proves the
  detected Codex row is visible in the multi-client picker (Q-03).
- Point input: `frontend/src/point-ui.js` — hover reads the renderer's visible-id channel;
  click, lasso, and keyboard selection update persistent selection emphasis (Q-04).
- Point rendering: `frontend/src/scene-renderer.js` — hover and selection are state separate
  from persistent marks and agent change highlights, with temporary visual priority (Q-05).
- CLI and documentation: `src/app/connect.py`, `README.md`, and `frontend/README.md` —
  `forge3d connect codex` renders native TOML and Codex is named as a stdio client (Q-06).

## Decisions

See [decisions.md](decisions.md).

## Assumptions still standing

None.

## Noticed but not done

None outside the traced feature seams.

## Known gaps

None. The backend, frontend unit, and real-browser suites all pass.
