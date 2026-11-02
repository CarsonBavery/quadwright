"""Draw previews: building footprints (FR-04), the elevation grid (FR-15), the 3D model (FR-21)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: this runs from the CLI, never a GUI session
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
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


def render_model(scene: trimesh.Scene, out_path: str | Path, title: str = "") -> None:
    """Render an assembled campus scene (FR-21) as oblique 3D views, saved as a PNG.

    Two panels: the whole kit, and a close-up of the densest part of
    campus (on a real campus the base is mostly lawn and woods, so at
    whole-kit size the buildings are hard to read).

    Everything in a panel goes into ONE Poly3DCollection on purpose:
    matplotlib's 3D renderer depth-sorts the faces *within* a collection,
    but draws separate collections whole, one after another -- so terrain
    and buildings as separate artists would paint over each other wrongly.
    Faces are shaded by hand (a fixed light from the northwest, as on a
    map), since Poly3DCollection only does flat, unlit color on its own.

    Proportions are true to the model (no extra vertical stretch beyond
    the config's own vertical_exaggeration), so this shows what the
    finished kit will actually look like.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    triangles, colors, normals, building_centers = [], [], [], []
    for node_name in scene.graph.nodes_geometry:
        transform, geometry_name = scene.graph[node_name]
        mesh = scene.geometry[geometry_name].copy()
        mesh.apply_transform(transform)
        triangles.append(mesh.triangles)
        normals.append(mesh.face_normals[:, 2])
        base_rgb = np.asarray(mesh.visual.material.baseColorFactor[:3], dtype=float) / 255
        colors.append(_shade(mesh.face_normals, base_rgb))
        if node_name != "base":
            building_centers.append(mesh.bounds.mean(axis=0)[:2])
    triangles = np.concatenate(triangles)
    colors = np.concatenate(colors)
    normals_z = np.concatenate(normals)

    fig = plt.figure(figsize=(18, 8), dpi=150)
    whole = fig.add_subplot(1, 2, 1, projection="3d")
    _draw_panel(whole, triangles, colors, "whole kit")

    if building_centers:
        # Crop to the campus core: the middle 80% of building centers in
        # each direction. Using every building's extent instead lets a few
        # outlying ones (a field house, a far parking deck) stretch the
        # "close-up" back to nearly the whole kit.
        centers_xy = np.array(building_centers)
        low = np.percentile(centers_xy, 10, axis=0)
        high = np.percentile(centers_xy, 90, axis=0)
        margin = 0.1 * max(high - low)
        face_centers = triangles.mean(axis=1)[:, :2]
        in_crop = np.all((face_centers >= low - margin) & (face_centers <= high + margin), axis=1)
        # Cropping exposes the base's underside along the cut edge; the
        # camera looks down from above, so downward faces are never wanted.
        in_crop &= normals_z >= 0
        close_up = fig.add_subplot(1, 2, 2, projection="3d")
        _draw_panel(close_up, triangles[in_crop], colors[in_crop], "campus core close-up")

    if title:
        fig.suptitle(title)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def _draw_panel(ax, triangles: np.ndarray, colors: np.ndarray, label: str) -> None:
    ax.add_collection3d(Poly3DCollection(triangles, facecolors=colors, edgecolors="none"))
    low, high = triangles.reshape(-1, 3).min(axis=0), triangles.reshape(-1, 3).max(axis=0)
    ax.set_xlim(low[0], high[0])
    ax.set_ylim(low[1], high[1])
    ax.set_zlim(low[2], high[2])
    ax.set_box_aspect(high - low)  # true model proportions, not matplotlib's default cube
    ax.view_init(elev=35, azim=-60)
    ax.set_axis_off()
    width, depth = high[0] - low[0], high[1] - low[1]
    ax.set_title(f"{label} ({width:.0f} x {depth:.0f} mm)")


def _shade(normals: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """Lambert shading: each face's color scaled by how squarely it faces the light."""
    light = np.array([-1.0, 1.0, 1.5])  # from the northwest and above
    light /= np.linalg.norm(light)
    brightness = 0.45 + 0.55 * np.clip(normals @ light, 0.0, 1.0)  # 0.45 ambient floor
    return np.clip(brightness[:, None] * rgb[None, :], 0.0, 1.0)
