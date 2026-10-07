"""Draw 2D previews: building footprints (FR-04) and the elevation grid (FR-15)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: this runs from the CLI, never a GUI session
import matplotlib.pyplot as plt
from shapely.geometry.base import BaseGeometry

from quadwright.model import Building
from quadwright.resolve.terrain import HeightGrid


def render_footprints(buildings: list[Building], out_path: str | Path) -> None:
    """Plot every building footprint (in local meters) and save it as a PNG."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots()
    for building in buildings:
        _add_polygon_patch(ax, building.footprint)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(f"{len(buildings)} building footprint(s)")
    fig.savefig(out_path)
    plt.close(fig)


def _add_polygon_patch(ax, geom: BaseGeometry) -> None:
    polygons = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for polygon in polygons:
        x, y = polygon.exterior.xy
        ax.fill(x, y, facecolor="tan", edgecolor="black", linewidth=0.5)


def render_heightmap(grid: HeightGrid, out_path: str | Path) -> None:
    """Plot the campus ground-elevation grid (real LIDAR data) as a colorized PNG."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots()
    # origin="lower": row 0 of the grid is its south edge (grid.origin_m),
    # matching how HeightGrid is built -- imshow's default would flip it.
    image = ax.imshow(grid.heights_m, origin="lower", cmap="terrain", aspect="equal")
    fig.colorbar(image, ax=ax, label="elevation (m)")
    ax.set_xlabel("x (grid cells)")
    ax.set_ylabel("y (grid cells)")
    low, high = grid.heights_m.min(), grid.heights_m.max()
    ax.set_title(f"Elevation: {low:.0f}-{high:.0f}m ({grid.cell_size_m:.1f}m/cell)")
    fig.savefig(out_path)
    plt.close(fig)
