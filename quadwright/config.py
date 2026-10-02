"""Campus configuration: the single YAML file that drives every build (FR-01).

Every model uses ``extra="forbid"`` so a typo in a YAML key fails loudly
instead of being silently ignored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OutputKind = Literal["part_stl", "base_stl", "heightmap", "setup_sheets", "tier_report"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CampusArea(_Strict):
    """Where the campus is: a name plus a WGS84 bounding box."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", description="URL-safe slug")
    bbox: tuple[float, float, float, float] = Field(description="west, south, east, north")

    @field_validator("bbox")
    @classmethod
    def _check_bbox(cls, v: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        west, south, east, north = v
        if not (-180 <= west < east <= 180):
            raise ValueError("bbox needs -180 <= west < east <= 180")
        if not (-90 <= south < north <= 90):
            raise ValueError("bbox needs -90 <= south < north <= 90")
        return v


class Scale(_Strict):
    """Physical size of the model. Set exactly one of target_size_mm or ratio."""

    target_size_mm: tuple[float, float] | None = None
    ratio: float | None = Field(default=None, gt=0, description="e.g. 2500 means 1:2500")
    vertical_exaggeration: float = Field(default=1.0, gt=0, le=5)

    @model_validator(mode="after")
    def _exactly_one(self) -> Scale:
        if (self.target_size_mm is None) == (self.ratio is None):
            raise ValueError("set exactly one of scale.target_size_mm or scale.ratio")
        if self.target_size_mm is not None and min(self.target_size_mm) <= 0:
            raise ValueError("scale.target_size_mm values must be positive")
        return self


class Tool(_Strict):
    diameter_mm: float = Field(gt=0, le=25)
    type: Literal["flat_end_mill", "ball_end_mill", "v_bit"] = "flat_end_mill"

    @property
    def radius_mm(self) -> float:
        return self.diameter_mm / 2


class Materials(_Strict):
    base: str
    buildings: str


class Heights(_Strict):
    default_m: float = Field(default=12.0, gt=0)
    meters_per_level: float = Field(default=3.5, gt=0)
    overrides: dict[str, float] = Field(default_factory=dict)


class Tiers(_Strict):
    merge_below_tool_diameters: float = Field(default=3, gt=0)
    rotate_above_tool_diameters: float = Field(default=20, gt=0)
    overrides: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> Tiers:
        if self.merge_below_tool_diameters >= self.rotate_above_tool_diameters:
            raise ValueError("tiers.merge_below must be smaller than tiers.rotate_above")
        bad = {k: v for k, v in self.overrides.items() if v not in (0, 1, 2, 3)}
        if bad:
            raise ValueError(f"tier overrides must be 0-3, got {bad}")
        return self


class Roofs(_Strict):
    engine: Literal["rules", "ml"] = "rules"


class CampusConfig(_Strict):
    """The full, validated contents of one campus YAML file."""

    campus: CampusArea
    scale: Scale
    tool: Tool
    materials: Materials
    heights: Heights = Field(default_factory=Heights)
    tiers: Tiers = Field(default_factory=Tiers)
    roofs: Roofs = Field(default_factory=Roofs)
    outputs: list[OutputKind] = Field(default_factory=lambda: ["part_stl", "base_stl"])


def load_config(path: str | Path) -> CampusConfig:
    """Read and validate a campus YAML file. Raises pydantic.ValidationError on bad input."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")
    return CampusConfig.model_validate(data)
