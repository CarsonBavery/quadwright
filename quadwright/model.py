"""Domain model shared by every pipeline stage (see handbook: Architecture > Domain model).

Geometry fields hold shapely objects at runtime; they are typed loosely here so
this module imports instantly and has no heavy dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Literal

HeightSource = Literal["tag", "levels", "lidar", "override", "default"]
RoofShape = Literal["flat", "gabled", "hipped", "dome", "other"]


class Tier(IntEnum):
    MERGE = 0  # too small to be its own part
    BLOCK = 1  # top setup only
    ROTATED = 2  # top plus side setups
    HERO = 3  # hand-tuned landmark


@dataclass(frozen=True)
class Building:
    """One normalized building from the data sources (meters, local UTM CRS)."""

    osm_id: str
    footprint: Any  # shapely Polygon or MultiPolygon
    name: str | None = None
    height_m: float | None = None
    height_source: HeightSource | None = None
    roof_shape: RoofShape = "flat"
    roof_source: Literal["tag", "rules", "ml", "default"] = "default"


@dataclass(frozen=True)
class Joint:
    """How a Part attaches to the base plate."""

    kind: Literal["tenon", "dowels"]
    clearance_mm: float
    tenon_shape: Any = None  # shapely Polygon, part-local mm
    dowel_points: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class Setup:
    """One way the blank sits in the corner-stop jig."""

    index: int
    face_up: Literal["top", "north", "south", "east", "west"]
    mesh_path: str | None = None


@dataclass(frozen=True)
class Part:
    """One physical piece of wood (one or more merged buildings), part-local mm."""

    id: str
    building_ids: tuple[str, ...]
    footprint_local: Any  # shapely Polygon
    height_mm: float
    tier: Tier
    position_on_base: tuple[float, float]
    rotation_deg: float = 0.0
    species: str = "maple"
    grain_axis: Literal["x", "y"] = "x"
    joint: Joint | None = None
    setups: tuple[Setup, ...] = ()


@dataclass
class Kit:
    """The complete output of one build; serialized to data/interim/kit.json."""

    campus: str
    base_plate: Any  # shapely Polygon, model mm
    parts: list[Part] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
