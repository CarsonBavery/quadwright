"""FR-02: fetch and cache OSM building footprints, without hitting the network."""

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from quadwright.config import CampusArea
from quadwright.sources import osm

AREA = CampusArea(name="example-university", bbox=(-80.000, 35.000, -79.990, 35.008))


def _fake_gdf() -> gpd.GeoDataFrame:
    corners = [(-79.998, 35.004), (-79.997, 35.004), (-79.997, 35.005), (-79.998, 35.005)]
    square = Polygon(corners)
    # osmnx 2.x names these index levels "element"/"id" (was "element_type"/"osmid" in 1.x)
    index = pd.MultiIndex.from_tuples([("way", 100)], names=["element", "id"])
    data = {"building": ["yes"], "geometry": [square]}
    return gpd.GeoDataFrame(data, index=index, crs="EPSG:4326")


def _patch_features_from_bbox(monkeypatch) -> list[int]:
    calls: list[int] = []

    def fake(*_args, **_kwargs):
        calls.append(1)
        return _fake_gdf()

    monkeypatch.setattr(osm.ox, "features_from_bbox", fake)
    return calls


def test_fr02_fetches_and_caches(tmp_path, monkeypatch):
    calls = _patch_features_from_bbox(monkeypatch)

    path = osm.fetch_buildings(AREA, cache_dir=tmp_path)

    assert path == tmp_path / "example-university" / "buildings.geojson"
    assert path.exists()
    assert len(calls) == 1


def test_fr02_second_fetch_is_a_cache_hit(tmp_path, monkeypatch):
    calls = _patch_features_from_bbox(monkeypatch)

    osm.fetch_buildings(AREA, cache_dir=tmp_path)
    osm.fetch_buildings(AREA, cache_dir=tmp_path)

    assert len(calls) == 1  # second call must not hit the (mocked) network again


def test_fr02_raises_if_network_called_unexpectedly(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("should not be called when cache already exists")

    cached = tmp_path / "example-university" / "buildings.geojson"
    cached.parent.mkdir(parents=True)
    cached.write_text('{"type": "FeatureCollection", "features": []}')
    monkeypatch.setattr(osm.ox, "features_from_bbox", boom)

    path = osm.fetch_buildings(AREA, cache_dir=tmp_path)

    assert path == cached
