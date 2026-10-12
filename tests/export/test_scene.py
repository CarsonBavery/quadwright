"""FR-21: assemble the base and every building into one viewable 3D scene."""

import numpy as np
import pytest
import trimesh
from shapely.geometry import Polygon, box

from quadwright.export.scene import (
    MAPLE_SHADES_RGBA,
    WALNUT_RGBA,
    build_campus_scene,
    place_buildings,
    seat_building,
    write_glb,
)
from quadwright.mesh.extrude import build_base_plate
from quadwright.mesh.terrain import FlatGround, GroundHeightLookup
from quadwright.model import Building, Part, Tier
from quadwright.resolve.terrain import HeightGrid


def _ramp_ground() -> GroundHeightLookup:
    # Ground rising 20mm from x=0 (6mm) to x=10 (26mm), at 1mm per meter.
    grid = HeightGrid(np.array([[100.0, 120.0]] * 2), origin_m=(0.0, 0.0), cell_size_m=10.0)
    return GroundHeightLookup(
        grid, scale_mm_per_m=1.0, vertical_exaggeration=1.0, base_thickness_mm=6.0
    )


def test_fr21_a_building_on_flat_ground_stands_on_the_base_top():
    mesh = seat_building(box(10, 10, 20, 30), height_mm=4.0, ground=FlatGround(6.0))

    assert mesh.bounds[:, 2].tolist() == pytest.approx([6.0, 10.0])
    assert mesh.bounds[:, :2].ravel().tolist() == pytest.approx([10, 10, 20, 30])


def test_fr21_a_building_on_a_slope_sits_at_its_lowest_ground_contact():
    # Footprint spans x=2..8 on the ramp: ground under it runs 10..22mm.
    # The bottom goes at 10 (no gap on the downhill side), and the roof
    # is height_mm above that -- the same reference heights are measured from.
    mesh = seat_building(box(2, 0, 8, 5), height_mm=15.0, ground=_ramp_ground())

    assert mesh.bounds[:, 2].tolist() == pytest.approx([10.0, 25.0])


def test_fr21_each_building_keeps_its_own_height_inside_a_merged_part():
    # One part milled from two buildings: the kit part is as tall as its
    # tallest member, but the preview shows each building as it really is.
    buildings = [Building("short", box(0, 0, 1, 1)), Building("tall", box(2, 0, 3, 1))]
    footprints = {b.osm_id: b.footprint for b in buildings}
    part = Part(
        id="part-0000",
        building_ids=("short", "tall"),
        footprint_local=box(0, 0, 3, 1),
        height_mm=9.0,
        tier=Tier.BLOCK,
        position_on_base=(0.0, 0.0),
    )

    placed = place_buildings(
        buildings, footprints, {"short": 3.0, "tall": 9.0}, [part], FlatGround(6.0)
    )

    by_id = {p.osm_id: p for p in placed}
    assert by_id["short"].mesh.bounds[1, 2] == pytest.approx(9.0)
    assert by_id["tall"].mesh.bounds[1, 2] == pytest.approx(15.0)
    assert {p.part_id for p in placed} == {"part-0000"}


def test_fr21_scene_names_buildings_by_part_and_colors_them_by_wood():
    base = build_base_plate(box(0, 0, 50, 50))
    placed = place_buildings(
        [Building("way/1", box(1, 1, 5, 5), name="Old Main"), Building("way/2", box(9, 9, 12, 12))],
        {"way/1": box(1, 1, 5, 5), "way/2": box(9, 9, 12, 12)},
        {"way/1": 4.0, "way/2": 2.0},
        [],
        FlatGround(6.0),
    )

    scene = build_campus_scene(base, placed)

    nodes = set(scene.graph.nodes_geometry)
    assert nodes == {"base", "unassigned/Old Main [way/1]", "unassigned/way/2"}
    assert tuple(scene.geometry["base"].visual.material.baseColorFactor) == WALNUT_RGBA
    assert tuple(scene.geometry["way/1"].visual.material.baseColorFactor) in MAPLE_SHADES_RGBA


def test_fr21_glb_is_real_size_in_meters_with_y_up(tmp_path):
    # A 300 x 200mm base with a 10mm-tall building: in glTF's convention
    # (meters, +Y up) that's 0.3m wide, 0.2m deep, and ~16mm tall.
    base = build_base_plate(box(0, 0, 300, 200))
    building = seat_building(Polygon([(10, 10), (20, 10), (20, 20)]), 10.0, FlatGround(6.0))
    scene = trimesh.Scene()
    scene.add_geometry(base, node_name="base")
    scene.add_geometry(building, node_name="b")

    path = write_glb(scene, tmp_path / "model.glb")

    loaded = trimesh.load(path)
    width, height, depth = loaded.extents
    assert (width, height, depth) == pytest.approx((0.300, 0.016, 0.200))
    assert loaded.bounds[0][1] == pytest.approx(0.0)  # the base's underside sits on y=0
