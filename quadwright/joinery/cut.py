"""Turn a Joint's shape data into real, cuttable geometry (FR-19).

quadwright.joinery.tenons only decides *what* joint a part gets; this
module turns that decision into trimesh solids -- a boss to add to the
part, a matching pocket to subtract from the base plate.
"""

from __future__ import annotations

import trimesh
from shapely.affinity import translate

from quadwright.mesh.extrude import extrude_box
from quadwright.model import Joint, Part

# PLACEHOLDER -- not measured. 2mm keeps a comfortable 4mm of material
# above and below the pocket on today's 6mm BASE_PLATE_THICKNESS_MM
# (quadwright.mesh.extrude) -- the coupon's own 10mm pocket (fab/coupon.py)
# assumed a dedicated 15mm-thick test blank, not this base plate.
POCKET_DEPTH_MM = 2.0

# PLACEHOLDER -- not sized against real dowel stock yet.
DOWEL_DIAMETER_MM = 3.0

# Extra depth/height poking past the mating surface, so a boss/cutter never
# sits exactly coplanar with the face it's added to or cut from -- same
# trick as fab/coupon.py's pocket cutter (built POCKET_DEPTH_MM + 1.0 deep).
_OVERSHOOT_MM = 1.0


def boss_for_joint(joint: Joint, pocket_depth_mm: float = POCKET_DEPTH_MM) -> trimesh.Trimesh:
    """The boss to union onto a part's mesh, in part-local mm, below z=0.

    Tenon: the already-shrunk `joint.tenon_shape`. Dowels: a pin at each
    `joint.dowel_points`, shrunk the same uniform way (radius, not diameter).
    """
    height_mm = pocket_depth_mm + _OVERSHOOT_MM

    if joint.kind == "dowels":
        radius_mm = DOWEL_DIAMETER_MM / 2 - joint.clearance_mm
        pins = [
            _cylinder_at(x, y, height_mm / 2 - pocket_depth_mm, radius_mm, height_mm)
            for x, y in joint.dowel_points
        ]
        return trimesh.util.concatenate(pins)

    boss = extrude_box(joint.tenon_shape, height_mm)
    boss.apply_translation([0, 0, -pocket_depth_mm])
    return boss


def pocket_cutter_for_part(
    part: Part, base_top_mm: float, pocket_depth_mm: float = POCKET_DEPTH_MM
) -> trimesh.Trimesh:
    """The cutter to subtract from the base plate, in base-plate mm.

    `base_top_mm` is the base plate's flat top surface -- this only makes
    sense for a flat base (see cli.py's terrain_grid check), not a sloped
    terrain block. Tenon: the part's full (nominal, unshrunk) footprint,
    at `part.position_on_base`. Dowels: a hole at each dowel point, at
    full `DOWEL_DIAMETER_MM` (unshrunk, unlike the matching boss pin).
    """
    offset_x, offset_y = part.position_on_base
    floor_z = base_top_mm - pocket_depth_mm
    height_mm = pocket_depth_mm + _OVERSHOOT_MM
    joint = part.joint

    if joint.kind == "dowels":
        radius_mm = DOWEL_DIAMETER_MM / 2
        holes = [
            _cylinder_at(x + offset_x, y + offset_y, floor_z + height_mm / 2, radius_mm, height_mm)
            for x, y in joint.dowel_points
        ]
        return trimesh.util.concatenate(holes)

    footprint = translate(part.footprint_local, xoff=offset_x, yoff=offset_y)
    cutter = extrude_box(footprint, height_mm)
    cutter.apply_translation([0, 0, floor_z])
    return cutter


def _cylinder_at(
    x_mm: float, y_mm: float, z_mm: float, radius_mm: float, height_mm: float
) -> trimesh.Trimesh:
    cylinder = trimesh.creation.cylinder(radius=radius_mm, height=height_mm)
    cylinder.apply_translation([x_mm, y_mm, z_mm])
    return cylinder
