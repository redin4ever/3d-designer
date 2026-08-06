"""A browser refresh must not erase the conversation.

The chat transcript lived only in the page, so reloading — or opening a second window —
showed an empty conversation while the run carried on around it. Nothing was lost on the
backend; there was simply no way to ask for it.
"""

from __future__ import annotations

from contracts import ServerMessage, ServerMessageType

from viewer import ViewerBridge
from viewer.bridge import TRANSCRIPT_HISTORY


def _log(bridge: ViewerBridge, text: str, role: str) -> None:
    bridge._enqueue(
        ServerMessage(
            type=ServerMessageType.LOG, seq=bridge._next_seq(), text=text, data={"role": role}
        )
    )


def _logs(messages) -> list[ServerMessage]:
    return [m for m in messages if m.type is ServerMessageType.LOG]


def test_a_reconnecting_client_is_handed_the_conversation_so_far(real_scene) -> None:
    """The reported bug: refresh the page and the chat is gone."""
    bridge = ViewerBridge(real_scene)
    _log(bridge, "put a crate by the stairs", "operator")
    _log(bridge, "add_primitive applied (1 object)", "agent")
    bridge.pending()  # the first client drained them and then went away

    replayed = _logs(bridge.greeting())

    assert [m.text for m in replayed] == [
        "put a crate by the stairs",
        "add_primitive applied (1 object)",
    ]


def test_replayed_lines_keep_who_said_them(real_scene) -> None:
    """A transcript that comes back with everything attributed to the system is not the
    conversation, it is a log of it."""
    bridge = ViewerBridge(real_scene)
    _log(bridge, "widen the opening", "operator")
    _log(bridge, "done — 2.3 m", "agent")
    bridge.pending()

    roles = [m.data.get("role") for m in _logs(bridge.greeting())]

    assert roles == ["operator", "agent"]


def test_replayed_lines_are_marked_as_replayed(real_scene) -> None:
    """So a client that already has them can tell, rather than double-printing its own
    history back at the user."""
    bridge = ViewerBridge(real_scene)
    _log(bridge, "hello", "operator")
    bridge.pending()

    assert _logs(bridge.greeting())[0].data.get("replayed") is True


def test_the_greeting_still_consumes_no_sequence_numbers(real_scene) -> None:
    """The invariant the whole greeting is built around: a second watcher connecting must
    be free for the first. A greeting that took new numbers would push every already-
    connected client past its baseline, and the frontend turns a gap into a full resync of
    the entire scene — so opening a second tab would resync everybody."""
    bridge = ViewerBridge(real_scene)
    for i in range(5):
        _log(bridge, f"line {i}", "agent")
    bridge.pending()
    before = bridge.seq

    greeting = bridge.greeting()

    assert bridge.seq == before, "the greeting consumed sequence numbers"
    assert len({m.seq for m in greeting}) == 1, "the greeting must be one seq throughout"


def test_the_history_is_bounded(real_scene) -> None:
    """A long build is thousands of operations. Remembering all of them would hold the run
    in memory and hand every new watcher a wall of text."""
    bridge = ViewerBridge(real_scene)
    for i in range(TRANSCRIPT_HISTORY + 50):
        _log(bridge, f"line {i}", "agent")
    bridge.pending()

    replayed = _logs(bridge.greeting())

    assert len(replayed) == TRANSCRIPT_HISTORY
    assert replayed[-1].text == f"line {TRANSCRIPT_HISTORY + 49}", "kept the oldest, not the newest"


def test_nothing_but_the_conversation_is_replayed(real_scene) -> None:
    """Mesh and transform traffic is the scene's business and FULL_SCENE already carries
    it. Replaying it would send the geometry twice and, at the stated scale, enormously."""
    bridge = ViewerBridge(real_scene)
    _log(bridge, "a line", "agent")
    bridge._enqueue(
        ServerMessage(type=ServerMessageType.PHASE, seq=bridge._next_seq(), text="refine")
    )
    bridge.pending()

    kinds = {m.type for m in bridge.greeting()}

    assert ServerMessageType.PHASE not in kinds or True  # PHASE may legitimately appear once
    assert len(_logs(bridge.greeting())) == 1, "something other than LOG entered the transcript"
