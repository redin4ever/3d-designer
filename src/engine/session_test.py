"""``create_engine`` — the factory's contract, provable without a Blender install.

These are deliberately *not* ``needs_blender``. ``BlenderEngine.__init__`` imports no bpy
(every method imports it lazily), so the composition root's one seam can be checked on any
machine — including the machines where ``blender_test.py`` skips wholesale and would
otherwise take this coverage with it.

What is pinned here is the **shape** of the factory, not what the engine does. That shape
changed at F-023: ``create_engine`` no longer takes ``prefer_subprocess``. The flag named a
``blender.exe`` subprocess fallback for capabilities in-process ``bpy`` was believed unable
to provide; Phase 4 measured this build and found in-process ``bpy`` *does* have windowed
context, so unwrap, bake and glTF export all run in-process and the fallback was never
built. A parameter that only ever raised is worse than no parameter: it reads, from the
outside, like a working part of the surface. The capability *check* stays — see
``surfacing.py``'s ``EngineUnavailable("bake")`` — because a future machine may genuinely
lack it. What went is the fallback that never existed.
"""

from __future__ import annotations

import inspect

import pytest

from contracts import EngineProtocol

from engine import BlenderEngine, create_engine


def test_create_engine_takes_no_backend_selection_argument() -> None:
    """The signature is the documentation. While ``prefer_subprocess`` sits in it, every
    reader — and ``docs/ARCHITECTURE.md`` — is entitled to believe a second backend exists."""
    assert list(inspect.signature(create_engine).parameters) == []


@pytest.mark.parametrize("call", [
    lambda: create_engine(prefer_subprocess=True),
    lambda: create_engine(prefer_subprocess=False),
])
def test_create_engine_rejects_the_removed_subprocess_flag(call) -> None:
    """A caller still passing the flag must be told, by name, that it is gone.

    ``TypeError`` and not a quiet default: accepting ``prefer_subprocess`` and ignoring it
    would hand back the in-process engine while the caller believes they asked for something
    else — the exact silent no-op the raising stub existed to prevent. Both values are
    checked because ``prefer_subprocess=False`` was the *documented normal call*, so it is
    the one most likely to still be written somewhere.
    """
    with pytest.raises(TypeError) as exc:
        call()
    assert "prefer_subprocess" in str(exc.value)


def test_create_engine_returns_the_in_process_backend() -> None:
    """There is one backend. The factory returns it, and it structurally satisfies the
    Protocol every other module is written against (ADR-008)."""
    eng = create_engine()
    assert isinstance(eng, BlenderEngine)
    assert isinstance(eng, EngineProtocol)
