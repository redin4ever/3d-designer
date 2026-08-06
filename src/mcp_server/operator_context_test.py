"""``get_operator_context`` — the half of Q-03 a report cannot carry.

``ActionReport`` is text. An annotation's crop is not, so the report says an image is waiting
and names an id, and this tool is what turns that id back into a picture. Without it the
"image" half of "text, image or both" is a promise the product never keeps.
"""

from __future__ import annotations

import pytest

from contracts import ToolError

from mcp_server import dispatch


def test_an_agent_can_read_what_the_operator_is_watching(orchestrator) -> None:
    """Focus rides every ``ActionReport`` already, but an idle agent has not performed an
    action and so has no report. This is how it finds out without changing the scene first —
    which would be a strange thing to have to do to answer "what should I be looking at"."""
    orchestrator.set_focus(("stair_railing_02", "newel_post_01"))

    result = dispatch("get_operator_context", {}, orchestrator=orchestrator)

    assert result["focus"] == ["stair_railing_02", "newel_post_01"]


def test_an_empty_context_is_a_clean_answer_not_an_error(orchestrator) -> None:
    """The overwhelmingly common case: a fully autonomous run nobody is watching (Gate A
    4.4). An agent that reflexively calls this must get "nothing" cheaply, not a refusal it
    has to reason about."""
    result = dispatch("get_operator_context", {}, orchestrator=orchestrator)

    assert result["focus"] == []
    assert result["images"] == []


def test_the_image_the_operator_attached_comes_back(orchestrator) -> None:
    """The whole reason this tool exists. The report says ``image attached (an-1)``; this is
    what an-1 resolves to."""
    orchestrator.hold_annotation_image("an-1", "data:image/png;base64,iVBORw0KGgo=")

    result = dispatch("get_operator_context", {"annotation_id": "an-1"}, orchestrator=orchestrator)

    assert result["image"].startswith("data:image/png")
    assert result["annotation_id"] == "an-1"


def test_asking_for_an_image_that_has_aged_out_refuses_by_name(orchestrator) -> None:
    """Images are bounded — they are hundreds of kilobytes each and a long session points at
    a lot of things. An agent that asks for one that has gone must be told so, not handed an
    empty string it will render as a broken picture or silently ignore."""
    with pytest.raises(ToolError, match="an-99"):
        dispatch("get_operator_context", {"annotation_id": "an-99"}, orchestrator=orchestrator)


def test_the_context_lists_which_images_are_still_available(orchestrator) -> None:
    """So an agent that missed a report, or is resuming, can discover what it can still look
    at rather than guessing ids."""
    orchestrator.hold_annotation_image("an-1", "data:image/png;base64,AAA=")
    orchestrator.hold_annotation_image("an-2", "data:image/png;base64,BBB=")

    result = dispatch("get_operator_context", {}, orchestrator=orchestrator)

    assert result["images"] == ["an-1", "an-2"]


def test_listing_the_context_never_inlines_the_images_themselves(orchestrator) -> None:
    """The listing has to stay cheap enough to call reflexively. Returning every held image
    would cost megabytes for a call whose whole job is to say what is available."""
    orchestrator.hold_annotation_image("an-1", "data:image/png;base64," + "A" * 5000)

    result = dispatch("get_operator_context", {}, orchestrator=orchestrator)

    assert "AAAA" not in repr(result)


def test_the_tool_is_readable_without_holding_the_write_lock(orchestrator) -> None:
    """A lease-less caller reaches INSPECT and nothing else (ADR-013). Asking what the
    operator is watching must not require the ability to change the scene — a read-only
    sub-agent is exactly the caller that needs this most."""
    result = dispatch("get_operator_context", {}, orchestrator=orchestrator)

    assert "focus" in result


def test_the_tool_is_visible_to_an_inspecting_agent() -> None:
    """A tool absent from the registry is unreachable with no error anywhere — the failure
    this whole feature's gate is arranged against."""
    from contracts import ToolRole
    from mcp_server import tools_for

    assert "get_operator_context" in {spec.name for spec in tools_for(ToolRole.INSPECT)}
