"""FR-04: render building footprints to a PNG. FR-15: render the elevation grid."""

from pathlib import Path

import numpy as np

from quadwright.config import Heights
from quadwright.geo.footprints import load_buildings
from quadwright.geo.render import render_footprints, render_heightmap
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
