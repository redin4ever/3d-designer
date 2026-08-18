"""Explicit legal intersections introduced by semantic construction operations."""

from __future__ import annotations

import math
from typing import Any

from contracts import JoineryIntent

__all__ = ["joinery_for"]


def joinery_for(kind: str, params: dict[str, Any]) -> tuple[JoineryIntent, ...]:
    """The declared support/cover overlaps for one operation, never inferred from meshes."""
    prefix = params.get("object_id", "")
    if kind == "add_impact_head":
        intents = [
            JoineryIntent(
                object_id=f"{prefix}_shoulder_{side}",
                into_object_id=f"{prefix}_body",
                depth=params["socket_depth"],
                axis="x",
                reason=f"{side} strike shoulder intentionally sockets into the load-bearing body",
            )
            for side in ("left", "right")
        ]
        intents.extend(
            JoineryIntent(
                object_id=f"{prefix}_striker_{side}",
                into_object_id=f"{prefix}_face_{side}",
                depth=params["striker_socket_depth"],
                axis="x",
                reason=f"{side} replaceable striker intentionally sockets into the face plate",
            )
            for side in ("left", "right")
        )
        intents.extend(
            JoineryIntent(
                object_id=f"{prefix}_rim_{side}",
                into_object_id=f"{prefix}_face_{side}",
                depth=params["rim_depth"] / 2.0,
                axis="x",
                reason=f"{side} retaining rim intentionally seats into the striking face",
            )
            for side in ("left", "right")
        )
        intents.extend((
            JoineryIntent(
                object_id=f"{prefix}_handle_socket",
                into_object_id=f"{prefix}_body",
                depth=params["handle_socket_depth"],
                axis="z",
                reason="handle socket intentionally penetrates the head body to transfer impact load",
            ),
            JoineryIntent(
                object_id=f"{prefix}_handle_collar",
                into_object_id=f"{prefix}_handle_socket",
                depth=params["handle_collar_depth"],
                axis="z",
                reason="handle collar intentionally wraps the exposed socket",
            ),
        ))
        return tuple(intents)

    if kind == "add_gable_roof":
        angle = math.radians(params["pitch_degrees"])
        miter_depth = params["trim_depth"] / (2.0 * math.cos(angle))
        insertion = max(
            0.0,
            params["thickness"] / 2.0 + params["trim_depth"] - miter_depth,
        )
        intents = [
            JoineryIntent(
                object_id=f"{prefix}_ridge_cap",
                into_object_id=f"{prefix}_slope_{side}",
                depth=insertion,
                axis="z",
                reason="ridge cap intentionally overlaps the roof panel to cover the seam",
            )
            for side in ("neg", "pos")
        ]
        intents.extend(
            JoineryIntent(
                object_id=f"{prefix}_gable_{gable}_trim",
                into_object_id=f"{prefix}_eave_{eave}_fascia",
                depth=params["trim_depth"],
                axis="z",
                reason=(
                    "rake and fascia intentionally share a compound-miter face; "
                    "their angled bounding boxes overlap"
                ),
            )
            for gable in ("neg", "pos")
            for eave in ("neg", "pos")
        )
        return tuple(intents)

    if kind == "add_chimney":
        return (
            JoineryIntent(
                object_id=f"{prefix}_flashing",
                into_object_id=f"{prefix}_shaft",
                depth=params["flashing_height"],
                axis="z",
                reason="roof flashing intentionally collars the masonry shaft",
            ),
        )

    if kind == "add_staircase_to_landing":
        depth = params["tread_thickness"]
        return tuple(
            JoineryIntent(
                object_id=f"{prefix}_stringer_{side}",
                into_object_id=f"{prefix}_tread_{index:03d}",
                depth=depth,
                axis="z",
                reason="stringer intentionally supports the tread from below",
            )
            for side in ("left", "right")
            for index in range(params["treads"])
        )
    return ()
