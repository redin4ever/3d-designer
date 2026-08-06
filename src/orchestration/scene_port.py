"""``ScenePort`` now lives in ``contracts``. This module is the re-export, nothing else.

It used to hold a second, local declaration of the same Protocol — this module's own guess
about ``scene``'s shape, written while ``scene`` did not exist. The guess was wrong twice,
and each time produced a P0 that three green suites could not see, because the doubles
matched the *declaration* rather than the real ``Scene``: ``document`` declared as a method
where ``Scene`` exposes a property, and ``apply`` declared without ``lease`` so
``perform`` called ``apply(op)`` and got ``LockContention`` against the lease it had just
verified.

One declaration both sides compile against is the only arrangement in which a double cannot
agree with the wrong side of a contract. Keeping the local copy alive "just as an alias"
would re-open exactly that gap the next time either side moves, so there is deliberately
nothing here but the import.
"""

from __future__ import annotations

from contracts import ScenePort

__all__ = ["ScenePort"]
