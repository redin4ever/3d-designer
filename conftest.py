"""Root pytest configuration.

Two jobs:

1. Put ``src/`` on the path so modules import as ``contracts``, ``engine``, ``measure`` …
   rather than ``src.contracts``. Keeps every import statement in the codebase short and
   identical whether running under pytest or the installed package.
2. Provide the shared ``engine`` fixture. Every module's tests take a ``FakeEngine`` from
   here, so no module invents its own double and they cannot drift apart.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from testing import FakeEngine  # noqa: E402 — must follow the sys.path insert


def _bpy_available() -> bool:
    try:
        return importlib.util.find_spec("bpy") is not None
    except (ImportError, ValueError):
        return False


BPY_AVAILABLE = _bpy_available()


def pytest_collection_modifyitems(config, items):
    """Skip ``@pytest.mark.needs_blender`` tests when bpy is not importable.

    Skipping is deliberate rather than failing: only ``src/engine/`` needs a real bpy, and
    the rest of the suite must stay runnable on a machine without it. The count of skipped
    tests is reported so a green run cannot silently mean "the engine was never tested" —
    silence is never success (Rule 6).
    """
    if BPY_AVAILABLE:
        return
    skip = pytest.mark.skip(reason="bpy not importable — engine tests need a real Blender")
    for item in items:
        if "needs_blender" in item.keywords:
            item.add_marker(skip)


def pytest_report_header(config):
    return [
        f"bpy available: {BPY_AVAILABLE}",
        "engine tests run against real bpy" if BPY_AVAILABLE
        else "engine tests SKIPPED — decision layer still fully covered via FakeEngine",
    ]


@pytest.fixture
def engine() -> FakeEngine:
    """A clean in-memory engine. Fast enough to take per-test."""
    return FakeEngine()


@pytest.fixture
def engine_without_bake() -> FakeEngine:
    """An engine whose ``bake`` raises ``EngineUnavailable`` — the real behaviour when
    in-process bpy has no windowed context. The UV module must handle this path."""
    return FakeEngine(bake_supported=False)
