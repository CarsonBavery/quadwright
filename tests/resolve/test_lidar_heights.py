"""FR-20: measure building heights from LIDAR building + ground returns."""

from pathlib import Path

import laspy
import numpy as np
import pyproj
import pytest
import shapely
from shapely.geometry import Polygon, box

from quadwright.geo.footprints import utm_crs_for_bbox
from quadwright.model import Building
from quadwright.resolve.lidar_heights import apply_lidar_heights, measure_building_heights

EXAMPLE_BBOX = (-80.000, 35.000, -79.990, 35.008)  # same campus as tests/resolve/test_terrain.py
GROUND_M = 200.0

# A 20x20m footprint somewhere inside EXAMPLE_BBOX, in the same local UTM
# meters buildings use. Writing the fixture tiles directly in that UTM CRS
# keeps them simple: no reprojection, and Z is already meters.
_x0, _y0 = pyproj.Transformer.from_crs(
    "EPSG:4326", utm_crs_for_bbox(EXAMPLE_BBOX), always_xy=True
).transform(-79.995, 35.004)
FOOTPRINT = box(_x0, _y0, _x0 + 20, _y0 + 20)


def _write_las(path: Path, xs, ys, zs, classes) -> Path:
    header = laspy.LasHeader(point_format=3, version="1.4")
    header.add_crs(pyproj.CRS.from_proj4(utm_crs_for_bbox(EXAMPLE_BBOX)))
    header.offsets = [float(np.min(xs)), float(np.min(ys)), 0.0]
    header.scales = [0.001, 0.001, 0.001]
    las = laspy.LasData(header)
    las.x, las.y, las.z = np.asarray(xs), np.asarray(ys), np.asarray(zs)
    las.classification = np.asarray(classes, dtype=np.uint8)
    las.write(str(path))
    return path


