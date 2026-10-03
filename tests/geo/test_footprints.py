"""FR-03: normalize cached OSM footprints into local-meter Buildings."""

import json
from pathlib import Path

from shapely.geometry import box

from quadwright.config import Heights
from quadwright.geo.footprints import campus_bbox_local, load_buildings, load_campus_boundary

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


# A rectangle covering only "Old Main" (way/100); way/101 sits entirely east of it.
BOUNDARY_COVERING_OLD_MAIN = box(-79.999, 35.0038, -79.9973, 35.0047)


def test_fr09_drops_buildings_outside_the_boundary():
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX, HEIGHTS, boundary=BOUNDARY_COVERING_OLD_MAIN)
    assert {b.osm_id for b in buildings} == {"way/100"}


def test_fr09_no_boundary_means_no_filtering():
    # The default (None) is what a synthetic campus with no real OSM entity uses.
    buildings = load_buildings(FIXTURE, EXAMPLE_BBOX, HEIGHTS, boundary=None)
    assert {b.osm_id for b in buildings} == {"way/100", "way/101"}


def _write_geojson(tmp_path: Path, features: list[dict]) -> Path:
    path = tmp_path / "buildings.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return path


def _feature(osm_id: int, lon: float, lat: float, **props) -> dict:
    size = 0.0002
    corners = [
        [lon, lat],
        [lon + size, lat],
        [lon + size, lat + size],
        [lon, lat + size],
        [lon, lat],
    ]
    return {
        "type": "Feature",
        "properties": {"element": "way", "id": osm_id, "building": "yes", **props},
        "geometry": {"type": "Polygon", "coordinates": [corners]},
    }


def test_fr09_keeps_a_historic_building_outside_the_boundary(tmp_path):
    # Far outside BOUNDARY_COVERING_OLD_MAIN, but historic=* always counts as on campus.
    raw_path = _write_geojson(tmp_path, [_feature(200, -79.990, 35.010, historic="building")])
    buildings = load_buildings(raw_path, EXAMPLE_BBOX, HEIGHTS, boundary=BOUNDARY_COVERING_OLD_MAIN)
    assert {b.osm_id for b in buildings} == {"way/200"}


def test_fr09_keeps_a_named_building_via_include_outside_boundary(tmp_path):
    raw_path = _write_geojson(tmp_path, [_feature(201, -79.990, 35.010, name="Old Gym")])
    buildings = load_buildings(
        raw_path,
        EXAMPLE_BBOX,
        HEIGHTS,
        boundary=BOUNDARY_COVERING_OLD_MAIN,
        include_outside_boundary=["Old Gym"],
    )
    assert {b.osm_id for b in buildings} == {"way/201"}


def test_fr09_drops_an_unnamed_non_historic_building_outside_the_boundary(tmp_path):
    raw_path = _write_geojson(tmp_path, [_feature(202, -79.990, 35.010)])
    buildings = load_buildings(raw_path, EXAMPLE_BBOX, HEIGHTS, boundary=BOUNDARY_COVERING_OLD_MAIN)
    assert buildings == []


def test_fr09_load_campus_boundary_reads_the_geocode_to_gdf_shape(tmp_path):
    # ox.geocode_to_gdf(...).to_file(..., driver="GeoJSON") writes a single-
    # feature FeatureCollection; this is what fetch_campus_boundary caches.
    boundary_path = tmp_path / "boundary.geojson"
    boundary_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"display_name": "Example Campus"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-80.0, 35.0],
                                    [-79.9, 35.0],
                                    [-79.9, 35.1],
                                    [-80.0, 35.1],
                                    [-80.0, 35.0],
                                ]
                            ],
                        },
                    }
                ],
            }
        )
    )
    boundary = load_campus_boundary(boundary_path)
    assert boundary.geom_type == "Polygon"
    assert boundary.bounds == (-80.0, 35.0, -79.9, 35.1)
