"""Decide each Part's Joint: footprint-shaped tenon, or two-dowel fallback (FR-18, ADR-0004).

Needs a real, measured `clearance_mm` (see quadwright.fab.coupon) -- there is no
built-in default, because a wrong guess here is a part that doesn't seat.
"""

from __future__ import annotations

from shapely.geometry import LineString, MultiPolygon, Polygon

from quadwright.model import Joint


class MissingClearanceError(ValueError):
    """Raised when a species has no measured clearance_mm yet."""


# TODO(carson): starting heuristic, not measured -- reconsider and tune.
# A footprint-shaped tenon on a tiny part leaves almost no wall between the
# tenon's shrunk outline and the tool path that cut the matching pocket --
# below some size it stops self-registering and becomes a fragile sliver.
# ADR-0004 says "small parts fall back to two dowels" but doesn't say how
# small, so this reuses assign_tier's tool-diameter-relative style
# (quadwright.parts.tiers) rather than inventing a new kind of threshold.
# Tier.MERGE parts already got bulked up by merge_isolated_small_parts
# (quadwright/parts/merge.py) before this runs, so "small" here means
# "still small despite that merge pass".
DOWEL_FALLBACK_BELOW_TOOL_DIAMETERS = 2.0


def _needs_dowel_fallback(footprint_local: Polygon, tool_diameter_mm: float) -> bool:
    """True when the footprint is too small for its own footprint-shaped tenon."""
    min_x, min_y, max_x, max_y = footprint_local.bounds
    narrowest_side_mm = min(max_x - min_x, max_y - min_y)
    return narrowest_side_mm < tool_diameter_mm * DOWEL_FALLBACK_BELOW_TOOL_DIAMETERS


def _dowel_points(
    footprint_local: Polygon | MultiPolygon,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Two pin centers along the footprint's longer axis, guaranteed to land on material.

    Offsetting +/- a quarter-width from the centroid works for a rectangle,
    but a centroid can fall outside the shape: between the islands of a
    merged MultiPolygon part, or in the notch of an L/U-shaped building.
    On unc-charlotte that left one pin of 3 dowel parts hanging in mid-air.

    Instead, draw a line along the longer axis through a point shapely
    guarantees is inside the shape (`representative_point`), keep the
    stretch of that line that's actually inside, and put the pins at its
    1/4 and 3/4 marks -- for a rectangle, the same spots as before.
    A MultiPolygon pins its largest island: pins have to share one solid
    piece, and the biggest island has the most material to hold them.
    """
    if isinstance(footprint_local, MultiPolygon):
        footprint_local = max(footprint_local.geoms, key=lambda island: island.area)

    anchor = footprint_local.representative_point()
    min_x, min_y, max_x, max_y = footprint_local.bounds
    if (max_x - min_x) >= (max_y - min_y):
        axis = LineString([(min_x - 1, anchor.y), (max_x + 1, anchor.y)])
    else:
        axis = LineString([(anchor.x, min_y - 1), (anchor.x, max_y + 1)])

    # A concave shape can cut the axis into several inside stretches; use
    # the one through the anchor so both pins sit on the same solid run.
    inside = axis.intersection(footprint_local)
    stretches = inside.geoms if hasattr(inside, "geoms") else [inside]
    stretch = min(stretches, key=lambda s: s.distance(anchor))

    first = stretch.interpolate(0.25, normalized=True)
    second = stretch.interpolate(0.75, normalized=True)
    return (first.x, first.y), (second.x, second.y)


def build_joint(
    footprint_local: Polygon, species: str, clearance_mm: float | None, tool_diameter_mm: float
) -> Joint:
    """Build the Joint for one Part, in part-local mm.

    `clearance_mm` comes from that species' coupon test (configs/species/*.yaml);
    `None` means the coupon hasn't been cut and fit yet.
    """
    if clearance_mm is None:
        raise MissingClearanceError(
            f"{species} has no measured clearance_mm yet. Run "
            f"`quadwright coupon --species {species}`, cut and test-fit it, "
            f"then set clearance_mm in configs/species/{species}.yaml."
        )

    if _needs_dowel_fallback(footprint_local, tool_diameter_mm):
        dowel_points = _dowel_points(footprint_local)
        return Joint(kind="dowels", clearance_mm=clearance_mm, dowel_points=dowel_points)

    # Same uniform inward shrink as the coupon's test tenons (fab/coupon.py):
    # every wall of the tenon sits clearance_mm inside the footprint, so the
    # gap felt at each edge once seated is clearance_mm, not half of it.
    tenon_shape = footprint_local.buffer(-clearance_mm, join_style="mitre")
    return Joint(kind="tenon", clearance_mm=clearance_mm, tenon_shape=tenon_shape)
