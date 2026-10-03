"""FR-06: extrude model-scale footprints and the base plate into meshes."""

import pytest
from shapely.geometry import MultiPolygon, Polygon

from quadwright.mesh.extrude import BASE_PLATE_THICKNESS_MM, build_base_plate, extrude_box

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
