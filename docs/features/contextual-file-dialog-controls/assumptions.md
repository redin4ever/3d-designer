# Contextual File Dialog Controls — assumptions

These choices are limited to the shared File dialog's presentation. Each is inexpensive to reverse by changing the action-to-field visibility map.

- **A-086:** Import keeps Local file and Import settings because both alter the import operation.
- **A-087:** Download name is hidden during import because import produces no download.
- **A-088:** Export keeps Download name, Target profile, Export scope, and Format.
- **A-089:** Open Project shows Local file only.
- **A-090:** Save Project and Save As show Download name only.
- **A-091:** Every dialog open reapplies a complete mode matrix so previous-mode visibility cannot leak.
- **A-092:** Labels and inputs hide together to avoid orphaned text.
- **A-093:** Hidden controls retain values so switching modes does not destroy user choices.
- **A-094:** Import and Open Project keep the current immediate native picker behavior.
- **A-095:** Progress and status remain universal because every file operation can report work.
- **A-096:** Unsaved-change confirmation remains unchanged.
- **A-097:** Mode changes are immediate, with no new animation.
- **A-098:** Hidden fields are removed from the accessibility tree through native hidden semantics plus `aria-hidden`.
- **A-099:** The current action-specific dialog title remains.
- **A-100:** Native dialog focus, Escape, and modal behavior remain unchanged.
- **A-101:** A real-browser regression covers import and export visibility because CSS/DOM visibility cannot be proven by pure logic alone.
- **A-102:** Payload construction is unchanged; this is presentation-only.
- **A-103:** The same visibility rules apply at every viewport size.
- **A-104:** Unknown future actions show no action-specific fields, a safer fallback than exposing unrelated controls.
