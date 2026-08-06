"""Stub — ``bake`` and ``unwrap_and_bake``: texture bake, ``EngineUnavailable`` reported by
name.

See ``src/uv/README.md``. In-process ``bpy`` genuinely may have no windowed context to bake
with (``contracts.EngineUnavailable``'s own docstring: "UV bake is the operation most likely
to hit this"). That must arrive as a reported, named limitation on the returned
``BakeResult`` — never a raised exception, never a silently empty ``maps``, and never folded
into the same shape a different kind of failure (a bad resolution, an unknown object) would
take. Only ``contracts.EngineUnavailable`` is caught here; every other exception propagates
unchanged.

**Policy — "bake before any unwrap" — resolved as "unwraps first, lazily":** ``bake()``
unwraps automatically only when the object has no UVs yet (``snapshot.uvs is None``), using
:func:`uv.suggest_seams`'s automatic seams; an object already explicitly unwrapped (including
with caller-chosen seams) is left exactly as it is. ``unwrap_and_bake()`` always unwraps,
because calling it is itself the request to (re)unwrap and the whole point of accepting
``seams`` there is letting a fresh override reach the engine even for an object baked once
already.

Nothing here computes anything yet; every function raises until an implementer replaces the
body (Rule 4 — tests come first).
"""

from __future__ import annotations

from typing import Sequence

from contracts import EngineProtocol, EngineUnavailable

from .results import BakeResult, UVResult
from .unwrap import unwrap

__all__ = ["bake", "unwrap_and_bake"]

DEFAULT_CHANNELS: tuple[str, ...] = ("albedo", "normal", "roughness")

_UNWRAP_KEYS = {"seams", "method", "margin"}
_BAKE_KEYS = {"channels", "resolution", "output_dir"}


def bake(
    engine: EngineProtocol,
    object_id: str,
    *,
    channels: Sequence[str] = DEFAULT_CHANNELS,
    resolution: int = 1024,
    output_dir: str = ".",
) -> BakeResult:
    """Bake ``channels`` for ``object_id`` at ``resolution`` into ``output_dir``.

    Unwraps first, lazily, only if the object has no UVs yet — see this module's docstring
    for the full policy and ``src/uv/README.md`` for why it was chosen over "fail cleanly and
    demand a prior ``unwrap()`` call".
    """
    snapshot = engine.snapshot(object_id)
    uv_result: UVResult | None = unwrap(engine, object_id) if snapshot.uvs is None else None
    ok, maps, reason = _perform_bake(engine, object_id, channels, resolution, output_dir)
    return BakeResult(
        object_id=object_id, ok=ok, maps=maps, unavailable_reason=reason, uv=uv_result
    )


def unwrap_and_bake(engine: EngineProtocol, object_id: str, **kw) -> BakeResult:
    """Compose :func:`uv.unwrap` and :func:`uv.bake` in one call.

    ``kw`` accepts every keyword either step takes (``seams``, ``method``, ``margin`` for the
    unwrap; ``channels``, ``resolution``, ``output_dir`` for the bake) and routes each to the
    right step; an unrecognised keyword raises ``TypeError`` naming it rather than being
    silently dropped. Unlike :func:`bake`, this always unwraps, so ``BakeResult.uv`` is always
    populated here, never ``None``.
    """
    unknown = set(kw) - _UNWRAP_KEYS - _BAKE_KEYS
    if unknown:
        raise TypeError(
            f"unwrap_and_bake() got unexpected keyword argument(s): {sorted(unknown)}"
        )
    unwrap_kwargs = {k: v for k, v in kw.items() if k in _UNWRAP_KEYS}
    bake_kwargs = {k: v for k, v in kw.items() if k in _BAKE_KEYS}

    uv_result = unwrap(engine, object_id, **unwrap_kwargs)
    ok, maps, reason = _perform_bake(
        engine,
        object_id,
        bake_kwargs.get("channels", DEFAULT_CHANNELS),
        bake_kwargs.get("resolution", 1024),
        bake_kwargs.get("output_dir", "."),
    )
    return BakeResult(
        object_id=object_id, ok=ok, maps=maps, unavailable_reason=reason, uv=uv_result
    )


def _perform_bake(
    engine: EngineProtocol,
    object_id: str,
    channels: Sequence[str],
    resolution: int,
    output_dir: str,
) -> tuple[bool, dict[str, str], str]:
    """Runs ``EngineProtocol.bake`` and shapes its outcome.

    Only ``EngineUnavailable`` is caught — a specific, named capability failure
    (``contracts.EngineUnavailable``'s own docstring) that must never be confused with any
    other kind of engine failure. Every other exception (an unknown object, a bad
    resolution, …) propagates unchanged rather than being folded into this same shape.
    """
    try:
        maps = engine.bake(object_id, tuple(channels), resolution, output_dir)
    except EngineUnavailable as exc:
        return False, {}, str(exc)
    return True, dict(maps), ""
