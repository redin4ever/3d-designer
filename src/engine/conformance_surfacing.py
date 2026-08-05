"""Conformance checks for ``MaterialOps`` + ``UVBakeOps`` — unwrap and bake.

Split out of ``conformance.py`` along the same actor seam as ``src/engine/surfacing.py``.
Both checks involving ``bake`` are deliberately written to accept "in-process bpy has no
windowed context" as a valid outcome — see ``conformance.py``'s module docstring for the
reasoning on validation order.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contracts import EngineError, EngineProtocol, EngineUnavailable, Vec3

__all__ = [
    "check_unwrap_produces_uvs_in_unit_range",
    "check_bake_requires_unwrap_first",
    "check_bake_succeeds_or_raises_capability_error",
    "check_mark_seams_changes_the_subsequent_unwrap",
    "check_bake_raises_engine_unavailable_when_capability_is_absent",
]


def check_unwrap_produces_uvs_in_unit_range(engine: EngineProtocol) -> None:
    """A UV outside [0, 1] wraps or clamps unpredictably at bake and export time, producing
    a visibly wrong texture with no error anywhere in the pipeline."""
    oid = engine.create_primitive("box", "cube", Vec3(2, 3, 1))
    engine.unwrap(oid)

    snap = engine.snapshot(oid)
    assert snap.uvs is not None and len(snap.uvs) == snap.vertex_count and len(snap.uvs) > 0
    assert all(0.0 - 1e-6 <= u <= 1.0 + 1e-6 for uv in snap.uvs for u in uv)


def check_bake_requires_unwrap_first(engine: EngineProtocol) -> None:
    """"Not unwrapped" must be checked, and raised, before any capability-gated bake work is
    attempted, so a caller's actual mistake (forgot to unwrap) is never misreported as an
    environment limitation ("Blender has no window") it cannot fix."""
    oid = engine.create_primitive("box", "cube", Vec3(1, 1, 1))

    with pytest.raises(EngineError) as exc:
        engine.bake(oid, ["albedo"], 1024, "/tmp")

    assert exc.value.rule == "engine.not_unwrapped"


def check_bake_succeeds_or_raises_capability_error(
    engine: EngineProtocol, tmp_path: Path
) -> None:
    """In-process bpy may genuinely lack a windowed context (ADR-001). That must arrive as a
    named capability failure the caller can act on ("install Blender, enable the subprocess
    fallback, or skip this step") — never a bare bpy ``RuntimeError`` an agent cannot parse."""
    oid = engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    engine.unwrap(oid)
    channels = ["albedo"]

    try:
        result = engine.bake(oid, channels, 1024, str(tmp_path))
    except EngineUnavailable as exc:
        assert exc.capability == "bake"
    except Exception as exc:  # noqa: BLE001 — the point of this check is "never a bare one"
        pytest.fail(
            f"bake raised a bare {type(exc).__name__} instead of succeeding or raising "
            f"EngineUnavailable: {exc}"
        )
    else:
        assert set(result) == set(channels)


# --------------------------------------------------------------------------- Blender-only

def check_mark_seams_changes_the_subsequent_unwrap(engine: EngineProtocol) -> None:
    """Blender-only, added in response to a conformance audit: ``FakeEngine.unwrap`` is a
    fixed planar XY projection that never consults marked seams, and exposes no accessor
    for the seam set either — there is nothing on the fake side for this check to observe.
    A no-op ``mark_seams`` on the real engine passes every other UV check in this suite
    silently; the layout would be wrong for anything but the trivial default projection,
    with no error anywhere in the pipeline to catch it."""
    oid = engine.create_primitive("seam_box", "cube", Vec3(2, 3, 1))
    engine.unwrap(oid)
    baseline = list(engine.snapshot(oid).uvs)

    edges = engine.snapshot(oid).edges()
    engine.mark_seams(oid, [i for i in range(min(4, len(edges)))])
    engine.unwrap(oid)
    seamed = list(engine.snapshot(oid).uvs)

    assert seamed != baseline, "marking seams had no effect on the subsequent unwrap"


# ----------------------------------------------------------------------------- fake-only

def check_bake_raises_engine_unavailable_when_capability_is_absent(
    engine: EngineProtocol,
) -> None:
    """Fake-only, added in response to a conformance audit: ``check_bake_succeeds_or_
    raises_capability_error`` above is deliberately permissive (either outcome is valid),
    and the plain ``engine`` fixture always supports bake, so its error branch is dead code
    on the fake side. This is the deterministic complement — called with the root
    conftest's ``engine_without_bake`` fixture, which simulates "no windowed context"
    unconditionally — confirming the exact exception type and capability name rather than
    just "succeeds or raises something". There is no equivalent guaranteed-unavailable
    fixture for the real engine, so this cannot run against ``BlenderEngine``."""
    oid = engine.create_primitive("box", "cube", Vec3(1, 1, 1))
    engine.unwrap(oid)

    with pytest.raises(EngineUnavailable) as exc:
        engine.bake(oid, ["albedo"], 1024, "/tmp")

    assert exc.value.capability == "bake"
