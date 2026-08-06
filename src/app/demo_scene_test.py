"""The seed must build through the real path, or it is a lie about what the product does."""

from __future__ import annotations

from app import build_app
from app.demo_scene import DEMO_OPERATIONS, seed_scene


def test_the_seed_actually_puts_geometry_in_the_scene() -> None:
    """`forge3d run` opened an empty room. A person starting the product for the first time
    saw a working live view of nothing, with no way to put anything in it."""
    app = build_app(prefer_blender=False, attach_viewer=False)

    result = seed_scene(app)

    assert result.ok, f"the demo scene did not build: {result.failed}"
    assert result.objects > 0, "the seed reported success and produced no objects"


def test_every_seeded_operation_is_one_an_agent_could_also_call() -> None:
    """The seed must not be a special mode that draws what the product cannot otherwise
    produce. If it works and an agent cannot reproduce it, the seed is broken."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    for kind, _params in DEMO_OPERATIONS:
        assert kind in app.handlers, f"{kind} is not a real operation"


def test_the_seed_goes_through_the_write_lock_and_the_log() -> None:
    """Not a back door into the engine. Same lease, same log, same checks, same viewer
    messages as an agent's call — which is also what makes the live view show it."""
    app = build_app(prefer_blender=False, attach_viewer=False)

    seed_scene(app)

    kinds = [op.kind for op in app.scene.document.operations]
    assert kinds, "the seed bypassed the operation log entirely"
    for kind, _params in DEMO_OPERATIONS:
        assert kind in kinds, f"{kind} never reached the log"


def test_the_seed_releases_the_lock_so_an_agent_can_take_it() -> None:
    """A seed that kept the write lease would leave every connected agent locked out of the
    scene it was supposed to be showing them."""
    app = build_app(prefer_blender=False, attach_viewer=False)

    seed_scene(app)

    app.orchestrator.acquire("some-agent", app.orchestrator.phase)


def test_a_failing_operation_is_reported_and_the_rest_still_run() -> None:
    """A seed that silently swallowed an error is the worst possible first impression: a
    scene quietly missing pieces, from a tool whose premise is telling you what is wrong."""
    app = build_app(prefer_blender=False, attach_viewer=False)

    result = seed_scene(app, operations=(
        ("add_primitive", {"object_id": "good", "kind": "cube", "size": [1.0, 1.0, 1.0]}),
        ("add_primitive", {"object_id": "bad", "kind": "dodecahedron", "size": [1.0, 1.0, 1.0]}),
        ("add_primitive", {"object_id": "also_good", "kind": "cube", "size": [1.0, 1.0, 1.0]}),
    ))

    assert not result.ok, "an unknown primitive kind should not report as a clean seed"
    assert len(result.applied) == 2, "one bad operation stopped the ones after it"
    assert result.failed and result.failed[0][0] == "add_primitive"
    assert "dodecahedron" in result.describe() or result.failed[0][1]


def test_a_held_write_lock_is_a_reason_not_to_seed_not_a_crash() -> None:
    """Starting a second session, or an agent that connected first, must not take the
    server down on startup."""
    app = build_app(prefer_blender=False, attach_viewer=False)
    app.orchestrator.acquire("someone-else", app.orchestrator.phase)

    result = seed_scene(app)

    assert not result.ok
    assert result.failed[0][0] == "acquire"
