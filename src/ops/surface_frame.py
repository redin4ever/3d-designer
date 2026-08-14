"""Host-surface frames used by semantic surface-mounted operations."""

from __future__ import annotations

from dataclasses import dataclass

from contracts import EngineProtocol, Quat, Vec3

__all__ = ["SurfaceFrame", "roof_frame", "wall_frame"]


@dataclass(frozen=True, slots=True)
class SurfaceFrame:
    centre: Vec3
    horizontal: Vec3
    vertical: Vec3
    normal: Vec3
    horizontal_min: float
    horizontal_max: float
    vertical_min: float
    vertical_max: float

    @property
    def width(self) -> float:
        return self.horizontal_max - self.horizontal_min

    @property
    def height(self) -> float:
        return self.vertical_max - self.vertical_min

    def rotation(self) -> Quat:
        raise NotImplementedError("surface frame rotation is not implemented")


def roof_frame(engine: EngineProtocol, object_id: str) -> SurfaceFrame:
    raise NotImplementedError("roof surface detection is not implemented")


def wall_frame(engine: EngineProtocol, object_id: str, toward: Vec3) -> SurfaceFrame:
    raise NotImplementedError("wall surface detection is not implemented")
