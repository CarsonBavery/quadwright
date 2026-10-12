"""FR-10: extrude a ground-elevation height grid into a solid terrain block."""

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon

from quadwright.mesh.terrain import FlatGround, GroundHeightLookup, build_terrain_plate
from quadwright.resolve.terrain import HeightGrid


def test_fr10_flat_grid_reduces_to_a_flat_box():
    # A uniform grid has no relief, so the terrain block should be exactly
    # the same box a flat base plate would be: (rows-1)*cell x (cols-1)*cell x thickness.
    grid = HeightGrid(np.full((3, 3), 100.0), origin_m=(0.0, 0.0), cell_size_m=10.0)
    mesh = build_terrain_plate(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=1.0, base_thickness_mm=6.0
    )

    assert mesh.is_watertight
    assert mesh.volume == pytest.approx(20.0 * 20.0 * 6.0)
    assert mesh.bounds[:, 2].tolist() == pytest.approx([0.0, 6.0])


def test_fr10_sloped_grid_rises_from_the_lowest_point():
    grid = HeightGrid(np.array([[100.0, 110.0, 120.0]] * 3), origin_m=(0.0, 0.0), cell_size_m=10.0)
    mesh = build_terrain_plate(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=1.0, base_thickness_mm=6.0
    )

    assert mesh.is_watertight
    # lowest point (100m) sits at exactly base_thickness_mm; highest (120m,
    # 20m of relief) rises 20mm above that at this 1:1 scale.
    assert mesh.bounds[:, 2].tolist() == pytest.approx([0.0, 26.0])


def test_fr10_vertical_exaggeration_only_scales_relief_not_the_floor():
    grid = HeightGrid(np.array([[100.0, 120.0]] * 2), origin_m=(0.0, 0.0), cell_size_m=10.0)
    mesh = build_terrain_plate(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=3.0, base_thickness_mm=6.0
    )

    # 20m of real relief x3 exaggeration = 60mm above the (unexaggerated) base thickness.
    assert mesh.bounds[:, 2].tolist() == pytest.approx([0.0, 66.0])


def test_fr10_irregular_grid_is_watertight():
    rng = np.random.default_rng(0)
    grid = HeightGrid(100 + rng.random((5, 7)) * 20, origin_m=(0.0, 0.0), cell_size_m=3.0)
    mesh = build_terrain_plate(
        grid, scale_mm_per_m=2.0, vertical_exaggeration=1.5, base_thickness_mm=6.0
    )

    assert mesh.is_watertight
    assert mesh.volume > 0


def test_fr10_ground_height_lookup_matches_the_mesh_surface():
    grid = HeightGrid(np.array([[100.0, 120.0]] * 2), origin_m=(5.0, 5.0), cell_size_m=10.0)
    lookup = GroundHeightLookup(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=1.0, base_thickness_mm=6.0
    )

    assert lookup(0.0, 0.0) == pytest.approx(6.0)  # grid origin -> the 100m (lowest) cell
    assert lookup(10.0, 0.0) == pytest.approx(26.0)  # one cell over -> the 120m cell


def test_fr10_min_height_under_finds_the_low_point_regardless_of_vertex_order():
    # Same two-cell grid as above: (0,*) is the 100m/6mm-low cell,
    # (10,*) is the 120m/26mm-high cell. A footprint spanning both would
    # float above the low side if positioned using only its first vertex
    # (e.g. the high corner) -- min_height_under must find the true low
    # point (6.0) no matter which vertex happens to come first.
    grid = HeightGrid(np.array([[100.0, 120.0]] * 2), origin_m=(5.0, 5.0), cell_size_m=10.0)
    lookup = GroundHeightLookup(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=1.0, base_thickness_mm=6.0
    )
    footprint_starting_at_the_high_corner = Polygon([(10, 0), (10, 5), (0, 5), (0, 0)])

    result = lookup.min_height_under(
        footprint_starting_at_the_high_corner, position_on_base=(0.0, 0.0)
    )

    assert result == pytest.approx(6.0)


def test_fr10_min_height_under_offsets_by_position_on_base():
    grid = HeightGrid(np.array([[100.0, 120.0]] * 2), origin_m=(0.0, 0.0), cell_size_m=10.0)
    lookup = GroundHeightLookup(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=1.0, base_thickness_mm=6.0
    )
    # A 1x1 footprint at part-local (0,0), placed at campus position (10,0)
    # -- lands squarely in the 120m/26mm cell once offset is applied.
    tiny_footprint = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])

    result = lookup.min_height_under(tiny_footprint, position_on_base=(10.0, 0.0))

    assert result == pytest.approx(26.0)


def test_fr10_min_height_under_handles_multipolygon_footprints():
    grid = HeightGrid(np.array([[100.0, 120.0]] * 2), origin_m=(0.0, 0.0), cell_size_m=10.0)
    lookup = GroundHeightLookup(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=1.0, base_thickness_mm=6.0
    )
    low_piece = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    high_piece = Polygon([(10, 0), (11, 0), (11, 1), (10, 1)])

    result = lookup.min_height_under(
        MultiPolygon([high_piece, low_piece]), position_on_base=(0.0, 0.0)
    )

    assert result == pytest.approx(6.0)


