"""What the live view subscribes to: ``subscribe`` (and the private ``_emit`` that
``document.py`` and ``history.py`` call).

``scene`` never imports ``src/viewer/``. The event this module carries
(``contracts.SceneChangeEvent``) is the entire dependency surface between them, and the
arrow points one way: the viewer subscribes to scene; scene knows nothing about the
viewer. See ``events_test.py::test_scene_source_never_imports_the_viewer``, which parses
every source file in this package and fails if any of them import anything named
``viewer``.
"""

from __future__ import annotations

from typing import Callable

from contracts import SceneChangeEvent

__all__ = ["EventsMixin", "Listener"]

Listener = Callable[[SceneChangeEvent], None]


class EventsMixin:
    """``subscribe``/``_emit``. Expects ``self._listeners: list[Listener]`` — see
    ``scene/__init__.py``."""

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Register ``listener`` and return a callable that unregisters it.

        Once implemented: append ``listener`` to ``self._listeners``; return a closure
        that removes exactly that listener (by identity, not equality — two distinct
        listeners that happen to compare equal must still be removable independently)
        and is safe to call more than once — unsubscribing an already-removed listener
        is a no-op, not an error, so a caller tearing down does not have to guard
        against a double-call.
        """
        self._listeners.append(listener)

        def _unsubscribe() -> None:
            for index, existing in enumerate(self._listeners):
                if existing is listener:
                    del self._listeners[index]
                    break

        return _unsubscribe

    def _emit(self, event: SceneChangeEvent) -> None:
        """Deliver ``event`` to every subscribed listener, independently.

        Once implemented: iterate ``list(self._listeners)`` (a copy — a listener that
        unsubscribes itself mid-delivery must not corrupt the list being iterated) and
        call each one inside its own ``try``/``except Exception``, swallowing whatever it
        raises rather than re-raising. **A raising listener must not stop the remaining
        listeners from being called, and must never propagate out of ``_emit``** — the
        viewer is allowed to crash without taking the geometry core, or any other
        subscriber, with it. See
        ``events_test.py::test_a_raising_listener_does_not_break_apply`` and
        ``test_other_listeners_still_receive_the_event_when_one_raises``.
        """
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                pass
