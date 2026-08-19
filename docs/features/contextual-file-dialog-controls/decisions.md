# Contextual File Dialog Controls — decisions

The user explicitly requested that export-only options disappear while importing and delegated identification of those options. The traced dialog supports five actions through one runtime switch, so the complete mode matrix is fixed here to avoid stale controls after switching actions.

| Decision | Chosen behavior | Basis |
|---|---|---|
| Q-01 | Import shows **Local file** and **Import settings** only. It hides **Download name**, **Target profile**, **Export scope**, and **Format**. | User request; exact export-only set identified from the current dialog. |
| Q-02–Q-03 | Keep source selection and import transformations; hide the output filename. | Assumed, reversible visibility policy. |
| Q-04–Q-06 | Export shows filename/profile/scope/format; Open Project shows only Local file; Save/Save As show only Download name. | Assumed complete mode matrix. |
| Q-07–Q-10 | Reapply the matrix on every open, hide labels with inputs, preserve values, and keep the immediate native picker. | Assumed to prevent stale UI without changing workflow. |
| Q-11–Q-13 | Status, progress, and unsaved confirmation remain universal; visibility changes immediately without animation. | Assumed to preserve existing job feedback. |
| Q-14–Q-16 | Hidden controls leave the accessibility tree; title, focus, and Escape behavior remain native and unchanged. | Assumed accessible default. |
| Q-17–Q-20 | Browser-test import/export; keep payloads and responsive behavior unchanged; unknown actions expose no action-specific controls. | Assumed narrow regression boundary. |

Detailed reversible assumptions are in [assumptions.md](assumptions.md). The user's wording was: “some options shouldnt show when importing ( ones used for exporting ) which do fix that”.

Decision coverage: Q-01, Q-02, Q-03, Q-04, Q-05, Q-06, Q-07, Q-08, Q-09, Q-10, Q-11, Q-12, Q-13, Q-14, Q-15, Q-16, Q-17, Q-18, Q-19, Q-20.