def _grid_points(polygon: Polygon, spacing_m: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Every grid point (at `spacing_m`) that falls strictly inside `polygon`."""
    min_x, min_y, max_x, max_y = polygon.bounds
    gx, gy = np.meshgrid(
        np.arange(min_x + spacing_m / 2, max_x, spacing_m),
        np.arange(min_y + spacing_m / 2, max_y, spacing_m),
    )
    gx, gy = gx.ravel(), gy.ravel()
    inside = shapely.contains_xy(polygon, gx, gy)
    return gx[inside], gy[inside]


def _scan(footprint: Polygon, roof_zs) -> tuple[list, list, list, list]:
    """A roof over `footprint` (z per point from `roof_zs(n)`) plus flat ground around it."""
    rx, ry = _grid_points(footprint)
    gx, gy = _grid_points(footprint.buffer(6).difference(footprint))
    xs = list(rx) + list(gx)
    ys = list(ry) + list(gy)
    zs = list(roof_zs(len(rx))) + [GROUND_M] * len(gx)
    classes = [6] * len(rx) + [2] * len(gx)
    return xs, ys, zs, classes


def _building(osm_id: str, footprint: Polygon, source: str = "default") -> Building:
    return Building(osm_id=osm_id, footprint=footprint, height_m=12.0, height_source=source)


def test_fr20_measures_roof_height_above_the_surrounding_ground(tmp_path):
    tile = _write_las(tmp_path / "t.las", *_scan(FOOTPRINT, lambda n: np.full(n, GROUND_M + 15)))

    heights = measure_building_heights([tile], [_building("a", FOOTPRINT)], EXAMPLE_BBOX)

    assert heights["a"] == pytest.approx(15.0, abs=0.01)


def test_fr20_a_small_rooftop_feature_does_not_set_the_height(tmp_path):
    # 10% of the roof is a 25m mechanical penthouse/antenna; the 70th
    # percentile still lands on the 15m main roof (max would say 25).
    def roof(n):
        zs = np.full(n, GROUND_M + 15)
        zs[: n // 10] = GROUND_M + 25
        return zs

    tile = _write_las(tmp_path / "t.las", *_scan(FOOTPRINT, roof))

    heights = measure_building_heights([tile], [_building("a", FOOTPRINT)], EXAMPLE_BBOX)

    assert heights["a"] == pytest.approx(15.0, abs=0.01)


def test_fr20_ground_is_the_lowest_ground_contact_on_a_slope(tmp_path):
    # Ground slopes 0..10m across the ring; the 5th percentile picks the
    # low side (OSM's `height` convention), not the average.
    xs, ys, zs, classes = _scan(FOOTPRINT, lambda n: np.full(n, GROUND_M + 20))
    min_x = FOOTPRINT.bounds[0] - 6
    zs = [
        z if c == 6 else GROUND_M + (x - min_x) / 32 * 10
        for x, z, c in zip(xs, zs, classes, strict=True)
    ]
    tile = _write_las(tmp_path / "t.las", xs, ys, zs, classes)

    heights = measure_building_heights([tile], [_building("a", FOOTPRINT)], EXAMPLE_BBOX)

    assert 18.5 < heights["a"] <= 20.0


def test_fr20_skips_a_footprint_with_no_roof_returns(tmp_path):
    # e.g. a building finished after the LIDAR flight: OSM has it, the scan doesn't.
    newer = box(_x0 + 100, _y0, _x0 + 120, _y0 + 20)
    tile = _write_las(tmp_path / "t.las", *_scan(FOOTPRINT, lambda n: np.full(n, GROUND_M + 15)))

    heights = measure_building_heights(
        [tile], [_building("a", FOOTPRINT), _building("new", newer)], EXAMPLE_BBOX
    )

    assert "a" in heights
    assert "new" not in heights


def test_fr20_skips_a_footprint_only_partly_covered_by_roof_returns(tmp_path):
    # A building replaced since the scan: its new (OSM) footprint only
    # overlaps the old roof in one corner -- that height describes the
    # old building, so it must not be used.
    replaced = box(_x0 + 15, _y0 + 15, _x0 + 45, _y0 + 45)
    tile = _write_las(tmp_path / "t.las", *_scan(FOOTPRINT, lambda n: np.full(n, GROUND_M + 15)))

    heights = measure_building_heights(
        [tile], [_building("a", FOOTPRINT), _building("replaced", replaced)], EXAMPLE_BBOX
    )

    assert "a" in heights
    assert "replaced" not in heights


def test_fr20_combines_a_footprint_split_across_two_tiles(tmp_path):
    xs, ys, zs, classes = _scan(FOOTPRINT, lambda n: np.full(n, GROUND_M + 15))
    mid_x = FOOTPRINT.centroid.x
    west = [i for i, x in enumerate(xs) if x < mid_x]
    east = [i for i, x in enumerate(xs) if x >= mid_x]
    tiles = [
        _write_las(tmp_path / f"{name}.las", *([v[i] for i in idx] for v in (xs, ys, zs, classes)))
        for name, idx in (("west", west), ("east", east))
    ]

    heights = measure_building_heights(tiles, [_building("a", FOOTPRINT)], EXAMPLE_BBOX)

    assert heights["a"] == pytest.approx(15.0, abs=0.01)


def test_fr20_lidar_replaces_estimates_but_not_explicit_heights():
    buildings = [
        _building("default", FOOTPRINT, "default"),
        _building("levels", FOOTPRINT, "levels"),
        _building("tag", FOOTPRINT, "tag"),
        _building("override", FOOTPRINT, "override"),
        _building("unmeasured", FOOTPRINT, "default"),
    ]
    measured = {"default": 9.0, "levels": 9.0, "tag": 9.0, "override": 9.0}

    result = {b.osm_id: b for b in apply_lidar_heights(buildings, measured)}

    assert (result["default"].height_m, result["default"].height_source) == (9.0, "lidar")
    assert (result["levels"].height_m, result["levels"].height_source) == (9.0, "lidar")
    assert (result["tag"].height_m, result["tag"].height_source) == (12.0, "tag")
    assert (result["override"].height_m, result["override"].height_source) == (12.0, "override")
    assert (result["unmeasured"].height_m, result["unmeasured"].height_source) == (12.0, "default")
