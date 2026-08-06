"""``raw`` — unrestricted Python execution against the live engine (ADR-009).

The de-facto standard agent-Blender bridge exposes exactly this capability and carries an
open CVSS 9.0 remote-code-execution issue as a result. This module exposes the same thing,
by the user's explicit choice, on the explicit understanding that the tool is private,
local, and single-user. This module's job is not to narrow that choice with a sandbox, an
allowlist, or an AST check — it is to be honest about what the capability does: report
what a script actually changed, never leak a bare traceback, and say plainly, once, what
the risk is.

Barrel: re-exports only. See ``README.md`` for the interface and its invariants, and
``docs/adr/ADR-009-unrestricted-execution-local-trust.md`` for the decision this module
implements.
"""

from .executor import RAW_TOOL_SPEC, RawResult, describe_risk, execute

__all__ = ["RawResult", "execute", "describe_risk", "RAW_TOOL_SPEC"]
