"""Build a ground-elevation height grid from cached LIDAR tiles (FR-10).

Only LAS classification 2 ("ground") points count -- buildings, trees,
and noise returns are excluded. ADR-0005's rules-based-first philosophy
applies here too: this is a plain grid average, not an ML-fitted surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import laspy
import numpy as np
import pyproj

from quadwright.geo.footprints import campus_bbox_local, utm_crs_for_bbox

GROUND_CLASSIFICATION = 2


class HeightGrid:
    """A regular grid of ground elevations in local UTM meters.

    `heights_m[row, col]` is the mean ground elevation in that cell;
    `origin_m` is the grid's (min_x, min_y) corner, matching the same
    origin `quadwright.mesh.scale.to_model_mm` uses for buildings and the
    base plate, so everything shares one coordinate frame.
    """

    def __init__(self, heights_m: np.ndarray, origin_m: tuple[float, float], cell_size_m: float):
        self.heights_m = heights_m
        self.origin_m = origin_m
        self.cell_size_m = cell_size_m

    @property
    def shape(self) -> tuple[int, int]:
        return self.heights_m.shape

    def elevation_at(self, x_m: float, y_m: float) -> float:
        """Nearest-cell ground elevation at a local-meter point (e.g. a building's centroid)."""
        n_rows, n_cols = self.heights_m.shape
        col = int((x_m - self.origin_m[0]) / self.cell_size_m)
        row = int((y_m - self.origin_m[1]) / self.cell_size_m)
        col = min(max(col, 0), n_cols - 1)
        row = min(max(row, 0), n_rows - 1)
        return float(self.heights_m[row, col])


def build_height_grid(
    lidar_paths: Sequence[str | Path],
    bbox: tuple[float, float, float, float],
    cell_size_m: float = 2.0,
) -> HeightGrid:
    """Read cached LIDAR tiles and bin ground points into a regular height grid.

    Points are cropped to the campus outline (`campus_bbox_local`, same
    rectangle the flat base plate used before this) so the grid's extent
    matches the base plate exactly, even though LIDAR tiles themselves
    cover extra surrounding area. `cell_size_m` is deliberately coarse --
    the finished model is tens of centimeters, so a fine-grained DEM buys
    nothing; per-cell averaging (no scipy interpolation) is plenty.
    """
    utm_crs = utm_crs_for_bbox(bbox)
    min_x, min_y, max_x, max_y = campus_bbox_local(bbox).bounds

    xs, ys, zs = _read_ground_points(lidar_paths, utm_crs)
    in_bounds = (xs >= min_x) & (xs <= max_x) & (ys >= min_y) & (ys <= max_y)
    xs, ys, zs = xs[in_bounds], ys[in_bounds], zs[in_bounds]
    if len(zs) == 0:
        raise ValueError("no ground-classified LIDAR points fall inside the campus bbox")

    n_cols = max(1, int((max_x - min_x) / cell_size_m) + 1)
    n_rows = max(1, int((max_y - min_y) / cell_size_m) + 1)
    col_idx = np.clip(((xs - min_x) / cell_size_m).astype(int), 0, n_cols - 1)
    row_idx = np.clip(((ys - min_y) / cell_size_m).astype(int), 0, n_rows - 1)

    sums = np.zeros((n_rows, n_cols))
    counts = np.zeros((n_rows, n_cols))
    np.add.at(sums, (row_idx, col_idx), zs)
    np.add.at(counts, (row_idx, col_idx), 1)

    heights = np.full((n_rows, n_cols), np.nan)
    has_data = counts > 0
    heights[has_data] = sums[has_data] / counts[has_data]
    _fill_empty_cells(heights)

    return HeightGrid(heights, (min_x, min_y), cell_size_m)


def _read_ground_points(
    lidar_paths: Sequence[str | Path], utm_crs: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read every tile's ground points, reprojected into one shared local UTM frame.

    Each LAS tile carries its own CRS (for USGS 3DEP, typically a state
    plane system in US survey feet, often with a NAVD88 *feet* vertical
    datum too) in its header. pyproj's X/Y reprojection to our purely
    horizontal UTM CRS is correct, but since that target CRS has no
    vertical component, pyproj leaves Z in the source's own unit
    unchanged -- it does NOT convert feet to meters. That conversion has
    to be applied by hand using the source CRS's own vertical axis unit.
    """
    xs_parts, ys_parts, zs_parts = [], [], []
    for path in lidar_paths:
        las = laspy.read(str(path))
        ground = las.classification == GROUND_CLASSIFICATION
        if not np.any(ground):
            continue
        source_crs = las.header.parse_crs()
        transformer = pyproj.Transformer.from_crs(source_crs, utm_crs, always_xy=True)
        x, y, z = transformer.transform(
            np.asarray(las.x)[ground], np.asarray(las.y)[ground], np.asarray(las.z)[ground]
        )
        xs_parts.append(x)
        ys_parts.append(y)
        zs_parts.append(np.asarray(z) * _vertical_unit_to_meters(source_crs))

    if not xs_parts:
        return np.array([]), np.array([]), np.array([])
    return np.concatenate(xs_parts), np.concatenate(ys_parts), np.concatenate(zs_parts)


def _vertical_unit_to_meters(crs: pyproj.CRS) -> float:
    """Factor to convert a LAS CRS's raw Z values to meters.

    For a compound CRS (horizontal + vertical, as USGS 3DEP LIDAR uses),
    the vertical sub-CRS's own axis carries its unit -- read that instead
    of assuming meters. A plain 2D CRS has no vertical component, so Z is
    assumed to already be in meters (factor 1.0).
    """
    if crs.is_vertical and len(crs.sub_crs_list) > 1:
        return crs.sub_crs_list[-1].axis_info[0].unit_conversion_factor
    return 1.0


def _fill_empty_cells(heights: np.ndarray, max_passes: int = 100) -> None:
    """Fill grid cells with no ground points from their nearest valid neighbor, in place.

    Repeated one-cell dilation from the 4-neighborhood; any cell still
    empty after `max_passes` (fully enclosed by other empty cells) gets
    the grid's overall mean as a last resort.
    """
    for _ in range(max_passes):
        missing = np.isnan(heights)
        if not missing.any():
            return
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbor = np.roll(heights, (dr, dc), axis=(0, 1))
            fillable = missing & ~np.isnan(neighbor) & np.isnan(heights)
            heights[fillable] = neighbor[fillable]
    heights[np.isnan(heights)] = np.nanmean(heights)
