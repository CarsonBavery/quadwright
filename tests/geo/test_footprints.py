"""FR-03: normalize cached OSM footprints into local-meter Buildings."""

from pathlib import Path

from quadwright.geo.footprints import load_buildings

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_buildings.geojson"
EXAMPLE_BBOX = (-80.000, 35.000, -79.990, 35.008)


def test_fr03_skips_non_polygon_features():
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX)
    assert len(buildings) == 2  # the fixture's lone Point feature is dropped


def test_fr03_keeps_name_when_present():
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX)
    names = {b.name for b in buildings}
    assert "Old Main" in names
    assert None in names  # the second fixture building has no name tag


def test_fr03_reprojects_to_local_meters():
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX)
    for building in buildings:
        minx, miny, maxx, maxy = building.footprint.bounds
        # Fixture footprints are ~50m wide; still-in-degrees coordinates
        # would be in the hundreds of thousands (lat/lon * UTM-scale meters).
        assert maxx - minx < 500
        assert maxy - miny < 500


def test_fr03_osm_id_includes_element_type():
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX)
    assert {b.osm_id for b in buildings} == {"way/100", "way/101"}
