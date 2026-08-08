# Multi-selection and repeat movement decisions

| ID | User-visible decision | Options | Decision |
|---|---|---|---|
| Q-01 | Holding Ctrl or Alt while selecting | Toggle · add only | Toggle the clicked or lassoed parts |
| Q-02 | Unmodified selection | Replace · accumulate | Preserve replacement |
| Q-03 | Inspector with several selected parts | Count + disable single edits · silently edit first | Show count and disable single-object controls |
| Q-04 | Starting another axis drag | Immediately · after echo | Immediately |
| Q-05 | Safety for rapid drags | Absolute positions + earliest rollback · drop pending edits | Absolute positions + earliest rollback (A-017) |
| Q-06 | Browser coverage | Ctrl and Alt · Ctrl only | Both Ctrl and Alt |

User wording: “i should be able to multi-select by holding ctrl or alt” and “if i move /
drag an object after stopping dragging to eg: adjust from x to y axis it stops my ability
to drag/move the object”.
