"""FR-06: extrude model-scale footprints and the base plate into meshes."""

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon

from quadwright.mesh.extrude import (
    BASE_PLATE_THICKNESS_MM,
    base_stock_mm,
    build_base_plate,
    extrude_box,
)
from quadwright.mesh.terrain import build_terrain_plate
from quadwright.resolve.terrain import HeightGrid

SQUARE_MM = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])


def test_fr06_extrude_box_has_the_requested_height():
    mesh = extrude_box(SQUARE_MM, height_mm=25.0)
    assert mesh.bounds[1][2] - mesh.bounds[0][2] == pytest.approx(25.0)


def test_fr06_extrude_box_volume_matches_footprint_area_times_height():
    mesh = extrude_box(SQUARE_MM, height_mm=25.0)
    assert mesh.volume == pytest.approx(SQUARE_MM.area * 25.0)


def test_fr06_base_plate_uses_the_default_thickness():
    mesh = build_base_plate(SQUARE_MM)
    assert mesh.bounds[1][2] - mesh.bounds[0][2] == pytest.approx(BASE_PLATE_THICKNESS_MM)


def test_fr06_extrude_box_handles_multipolygon_footprints():
    # Real OSM relations (multi-way buildings) normalize to a MultiPolygon;
    # trimesh.creation.extrude_polygon alone can't handle that directly.
    other_square = Polygon([(20, 0), (30, 0), (30, 10), (20, 10)])
    footprint = MultiPolygon([SQUARE_MM, other_square])

    mesh = extrude_box(footprint, height_mm=25.0)

    assert mesh.volume == pytest.approx((SQUARE_MM.area + other_square.area) * 25.0)


def test_fr23_extrude_box_survives_a_duplicate_vertex_and_micron_edges():
    # The kind of outline merge's unions/buffers leave: a repeated vertex
    # and a 0.0005mm jog. Unsimplified, trimesh can't close the volume.
    messy = Polygon([(0, 0), (10, 0), (10, 0), (10, 5), (10.0005, 5.0002), (10, 10), (0, 10)])

    mesh = extrude_box(messy, height_mm=5.0)

    assert mesh.is_volume
    assert mesh.volume == pytest.approx(100.0 * 5.0, rel=1e-3)


def test_fr22_base_floor_is_at_least_23mm():
    assert BASE_PLATE_THICKNESS_MM >= 23.0


def test_fr22_flat_base_stock_is_just_the_floor():
    assert base_stock_mm(build_base_plate(SQUARE_MM)) == pytest.approx(BASE_PLATE_THICKNESS_MM)


def test_fr22_terrain_base_stock_is_floor_plus_scaled_relief():
    # 10m of real relief at 0.5 mm/m and 2x exaggeration -> 10mm above the floor.
    grid = HeightGrid(np.array([[100.0, 110.0], [100.0, 110.0]]), (0.0, 0.0), cell_size_m=10.0)
    plate = build_terrain_plate(
        grid, scale_mm_per_m=0.5, vertical_exaggeration=2.0, base_thickness_mm=23.0
    )
    assert base_stock_mm(plate) == pytest.approx(23.0 + 10.0)
