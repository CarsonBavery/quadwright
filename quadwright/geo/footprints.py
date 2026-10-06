"""Normalize cached OSM footprints into Buildings, reprojected to local UTM (FR-03, FR-09)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyproj
from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.ops import transform

from quadwright.config import Heights
from quadwright.model import Building
from quadwright.resolve.heights import resolve_height


def load_buildings(
    raw_path: str | Path,
    bbox: tuple[float, float, float, float],
    heights: Heights,
    boundary: Polygon | MultiPolygon | None = None,
    include_outside_boundary: Sequence[str] = (),
) -> list[Building]:
    """Read a cached GeoJSON of raw OSM features and return Buildings in local UTM meters.

    `bbox` (the campus area's west, south, east, north) picks the UTM zone, so
    every building in one campus lands in the same local, metric coordinate
    system regardless of which zone it's actually in. `heights` is the
    campus config's height rules, used to fill in height_m (FR-05) since
    most OSM buildings don't carry a height tag.

    `boundary` is the campus's real OSM boundary polygon in WGS84 (see
    `load_campus_boundary`), used to drop buildings that only fall inside
    `bbox` because it's a rectangle (FR-09) -- off-campus housing, nearby
    stores. Passing None (the default, for a campus with no real-world OSM
    boundary) disables filtering entirely. A building tagged `historic=*`
    in OSM, or named in `include_outside_boundary`, is kept regardless.
    """
    data = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    to_local = _utm_projector(bbox)

    buildings: list[Building] = []
    for feature in data["features"]:
        geom = shape(feature["geometry"])
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue  # OSM tag queries can also return points/lines; footprints only
        props = feature.get("properties", {})
        name = props.get("name")
        if boundary is not None and not _in_campus_scope(
            geom, name, props, boundary, include_outside_boundary
        ):
            continue
        # osmnx's GeoDataFrame index columns are "element"/"id" as of osmnx 2.x
        # (renamed from "element_type"/"osmid" in osmnx 1.x).
        osm_id = f"{props.get('element', 'way')}/{props.get('id', '')}"
        height_m, height_source = resolve_height(props, name, heights)
        buildings.append(
            Building(
                osm_id=osm_id,
                footprint=transform(to_local, geom),
                name=name,
                height_m=height_m,
                height_source=height_source,
            )
        )
    return buildings


def _in_campus_scope(
    geom: Any,
    name: str | None,
    props: dict[str, Any],
    boundary: Polygon | MultiPolygon,
    include_outside_boundary: Sequence[str],
) -> bool:
    """Decide whether a building (still in WGS84) counts as "on campus" (FR-09)."""
    if boundary.contains(geom.centroid):
        return True
    if props.get("historic") is not None:
        return True
    return name is not None and name in include_outside_boundary


def load_campus_boundary(path: str | Path) -> Polygon | MultiPolygon:
    """Read a cached campus boundary GeoJSON (see `fetch_campus_boundary`) in WGS84.

    `ox.geocode_to_gdf` writes a one-feature FeatureCollection -- the campus
    polygon is that single feature's geometry.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return shape(data["features"][0]["geometry"])


def campus_bbox_local(bbox: tuple[float, float, float, float]) -> Polygon:
    """Reproject the campus bounding box into the same local UTM meters as buildings.

    This is the campus outline the base plate is cut from (FR-06), so it
    must share buildings' coordinate system -- same `_utm_projector` call.
    """
    west, south, east, north = bbox
    return transform(_utm_projector(bbox), box(west, south, east, north))


def utm_crs_for_bbox(bbox: tuple[float, float, float, float]) -> str:
    """Pick a local UTM CRS (as a proj4 string) for a campus bounding box.

    Shared by buildings, the campus outline, and (FR-10) terrain, so
    everything lands in the same local, metric coordinate system
    regardless of which UTM zone the campus actually falls in.
    """
    west, south, east, north = bbox
    lon, lat = (west + east) / 2, (south + north) / 2
    zone = int((lon + 180) / 6) + 1
    hemisphere = "north" if lat >= 0 else "south"
    return f"+proj=utm +zone={zone} +{hemisphere} +datum=WGS84 +units=m +no_defs"


def _utm_projector(bbox: tuple[float, float, float, float]):
    """Build a WGS84 -> local UTM transform function for the campus bounding box."""
    transformer = pyproj.Transformer.from_crs("EPSG:4326", utm_crs_for_bbox(bbox), always_xy=True)
    return transformer.transform
