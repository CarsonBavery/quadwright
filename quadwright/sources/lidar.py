"""Fetch and cache raw LIDAR point cloud tiles from USGS 3DEP (FR-10).

USGS organizes LIDAR by "project" (one survey campaign), hosted under
prd-tnm.s3.amazonaws.com. There's no bbox-based discovery API reachable
from every network, so `CampusArea.lidar_project` names the project
explicitly -- the same manual-lookup pattern as `boundary_query`.
"""

from __future__ import annotations

from pathlib import Path

import requests

from quadwright.config import CampusArea

_TNM_PROJECTS_BASE = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/LPC/Projects"
_REQUEST_TIMEOUT_S = 30
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024


def fetch_campus_lidar(area: CampusArea, cache_dir: str | Path = "data/raw") -> list[Path]:
    """Download LIDAR tiles overlapping the campus bbox, caching each as a .laz file.

    Returns the cached tile paths. A tile already on disk isn't
    re-downloaded, so re-running `fetch` only pulls what's missing --
    this still fetches the (small) tile index every call to know what
    "missing" means, unlike `fetch_buildings`'s single-file cache check.
    Returns [] without touching the network when `area.lidar_project`
    isn't set (the default -- flat base plate, no terrain).
    """
    if area.lidar_project is None:
        return []

    project_base = f"{_TNM_PROJECTS_BASE}/{area.lidar_project}"
    project_name = area.lidar_project.rsplit("/", 1)[-1]
    index = requests.get(f"{project_base}/{project_name}.vpc", timeout=_REQUEST_TIMEOUT_S).json()
    download_urls = _fetch_download_links(project_base)

    out_dir = Path(cache_dir) / area.name / "lidar"
    out_dir.mkdir(parents=True, exist_ok=True)

    tile_paths: list[Path] = []
    for feature in index["features"]:
        if not _overlaps_xy(feature["bbox"], area.bbox):
            continue
        filename = feature["assets"]["data"]["href"].rsplit("/", 1)[-1]
        tile_path = out_dir / filename
        if not tile_path.exists():
            _download(download_urls[filename], tile_path)
        tile_paths.append(tile_path)
    return tile_paths


def _fetch_download_links(project_base: str) -> dict[str, str]:
    """Map each tile's filename to its real download URL (rockyweb.usgs.gov).

    The `.vpc` index's asset hrefs are relative paths that don't resolve
    against prd-tnm.s3.amazonaws.com directly; this manifest has the
    actual working URLs.
    """
    text = requests.get(
        f"{project_base}/0_file_download_links.txt", timeout=_REQUEST_TIMEOUT_S
    ).text
    return {line.rsplit("/", 1)[-1]: line for line in text.splitlines() if line.strip()}


def _overlaps_xy(stac_bbox: list[float], campus_bbox: tuple[float, float, float, float]) -> bool:
    """A `.vpc` tile's STAC bbox is 3D [minx, miny, minz, maxx, maxy, maxz]; compare XY only."""
    min_x, min_y, _, max_x, max_y, _ = stac_bbox
    west, south, east, north = campus_bbox
    return not (max_x < west or min_x > east or max_y < south or min_y > north)


def _download(url: str, path: Path) -> None:
    with requests.get(url, timeout=_REQUEST_TIMEOUT_S, stream=True) as response:
        response.raise_for_status()
        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_BYTES):
                f.write(chunk)
