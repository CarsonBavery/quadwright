"""Extrude a ground-elevation height grid into a solid terrain block (FR-10).

The top surface follows real elevation; the bottom is one flat plane at
z=0, placed `base_thickness_mm` below the grid's *lowest* point -- so
every point of the block has at least that much material under it (the
low points, not the high points, are what a mill could cut through), and
the result is one watertight solid, not just a draped surface.
"""

from __future__ import annotations

import numpy as np
import trimesh

from quadwright.resolve.terrain import HeightGrid


def build_terrain_plate(
    grid: HeightGrid,
    scale_mm_per_m: float,
    vertical_exaggeration: float,
    base_thickness_mm: float,
) -> trimesh.Trimesh:
    """Build the terrain base plate as a solid mesh, in model mm.

    Returns the mesh together with a `ground_height_mm(x_mm, y_mm)`
    function closed over this same grid -- callers (parts placement) need
    it to sit each part at its local ground height instead of a flat z.
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


class GroundHeightLookup:
    """Converts a local-mm (x, y) into the terrain's top-surface z, in model mm.

    Use the same grid/scale/exaggeration/thickness passed to
    `build_terrain_plate` so a part's base lines up with the mesh it sits on.
    """

    def __init__(
        self,
        grid: HeightGrid,
        scale_mm_per_m: float,
        vertical_exaggeration: float,
        base_thickness_mm: float,
    ):
        self._grid = grid
        self._scale_mm_per_m = scale_mm_per_m
        self._vertical_exaggeration = vertical_exaggeration
        self._base_thickness_mm = base_thickness_mm
        self._z_min_m = np.nanmin(grid.heights_m)

    def __call__(self, x_mm: float, y_mm: float) -> float:
        x_m = self._grid.origin_m[0] + x_mm / self._scale_mm_per_m
        y_m = self._grid.origin_m[1] + y_mm / self._scale_mm_per_m
        elevation_m = self._grid.elevation_at(x_m, y_m)
        return (
            elevation_m - self._z_min_m
        ) * self._scale_mm_per_m * self._vertical_exaggeration + self._base_thickness_mm


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
        faces.append((top_i, top_j, bot_j))
        faces.append((top_i, bot_j, bot_i))

    return trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=False)
