"""Fetch and cache OSM building footprints via Overpass (FR-02)."""

from __future__ import annotations

from pathlib import Path

import osmnx as ox

from quadwright.config import CampusArea


def fetch_buildings(area: CampusArea, cache_dir: str | Path = "data/raw") -> Path:
    """Download building footprints for the campus bbox, caching to GeoJSON.

    Returns the cache path without hitting the network if it already exists,
    so re-running `fetch` is free and idempotent.
    """
    cache_path = Path(cache_dir) / area.name / "buildings.geojson"
    if cache_path.exists():
        return cache_path

    gdf = ox.features_from_bbox(area.bbox, tags={"building": True})
    gdf = gdf.reset_index()  # keep element_type/osmid as columns, not just the index

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(cache_path, driver="GeoJSON")
    return cache_path
