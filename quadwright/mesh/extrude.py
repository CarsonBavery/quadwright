"""Build 3D meshes from model-scale footprints and the base plate (FR-06).

ADR-0004: buildings are milled as separate parts rather than unioned into
one mesh, so each footprint becomes its own box here -- no boolean ops.
"""

from __future__ import annotations

import trimesh
from shapely.geometry import MultiPolygon, Polygon

BASE_PLATE_THICKNESS_MM = 6.0  # a plain slab for now; joinery pockets come in a later milestone


def extrude_box(footprint_mm: Polygon | MultiPolygon, height_mm: float) -> trimesh.Trimesh:
    """Extrude a flat-roofed box from a part-local footprint, in model mm.

    Every building is a flat-topped box for this first pass -- gabled and
    hipped roofs need `resolve`'s roof-shape logic, which doesn't exist yet.

    Some real OSM buildings (relations with multiple ways) normalize to a
    MultiPolygon rather than a single Polygon -- extrude each piece and
    stitch them into one mesh, since trimesh only extrudes one ring at a time.
    """
    if isinstance(footprint_mm, MultiPolygon):
        parts = [trimesh.creation.extrude_polygon(piece, height_mm) for piece in footprint_mm.geoms]
        return trimesh.util.concatenate(parts)
    return trimesh.creation.extrude_polygon(footprint_mm, height_mm)


def build_base_plate(
    outline_mm: Polygon, thickness_mm: float = BASE_PLATE_THICKNESS_MM
) -> trimesh.Trimesh:
    """Extrude the campus outline into the flat slab every part sits on."""
    return trimesh.creation.extrude_polygon(outline_mm, thickness_mm)
