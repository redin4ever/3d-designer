"""The Python and JavaScript halves of the wire protocol must agree.

`src/viewer/` and `frontend/` were built independently against `contracts/wire.py`, in two
different languages, by two different agents. Nothing in either suite can catch a
disagreement between them: the Python side tests that it emits well-formed messages, the JS
side tests that it parses well-formed messages, and both pass while each has a different
idea of what "well-formed" means.

The failure mode is the worst kind — a permanently blank viewport with no error anywhere.
The socket connects, messages arrive, the client silently ignores every one of them because
the discriminator string does not match, and nothing logs a thing.

These tests read the JavaScript as text and compare it against the frozen Python contract.
That is deliberately crude, and it is the only thing that can see both sides at once
without a browser and a running server.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

import pytest

from contracts import (
    ClientMessageType,
    MeshPayload,
    ServerMessage,
    ServerMessageType,
    TransformPayload,
)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _js_enum(name: str) -> set[str]:
    """Pull the string values out of a frozen JS enum object, wherever it is declared.

    Searches every file rather than taking a filename, so moving a constant between
    modules — an ordinary refactor — does not turn this into a false alarm about the
    protocol.
    """
    for path in sorted(FRONTEND.glob("*.js")):
        match = re.search(
            rf"{name}\s*=\s*Object\.freeze\(\{{(.*?)\}}\)",
            path.read_text(encoding="utf-8"),
            re.S,
        )
        if match:
            return set(re.findall(r"'([^']+)'", match.group(1)))
    raise AssertionError(f"could not find {name} anywhere in frontend/src/")


def test_server_message_types_agree_across_the_two_languages() -> None:
    """A type the server sends and the client does not know is silently dropped — the
    viewport stops updating and nothing anywhere reports why."""
    python_side = {m.value for m in ServerMessageType}
    js_side = _js_enum("ServerMessageType")

    assert python_side - js_side == set(), (
        f"server sends these and the browser ignores them: {sorted(python_side - js_side)}"
    )
    assert js_side - python_side == set(), (
        f"browser waits for these and the server never sends them: {sorted(js_side - python_side)}"
    )


def test_client_message_types_agree_across_the_two_languages() -> None:
    """A control the browser sends that the server does not recognise means the operator
    presses pause and nothing happens."""
    python_side = {m.value for m in ClientMessageType}
    js_side = _js_enum("ClientMessageType")

    assert python_side - js_side == set(), (
        f"server accepts these and the browser never sends them: {sorted(python_side - js_side)}"
    )
    assert js_side - python_side == set(), (
        f"browser sends these and the server rejects them: {sorted(js_side - python_side)}"
    )


def test_every_field_the_browser_reads_exists_on_the_python_message() -> None:
    """A renamed field is invisible until runtime, where it reads as `undefined` and the
    client renders nothing rather than raising."""
    fields = set(asdict(ServerMessage(type=ServerMessageType.LOG)))
    read_by_js: set[str] = set()
    for path in FRONTEND.glob("*.js"):
        source = path.read_text(encoding="utf-8")
        read_by_js |= set(re.findall(r"\bmessage\.([a-z_]+)\b", source))
        read_by_js |= set(re.findall(r"\bmsg\.([a-z_]+)\b", source))

    unknown = read_by_js - fields
    assert unknown == set(), (
        f"the browser reads fields that do not exist on ServerMessage: {sorted(unknown)}"
    )


def test_a_real_message_survives_the_actual_json_encoding() -> None:
    """`json.dumps(asdict(...))` is what the server really does. StrEnum members have to
    come out as plain strings and tuples as arrays, or the browser's `===` comparison
    against its own string constants never matches — and it fails silently, per message,
    forever."""
    message = ServerMessage(
        type=ServerMessageType.MESH_UPSERT,
        seq=7,
        meshes=(
            MeshPayload(
                object_id="post_001",
                positions=[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                indices=[0, 1, 2],
                materials=("metal",),
                triangle_count=1,
            ),
        ),
        transforms=(
            TransformPayload(
                object_id="post_001",
                position=(1.0, 2.0, 3.0),
                quaternion=(0.0, 0.0, 0.0, 1.0),
            ),
        ),
        object_ids=("post_001",),
    )

    decoded = json.loads(json.dumps(asdict(message), default=str))

    assert decoded["type"] == "mesh_upsert", "the discriminator did not survive as a string"
    assert isinstance(decoded["meshes"], list), "tuples must arrive as JSON arrays"
    assert decoded["meshes"][0]["positions"] == [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    assert decoded["transforms"][0]["quaternion"] == [0.0, 0.0, 0.0, 1.0], (
        "quaternion must be x,y,z,w for three.js — converted once, at this boundary"
    )
    assert decoded["seq"] == 7


def test_the_browser_never_hardcodes_a_colour() -> None:
    """`tokens.css` is generated from DESIGN.md. A raw hex anywhere else means the design
    system is decoration — the token file can be regenerated and the interface will not
    change with it."""
    offenders = []
    for path in FRONTEND.glob("*"):
        if path.name == "tokens.css" or path.is_dir():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"#[0-9a-fA-F]{6}\b", line) and "//" not in line.split("#")[0][-3:]:
                offenders.append(f"{path.name}:{n}: {line.strip()[:70]}")
    assert offenders == [], "raw hex outside tokens.css:\n" + "\n".join(offenders)


@pytest.mark.parametrize("required", ["--canvas", "--surface-1", "--ink", "--accent"])
def test_the_generated_token_file_carries_the_semantic_names(required: str) -> None:
    """Components must never know the brand. If a component reaches for
    `--linear-lavender` instead of `--accent`, swapping the design system means editing
    every component rather than one file."""
    tokens = (FRONTEND / "tokens.css").read_text(encoding="utf-8")
    assert required in tokens, f"{required} missing from the generated token file"
