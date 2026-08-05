"""Run control: pause, resume, and the run's own state (Gate A 5.4).

Pause is cooperative — checked between operations, never mid-operation, so the log is
never left half-applied (``contracts.RunState.PAUSED``'s own docstring). This module owns
only the state flag; ``reporting.perform`` is what actually consults it, once
implemented.

Nothing here computes anything yet — every method raises until an implementer replaces
the body (Rule 4 — tests come first).
"""

from __future__ import annotations

from contracts import RunState

_NOT_IMPLEMENTED = "orchestration.{name}: not implemented"


class RunPaused(RuntimeError):
    """Raised by ``reporting.perform`` while the run is paused.

    This module's chosen answer to the brief's "raises or defers — pick one, test it,
    document it": **raises**. A caller that ignores a raised error is unambiguously a
    caller bug; a deferred call could instead be silently lost if the agent's turn ends
    before ``resume()`` — MCP is call/response, so there is no later moment to deliver a
    deferred result into. Raising also composes with the cooperative-pause guarantee:
    the check happens before ``self._scene.apply`` runs, never after, so a paused run
    never has a half-applied operation to resume into either.

    Not defined in ``src/contracts/`` because Rule 5 reserves that package for the main
    agent; this is orchestration's own addition pending reconciliation (see this task's
    ``contractRequests`` output).
    """

    def __init__(
        self, detail: str = "the run is paused; call resume() before performing more operations"
    ) -> None:
        super().__init__(detail)
        self.rule = "orchestration.run_paused"
        self.detail = detail


class RunMixin:
    """Mixed into :class:`Orchestrator`. See ``src/orchestration/__init__.py``."""

    def pause(self) -> None:
        """Set run state to :attr:`contracts.RunState.PAUSED`. Once implemented,
        ``reporting.perform`` must consult this before starting a new operation — never
        abort one already in flight, which is what "cooperative" means here."""
        self._state = RunState.PAUSED

    def resume(self) -> None:
        """Restore :attr:`contracts.RunState.RUNNING`."""
        self._state = RunState.RUNNING

    @property
    def state(self) -> RunState:
        return self._state
