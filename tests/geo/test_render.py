"""FR-04: render building footprints to a PNG. FR-15: the elevation grid. FR-21: the 3D model."""

from pathlib import Path

import numpy as np
from shapely.geometry import box

from quadwright.config import Heights
from quadwright.export.scene import build_campus_scene, place_buildings
from quadwright.geo.footprints import load_buildings
from quadwright.geo.render import render_footprints, render_heightmap, render_model
from quadwright.mesh.extrude import build_base_plate
from quadwright.mesh.terrain import FlatGround
from quadwright.model import Building
from quadwright.resolve.terrain import HeightGrid

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_buildings.geojson"
EXAMPLE_BBOX = (-80.000, 35.000, -79.990, 35.008)


def test_fr04_writes_a_nonempty_png(tmp_path):
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX, Heights())
    out_path = tmp_path / "footprints.png"

    render_footprints(buildings, out_path)

    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_fr15_writes_a_nonempty_heightmap_png(tmp_path):
    grid = HeightGrid(
        np.array([[100.0, 110.0], [105.0, 120.0]]), origin_m=(0.0, 0.0), cell_size_m=10.0
    )
    out_path = tmp_path / "heightmap.png"

    render_heightmap(grid, out_path)

    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_fr15_creates_parent_directories(tmp_path):
    grid = HeightGrid(np.array([[100.0, 110.0]]), origin_m=(0.0, 0.0), cell_size_m=10.0)
    nested = tmp_path / "outputs" / "example-university" / "heightmap.png"

    render_heightmap(grid, nested)

    assert nested.exists()


def test_fr21_writes_a_nonempty_model_png(tmp_path):
    buildings = [Building("a", box(10, 10, 20, 20)), Building("b", box(30, 30, 35, 40))]
    placed = place_buildings(
        buildings,
        {b.osm_id: b.footprint for b in buildings},
        {"a": 5.0, "b": 8.0},
        [],
        FlatGround(6.0),
    )
    scene = build_campus_scene(build_base_plate(box(0, 0, 50, 50)), placed)
    out_path = tmp_path / "model.png"

    render_model(scene, out_path, title="test campus")

    assert out_path.stat().st_size > 0
