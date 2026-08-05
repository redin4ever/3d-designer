"""``UVResult`` and ``BakeResult`` — the two outcome shapes this module returns.

Real, constructed dataclasses, not stubs — every function in this module needs the exact
shape to exist at import time, mirroring ``detail.results.DetailResult`` and
``contracts.RepairOutcome``'s own justification for a typed outcome over a bare bool: ``ok``
alone cannot distinguish a clean unwrap from one that quietly produced degenerate UVs, and a
bare dict of maps cannot distinguish "this object has no albedo channel" from "the capacity
to bake albedo does not exist in this Blender install at all" (``EngineUnavailable``).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["UVResult", "BakeResult"]


@dataclass(frozen=True, slots=True)
class UVResult:
    """What one :func:`uv.unwrap` call produced.

    ``coverage``, ``max_stretch`` and ``overlaps`` are the same three computable proxies
    :func:`uv.uv_quality` returns as ``Measurement`` values — carried here too, un-boxed, so
    a caller that just unwrapped an object does not need a second round trip through the
    engine to learn whether the result it just produced is any good.

    ``seam_count`` is the number of edges actually marked — whichever set won, agent-supplied
    or suggested (see :func:`uv.unwrap`'s docstring). It is the cheapest possible proof that
    an explicit ``seams=`` override reached the engine: it will differ from the count
    :func:`uv.suggest_seams` would have produced on its own whenever the caller's override
    genuinely differs in size.
    """

    object_id: str
    ok: bool
    seam_count: int
    coverage: float
    max_stretch: float
    overlaps: int
    detail: str = ""


@dataclass(frozen=True, slots=True)
class BakeResult:
    """What one :func:`uv.bake` (or :func:`uv.unwrap_and_bake`) call produced.

    ``ok=False`` with a populated ``unavailable_reason`` is the ``EngineUnavailable`` path —
    baking generally needs a windowed Blender context that in-process ``bpy`` does not have
    (``contracts.EngineUnavailable``'s own docstring). This is always a reported, named
    limitation carried on this dataclass, never a raised exception past this module's public
    functions and never a silently empty ``maps`` with no explanation attached.

    ``uv`` carries the :class:`UVResult` from whichever unwrap step this bake performed, when
    it performed one at all — see ``bake.py`` for exactly when that is ``None`` versus
    populated; the difference is documented behaviour, not an oversight.
    """

    object_id: str
    ok: bool
    maps: dict[str, str]
    unavailable_reason: str = ""
    uv: UVResult | None = None
