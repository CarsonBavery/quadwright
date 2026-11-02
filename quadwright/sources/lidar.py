"""Fetch and cache raw LIDAR point cloud tiles from USGS 3DEP (FR-10).

USGS organizes LIDAR by "project" (one survey campaign), hosted under
prd-tnm.s3.amazonaws.com. There's no bbox-based discovery API reachable
from every network, so `CampusArea.lidar_project` names the project
explicitly -- the same manual-lookup pattern as `boundary_query`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

# Imported by name (not as requests.HTTPError) so tests that swap out the
# module-level `requests` for a fake still see the real exception class.
from requests import ConnectionError as RequestsConnectionError
from requests import HTTPError, Response, Timeout

from quadwright.config import CampusArea

_TNM_PROJECTS_BASE = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/LPC/Projects"
_REQUEST_TIMEOUT_S = 30
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024

# The tile list fetch_campus_lidar *meant* to cache, written before any
# download starts -- so a fetch cut short (rate limit, dropped Wi-Fi)
# leaves a record of what's missing instead of a quietly partial folder.
MANIFEST_NAME = "tiles.json"

# rockyweb.usgs.gov answers 429 Too Many Requests after a few tiles in a
# row (uw-madison stopped at 3 of 17). Those, 5xx hiccups, and network
# drops (a DNS lookup failed at tile 8) are worth waiting out; a 404 or
# 403 isn't.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 6
_BACKOFF_BASE_S = 10  # 10, 20, 40, 80, 160s between attempts: ~5 minutes total


class IncompleteLidarError(RuntimeError):
    """Raised when a campus's LIDAR cache is missing tiles its manifest lists."""


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

    filenames = [
        feature["assets"]["data"]["href"].rsplit("/", 1)[-1]
        for feature in index["features"]
        if _overlaps_xy(feature["bbox"], area.bbox)
    ]
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps({"project": area.lidar_project, "tiles": filenames}, indent=2),
        encoding="utf-8",
    )

    tile_paths: list[Path] = []
    for filename in filenames:
        tile_path = out_dir / filename
        if not tile_path.exists():
            _download(download_urls[filename], tile_path)
        tile_paths.append(tile_path)
    return tile_paths


def cached_lidar_tiles(lidar_dir: str | Path) -> list[Path]:
    """The campus's cached tiles, refusing a partial set its manifest knows about.

    With a manifest (every fetch since FR-10's coverage fix), returns its
    tiles in order, or raises IncompleteLidarError naming how many are
    missing -- a partial set builds a terrain where one tile's ground is
    smeared across the whole campus by HeightGrid's gap fill, which looks
    plausible and is wrong. Without one (a cache fetched before manifests
    existed) it falls back to whatever .laz files are there.
    """
    lidar_dir = Path(lidar_dir)
    if not lidar_dir.exists():
        return []
    manifest = lidar_dir / MANIFEST_NAME
    if not manifest.exists():
        return sorted(lidar_dir.glob("*.laz"))

    expected = json.loads(manifest.read_text(encoding="utf-8"))["tiles"]
    missing = [name for name in expected if not (lidar_dir / name).exists()]
    if missing:
        raise IncompleteLidarError(
            f"only {len(expected) - len(missing)} of {len(expected)} LIDAR tiles are "
            f"cached in {lidar_dir}"
        )
    return [lidar_dir / name for name in expected]


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
    """Download one tile, waiting out rate limits and server hiccups.

    Retries statuses in _RETRY_STATUSES (honoring the server's own
    Retry-After when it sends one), plus failed connections and timeouts.
    Anything else -- and the last failed attempt -- propagates, leaving
    the tile missing for the next fetch.
    """
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            _download_once(url, path)
            return
        except (RequestsConnectionError, Timeout):
            if attempt == _MAX_ATTEMPTS:
                raise
            time.sleep(_retry_delay_s(None, attempt))
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status not in _RETRY_STATUSES or attempt == _MAX_ATTEMPTS:
                raise
            time.sleep(_retry_delay_s(exc.response, attempt))


def _retry_delay_s(response: Response | None, attempt: int) -> float:
    """Seconds to wait before retry `attempt + 1`: the server's Retry-After, else backoff."""
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after is not None and retry_after.strip().isdigit():
        return float(retry_after)
    return _BACKOFF_BASE_S * 2 ** (attempt - 1)


def _download_once(url: str, path: Path) -> None:
    """Stream `url` to `path`, so that `path` only ever exists complete.

    fetch_campus_lidar treats "file exists" as "tile is cached". Writing
    straight to `path` meant a dropped connection left a truncated .laz
    that every later fetch skipped, and the build then failed deep inside
    the LAZ decoder. Streaming to a sibling `.part` file and renaming it
    only after the last chunk keeps a failed download from ever looking
    like a cached tile; the next fetch just starts that tile over.
    """
    partial = path.with_name(path.name + ".part")
    try:
        with requests.get(url, timeout=_REQUEST_TIMEOUT_S, stream=True) as response:
            response.raise_for_status()
            with open(partial, "wb") as f:
                for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_BYTES):
                    f.write(chunk)
    except BaseException:
        # BaseException, not Exception: Ctrl-C mid-download should clean up too.
        partial.unlink(missing_ok=True)
        raise
    # replace() is atomic on one filesystem, so there's no moment where
    # `path` exists half-written.
    partial.replace(path)
