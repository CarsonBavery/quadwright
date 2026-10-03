"""FR-03: normalize cached OSM footprints into local-meter Buildings."""

from pathlib import Path

from quadwright.config import Heights
from quadwright.geo.footprints import campus_bbox_local, load_buildings

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_buildings.geojson"
EXAMPLE_BBOX = (-80.000, 35.000, -79.990, 35.008)
HEIGHTS = Heights()  # the fixture has no height/levels tags, so these are all defaults


def test_fr03_skips_non_polygon_features():
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX, HEIGHTS)
    assert len(buildings) == 2  # the fixture's lone Point feature is dropped


def test_fr03_keeps_name_when_present():
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX, HEIGHTS)
    names = {b.name for b in buildings}
    assert "Old Main" in names
    assert None in names  # the second fixture building has no name tag


def test_fr03_reprojects_to_local_meters():
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX, HEIGHTS)
    for building in buildings:
        minx, miny, maxx, maxy = building.footprint.bounds
        # Fixture footprints are ~50m wide; still-in-degrees coordinates
        # would be in the hundreds of thousands (lat/lon * UTM-scale meters).
        assert maxx - minx < 500
        assert maxy - miny < 500


def test_fr03_osm_id_is_unique_per_building():
    # Regression: osmnx 2.x's GeoJSON export names these columns "element"/
    # "id" (1.x used "element_type"/"osmid"); reading the wrong keys made
    # every real building collapse onto the same fallback osm_id ("way/"),
    # invisible until something (M3's build command) relied on uniqueness.
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX, HEIGHTS)
    assert {b.osm_id for b in buildings} == {"way/100", "way/101"}


def test_fr05_defaults_height_when_fixture_has_no_tags():
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX, HEIGHTS)
    assert {b.height_source for b in buildings} == {"default"}
    assert {b.height_m for b in buildings} == {HEIGHTS.default_m}


def test_fr06_campus_bbox_local_matches_building_coordinate_system():
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX, HEIGHTS)
    outline = campus_bbox_local(EXAMPLE_BBOX)
    # Every fixture building should land inside the campus's own outline
    # once both are reprojected into the same local UTM meters.
    assert all(outline.contains(b.footprint) for b in buildings)
