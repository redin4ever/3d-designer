"""MCP-facing import specs, kept handler-less for operation-log dispatch.

Main registry wiring should add ``IMPORT_TOOL_SPECS`` to its source list and add
``import_model_file`` to the operation handler registry. This module deliberately attaches
no direct handler: import changes scene geometry and must go through the single writer,
history, and opaque snapshot barrier.
"""

from __future__ import annotations

from importing import IMPORT_SPECS

__all__ = ["IMPORT_TOOL_SPECS"]

IMPORT_TOOL_SPECS = IMPORT_SPECS
