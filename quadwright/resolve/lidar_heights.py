"""Measure real building heights from LIDAR roof returns (FR-20).

OSM rarely tags a building's height (on unc-charlotte, 276 of 286
buildings fell through to the 12m default), but the same cached USGS
LIDAR tiles that give us terrain (FR-10) also carry classification 6
("building") returns -- tens of points per square meter of roof. This
module turns those into one height per footprint, the same way the
Dutch national 3D building model (3D BAG) builds its block ("LoD1")
models:

- roof elevation  = 70th percentile of building points inside the footprint
- ground elevation = 5th percentile of ground points within 4m of it
- height_m         = roof - ground

Why percentiles instead of max/min: max would let one antenna, HVAC
unit, or stray return set the whole building's height, and a single
LoD1 box can't represent a tower anyway. The 70th percentile lands on
the main roof of a flat building with a small penthouse, and between
eave and ridge on a pitched roof. Likewise the 5th percentile of ground
ignores a few noisy low returns but still finds the building's lowest
ground contact -- the same reference OSM's `height` tag is measured from,
and the reference quadwright.mesh.terrain seats a building at.

This is plain measurement, not a learned model, so it fits ADR-0005's
rules-based-first approach.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import replace
from pathlib import Path

import laspy
import numpy as np
import pyproj
import shapely
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from quadwright.geo.footprints import utm_crs_for_bbox
from quadwright.model import Building
from quadwright.resolve.terrain import GROUND_CLASSIFICATION, _vertical_unit_to_meters

BUILDING_CLASSIFICATION = 6  # ASPRS LAS standard class for building returns

ROOF_PERCENTILE = 70
GROUND_PERCENTILE = 5
GROUND_RING_OUTER_M = 4.0
# Ground points hugging the wall line are the least trustworthy (roof
# overhangs, slight misregistration between OSM and LIDAR), so the ring
# starts a little way out from the footprint.
GROUND_RING_INNER_M = 0.5

MIN_ROOF_POINTS = 10
# A footprint needs at least this fraction of the campus's typical roof
# point density. A building finished after the scan has no roof points
# at all; a building *replaced* since the scan (new footprint over part
# of an old one) has some, but only where the old roof overlapped -- and
# its height would describe the old building. On unc-charlotte, measured
# footprints cluster at ~9 points/m^2 while the stale ones sit at 1-4.
MIN_RELATIVE_DENSITY = 0.5

# Sources that are estimates, not measurements: a LIDAR height replaces
# these. An explicit OSM `height` tag or a config override still wins.
_REPLACEABLE_SOURCES = ("levels", "default")


def measure_building_heights(
    lidar_paths: Sequence[str | Path],
    buildings: Iterable[Building],
    bbox: tuple[float, float, float, float],
) -> dict[str, float]:
    """Measure each building's height in meters from LIDAR, keyed by osm_id.

    Buildings with too few roof returns (see MIN_ROOF_POINTS and
    MIN_RELATIVE_DENSITY) or no nearby ground returns are left out of the
    result rather than guessed -- callers keep their existing height.
    """
    buildings = list(buildings)
    utm_crs = utm_crs_for_bbox(bbox)
    rings = {
        b.osm_id: b.footprint.buffer(GROUND_RING_OUTER_M).difference(
            b.footprint.buffer(GROUND_RING_INNER_M)
        )
        for b in buildings
    }

    roof_z: dict[str, list[np.ndarray]] = defaultdict(list)
    ground_z: dict[str, list[np.ndarray]] = defaultdict(list)
    # Reprojecting a few hundred footprints into a tile's CRS is far
    # cheaper than reprojecting its ~20 million points into ours, so the
    # point-in-polygon tests below happen in each tile's own coordinates.
    # Every tile in a project usually shares one CRS, so cache per CRS.
    reprojected: dict[str, dict[str, tuple[BaseGeometry, BaseGeometry]]] = {}

    for path in lidar_paths:
        las = laspy.read(str(path))
        tile_crs = las.header.parse_crs()
        z_to_m = _vertical_unit_to_meters(tile_crs)
        crs_key = tile_crs.to_wkt()
        if crs_key not in reprojected:
            to_tile = pyproj.Transformer.from_crs(utm_crs, tile_crs, always_xy=True).transform
            reprojected[crs_key] = {
                b.osm_id: (transform(to_tile, b.footprint), transform(to_tile, rings[b.osm_id]))
                for b in buildings
            }

        classification = np.asarray(las.classification)
        roofs = _PointsSortedByX(las, classification == BUILDING_CLASSIFICATION, z_to_m)
        grounds = _PointsSortedByX(las, classification == GROUND_CLASSIFICATION, z_to_m)
        for osm_id, (footprint, ring) in reprojected[crs_key].items():
            roof_z[osm_id].append(roofs.z_within(footprint))
            ground_z[osm_id].append(grounds.z_within(ring))

    roofs_by_id = {b.osm_id: _concat(roof_z[b.osm_id]) for b in buildings}
    densities = {b.osm_id: len(roofs_by_id[b.osm_id]) / b.footprint.area for b in buildings}
    covered = [densities[i] for i, z in roofs_by_id.items() if len(z) >= MIN_ROOF_POINTS]
    if not covered:
        return {}
    # "Typical" density comes from this campus's own data rather than a
    # fixed points/m^2 number, since USGS projects range from ~2 to 50+.
    typical_density = float(np.median(covered))

    heights: dict[str, float] = {}
    for b in buildings:
        roof = roofs_by_id[b.osm_id]
        ground = _concat(ground_z[b.osm_id])
        if len(roof) < MIN_ROOF_POINTS or len(ground) == 0:
            continue
        if densities[b.osm_id] < MIN_RELATIVE_DENSITY * typical_density:
            continue
        height_m = float(
            np.percentile(roof, ROOF_PERCENTILE) - np.percentile(ground, GROUND_PERCENTILE)
        )
        if height_m > 0:
            heights[b.osm_id] = height_m
    return heights


def apply_lidar_heights(
    buildings: Iterable[Building], heights_m: dict[str, float]
) -> list[Building]:
    """Swap in measured heights for buildings whose height was only an estimate.

    Precedence (most trusted first): config override > OSM `height` tag >
    LIDAR > `building:levels` x meters_per_level > campus default. A
    floor count is a guess at storey height (unc-charlotte's 12-storey
    dorms come out at 42m that way, vs. ~35m measured), so a real
    measurement beats it -- but an explicit height someone typed in, in
    OSM or the campus config, is a deliberate choice and is kept.
    """
    return [
        replace(b, height_m=heights_m[b.osm_id], height_source="lidar")
        if b.osm_id in heights_m and b.height_source in _REPLACEABLE_SOURCES
        else b
        for b in buildings
    ]


class _PointsSortedByX:
    """One classification's points from a tile, sorted by x for fast window queries.

    A footprint's bounding box covers a thin vertical strip of the tile,
    so a binary search on sorted x narrows millions of points down to
    that strip before any (slower) point-in-polygon test runs.
    """

    def __init__(self, las: laspy.LasData, mask: np.ndarray, z_to_m: float):
        x = np.asarray(las.x)[mask]
        order = np.argsort(x)
        self._x = x[order]
        self._y = np.asarray(las.y)[mask][order]
        self._z_m = np.asarray(las.z)[mask][order] * z_to_m

    def z_within(self, polygon: BaseGeometry) -> np.ndarray:
        """Elevations (meters) of every point inside `polygon`."""
        min_x, min_y, max_x, max_y = polygon.bounds
        start = int(np.searchsorted(self._x, min_x, side="left"))
        stop = int(np.searchsorted(self._x, max_x, side="right"))
        x, y, z = self._x[start:stop], self._y[start:stop], self._z_m[start:stop]
        in_box = (y >= min_y) & (y <= max_y)
        x, y, z = x[in_box], y[in_box], z[in_box]
        return z[shapely.contains_xy(polygon, x, y)]


def _concat(arrays: list[np.ndarray]) -> np.ndarray:
    return np.concatenate(arrays) if arrays else np.array([])
