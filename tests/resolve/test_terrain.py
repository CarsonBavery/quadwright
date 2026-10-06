"""FR-10: build a ground-elevation height grid from cached LIDAR tiles."""

from pathlib import Path

import laspy
import numpy as np
import pyproj
import pytest
from shapely.geometry import Point

from quadwright.geo.footprints import campus_bbox_local, utm_crs_for_bbox
from quadwright.resolve.terrain import build_height_grid

EXAMPLE_BBOX = (-80.000, 35.000, -79.990, 35.008)  # same campus as tests/geo/test_footprints.py


def _write_las(path: Path, points: list[tuple[float, float, float, int]]) -> Path:
    """points: (lon, lat, elevation_m, classification) in WGS84, the simplest test-fixture CRS."""
    header = laspy.LasHeader(point_format=3, version="1.4")
    header.add_crs(pyproj.CRS.from_epsg(4326))
    # LAS quantizes coordinates to fixed-point using these scales; the
    # default (0.01, meant for meter-scale projected coords) would round
    # WGS84 degree values to nothing. Fine enough for degrees + meters.
    header.scales = [1e-7, 1e-7, 0.001]
    las = laspy.LasData(header)
    las.x = np.array([p[0] for p in points])
    las.y = np.array([p[1] for p in points])
    las.z = np.array([p[2] for p in points])
    las.classification = np.array([p[3] for p in points], dtype=np.uint8)
    las.write(str(path))
    return path


# A point near the SW corner of EXAMPLE_BBOX's campus outline, comfortably inside it.
INSIDE_LON, INSIDE_LAT = -79.9975, 35.0030


def test_fr10_converts_a_feet_based_vertical_datum_to_meters(tmp_path):
    # Regression: real USGS 3DEP tiles use a compound CRS (horizontal +
    # NAVD88 *feet* vertical datum). pyproj's X/Y reprojection to our
    # purely-horizontal UTM CRS is correct, but it silently leaves Z
    # unconverted -- a 700ft point would otherwise land at "700m" instead
    # of ~213m. INSIDE_LON/LAT in NC State Plane feet (EPSG:6543), the
    # real CRS family USGS 3DEP North Carolina tiles actually use.
    header = laspy.LasHeader(point_format=3, version="1.4")
    header.add_crs(pyproj.CRS.from_user_input("EPSG:6543+6360"), keep_compatibility=False)
    header.scales = [0.001, 0.001, 0.001]
    las = laspy.LasData(header)
    las.x = np.array([1701298.68])  # EPSG:6543 feet, ~= INSIDE_LON/LAT
    las.y = np.array([457521.54])
    las.z = np.array([700.0])  # NAVD88 feet
    las.classification = np.array([2], dtype=np.uint8)
    path = tmp_path / "state_plane.las"
    las.write(str(path))

    grid = build_height_grid([path], EXAMPLE_BBOX, cell_size_m=500.0)

    assert grid.elevation_at(*_local_xy(INSIDE_LON, INSIDE_LAT)) == pytest.approx(
        700.0 * 0.3048006096012192, abs=0.5
    )


def test_fr10_averages_ground_points_within_one_cell(tmp_path):
    path = _write_las(
        tmp_path / "tile.las",
        [
            (INSIDE_LON, INSIDE_LAT, 100.0, 2),
            (
                INSIDE_LON,
                INSIDE_LAT,
                104.0,
                2,
            ),  # same cell at a coarse cell size -> averages to 102
        ],
    )
    grid = build_height_grid([path], EXAMPLE_BBOX, cell_size_m=500.0)
    assert grid.elevation_at(*_local_xy(INSIDE_LON, INSIDE_LAT)) == pytest.approx(102.0)