def test_fr10_ground_height_lookup_interpolates_between_vertices():
    # Halfway between the 100m (6mm) and 120m (26mm) vertices -- the mesh
    # surface there is a straight ramp, so 16mm, not either cell's value.
    grid = HeightGrid(np.array([[100.0, 120.0]] * 2), origin_m=(0.0, 0.0), cell_size_m=10.0)
    lookup = GroundHeightLookup(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=1.0, base_thickness_mm=6.0
    )

    assert lookup(5.0, 3.0) == pytest.approx(16.0)


def test_fr10_ground_height_lookup_is_exactly_the_mesh_surface():
    # Compare against the triangles the mesh actually has (including which
    # way each cell's diagonal runs): find the upward-facing triangle
    # above each random point and interpolate on it directly.
    rng = np.random.default_rng(1)
    grid = HeightGrid(100 + rng.random((4, 5)) * 30, origin_m=(0.0, 0.0), cell_size_m=10.0)
    kwargs = dict(scale_mm_per_m=0.5, vertical_exaggeration=2.0, base_thickness_mm=6.0)
    mesh = build_terrain_plate(grid, **kwargs)
    lookup = GroundHeightLookup(grid, **kwargs)
    # Outward normals: top faces point (at least partly) up, walls exactly sideways.
    top_triangles = mesh.triangles[mesh.face_normals[:, 2] > 1e-9]

    for x, y in rng.random((50, 2)) * [20.0, 15.0]:  # the mesh spans 4x3 cells of 5mm
        assert lookup(x, y) == pytest.approx(_mesh_surface_z(top_triangles, x, y), abs=1e-6)


def _mesh_surface_z(triangles: np.ndarray, x: float, y: float) -> float:
    """z of the triangle whose XY shadow contains (x, y), by 2D barycentric coordinates."""
    for a, b, c in triangles:
        det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        wa = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
        wb = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
        wc = 1 - wa - wb
        if min(wa, wb, wc) >= -1e-9:
            return wa * a[2] + wb * b[2] + wc * c[2]
    raise AssertionError(f"no surface triangle above ({x}, {y})")


def test_fr10_min_height_under_finds_a_dip_no_footprint_vertex_touches():
    # A bowl: high all around, one low vertex in the middle. A footprint
    # covering the whole bowl has every corner on high ground -- only
    # checking interior mesh vertices finds the 6mm floor.
    heights = np.full((3, 3), 120.0)
    heights[1, 1] = 100.0
    grid = HeightGrid(heights, origin_m=(0.0, 0.0), cell_size_m=10.0)
    lookup = GroundHeightLookup(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=1.0, base_thickness_mm=6.0
    )

    result = lookup.min_height_under(
        Polygon([(2, 2), (18, 2), (18, 18), (2, 18)]), position_on_base=(0.0, 0.0)
    )

    assert result == pytest.approx(6.0)


def test_fr10_min_height_under_finds_a_low_point_mid_edge():
    # A valley running north-south through x=10: a footprint whose
    # corners sit on both slopes still dips to the valley floor along its
    # south and north edges, where they cross the x=10 column of vertices.
    grid = HeightGrid(np.array([[120.0, 100.0, 120.0]] * 2), origin_m=(0.0, 0.0), cell_size_m=10.0)
    lookup = GroundHeightLookup(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=1.0, base_thickness_mm=6.0
    )

    result = lookup.min_height_under(
        Polygon([(5, 0), (15, 0), (15, 10), (5, 10)]), position_on_base=(0.0, 0.0)
    )

    assert result == pytest.approx(6.0)


def test_fr21_flat_ground_is_the_same_height_everywhere():
    ground = FlatGround(top_mm=6.0)
    footprint = Polygon([(0, 0), (40, 0), (40, 40), (0, 40)])

    assert ground(123.0, 45.0) == 6.0
    assert ground.min_height_under(footprint, position_on_base=(100.0, 100.0)) == 6.0


def test_fr10_terrain_block_is_a_consistent_outward_facing_solid():
    # Regression: the side walls used to be wound inward while the top
    # and bottom faced out -- watertight, but not a valid volume, and the
    # final volume-sign check then flipped the top surface to face down.
    rng = np.random.default_rng(0)
    grid = HeightGrid(100 + rng.random((5, 7)) * 20, origin_m=(0.0, 0.0), cell_size_m=3.0)
    mesh = build_terrain_plate(
        grid, scale_mm_per_m=2.0, vertical_exaggeration=1.5, base_thickness_mm=6.0
    )

    assert mesh.is_winding_consistent
    assert mesh.is_volume
    top_faces = ~np.all(np.isclose(mesh.triangles[:, :, 2], 0.0), axis=1) & (
        np.abs(mesh.face_normals[:, 2]) > 0.5
    )
    assert np.all(mesh.face_normals[top_faces, 2] > 0)
