"""``_curve``'s own guards — the ones a direct caller, not ``array_along_curve``, hits.

``ModifierOpsMixin.array_along_curve`` validates ``spacing`` itself before it ever calls in
here, so no path through the product currently reaches these. That is exactly why they need
a test of their own: ``sample_polyline`` is exported from ``_curve.__all__``, its twin in
``testing/mesh_helpers.py`` has guarded ``spacing <= 0`` since it was written, and this copy
had silently diverged (F-025). ``while t <= length + 1e-9: ... t += spacing`` with
``spacing == 0`` never advances — a direct call does not return a wrong answer, it hangs the
process and grows a list until memory runs out.

That hang is why these tests do not simply call and wait. A regression must fail in
milliseconds, not at the 60-second suite timeout, so :class:`_BudgetedVec3` bounds the loop
by **counting vector additions** rather than by wall clock: deterministic, no timing flake,
and it names the runaway loop in the failure message instead of leaving a wedged worker.

The parity test at the bottom is the standing defence against the divergence recurring. It
compares the two copies' *outputs*, never importing one into the other — ``src/engine/`` may
not depend on ``src/testing/`` at runtime (see ``src/engine/CLAUDE.md``), but a test may
read both and insist they agree.
"""

from __future__ import annotations

import math

import pytest

from contracts import EngineError, Vec3
from engine._curve import arc_length_to, rotation_from_up_to, sample_polyline, tangent_at

_ADDITION_BUDGET = 10_000


class _RanAway(AssertionError):
    """Raised instead of hanging, so an unguarded loop fails the test in milliseconds."""


class _BudgetedVec3(Vec3):
    """A ``Vec3`` that refuses to take part in more than ``_ADDITION_BUDGET`` additions.

    ``sample_polyline`` appends ``a + direction * t`` once per emitted position, where ``a``
    is a point the caller supplied — so counting ``__add__`` on the caller's own points
    bounds the loop from outside without the helper knowing it is being watched.
    """

    additions = 0

    @classmethod
    def reset_budget(cls) -> None:
        cls.additions = 0

    def __add__(self, other: Vec3) -> Vec3:
        type(self).additions += 1
        if type(self).additions > _ADDITION_BUDGET:
            raise _RanAway(
                f"sample_polyline emitted more than {_ADDITION_BUDGET} positions on a "
                "two-point path — the spacing guard is missing and the loop never advances"
            )
        return Vec3.__add__(self, other)


@pytest.fixture(autouse=True)
def _fresh_budget() -> None:
    _BudgetedVec3.reset_budget()


def _budgeted_path() -> list[Vec3]:
    return [_BudgetedVec3(0.0, 0.0, 0.0), _BudgetedVec3(3.0, 0.0, 0.0)]


@pytest.mark.parametrize("spacing", [0.0, -0.5])
def test_sample_polyline_rejects_non_positive_spacing(spacing: float) -> None:
    """Zero spacing makes ``t += spacing`` a no-op, so the loop never terminates; a negative
    spacing walks backwards forever. Neither is a request that can be honoured, and both
    take the process with them rather than returning something wrong a caller could notice."""
    with pytest.raises(EngineError) as exc:
        sample_polyline(_budgeted_path(), spacing)
    assert exc.value.rule == "engine.bad_spacing"
    assert exc.value.suggestion, "a rule name with no next step makes an agent retry forever"


def test_sample_polyline_still_samples_a_valid_spacing() -> None:
    """The guard must reject only what it was written for — and this is also what proves
    the budget above does not fire on ordinary input."""
    out = sample_polyline(_budgeted_path(), 1.0)
    assert [round(p.x, 6) for p in out] == [0.0, 1.0, 2.0, 3.0]


# ------------------------------------------------------------------ divergence, F-025


def _reference():
    """``testing.mesh_helpers`` — the twin. Imported inside the test module only; production
    code in ``src/engine/`` must never reach for it."""
    from testing import mesh_helpers

    return mesh_helpers


_PATHS = [
    [Vec3(0, 0, 0), Vec3(3, 0, 0)],
    [Vec3(0, 0, 0), Vec3(2, 0, 0), Vec3(2, 2, 0)],
    [Vec3(0, 0, 0), Vec3(1, 0, 0.5), Vec3(2, 0, 1.0), Vec3(3, 0, 1.5)],  # a stair rake
]


@pytest.mark.parametrize("path", _PATHS)
def test_curve_helpers_agree_with_their_twin_in_testing(path: list[Vec3]) -> None:
    """The four helpers here are a deliberate duplicate of ``testing.mesh_helpers``'.

    The duplication is the right call — ``FakeEngine`` is test infrastructure and production
    code may not depend on it — but a duplicate with nobody watching it drifts, which is how
    F-025 happened. This pins the two copies to the same answers on the same inputs, so the
    next divergence is a red test rather than a defect found by reading.
    """
    ref = _reference()
    for spacing in (0.4, 1.0):
        assert [p.as_tuple() for p in sample_polyline(path, spacing)] == [
            p.as_tuple() for p in ref.sample_polyline(path, spacing)
        ]
    for probe in (Vec3(0.7, 0.1, 0.2), Vec3(2.5, 0.0, 1.1), path[-1]):
        assert arc_length_to(path, probe) == pytest.approx(ref.arc_length_to(path, probe))
        assert tangent_at(path, probe).as_tuple() == pytest.approx(
            ref.tangent_at(path, probe).as_tuple()
        )
    for direction in (Vec3(1, 0, 0), Vec3(0, 0, 1), Vec3(0, 0, -1), Vec3(1, 1, 1)):
        mine, theirs = rotation_from_up_to(direction), ref.rotation_from_up_to(direction)
        assert (mine.w, mine.x, mine.y, mine.z) == pytest.approx(
            (theirs.w, theirs.x, theirs.y, theirs.z)
        )


def test_rotation_from_up_to_is_still_a_unit_quaternion() -> None:
    """Both copies feed ``duplicate()``'s transform directly; a non-unit quaternion there
    scales the instance as well as rotating it, which no caller asks for."""
    for direction in (Vec3(1, 0, 0), Vec3(0, 0, -1), Vec3(0.3, -0.4, 0.86)):
        q = rotation_from_up_to(direction)
        assert math.sqrt(q.w * q.w + q.x * q.x + q.y * q.y + q.z * q.z) == pytest.approx(1.0)
