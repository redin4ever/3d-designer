"""Minimal, JSON-schema-shaped validation for MCP tool params (Gate A 4.2).

Not a general JSON Schema implementation — just what every ``ToolSpec.input_schema`` in
this codebase actually uses: ``required``, ``properties[].type``, ``properties[].enum``,
and ``additionalProperties``. An agent handed a bare traceback loops on the same failing
call; one told which parameter is wrong, and given a suggestion, fixes it first try.

Nothing here computes anything yet — every function raises until the next pass replaces
the body (Rule 4 — tests come first). Not part of ``mcp``'s public barrel — exercised
transitively through ``dispatch()``, same as ``orchestration/_tool_registry.py`` is
exercised only through ``tools_for``.
"""

from __future__ import annotations

from typing import Any, Callable

from contracts import ToolError

__all__ = ["validate_params"]

_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "array": lambda v: isinstance(v, (list, tuple)),
    "object": lambda v: isinstance(v, dict),
}


def validate_params(tool_name: str, schema: dict[str, Any], params: dict[str, Any]) -> None:
    """Raise :class:`contracts.ToolError` on the first violation found: a missing required
    parameter first (named, with a suggestion), then an unknown parameter when the schema
    forbids extras, then a wrong type, then a value outside a declared ``enum``.

    A missing parameter is reported before anything else about it — there is nothing more
    useful to say about a value that was never given.
    """
    properties: dict[str, Any] = schema.get("properties", {})
    required: list[str] = list(schema.get("required", ()))

    for key in required:
        if key not in params:
            raise ToolError(
                rule="mcp.missing_parameter",
                detail=f"{tool_name!r} call is missing required parameter {key!r}",
                suggestion=f"include {key!r} in params — required by {tool_name}'s schema",
            )

    if schema.get("additionalProperties") is False:
        unknown = sorted(set(params) - set(properties))
        if unknown:
            raise ToolError(
                rule="mcp.unknown_parameter",
                detail=f"{tool_name!r} does not accept parameter {unknown[0]!r}",
                suggestion=f"remove {unknown[0]!r}; valid parameters are {sorted(properties)}",
            )

    for key, value in params.items():
        prop_schema = properties.get(key)
        if prop_schema is None:
            continue
        _check_type(tool_name, key, prop_schema, value)
        _check_enum(tool_name, key, prop_schema, value)


def _check_type(tool_name: str, key: str, prop_schema: dict[str, Any], value: Any) -> None:
    expected = prop_schema.get("type")
    check = _TYPE_CHECKS.get(expected)
    if check is not None and not check(value):
        raise ToolError(
            rule="mcp.invalid_parameter_type",
            detail=(
                f"{tool_name!r} parameter {key!r} must be of type {expected!r}, got "
                f"{type(value).__name__}"
            ),
            suggestion=f"pass a {expected} value for {key!r}",
        )


def _check_enum(tool_name: str, key: str, prop_schema: dict[str, Any], value: Any) -> None:
    enum = prop_schema.get("enum")
    if enum is not None and value not in enum:
        raise ToolError(
            rule="mcp.invalid_parameter_value",
            detail=f"{tool_name!r} parameter {key!r} must be one of {enum}, got {value!r}",
            suggestion=f"choose one of {enum} for {key!r}",
        )