def test_fr10_excludes_non_ground_classifications(tmp_path):
    path = _write_las(
        tmp_path / "tile.las",
        [
            (INSIDE_LON, INSIDE_LAT, 100.0, 2),  # ground
            (INSIDE_LON, INSIDE_LAT, 500.0, 6),  # building roof -- must not pull the average up
        ],
    )
    grid = build_height_grid([path], EXAMPLE_BBOX, cell_size_m=500.0)
    assert grid.elevation_at(*_local_xy(INSIDE_LON, INSIDE_LAT)) == pytest.approx(100.0)


def test_fr10_crops_points_outside_the_campus_bbox(tmp_path):
    outside_lon, outside_lat = -80.5, 35.5  # far outside EXAMPLE_BBOX
    path = _write_las(
        tmp_path / "tile.las",
        [
            (INSIDE_LON, INSIDE_LAT, 100.0, 2),
            (outside_lon, outside_lat, 9999.0, 2),  # would wreck the result if not cropped out
        ],
    )
    grid = build_height_grid([path], EXAMPLE_BBOX, cell_size_m=500.0)
    assert np.nanmax(grid.heights_m) < 1000.0  # the 9999 outlier never entered the grid


def test_fr10_reads_multiple_tiles_together(tmp_path):
    tile_a = _write_las(tmp_path / "a.las", [(INSIDE_LON, INSIDE_LAT, 100.0, 2)])
    other_lon, other_lat = (
        -79.9965,
        35.0070,
    )  # still inside EXAMPLE_BBOX, different cell at a fine size
    tile_b = _write_las(tmp_path / "b.las", [(other_lon, other_lat, 120.0, 2)])

    grid = build_height_grid([tile_a, tile_b], EXAMPLE_BBOX, cell_size_m=50.0)

    assert grid.elevation_at(*_local_xy(INSIDE_LON, INSIDE_LAT)) == pytest.approx(100.0, abs=1.0)
    assert grid.elevation_at(*_local_xy(other_lon, other_lat)) == pytest.approx(120.0, abs=1.0)


def test_fr10_fills_cells_with_no_ground_points(tmp_path):
    # A coarse grid over a wide, sparse point set: most cells start empty
    # and must be filled from a neighbor rather than left NaN.
    path = _write_las(tmp_path / "tile.las", [(INSIDE_LON, INSIDE_LAT, 150.0, 2)])
    grid = build_height_grid([path], EXAMPLE_BBOX, cell_size_m=100.0)
    assert not np.isnan(grid.heights_m).any()


def test_fr10_raises_when_no_ground_points_fall_in_bbox(tmp_path):
    path = _write_las(
        tmp_path / "tile.las", [(INSIDE_LON, INSIDE_LAT, 100.0, 6)]
    )  # no classification 2 at all
    with pytest.raises(ValueError, match="no ground"):
        build_height_grid([path], EXAMPLE_BBOX, cell_size_m=500.0)


def test_fr10_elevation_at_clamps_outside_the_grid(tmp_path):
    path = _write_las(tmp_path / "tile.las", [(INSIDE_LON, INSIDE_LAT, 100.0, 2)])
    grid = build_height_grid([path], EXAMPLE_BBOX, cell_size_m=500.0)
    # Querying far outside the grid clamps to the nearest edge cell instead of raising.
    assert grid.elevation_at(-1e9, -1e9) == pytest.approx(grid.heights_m[0, 0])


def _local_xy(lon: float, lat: float) -> tuple[float, float]:
    """Reproject a WGS84 test point the same way build_height_grid reprojects LAS points."""
    transformer = pyproj.Transformer.from_crs(
        "EPSG:4326", utm_crs_for_bbox(EXAMPLE_BBOX), always_xy=True
    )
    return transformer.transform(lon, lat)


def test_fr10_campus_outline_matches_grid_origin():
    # Sanity check that the helper above and build_height_grid agree on
    # where the campus outline actually sits -- not a terrain test per se,
    # just guards the other tests' assumptions.
    outline = campus_bbox_local(EXAMPLE_BBOX)
    assert outline.contains(Point(*_local_xy(INSIDE_LON, INSIDE_LAT)))
