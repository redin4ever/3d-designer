"""A scene to look at, built through the real path.

``forge3d run`` opened an empty room. Geometry only ever arrives from a connected agent, so
someone starting the product for the first time got a working live view of nothing at all,
with no way to put anything in it short of writing an MCP client. "There are no meshes" is
the correct reading of what the product did, not a misunderstanding of it.

This seeds a scene so there is something on screen immediately. Two rules make it worth
having rather than a lie:

**It goes through the real path.** Every operation here runs through
``Orchestrator.perform`` with a genuine write lease, exactly as an agent's call does — the
same handlers, the same log, the same undo, the same checks, the same viewer messages. It is
not a special "demo mode" that draws something the product could not otherwise produce. If
the seed works and an agent cannot reproduce it, the seed is broken.

**It stays honest about failure.** A refused operation is reported and the rest continue. A
seed that silently swallowed an error would be the worst possible first impression: a scene
that is quietly missing pieces, from a tool whose entire premise is that it tells you what
is wrong with your geometry.

The staircase and railing are deliberate. They are this library's flagship — the railing
places posts plumb on a sloped multi-segment path, which is the case a naive generator gets
visibly wrong — and they are the most convincing thing the product can put on a screen in
under a second.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts import Operation, Phase

__all__ = ["DEMO_OPERATIONS", "SeedResult", "seed_scene"]


DEMO_OPERATIONS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("add_floor", {"object_id": "deck", "width": 8.0, "depth": 8.0, "thickness": 0.2}),
    (
        "add_staircase",
        {
            "object_id": "stair",
            "treads": 10,
            "rise": 0.18,
            "run": 0.28,
            "width": 1.2,
            "origin": [-1.0, -2.0, 0.1],
        },
    ),
    (
        "add_railing",
        {
            "object_id": "rail",
            # Follows the stair's rake: 10 treads at 0.18 rise and 0.28 run.
            "path": [[-0.3, -2.0, 0.1], [-0.3, 0.8, 1.9]],
            "height": 1.0,
            "post_spacing": 0.9,
            "baluster_gap": 0.11,
        },
    ),
    ("add_primitive", {"object_id": "crate", "kind": "cube", "size": [0.7, 0.7, 0.7]}),
)
"""What the seed builds. A tuple so it is inspectable and testable without running it."""


@dataclass(frozen=True)
class SeedResult:
    applied: tuple[str, ...] = ()
    failed: tuple[tuple[str, str], ...] = ()
    objects: int = 0

    @property
    def ok(self) -> bool:
        return not self.failed

    def describe(self) -> str:
        if self.ok:
            return f"  demo scene: {len(self.applied)} operations, {self.objects} objects"
        lines = [f"  demo scene: {len(self.applied)} of {len(self.applied) + len(self.failed)} operations"]
        for kind, why in self.failed:
            lines.append(f"    {kind} failed: {why}")
        return "\n".join(lines)


def seed_scene(app: Any, *, operations: tuple[tuple[str, dict[str, Any]], ...] = DEMO_OPERATIONS) -> SeedResult:
    """Build the demo scene through ``app``'s real orchestrator. Never raises."""
    orch = app.orchestrator
    applied: list[str] = []
    failed: list[tuple[str, str]] = []

    try:
        lease = orch.acquire("forge3d-demo", Phase.BLOCKOUT)
    except Exception as exc:  # noqa: BLE001 — a held lock is a normal reason not to seed
        return SeedResult(failed=(("acquire", str(exc)),))

    try:
        for index, (kind, params) in enumerate(operations):
            op = Operation(op_id=f"demo-{index:02d}-{kind}", kind=kind, params=dict(params))
            try:
                report = orch.perform(op, lease)
            except Exception as exc:  # noqa: BLE001
                failed.append((kind, f"{type(exc).__name__}: {exc}"))
                continue
            if getattr(report, "ok", False):
                applied.append(kind)
            else:
                failed.append((kind, getattr(report, "error_detail", "") or "refused"))
    finally:
        try:
            orch.release(lease)
        except Exception:  # noqa: BLE001 — releasing a lease we hold should not mask a result
            pass

    try:
        objects = len(app.scene.engine.list_objects())
    except Exception:  # noqa: BLE001
        objects = 0

    return SeedResult(applied=tuple(applied), failed=tuple(failed), objects=objects)
