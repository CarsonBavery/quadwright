"""Extrude a ground-elevation height grid into a solid terrain block (FR-10).

The top surface follows real elevation; the bottom is one flat plane at
z=0, placed `base_thickness_mm` below the grid's *lowest* point -- so
every point of the block has at least that much material under it (the
low points, not the high points, are what a mill could cut through), and
the result is one watertight solid, not just a draped surface.
"""

from __future__ import annotations

import math
from typing import Protocol

import numpy as np
import shapely
import trimesh
from shapely.affinity import translate
from shapely.geometry import MultiPolygon, Polygon

from quadwright.resolve.terrain import HeightGrid


def build_terrain_plate(
    grid: HeightGrid,
    scale_mm_per_m: float,
    vertical_exaggeration: float,
    base_thickness_mm: float,
) -> trimesh.Trimesh:
    """Build the terrain base plate as a solid mesh, in model mm.

    To place a part on this same terrain (rather than at a flat z), build
    a `GroundHeightLookup` with the same grid/scale/exaggeration/thickness
    and call its `min_height_under()`.
    """
    n_rows, n_cols = grid.shape
    z_min_m = np.nanmin(grid.heights_m)

    # top_z_mm[row, col]: the lowest grid point sits at exactly
    # base_thickness_mm, everything else rises from there.
    top_z_mm = (
        grid.heights_m - z_min_m
    ) * scale_mm_per_m * vertical_exaggeration + base_thickness_mm

    xs_mm = np.arange(n_cols) * grid.cell_size_m * scale_mm_per_m
    ys_mm = np.arange(n_rows) * grid.cell_size_m * scale_mm_per_m

    top = _grid_surface(xs_mm, ys_mm, top_z_mm)
    bottom = _grid_surface(xs_mm, ys_mm, np.zeros_like(top_z_mm), flip=True)
    walls = _perimeter_walls(xs_mm, ys_mm, top_z_mm)

    solid = trimesh.util.concatenate([top, bottom, walls])
    solid.merge_vertices()  # top/bottom/walls share edges as separate vertices until welded
    if solid.volume < 0:
        solid.invert()
    return solid


class GroundSurface(Protocol):
    """Anything a building or part can be seated on: a terrain block or a flat slab."""

    def min_height_under(
        self, footprint_local: Polygon | MultiPolygon, position_on_base: tuple[float, float]
    ) -> float: ...


class FlatGround:
    """A flat base plate's top surface: the same height everywhere."""

    def __init__(self, top_mm: float):
        self._top_mm = top_mm

    def __call__(self, x_mm: float, y_mm: float) -> float:
        return self._top_mm

    def min_height_under(
        self, footprint_local: Polygon | MultiPolygon, position_on_base: tuple[float, float]
    ) -> float:
        return self._top_mm


class GroundHeightLookup:
    """Converts a local-mm (x, y) into the terrain's top-surface z, in model mm.

    Use the same grid/scale/exaggeration/thickness passed to
    `build_terrain_plate` so a part's base lines up with the mesh it sits on.

    "Lines up" is exact, not approximate: `build_terrain_plate` puts one
    vertex per grid cell and splits every cell into two triangles along
    the same diagonal, so the surface between vertices is flat triangles
    -- and this lookup interpolates on exactly those triangles. (Reading
    the nearest cell instead is off by up to a whole cell's worth of
    slope -- ~22m of real ground on unc-charlotte -- which shows up as
    buildings floating or sinking.)
    """

    def __init__(
        self,
        grid: HeightGrid,
        scale_mm_per_m: float,
        vertical_exaggeration: float,
        base_thickness_mm: float,
    ):
        # Same formula as build_terrain_plate's top_z_mm, so the two can't drift apart.
        z_min_m = np.nanmin(grid.heights_m)
        self._top_z_mm = (
            grid.heights_m - z_min_m
        ) * scale_mm_per_m * vertical_exaggeration + base_thickness_mm
        self._cell_mm = grid.cell_size_m * scale_mm_per_m

    def __call__(self, x_mm: float, y_mm: float) -> float:
        n_rows, n_cols = self._top_z_mm.shape
        # Position in grid units, clamped onto the mesh (a point past the
        # last vertex reads the edge height -- the mesh has no surface there).
        u = min(max(x_mm / self._cell_mm, 0.0), n_cols - 1)
        v = min(max(y_mm / self._cell_mm, 0.0), n_rows - 1)
        col, row = min(int(u), max(n_cols - 2, 0)), min(int(v), max(n_rows - 2, 0))
        fu, fv = u - col, v - row
        next_col, next_row = min(col + 1, n_cols - 1), min(row + 1, n_rows - 1)

        z = self._top_z_mm
        # Cell corners, named like _grid_surface's vertices: a=(row, col),
        # b=(row, col+1), c=(row+1, col), d=(row+1, col+1). Its two
        # triangles are (a, b, c) and (b, d, c), split along the b-c diagonal.
        za, zb = z[row, col], z[row, next_col]
        zc, zd = z[next_row, col], z[next_row, next_col]
        if fu + fv <= 1.0:  # in triangle a-b-c
            return float(za + fu * (zb - za) + fv * (zc - za))
        return float(zd + (1 - fu) * (zc - zd) + (1 - fv) * (zb - zd))  # in triangle b-d-c

    def min_height_under(
        self, footprint_local: Polygon | MultiPolygon, position_on_base: tuple[float, float]
    ) -> float:
        """The lowest terrain height anywhere under a part's full footprint, in model mm.

        Sampling ground height at only one point (e.g. a part's own local
        origin) lets a flat-bottomed part "float": its bottom touches
        ground at that one point while hovering above the (sloped)
        terrain everywhere else under it. So this returns the true
        minimum over the whole footprint, so the part's bottom always
        rests on or slightly into the terrain -- never above it.

        Exact, not sampled: the surface is flat triangles, and a flat
        (linear) function over a region bounded by straight lines reaches
        its minimum at a corner of that region. Overlaying the footprint
        on the triangle mesh, those corners are (1) the footprint's own
        vertices, (2) mesh vertices inside the footprint -- e.g. a dip
        under the middle of a big building that no wall touches -- and
        (3) points where a footprint edge crosses a triangle edge.
        Checking all three finds the minimum without guessing a sample
        spacing.
        """
        offset_x, offset_y = position_on_base
        placed = translate(footprint_local, xoff=offset_x, yoff=offset_y)
        return min(self(x, y) for x, y in self._candidate_points(placed))

    def _candidate_points(self, footprint: Polygon | MultiPolygon) -> list[tuple[float, float]]:
        cell = self._cell_mm
        polygons = footprint.geoms if isinstance(footprint, MultiPolygon) else [footprint]
        rings = [ring for polygon in polygons for ring in (polygon.exterior, *polygon.interiors)]
        points: list[tuple[float, float]] = []

        for ring in rings:
            coords = list(ring.coords)
            points.extend(coords)
            for (x0, y0), (x1, y1) in zip(coords, coords[1:], strict=False):
                # Triangle edges lie on three families of lines, in grid
                # units: x = k (columns), y = k (rows), and x + y = k (the
                # b-c diagonals). Along a segment each family's value
                # changes linearly, so solve for where it hits each integer.
                for f0, f1 in (
                    (x0 / cell, x1 / cell),
                    (y0 / cell, y1 / cell),
                    ((x0 + y0) / cell, (x1 + y1) / cell),
                ):
                    if f0 == f1:
                        continue
                    for k in range(math.ceil(min(f0, f1)), math.floor(max(f0, f1)) + 1):
                        t = (k - f0) / (f1 - f0)
                        points.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))

        min_x, min_y, max_x, max_y = footprint.bounds
        cols = np.arange(math.ceil(min_x / cell), math.floor(max_x / cell) + 1) * cell
        rows = np.arange(math.ceil(min_y / cell), math.floor(max_y / cell) + 1) * cell
        if len(cols) and len(rows):
            grid_x, grid_y = (a.ravel() for a in np.meshgrid(cols, rows))
            # Vertices exactly on the outline are already edge crossings above.
            inside = shapely.contains_xy(footprint, grid_x, grid_y)
            points.extend(zip(grid_x[inside], grid_y[inside], strict=True))
        return points


