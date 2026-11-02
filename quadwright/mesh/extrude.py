"""Build 3D meshes from model-scale footprints and the base plate (FR-06).

ADR-0004: buildings are milled as separate parts rather than unioned into
one mesh, so each footprint becomes its own box here -- no boolean ops.
(quadwright.joinery.cut adds each part's tenon/dowel boss and the base's
matching pockets on top of these boxes, FR-19 -- those booleans live
there, not here.)
"""

from __future__ import annotations

import trimesh
from shapely.geometry import MultiPolygon, Polygon

# Carson's minimum base thickness: the thinnest the base may be anywhere.
# A flat slab is exactly this thick; a terrain block (quadwright.mesh.terrain)
# has this much wood under its *lowest* point and rises with the topography
# above it, so each campus needs a thicker blank -- see base_stock_mm.
BASE_PLATE_THICKNESS_MM = 23.0

# 1 micron: far below any tool, far above floating-point noise (see extrude_box).
_SIMPLIFY_MM = 0.001


def extrude_box(footprint_mm: Polygon | MultiPolygon, height_mm: float) -> trimesh.Trimesh:
    """Extrude a flat-roofed box from a part-local footprint, in model mm.

    Every building is a flat-topped box for this first pass -- gabled and
    hipped roofs need `resolve`'s roof-shape logic, which doesn't exist yet.

    Some real OSM buildings (relations with multiple ways) normalize to a
    MultiPolygon rather than a single Polygon -- extrude each piece and
    stitch them into one mesh, since trimesh only extrudes one ring at a time.

    Shapely unions and buffers (quadwright.parts.merge) leave behind
    zero-length and micron-long edges; trimesh's triangulator turns those
    into a mesh that isn't a closed volume, and the joinery booleans then
    refuse it. Simplifying at _SIMPLIFY_MM removes them without moving any
    edge by more than a mill could ever resolve.
    """
    footprint_mm = footprint_mm.simplify(_SIMPLIFY_MM)
    if isinstance(footprint_mm, MultiPolygon):
        parts = [trimesh.creation.extrude_polygon(piece, height_mm) for piece in footprint_mm.geoms]
        return trimesh.util.concatenate(parts)
    return trimesh.creation.extrude_polygon(footprint_mm, height_mm)


def build_base_plate(
    outline_mm: Polygon, thickness_mm: float = BASE_PLATE_THICKNESS_MM
) -> trimesh.Trimesh:
    """Extrude the campus outline into the flat slab every part sits on."""
    return trimesh.creation.extrude_polygon(outline_mm, thickness_mm)


def base_stock_mm(base_mesh: trimesh.Trimesh) -> float:
    """How thick a blank the base must be milled from, in mm.

    Every base (flat slab or terrain block) has its flat bottom at z=0,
    so the stock needed is just its highest point: BASE_PLATE_THICKNESS_MM
    for a flat slab, that floor plus the campus's scaled relief for terrain.
    Pockets are cut downward from the top, so they never change this.
    """
    return float(base_mesh.bounds[1][2])
