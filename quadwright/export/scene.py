"""Assemble the whole campus into one 3D scene for viewing (FR-21).

Part STLs are block-local (ADR-0003) -- every part sits at its own
origin, ready for the mill, so opening them shows a pile at (0, 0). This
module puts everything back where it belongs: the base, plus every
building at its own campus position, height, and ground level.

It draws *buildings*, not parts: a merged part is milled to its tallest
member's height (quadwright.parts.merge), but here each building keeps
its own measured height, so the preview shows the real campus. Buildings
are still grouped (and tinted) by the part they belong to, so the kit's
grouping is visible too.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon

from quadwright.mesh.extrude import extrude_box
from quadwright.mesh.terrain import GroundSurface
from quadwright.model import Building, Part

# sRGB colors for the two woods in the kit: walnut base, maple buildings.
# Maple gets a few close shades, cycled by part, so neighboring kit pieces
# are distinguishable without looking like different materials.
WALNUT_RGBA = (92, 64, 51, 255)
MAPLE_SHADES_RGBA = ((233, 211, 168, 255), (222, 196, 150, 255), (240, 222, 186, 255))

# glTF's convention is meters with +Y up; the model is millimeters with +Z
# up. Exporting with this transform makes a viewer show the kit at its
# real physical size (0.45m wide for unc-charlotte), standing upright.
_MM_Z_UP_TO_M_Y_UP = np.array(
    [
        [0.001, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.001, 0.0],  # new y (up) = old z
        [0.0, -0.001, 0.0, 0.0],  # new z (toward viewer) = -old y (north points away)
        [0.0, 0.0, 0.0, 1.0],
    ]
)


@dataclass(frozen=True)
class PlacedBuilding:
    """One building's mesh, in campus model mm, seated on the base."""

    osm_id: str
    name: str | None
    part_id: str | None
    mesh: trimesh.Trimesh


def seat_building(
    footprint_mm: Polygon | MultiPolygon, height_mm: float, ground: GroundSurface
) -> trimesh.Trimesh:
    """Extrude a campus-mm footprint and stand it on the ground beneath it.

    The bottom sits at the *lowest* ground under the footprint. On a
    slope that buries the uphill side a little -- which is what real
    buildings do (they're cut into hillsides) -- while seating at the
    highest or average point would leave a visible gap under the downhill
    side. It also matches how the height was measured: OSM's `height`
    tag and FR-20's LIDAR heights both count from the lowest ground
    contact, so the roof lands at the right absolute elevation.
    """
    base_z_mm = ground.min_height_under(footprint_mm, position_on_base=(0.0, 0.0))
    mesh = extrude_box(footprint_mm, height_mm)
    mesh.apply_translation([0.0, 0.0, base_z_mm])
    return mesh


def place_buildings(
    buildings: Iterable[Building],
    footprints_mm: dict[str, Polygon | MultiPolygon],
    heights_mm: dict[str, float],
    parts: Iterable[Part],
    ground: GroundSurface,
) -> list[PlacedBuilding]:
    """Seat every building on `ground`, tagged with the kit part it's milled in."""
    part_of = {osm_id: part.id for part in parts for osm_id in part.building_ids}
    return [
        PlacedBuilding(
            osm_id=b.osm_id,
            name=b.name,
            part_id=part_of.get(b.osm_id),
            mesh=seat_building(footprints_mm[b.osm_id], heights_mm[b.osm_id], ground),
        )
        for b in buildings
    ]


def build_campus_scene(
    base_mesh: trimesh.Trimesh, placed: Iterable[PlacedBuilding]
) -> trimesh.Scene:
    """One scene: the base plus every building, colored by wood, named for browsing.

    Node names are "<part id>/<building name> [<osm id>]", so a viewer's
    outline panel lists buildings grouped by the part they're milled in.
    """
    scene = trimesh.Scene()
    scene.add_geometry(_colored(base_mesh, WALNUT_RGBA), node_name="base", geom_name="base")

    part_shade: dict[str | None, tuple[int, int, int, int]] = {}
    for building in placed:
        if building.part_id not in part_shade:
            part_shade[building.part_id] = MAPLE_SHADES_RGBA[
                len(part_shade) % len(MAPLE_SHADES_RGBA)
            ]
        # Names aren't unique (one "University Recreation Center" is three
        # OSM ways), so the osm_id rides along to keep node names distinct.
        label = f"{building.name} [{building.osm_id}]" if building.name else building.osm_id
        node_name = f"{building.part_id or 'unassigned'}/{label}"
        scene.add_geometry(
            _colored(building.mesh, part_shade[building.part_id]),
            node_name=node_name,
            geom_name=building.osm_id,
        )
    return scene


def write_glb(scene: trimesh.Scene, path: str | Path) -> Path:
    """Export the scene as binary glTF at real physical size (meters, +Y up)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    exported = scene.copy()
    exported.apply_transform(_MM_Z_UP_TO_M_Y_UP)
    path.write_bytes(exported.export(file_type="glb"))
    return path


def _colored(mesh: trimesh.Trimesh, rgba: tuple[int, int, int, int]) -> trimesh.Trimesh:
    """A copy of `mesh` with a matte wood-colored material (PBR, which every glTF viewer reads)."""
    colored = mesh.copy()
    colored.visual = trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=rgba, metallicFactor=0.0, roughnessFactor=0.85
        )
    )
    return colored