def _grid_surface(
    xs_mm: np.ndarray, ys_mm: np.ndarray, z_mm: np.ndarray, flip: bool = False
) -> trimesh.Trimesh:
    """Triangulate a regular XY grid at per-cell heights into a surface mesh."""
    n_rows, n_cols = z_mm.shape
    grid_x, grid_y = np.meshgrid(xs_mm, ys_mm)
    vertices = np.column_stack([grid_x.ravel(), grid_y.ravel(), z_mm.ravel()])

    def vertex_index(row: int, col: int) -> int:
        return row * n_cols + col

    faces = []
    for row in range(n_rows - 1):
        for col in range(n_cols - 1):
            a, b = vertex_index(row, col), vertex_index(row, col + 1)
            c, d = vertex_index(row + 1, col), vertex_index(row + 1, col + 1)
            faces.append((a, c, b) if flip else (a, b, c))
            faces.append((b, c, d) if flip else (b, d, c))

    return trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=False)


def _perimeter_walls(xs_mm: np.ndarray, ys_mm: np.ndarray, top_z_mm: np.ndarray) -> trimesh.Trimesh:
    """Build the vertical side walls connecting the top surface's edge down to z=0."""
    n_rows, n_cols = top_z_mm.shape

    def edge_points(rows: np.ndarray, cols: np.ndarray) -> list[tuple[float, float, float]]:
        return [(xs_mm[c], ys_mm[r], top_z_mm[r, c]) for r, c in zip(rows, cols, strict=True)]

    # Each segment drops its last point -- it's the next segment's first
    # point (a shared corner) -- so the loop has no duplicate vertices.
    perimeter = (
        edge_points(np.zeros(n_cols, dtype=int), np.arange(n_cols))[:-1]  # south, west->east
        + edge_points(np.arange(n_rows), np.full(n_rows, n_cols - 1))[:-1]  # east, south->north
        + edge_points(np.full(n_cols, n_rows - 1), np.arange(n_cols)[::-1])[
            :-1
        ]  # north, east->west
        + edge_points(np.arange(n_rows)[::-1], np.zeros(n_rows, dtype=int))[
            :-1
        ]  # west, north->south
    )

    top_vertices = np.array(perimeter)
    bottom_vertices = top_vertices.copy()
    bottom_vertices[:, 2] = 0.0
    vertices = np.vstack([top_vertices, bottom_vertices])

    n = len(perimeter)
    faces = []
    for i in range(n):
        j = (i + 1) % n
        top_i, top_j, bot_i, bot_j = i, j, i + n, j + n
        # The perimeter runs counter-clockwise seen from above, so going
        # top_i -> bot_i -> bot_j turns the normal outward -- matching the
        # top surface (normals up) and bottom (normals down). Winding these
        # the other way made the solid inside-out at its walls: still
        # watertight, but not a consistent volume.
        faces.append((top_i, bot_i, bot_j))
        faces.append((top_i, bot_j, top_j))

    return trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=False)
