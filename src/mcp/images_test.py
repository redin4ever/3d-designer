"""Tests for ``downscale_image`` — token-cost control for MCP image responses (ADR-003).

A 1000x1000 render costs about 1,300 tokens; a 2000x2000 costs about 5,300, and some MCP
clients pass image bytes through as text at 15-25k tokens. Downscaling before return is
the difference between a usable feedback loop and an unusable one.

Operates on binary PPM (``P6``) bytes — this codebase has no Pillow/PNG-codec dependency
(see ``CLAUDE.md``); see ``images.py``'s module docstring for why.

``downscale_image`` is a throwing stub as of this file (Rule 4 — tests come first); every
test below is expected to fail with ``NotImplementedError`` until the next pass implements
it.
"""

from __future__ import annotations

from mcp import downscale_image


def _ppm(width: int, height: int, color: tuple[int, int, int] = (120, 40, 200)) -> bytes:
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    return header + bytes(color) * (width * height)


def _split_header(data: bytes) -> tuple[list[int], bytes]:
    """Walk the three whitespace-delimited header fields (width, height, maxval) byte by
    byte rather than string-searching for a literal ``"255\\n"`` — a fixture's pixel bytes
    could coincidentally contain that sequence, and a real parser has to walk the header
    the same way regardless."""
    assert data.startswith(b"P6"), "result is not a P6 PPM image"
    pos = 2
    fields: list[int] = []
    while len(fields) < 3:
        while data[pos : pos + 1].isspace():
            pos += 1
        start = pos
        while not data[pos : pos + 1].isspace():
            pos += 1
        fields.append(int(data[start:pos]))
    return fields, data[pos + 1 :]


def _dimensions(data: bytes) -> tuple[int, int]:
    (width, height, _maxval), _pixels = _split_header(data)
    return width, height


def _pixel_bytes(data: bytes) -> bytes:
    _fields, pixels = _split_header(data)
    return pixels


def test_a_large_image_is_reduced_to_within_max_edge() -> None:
    data = _ppm(2000, 1000)

    result = downscale_image(data, max_edge=500)

    width, height = _dimensions(result)
    assert max(width, height) <= 500
    assert width == 2 * height  # aspect ratio preserved (source is 2:1)


def test_a_small_image_is_left_alone() -> None:
    data = _ppm(200, 100)

    result = downscale_image(data, max_edge=1024)

    assert result == data


def test_an_image_exactly_at_max_edge_is_left_alone() -> None:
    data = _ppm(1024, 512)

    result = downscale_image(data, max_edge=1024)

    assert result == data


def test_downscaled_bytes_are_a_well_formed_image_at_the_new_dimensions() -> None:
    data = _ppm(2000, 1000, color=(9, 200, 30))

    result = downscale_image(data, max_edge=250)

    width, height = _dimensions(result)
    assert (width, height) == (250, 125)
    assert len(_pixel_bytes(result)) == width * height * 3


def test_a_tall_image_is_downscaled_by_its_longest_edge() -> None:
    data = _ppm(300, 3000)

    result = downscale_image(data, max_edge=300)

    width, height = _dimensions(result)
    assert height == 300
    assert width == 30
