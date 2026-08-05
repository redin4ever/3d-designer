"""``downscale_image`` — shrink an oversized render before it goes back over MCP
(ADR-003).

Several MCP clients pass ``ImageContent`` payloads through to the model as literal text
instead of native image tokens — 15-25k tokens for something that should cost ~1,600.
Downscaling to at most ``max_edge`` pixels on the long side before the image ever leaves
this process is what keeps a multi-turn "make a change, look at it, adjust" loop
affordable rather than something an agent avoids.

Nothing here computes anything yet — every function raises until the next pass replaces
the body (Rule 4 — tests come first).
"""

from __future__ import annotations

__all__ = ["downscale_image"]

#: Operates on binary PPM (``P6``) bytes — width, height and pixel data self-described in
#: one small header — rather than a real PNG/JPEG codec. This codebase has no Pillow
#: dependency (see ``CLAUDE.md``); the engine boundary that actually produces a render is
#: free to encode PPM before handing bytes here, or this function's format support can
#: grow the day a real codec dependency is decided at a gate.


def _parse_ppm(data: bytes) -> tuple[int, int, int, bytes]:
    if not data.startswith(b"P6"):
        raise ValueError("downscale_image: only binary PPM ('P6') image bytes are supported")

    fields: list[int] = []
    pos = 2
    length = len(data)
    while len(fields) < 3:
        while pos < length and data[pos : pos + 1].isspace():
            pos += 1
        if pos < length and data[pos : pos + 1] == b"#":
            while pos < length and data[pos : pos + 1] != b"\n":
                pos += 1
            continue
        start = pos
        while pos < length and not data[pos : pos + 1].isspace():
            pos += 1
        fields.append(int(data[start:pos]))
    pos += 1  # the single whitespace byte the PPM header requires after maxval
    width, height, maxval = fields
    return width, height, maxval, data[pos:]


def _resize_nearest(
    pixels: bytes, width: int, height: int, new_width: int, new_height: int
) -> bytes:
    out = bytearray(new_width * new_height * 3)
    for ny in range(new_height):
        sy = min(height - 1, (ny * height) // new_height)
        src_row = sy * width * 3
        dst_row = ny * new_width * 3
        for nx in range(new_width):
            sx = min(width - 1, (nx * width) // new_width)
            src = src_row + sx * 3
            dst = dst_row + nx * 3
            out[dst : dst + 3] = pixels[src : src + 3]
    return bytes(out)


def downscale_image(data: bytes, *, max_edge: int = 1024) -> bytes:
    """Shrink ``data`` so neither dimension exceeds ``max_edge``, preserving aspect
    ratio. An image already within bounds is returned unchanged — this is a cost control,
    not a normalisation pass, and there is no reason to spend cycles re-encoding an image
    that already costs what it should."""
    width, height, maxval, pixels = _parse_ppm(data)
    longest = max(width, height)
    if longest <= max_edge:
        return data

    scale = max_edge / longest
    new_width = max(1, round(width * scale))
    new_height = max(1, round(height * scale))
    resized = _resize_nearest(pixels, width, height, new_width, new_height)
    header = f"P6\n{new_width} {new_height}\n{maxval}\n".encode("ascii")
    return header + resized
