"""The one error this module raises, and why it has two bases.

Gate A 4.2, verbatim: a failing agent is told **what rule it broke**. Gate B 5.4 found that
promise half-kept — and this module was half of the half. Its *validation* failures were
already exemplary (:class:`contracts.ConstraintError` carries ``rule``/``detail``/
``suggestion`` and every unknown object, bad index and cycle raises one), while its
*geometry* failures fell through to ``contracts.Vec3.normalized()`` and reached the agent as
``ValueError: cannot normalize a zero-length vector`` — a traceback pointing at a file the
agent has never seen, with nothing in it to act on.

Naming the rule is only half of what makes that fixable. The other half is that the boundary
must be able to *recognise* a named failure without knowing every module's own exception
type, which is what :class:`contracts.RuleError` is for: ``EngineError``, ``ToolError``,
``LockContention``, ``RunPaused``, ``ProposalConflict`` and ``PromotionRefused`` all derive
from it, so ``app/handlers.py`` catches one type and treats anything else as an unnamed
failure to wrap. ``ConstraintError`` does not — it predates ``RuleError`` and derives from
``ValueError`` — so every error this module raises is invisible to that check.

:class:`ConstraintRuleError` closes that locally rather than reaching into the frozen
contract (Rule 5). ``src/contracts/`` is main-agent-owned; the request to give
``ConstraintError`` the same two bases is filed in ``.pipeline/contract-requests.json``, and
when it lands **this whole file deletes and every raise site goes back to naming
``ConstraintError`` directly**. That is the point of doing it this way: the adapter is one
class and one import, reversible in a single commit, and nothing outside this package has to
learn a new exception name in the meantime.

Two bases, in that order, for the reason ``orchestration.PromotionRefused`` gives for the
same construction: ``ConstraintError`` first so every existing ``except ConstraintError``
and every ``pytest.raises(ConstraintError)`` in the suite keeps working unchanged, and
``RuleError`` second so the boundary's single ``isinstance`` sees it. ``ConstraintError``
already derives from ``ValueError``, so a caller catching that is unaffected too — this
widens what the failure *carries* and narrows nothing about what it *is*.
"""

from __future__ import annotations

from contracts import ConstraintError, RuleError

__all__ = ["ConstraintRuleError", "AXIS_RULE", "UNSUPPORTED_KIND_RULE"]

#: Raised when a constraint's ``axis`` cannot be used as a direction.
#:
#: The most likely cause is worth stating in the suggestion rather than in a comment:
#: ``Constraint.axis`` is a *direction* for ``offset_from``/``flush_with``/``spacing``/
#: ``clear_of`` and a component-wise *mask* only for ``centred_on`` (``CLAUDE.md``). An agent
#: reasoning in masks writes ``Vec3(0, 0, 0)`` to mean "no axis", which is precisely the
#: value that has no direction.
AXIS_RULE = "constraints.unusable_axis"

#: Raised when a constraint kind reaches a family that does not handle it.
#:
#: Unreachable from agent input today — :func:`constraints.solve` dispatches by membership in
#: ``POSITION_KINDS``/``FORWARD_KINDS``/``UP_KINDS``, so a kind only arrives here if it is in
#: none of them. That makes this a message for whoever adds the thirteenth
#: :class:`contracts.ConstraintKind`, and the reason it names the three sets by name.
UNSUPPORTED_KIND_RULE = "constraints.unsupported_kind"


class ConstraintRuleError(ConstraintError, RuleError):
    """A constraint failure that the boundary can recognise as a named one.

    Identical in shape and construction to :class:`contracts.ConstraintError` — same
    ``rule``/``detail``/``suggestion``, same message formatting — and additionally a
    :class:`contracts.RuleError`, which is what ``as_dict()`` and the boundary's one
    ``isinstance`` check need. See this module's docstring for why it exists here rather
    than in ``contracts``, and what removes it.
    """
