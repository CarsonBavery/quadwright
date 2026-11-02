"""Merge buildings into machinable Parts (FR-07, FR-23, ADR-0006).

ADR-0004: buildings are milled as separate parts. ADR-0006 narrows when
two buildings may share one: only when they share a wall or sit at most
`tiers.merge_gap_mm` apart *at model scale* -- a gap so small the base
couldn't keep a wall between their two pockets anyway. Buildings any
farther apart stay separate parts, however small; parts narrower than
the tool itself are dropped, since there's nothing the mill can shape.
"""

from __future__ import annotations

from shapely.affinity import translate
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import nearest_points, unary_union

from quadwright.config import Tiers
from quadwright.joinery.tenons import build_joint
from quadwright.model import Building, Part, Tier
from quadwright.parts.setups import assign_setups
from quadwright.parts.tiers import assign_tier

# Closing bridges gaps up to merge_gap_mm. A gap of *exactly* that width
# would have its two buffers meet at a single point, which the shrink-back
# step can pinch apart again -- 10 microns of extra reach (far below
# anything a mill resolves) makes the bridge reliably solid.
_CLOSING_MARGIN_MM = 0.01


def group_nearby_buildings(
    buildings: list[Building], footprints_mm: dict[str, Polygon], max_gap_mm: float
) -> list[list[Building]]:
    """Cluster buildings whose model-mm footprints are at most `max_gap_mm` apart.

    Touching footprints (shared walls, multi-way relations) are 0mm apart,
    so they always group. Chains group transitively: A-B close and B-C
    close puts all three together even if A and C are far apart -- they
    end up in one blank either way, since B connects them.

    Plain O(n^2) flood fill -- fine for the hundreds of buildings a campus
    has, not meant to scale to a planet-sized dataset.
    """
    groups: list[list[Building]] = []
    remaining = list(buildings)

    while remaining:
        group = [remaining.pop(0)]
        frontier = [group[0]]
        while frontier:
            current = footprints_mm[frontier.pop().osm_id]
            still_remaining = []
            for candidate in remaining:
                if current.distance(footprints_mm[candidate.osm_id]) <= max_gap_mm:
                    group.append(candidate)
                    frontier.append(candidate)
                else:
                    still_remaining.append(candidate)
            remaining = still_remaining
        groups.append(group)

    return groups


def group_footprint(
    group: list[Building], footprints_mm: dict[str, Polygon], max_gap_mm: float
) -> Polygon | MultiPolygon:
    """The one solid outline a group is milled as, in campus mm.

    A plain union of buildings that only *nearly* touch is still separate
    islands -- not one piece of wood. A morphological closing (grow every
    edge outward by half the gap, union, then shrink back by the same
    amount) fills each gap up to `max_gap_mm` while leaving outer walls
    where they were. "mitre" joins keep square building corners square
    instead of rounding them off. Single-piece unions skip it untouched.

    Closing only fills a gap where two walls *face* each other. Buildings
    offset corner-to-corner overlap in just a sliver when grown, which
    the shrink-back erodes away again (4 such parts on unc-charlotte).
    Any islands left get an explicit bridge: a strip as wide as the gap
    between their two nearest points. A bridge overlaps both islands, so
    each pass leaves one fewer, and the loop always ends at one Polygon.
    """
    union = unary_union([footprints_mm[b.osm_id] for b in group])
    if not isinstance(union, MultiPolygon):
        return union
    reach_mm = max_gap_mm / 2 + _CLOSING_MARGIN_MM
    outline = union.buffer(reach_mm, join_style="mitre").buffer(-reach_mm, join_style="mitre")

    while isinstance(outline, MultiPolygon):
        largest, *others = sorted(outline.geoms, key=lambda island: island.area, reverse=True)
        nearest = min(others, key=largest.distance)
        a, b = nearest_points(largest, nearest)
        bridge = LineString([a, b]).buffer(reach_mm)
        outline = unary_union([outline, bridge])
    return outline


def narrower_than_tool(footprint_mm: Polygon | MultiPolygon, tool_diameter_mm: float) -> bool:
    """True when the footprint's narrowest bounding-box side is under one tool diameter.

    Same bounding-box measure assign_tier uses (quadwright.parts.tiers), so
    "too narrow to mill" and "small enough to be tier MERGE" agree on what
    "narrow" means.
    """
    min_x, min_y, max_x, max_y = footprint_mm.bounds
    return min(max_x - min_x, max_y - min_y) < tool_diameter_mm


def _group_tier(
    group: list[Building],
    footprint: Polygon,
    heights_mm: dict[str, float],
    tool_diameter_mm: float,
    tiers: Tiers,
) -> Tier:
    height_mm = max(heights_mm[b.osm_id] for b in group)
    name = next((b.name for b in group if b.name is not None), None)
    return assign_tier(footprint, height_mm, name, tool_diameter_mm, tiers)


def build_parts(
    buildings: list[Building],
    footprints_mm: dict[str, Polygon],
    heights_mm: dict[str, float],
    tool_diameter_mm: float,
    tiers: Tiers,
    species: str = "maple",
    clearance_mm: float | None = None,
) -> list[Part]:
    """Group touching/near-touching buildings, one Part per group (FR-23).

    `footprints_mm`/`heights_mm` map each building's osm_id to its already
    campus-mm-scaled footprint/height (see `quadwright.mesh.scale.scale_buildings`).
    A merged part's height is its tallest member's height, since the whole
    group is milled from one blank. Output is in part-local mm (ADR-0003).

    Groups narrower than `tool_diameter_mm` are left out entirely -- a
    building that isn't in any returned Part's `building_ids` was dropped,
    which is how callers list what got skipped.

    `species` should be the campus config's `materials.buildings`. Each
    part's `setups` come from its tier (FR-16, see `assign_setups`).
    `clearance_mm` is that species' measured coupon-test value (FR-17/FR-18,
    see `quadwright.config.load_species_config`); `None` propagates into
    `build_joint` raising `MissingClearanceError`.
    """
    groups = group_nearby_buildings(buildings, footprints_mm, tiers.merge_gap_mm)

    parts: list[Part] = []
    for group in groups:
        footprint = group_footprint(group, footprints_mm, tiers.merge_gap_mm)
        if narrower_than_tool(footprint, tool_diameter_mm):
            continue
        min_x, min_y = footprint.bounds[:2]
        footprint_local = translate(footprint, xoff=-min_x, yoff=-min_y)
        height_mm = max(heights_mm[b.osm_id] for b in group)
        tier = _group_tier(group, footprint_local, heights_mm, tool_diameter_mm, tiers)
        joint = build_joint(footprint_local, species, clearance_mm, tool_diameter_mm)
        parts.append(
            Part(
                # Numbered after dropping, so kept parts' ids stay sequential.
                id=f"part-{len(parts):04d}",
                building_ids=tuple(b.osm_id for b in group),
                footprint_local=footprint_local,
                height_mm=height_mm,
                tier=tier,
                position_on_base=(min_x, min_y),
                species=species,
                setups=assign_setups(tier),
                joint=joint,
            )
        )
    return parts
