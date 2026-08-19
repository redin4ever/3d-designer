# Contextual File Dialog Controls

## Delivered

The shared File dialog now applies a complete field-visibility policy every time an action opens:

| Action | Visible action-specific controls |
|---|---|
| Open Project | Local file |
| Save Project / Save As | Download name |
| Import Model | Local file, Import settings |
| Export Model | Download name, Target profile, Export scope, Format |

Labels and controls hide together using native hidden semantics and `aria-hidden`. Hidden values are preserved, and picker behavior, status, progress, unsaved confirmation, operation payloads, focus, and Escape behavior are unchanged.

## Verification

- The new real-browser regression failed against the old always-visible dialog, then passed after implementation.
- 210 frontend unit tests passed.
- 35 real-Chrome tests passed, including Import-to-Export mode switching.
- `frontend/src/file-io.js` passed Node syntax checking.

## Noticed but not done

None. No backend, file-format, or visual-design changes were needed for this focused UI correction.
