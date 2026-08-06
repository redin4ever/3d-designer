"""Pytest configuration local to ``src/engine/``.

Registers the ``slow`` marker. It lives here rather than in the root ``pyproject.toml``
because ``pyproject.toml`` is shared root config, main-agent-owned (Rule 5), and only this
module has a slow test to mark — ``addinivalue_line`` from a directory ``conftest.py`` is
the sanctioned way to register a marker for one package, and satisfies ``--strict-markers``
exactly as an ``ini`` entry would.

``slow`` composes with, rather than replaces, the module's ``needs_blender`` convention:
``scale_test.py`` carries both, so it is skipped outright without Blender and can be
deselected with ``-m "not slow"`` on a machine that has it.
"""

from __future__ import annotations


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "slow: takes seconds rather than milliseconds — a scale measurement, not a unit "
        'test. Deselect with -m "not slow".',
    )
