"""Convert dataclasses, ``StrEnum`` members and tuples into plain JSON-serialisable
values, so every ``dispatch()`` result round-trips through ``json.dumps`` without a
custom encoder on the caller's side.

Nothing here computes anything yet — every function raises until the next pass replaces
the body (Rule 4 — tests come first). Not part of ``mcp``'s public barrel — exercised
transitively through ``dispatch()``.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

__all__ = ["to_jsonable"]


def to_jsonable(value: Any) -> Any:
    """Recursively convert ``value`` — a dataclass, ``Enum`` member, tuple/list/set, dict,
    or plain scalar — into something ``json.dumps`` accepts unmodified."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (tuple, list, set, frozenset)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value
