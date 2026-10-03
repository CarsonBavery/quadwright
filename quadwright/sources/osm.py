"""Fetch and cache OSM building footprints and campus boundaries (FR-02, FR-09)."""

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
    gdf = gdf.reset_index()  # keep element/id as columns, not just the index

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(cache_path, driver="GeoJSON")
    return cache_path


def fetch_campus_boundary(area: CampusArea, cache_dir: str | Path = "data/raw") -> Path | None:
    """Download and cache the campus's real OSM boundary polygon, if configured.

    `area.bbox` is always a rectangle, so it inevitably includes whatever's
    nearby -- off-campus housing, gas stations, restaurants. The boundary
    polygon is what `load_buildings` filters against (FR-09) to keep only
    buildings actually on campus. Returns None without touching the network
    when `area.boundary_query` isn't set (e.g. a synthetic campus with no
    real-world OSM entity to look up).
    """
    if area.boundary_query is None:
        return None

    cache_path = Path(cache_dir) / area.name / "boundary.geojson"
    if cache_path.exists():
        return cache_path

    gdf = ox.geocode_to_gdf(area.boundary_query)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(cache_path, driver="GeoJSON")
    return cache_path
