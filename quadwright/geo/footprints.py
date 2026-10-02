"""Normalize cached OSM footprints into Buildings, reprojected to local UTM (FR-03)."""

from __future__ import annotations

import json
from pathlib import Path

import pyproj
from shapely.geometry import shape
from shapely.ops import transform

from quadwright.model import Building


def load_buildings(raw_path: str | Path, bbox: tuple[float, float, float, float]) -> list[Building]:
    """Read a cached GeoJSON of raw OSM features and return Buildings in local UTM meters.

    `bbox` (the campus area's west, south, east, north) picks the UTM zone, so
    every building in one campus lands in the same local, metric coordinate
    system regardless of which zone it's actually in.
    """
    data = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    to_local = _utm_projector(bbox)

    buildings: list[Building] = []
    for feature in data["features"]:
        geom = shape(feature["geometry"])
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue  # OSM tag queries can also return points/lines; footprints only
        props = feature.get("properties", {})
        osm_id = f"{props.get('element_type', 'way')}/{props.get('osmid', feature.get('id', ''))}"
        buildings.append(
            Building(
                osm_id=osm_id,
                footprint=transform(to_local, geom),
                name=props.get("name"),
            )
        )
    return buildings


def _utm_projector(bbox: tuple[float, float, float, float]):
    """Build a WGS84 -> local UTM transform function for the campus bounding box."""
    west, south, east, north = bbox
    lon, lat = (west + east) / 2, (south + north) / 2
    zone = int((lon + 180) / 6) + 1
    hemisphere = "north" if lat >= 0 else "south"
    utm_crs = f"+proj=utm +zone={zone} +{hemisphere} +datum=WGS84 +units=m +no_defs"
    transformer = pyproj.Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    return transformer.transform
