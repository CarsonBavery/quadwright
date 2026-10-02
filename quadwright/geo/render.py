"""Draw a 2D preview of building footprints (FR-04)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: this runs from the CLI, never a GUI session
import matplotlib.pyplot as plt
from shapely.geometry.base import BaseGeometry

from quadwright.model import Building


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
