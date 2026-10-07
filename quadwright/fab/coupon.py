"""Generate the tolerance-test coupon (FR-17).

One pocket blank (all pockets the same nominal size) plus a row of test
tenons, each shrunk inward by a different clearance. Cut both, test-fit
each tenon in its pocket, and write the clearance that felt right into
that species' configs/species/<name>.yaml -- that's the real,
measured `clearance_mm` M5 Joinery is blocked on.

Not meant to mirror production tenons (ADR-0004's are footprint-shaped)
-- a simple square peg isolates the one variable this test is for.
"""

from __future__ import annotations

from dataclasses import dataclass

import trimesh
from shapely.geometry import box

NOMINAL_SIZE_MM = 20.0  # pocket side length, and each tenon's un-shrunk size
POCKET_DEPTH_MM = 10.0
BLANK_THICKNESS_MM = 15.0  # thicker than the pocket is deep, so it doesn't break through
SPECIMEN_GAP_MM = 15.0  # clearance between neighboring specimens (and from the blank's edge)
DEFAULT_CLEARANCES_MM = (0.05, 0.10, 0.15, 0.20, 0.25)


@dataclass(frozen=True)
class Coupon:
    """The two pieces to cut: a pocket blank, and a tray of test tenons."""

    pockets: trimesh.Trimesh
    tenons: trimesh.Trimesh
    clearances_mm: tuple[float, ...]


def build_coupon(clearances_mm: tuple[float, ...] = DEFAULT_CLEARANCES_MM) -> Coupon:
    """Build the pocket blank and the matching tenons, in model mm.

    Clearance is a uniform inward shrink (shapely buffer): each tenon
    wall sits `clearance_mm` inside the nominal square, so the gap felt
    at every edge once seated is that same clearance_mm -- not half of
    it, and not a diametral figure.
    """
    n = len(clearances_mm)
    blank_width = n * NOMINAL_SIZE_MM + (n + 1) * SPECIMEN_GAP_MM
    blank_depth = NOMINAL_SIZE_MM + 2 * SPECIMEN_GAP_MM

    blank = trimesh.creation.box(extents=[blank_width, blank_depth, BLANK_THICKNESS_MM])
    blank.apply_translation([blank_width / 2, blank_depth / 2, BLANK_THICKNESS_MM / 2])

    cutters = []
    tenons = []
    for i, clearance_mm in enumerate(clearances_mm):
        center_x = SPECIMEN_GAP_MM + i * (NOMINAL_SIZE_MM + SPECIMEN_GAP_MM) + NOMINAL_SIZE_MM / 2
        center_y = blank_depth / 2
        half = NOMINAL_SIZE_MM / 2
        pocket_2d = box(center_x - half, center_y - half, center_x + half, center_y + half)

        cutter = trimesh.creation.extrude_polygon(pocket_2d, POCKET_DEPTH_MM + 1.0)
        cutter.apply_translation([0, 0, BLANK_THICKNESS_MM - POCKET_DEPTH_MM])
        cutters.append(cutter)

        tenon_2d = pocket_2d.buffer(-clearance_mm, join_style="mitre")
        tenon = trimesh.creation.extrude_polygon(tenon_2d, POCKET_DEPTH_MM)
        tenon.apply_translation([0, blank_depth + SPECIMEN_GAP_MM, 0])
        tenons.append(tenon)

    pockets = blank.difference(cutters)
    return Coupon(
        pockets=pockets, tenons=trimesh.util.concatenate(tenons), clearances_mm=clearances_mm
    )


def build_manifest(clearances_mm: tuple[float, ...]) -> str:
    """A plain-text key: each tenon's position (left to right) to its clearance."""
    lines = [
        "Tolerance coupon: tenon positions, left to right, and their clearance_mm.",
        "Test-fit each tenon in the pocket blank's matching position; record which",
        "one felt snug-but-removable in that species' configs/species/<name>.yaml.",
        "",
    ]
    lines.extend(f"  position {i + 1}: {c:.2f}mm" for i, c in enumerate(clearances_mm))
    return "\n".join(lines) + "\n"
