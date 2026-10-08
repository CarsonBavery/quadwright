"""Campus configuration: the single YAML file that drives every build (FR-01).

Every model uses ``extra="forbid"`` so a typo in a YAML key fails loudly
instead of being silently ignored.
"""

from __future__ import annotations

from datetime import date
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
    boundary_query: str | None = Field(
        default=None,
        description=(
            "Nominatim place name (e.g. 'UNC Charlotte') to fetch the campus's real "
            "OSM boundary polygon. bbox is a rectangle and always includes nearby "
            "off-campus buildings (stores, off-campus housing); when set, only "
            "buildings inside this polygon are kept (FR-09). Leave unset for a "
            "synthetic campus with no real-world OSM entity -- then bbox alone decides."
        ),
    )
    include_outside_boundary: list[str] = Field(
        default_factory=list,
        description=(
            "Building names to always include even though they fall outside "
            "boundary_query's polygon -- for real but technically-off-campus places "
            "worth keeping (a historic building OSM doesn't tag as historic, a "
            "campus-run service just across the boundary line). Buildings tagged "
            "historic=* in OSM are included automatically and don't need listing here."
        ),
    )
    lidar_project: str | None = Field(
        default=None,
        description=(
            "USGS 3DEP LIDAR project path (e.g. "
            "'NC_Phase_4_CentralWestNC_GEIGER_A16/NC_Phase4_Mecklenburg_2016'), used to "
            "fetch real ground-elevation point cloud tiles for a contoured terrain base "
            "plate (FR-10) instead of a flat slab. Find it by browsing "
            "prd-tnm.s3.amazonaws.com (?list-type=2&prefix=StagedProducts/Elevation/LPC/"
            "Projects/) for a project covering the campus -- there's no reachable bbox lookup "
            "API, so this is a one-time manual find per campus. Leave unset for a flat "
            "base plate (today's behavior)."
        ),
    )

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


class SpeciesConfig(_Strict):
    """Fit data for one wood species, measured from its tolerance coupon (FR-17)."""

    species: str
    clearance_mm: float | None = Field(
        default=None,
        description="Tenon-to-pocket gap felt as snug-but-removable. null until the "
        "coupon (`quadwright coupon`) has been cut and test-fit by hand.",
    )
    tested_on: date | None = None
    notes: str = ""


def load_species_config(species: str, species_dir: str | Path = "configs/species") -> SpeciesConfig:
    """Read and validate `<species_dir>/<species>.yaml`. Raises pydantic.ValidationError."""
    path = Path(species_dir) / f"{species}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")
    return SpeciesConfig.model_validate(data)
