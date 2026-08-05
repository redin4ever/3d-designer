"""Anchor resolution — turning a symbolic reference into world geometry.

An ``Anchor`` (``src/contracts/constraints.py``) names a target *symbolically*:
``stair_01.outer_edge``, never a resolved coordinate. That is the entire mechanism behind
live re-solve (ADR-002) — the stair moves, the anchor's identity survives, and the next
resolve call reads the new geometry. Anything that resolves an anchor once and caches the
number defeats the reason anchors are symbolic in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts import Anchor, EngineProtocol, Vec3

__all__ = ["AnchorResolution", "resolve_anchor"]


@dataclass(frozen=True, slots=True)
class AnchorResolution:
    """The concrete geometry an :class:`~contracts.Anchor` resolves to, at one moment.

    Never stored across a solve — an anchor is re-resolved every time
    :func:`constraints.solve` or :func:`constraints.satisfies` runs, which is what lets a
    moved upstream object be detected rather than silently read as stale.
    """

    point: Vec3
    """A representative world-space point for the anchor — the vertex, the face centre,
    the object's origin, or the first point of a path."""

    normal: Vec3 | None = None
    """Populated for face-like anchors (``AnchorKind.FACE``). Unit length, pointing away
    from the surface — this is what ``on`` measures vertical contact against and what
    ``coplanar_with`` aligns another object's own normal axis onto."""

    direction: Vec3 | None = None
    """Populated for edge/path/centreline-like anchors — the resolved tangent, unit
    length. This is what ``follows`` orients an instance's forward axis onto and what
    ``parallel_to``/``perpendicular_to`` measure their angle against."""

    path: tuple[Vec3, ...] | None = None
    """Populated for ``AnchorKind.PATH`` / ``AnchorKind.CENTRELINE`` — the full polyline,
    not just its endpoints, so a following constraint can walk the whole curve rather than
    interpolate a straight chord across a corner it never actually turns."""


def resolve_anchor(engine: EngineProtocol, anchor: Anchor) -> AnchorResolution:
    """Resolve one symbolic anchor against the engine's *current* geometry.

    ``AnchorKind.WORLD`` (see ``Anchor.world_up()``) resolves with no object lookup at
    all — ``direction`` is world up, ``point`` is the origin. Every other kind resolves
    through ``anchor.object_id``.

    Must raise :class:`~contracts.ConstraintError` — never a bare ``KeyError`` or
    ``AttributeError`` — when ``anchor.object_id`` does not name a live object. Gate A 4.2
    requires an agent be told which id was missing and what to try next, not handed a
    traceback it cannot act on; ``engine.exists()``/``engine.list_objects()`` are what
    make that suggestion possible without a bare lookup failure.
    """
    raise NotImplementedError("constraints.resolve_anchor: not implemented")
