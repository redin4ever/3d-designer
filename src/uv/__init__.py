"""``uv`` — full UV unwrap and baked texture maps, with agent-overridable seams.

Research flagged this as the highest-risk area in v1: seams and stretching are where every
existing AI-3D tool fails most visibly. This file is a barrel: re-exports only, no logic —
see ``README.md`` for the public interface and invariants, ``CLAUDE.md`` for local
conventions.
"""

from .bake import bake, unwrap_and_bake
from .quality import uv_quality
from .results import BakeResult, UVResult
from .seams import suggest_seams
from .specs import UV_SPECS
from .unwrap import unwrap

__all__ = [
    "UVResult",
    "BakeResult",
    "suggest_seams",
    "unwrap",
    "bake",
    "uv_quality",
    "unwrap_and_bake",
    "UV_SPECS",
]
