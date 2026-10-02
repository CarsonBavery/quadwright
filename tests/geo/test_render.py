"""FR-04: render building footprints to a PNG."""

from pathlib import Path

from quadwright.geo.footprints import load_buildings
from quadwright.geo.render import render_footprints

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_buildings.geojson"
EXAMPLE_BBOX = (-80.000, 35.000, -79.990, 35.008)


def test_fr04_writes_a_nonempty_png(tmp_path):
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX)
    out_path = tmp_path / "footprints.png"

    render_footprints(buildings, out_path)

    assert out_path.exists()
    assert out_path.stat().st_size > 0
