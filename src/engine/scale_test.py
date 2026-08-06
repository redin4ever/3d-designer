"""The object-creation cost curve, measured against real Blender out to 3,000 objects.

Gate A 11.4 named *thousands of objects* as the target. ``blender_test.py``'s
``test_object_creation_does_not_degrade_quadratically`` guards the fix that made that
plausible — ``apply_transform_fields`` used to call ``view_layer.update()``, a full
dependency-graph re-evaluation, once per object, making creation O(scene) each time and
O(n²) overall: 3.16 ms/op at ~100 objects rising to **54.52 ms/op at ~900** — but it stops
at ~600 objects. A target of thousands verified only to hundreds is a stated target, not a
measured one, and the interesting part of an O(n²) curve is exactly the part past where you
stopped looking.

This file follows the curve to 3,000 and asserts its *shape*, not just its endpoint: cost is
sampled once per 500-object block, so a bend shows up as the block it bends at rather than
being averaged away into a single endpoint number that looks fine.

Marked ``slow`` as well as ``needs_blender`` — it builds 3,000 real objects and the scene
teardown that follows is itself the most expensive part. Deselect with ``-m "not slow"``; the
marker is registered in this directory's ``conftest.py`` (``--strict-markers`` is on).

Measured on the development machine, Blender 5.2.0, three consecutive runs: 0.23-0.25 ms/op
at 500, a reproducible one-block bump to ~0.34 at 1,000, then 0.19-0.28 flat through 3,000 —
last-block/first-block ratio 1.07, 1.19, 1.16. The bump repeats at the same block every run
and does not compound, so it reads as a one-off bpy collection resize rather than growth.
The thresholds below are set well above that spread: they exist to catch the return of an
O(n²) term, not to police a few tenths of a millisecond on a shared machine, because a
timing assertion tight enough to flake is a timing assertion that gets deleted.
"""

from __future__ import annotations

import time

import pytest

from contracts import Transform, Vec3

from engine import BlenderEngine

pytestmark = [pytest.mark.needs_blender, pytest.mark.slow]

BLOCK = 500
TOTAL = 3000

#: Per-object ceiling at full size. Measured ~0.26 ms/op at 3,000; the regression this
#: guards was 54.52 ms/op at 900. Set at 2.0 so a loaded or slower machine has ~8x room
#: while an O(n²) term is still caught by a factor of 25.
CEILING_MS_PER_OP = 2.0

#: How much the last block may cost relative to the first. Measured 1.07-1.19. A genuinely
#: quadratic per-object cost over this 6x growth in scene size would land near 6x.
MAX_GROWTH_RATIO = 3.0


@pytest.fixture
def engine():
    eng = BlenderEngine()
    eng.reset()
    yield eng
    eng.reset()


def _creation_curve(engine) -> list[tuple[int, float]]:
    """``[(objects_in_scene, ms_per_op_for_that_block), ...]`` building up to ``TOTAL``.

    Each point is the cost of the block that *ended* at that object count, so the value at
    3,000 is the marginal cost of creating an object in a scene that already holds 2,500 —
    which is the number that matters. A cumulative average would dilute exactly the late
    degradation this test exists to find.
    """
    curve: list[tuple[int, float]] = []
    made = 0
    while made < TOTAL:
        start = time.perf_counter()
        for i in range(BLOCK):
            n = made + i
            engine.create_primitive(
                f"scale{n}", "cube", Vec3(0.1, 0.1, 0.1),
                Transform(translation=Vec3(n * 0.5, 0.0, 0.0)),
            )
        elapsed = time.perf_counter() - start
        made += BLOCK
        curve.append((made, elapsed / BLOCK * 1000.0))
    return curve


def _render(curve) -> str:
    return "  ".join(f"{n}:{ms:.3f}ms/op" for n, ms in curve)


def test_object_creation_stays_flat_to_three_thousand(engine) -> None:
    """Creating the 3,000th object must cost about what creating the 500th did.

    Two assertions, because either alone can be passed by a broken engine. The ratio alone
    is satisfied by something uniformly slow (10 ms/op at both ends is flat and useless);
    the ceiling alone is satisfied by a curve that is already bending but has not yet
    crossed it. Together they say: still fast, and still not growing.
    """
    curve = _creation_curve(engine)
    assert len(engine.list_objects()) >= TOTAL, "the scene did not actually reach 3,000 objects"

    first_count, first_ms = curve[0]
    last_count, last_ms = curve[-1]
    shape = _render(curve)

    assert last_ms < CEILING_MS_PER_OP, (
        f"creating an object in a {last_count}-object scene cost {last_ms:.3f} ms, over the "
        f"{CEILING_MS_PER_OP} ms/op ceiling — curve: {shape}"
    )
    assert last_ms <= first_ms * MAX_GROWTH_RATIO, (
        f"per-object cost grew {last_ms / first_ms:.1f}x between {first_count} and "
        f"{last_count} objects ({first_ms:.3f} -> {last_ms:.3f} ms/op), over the "
        f"{MAX_GROWTH_RATIO}x bound — creation is scaling with scene size again. "
        f"Curve: {shape}"
    )


def test_the_curve_has_no_single_block_that_bends(engine) -> None:
    """No block may cost more than the ceiling either — including the ones in the middle.

    The endpoint test above would pass a curve that spikes at 1,500 and recovers by 3,000,
    which is not flat; it is a scene-size-dependent cost that happens to have been sampled
    at a good moment. Checking every block is what makes the assertion about the curve's
    *shape* rather than about its two ends.
    """
    curve = _creation_curve(engine)
    shape = _render(curve)

    over = [(n, ms) for n, ms in curve if ms >= CEILING_MS_PER_OP]
    assert not over, (
        f"{len(over)} block(s) exceeded {CEILING_MS_PER_OP} ms/op: "
        f"{', '.join(f'{n} objects at {ms:.3f}ms' for n, ms in over)}. Curve: {shape}"
    )

    baseline = curve[0][1]
    worst_count, worst_ms = max(curve, key=lambda point: point[1])
    assert worst_ms <= baseline * MAX_GROWTH_RATIO, (
        f"the worst block ({worst_count} objects, {worst_ms:.3f} ms/op) is "
        f"{worst_ms / baseline:.1f}x the first block ({baseline:.3f} ms/op), over the "
        f"{MAX_GROWTH_RATIO}x bound — the curve bends there. Curve: {shape}"
    )
