"""The shapes an operator's pointing, words, image and priority marks take.

A themed split, following ``gate_b_contracts_test.py``'s precedent rather than growing
``contracts_test.py`` past its budget. Every ``__post_init__`` guard added by this feature has
its regression test here, per this package's own rule: a guard with no test showing what it
stops reads as pedantry to the next person and gets removed.
"""

from __future__ import annotations

import pytest

from contracts import (
    MAX_ANNOTATION_IMAGE_BYTES,
    ActionReport,
    AnnotatePayload,
    ClientMessageType,
    FocusPayload,
    OperatorAnnotation,
    ServerMessageType,
)

TINY_PNG = "data:image/png;base64,iVBORw0KGgo="


# ─── the message types exist at all ─────────────────────────────────────────────────


def test_the_operator_can_annotate_and_set_focus_over_the_wire() -> None:
    """Without these two members the browser has no way to say "I am pointing at this" or
    "this matters", and ``viewer.client`` answers both with ``unhandled client message
    type`` — an error, in the operator's face, for the feature working correctly."""
    assert ClientMessageType.ANNOTATE == "annotate"
    assert ClientMessageType.SET_FOCUS == "set_focus"


def test_focus_is_echoed_to_every_watcher() -> None:
    """Gate A 10.1 chose many watchers on one session. A mark one person puts up that the
    others never see makes the build look like it is being redirected by nobody."""
    assert ServerMessageType.FOCUS == "focus"


# ─── an annotation ──────────────────────────────────────────────────────────────────


def test_pointing_at_something_without_typing_is_a_complete_annotation() -> None:
    """Q-04's click is a whole gesture on its own. Requiring words would mean you cannot
    simply show the agent a part."""
    payload = AnnotatePayload(object_ids=("stair_railing_02",))
    assert payload.object_ids == ("stair_railing_02",)
    assert payload.text == ""
    assert payload.image == ""


def test_typing_without_pointing_is_also_complete() -> None:
    """The existing redirect composer still works and still reaches this path. An
    annotation is a redirect that may also carry a target and a picture, not a new
    second-class channel."""
    assert AnnotatePayload(text="make the newel post thicker").text


def test_an_empty_annotation_is_refused_rather_than_silently_dropped() -> None:
    """Exactly ``RedirectPayload``'s reasoning: something with nothing in it travels the
    whole way to the agent and then does nothing, and the operator has no way to tell that
    from it having worked."""
    with pytest.raises(ValueError, match="nothing"):
        AnnotatePayload()

    with pytest.raises(ValueError, match="nothing"):
        AnnotatePayload(text="   ")


def test_an_image_must_be_a_data_url() -> None:
    """The browser produces its crop with ``canvas.toDataURL`` (A-012). Anything else here
    means some other thing built this message, and a remote URL in particular would have
    the server fetching an address the browser chose — which is not a capability this
    feature is asking for."""
    with pytest.raises(ValueError, match="data:"):
        AnnotatePayload(object_ids=("wall_01",), image="https://example.com/thing.png")


def test_an_oversized_image_is_refused_with_the_limit_named() -> None:
    """A-011's filed caveat. Annotations ride the viewer WebSocket, and a frame past the
    server's ``max_size`` does not error — it closes the connection. The operator would see
    the live view drop for no stated reason, at the exact moment they tried to say
    something. Refusing here, in the browser, with the number, is the difference between a
    message and a mystery."""
    huge = "data:image/png;base64," + "A" * (MAX_ANNOTATION_IMAGE_BYTES + 1)
    with pytest.raises(ValueError, match=str(MAX_ANNOTATION_IMAGE_BYTES)):
        AnnotatePayload(object_ids=("wall_01",), image=huge)


def test_the_image_limit_leaves_room_for_the_1024px_crop_the_user_asked_for() -> None:
    """Q-23 chose detail over per-point cost — up to 1024px on the long edge. A limit set
    below what that typically encodes to would turn the chosen answer into a permanent
    error message."""
    assert MAX_ANNOTATION_IMAGE_BYTES >= 1_000_000


# ─── focus ──────────────────────────────────────────────────────────────────────────


def test_focus_is_the_whole_set_and_an_empty_one_clears_it() -> None:
    """Q-11 chose "until you clear it", and declaring the complete set is what makes
    clearing expressible at all. A delta protocol needs an explicit clear message, and the
    two drift apart the moment one is dropped."""
    assert FocusPayload(object_ids=()).object_ids == ()
    assert FocusPayload(object_ids=("a", "b")).object_ids == ("a", "b")


def test_focus_refuses_duplicates_rather_than_reporting_a_part_twice() -> None:
    """Focus is re-attached to every report (A-013). A duplicate would tell the agent the
    same object is important twice, every turn, for the rest of the session."""
    with pytest.raises(ValueError, match="twice"):
        FocusPayload(object_ids=("railing", "railing"))


# ─── what the agent is handed ───────────────────────────────────────────────────────


def test_an_annotation_carries_the_measurements_rather_than_a_reference_to_them() -> None:
    """Q-02 chose "everything already measured". The point is that the agent can act
    without spending a call asking what it is looking at, so the facts travel with the
    annotation instead of being something to go and fetch."""
    annotation = OperatorAnnotation(
        object_ids=("stair_railing_02",),
        text="this one clips the tread",
        facts=("stair_railing_02: 1.04 x 0.06 x 0.92 m, 412 tris, 1 defect(s)",),
    )
    assert "412 tris" in annotation.render()
    assert "clips the tread" in annotation.render()


def test_an_annotation_with_an_image_says_so_and_says_how_to_get_it() -> None:
    """``ActionReport`` is text. An image cannot ride it, and the honest response to that is
    to say an image is waiting and name the call that returns it — not to quietly drop the
    half of Q-03 that the report cannot carry."""
    annotation = OperatorAnnotation(
        object_ids=("wall_01",), text="like this", has_image=True, annotation_id="an-3"
    )
    rendered = annotation.render()
    assert "an-3" in rendered
    assert "get_operator_context" in rendered


def test_an_annotation_without_an_image_never_claims_one() -> None:
    """An agent that calls ``get_operator_context`` for an image that does not exist has
    spent a turn learning nothing, and will learn to stop trusting the marker."""
    assert "get_operator_context" not in OperatorAnnotation(text="just words").render()


def test_a_report_carries_focus_and_annotations_and_defaults_to_neither() -> None:
    """Both fields are additive and defaulted, which is what lets sixteen modules that
    construct an ``ActionReport`` keep doing it untouched."""
    plain = ActionReport(op_id="op-1", ok=True, summary="did a thing")
    assert plain.operator_focus == ()
    assert plain.operator_annotations == ()


def test_a_report_shows_the_operator_what_the_agent_was_told() -> None:
    """Focus is a standing instruction re-read every turn (Q-10), so it has to appear in the
    rendered report every turn — a focus set that is held but never shown is one nobody can
    tell is working."""
    report = ActionReport(
        op_id="op-1",
        ok=True,
        summary="did a thing",
        operator_focus=("stair_railing_02", "newel_post_01"),
        operator_annotations=(
            OperatorAnnotation(object_ids=("tread_04",), text="too shallow"),
        ),
    )
    rendered = report.render()
    assert "FOCUS" in rendered
    assert "stair_railing_02" in rendered
    assert "newel_post_01" in rendered
    assert "too shallow" in rendered
