"""Stub — computable realism proxies. Explicitly not a "looks realistic" score.

See ``src/detail/README.md``. Gate A 11.3 splits verification authority: measurement decides
hard facts, the agent decides appearance. There is no computed metric for "looks realistic"
— research found no published one (``docs/research/domain.md``: "'Has bevels' / sharp-edge
ratio ... Partially ... inferred, not a published metric"), and inventing one would hand back
a number dressed up as a fact when it is actually an opinion with a decimal point. This module
returns only the individual, named proxies that ARE computable, and the caller (an agent
judging appearance, per Gate A 8.1/11.3) reads them alongside the render — it does not fold
them into one score.

Nothing here computes anything yet; the function raises until an implementer replaces the
body.

**Contract note (see the parent task's ``contractRequests``):** ``contracts.MetricKind`` has
seven members, of which only ``TRIANGLE_COUNT`` names one of this module's four documented
proxies directly. The other three — sharp-edge ratio, triangle aspect ratio, edge-length
uniformity — have no dedicated member. Until ``contracts`` grows one, an implementation must
reuse an existing ``MetricKind`` and carry the proxy's real name in ``Measurement.subject``/
``Measurement.detail`` instead of inventing an enum value of its own; ``report_test.py`` only
asserts that every returned ``kind`` is a genuine ``MetricKind`` member, not which one, so it
does not block on this gap.
"""

from __future__ import annotations

from contracts import EngineProtocol, Measurement

__all__ = ["realism_report"]


def realism_report(engine: EngineProtocol, object_id: str) -> tuple[Measurement, ...]:
    """Computable realism proxies for ``object_id`` — never a "looks realistic" verdict.

    Once implemented, this returns one :class:`contracts.Measurement` per proxy, at minimum:

    - **Sharp-edge ratio** — fraction of ``snapshot.edges()`` with two adjacent faces whose
      dihedral angle clears some "sharp" band (see :func:`detail.select_bevel_edges` for the
      same underlying angle computation; this is a read-only echo of it, not a re-derivation).
    - **Triangle aspect ratio** — a measure of how far the mesh's triangles are from
      equilateral (e.g. longest edge over shortest edge, averaged or worst-case); slivers are
      themselves a tell independent of anything about edges or materials.
    - **Edge-length uniformity** — spread of edge lengths across the mesh (e.g. coefficient of
      variation); a hand-authored or well-retopologised mesh does not have wildly
      inconsistent edge lengths, a naive generator often does.
    - **Triangle count** — ``MetricKind.TRIANGLE_COUNT``, the one proxy with an exact existing
      contract member; computed from ``engine.snapshot(object_id)`` directly, not imported
      from ``measure`` (this module does not depend on ``measure`` for anything computed
      fresh here — see ``.pipeline/modules.json``).

    None of these may be named, described, or documented as an overall realism, quality, or
    "does this look real" score — see ``report_test.py`` for the exact check. This function
    is read-only: it must never call a mutating ``EngineProtocol`` method.
    """
    raise NotImplementedError("detail.realism_report: not implemented")
