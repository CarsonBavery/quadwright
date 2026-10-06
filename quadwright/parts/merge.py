"""Merge buildings into machinable Parts (FR-07, FR-08).

ADR-0004: buildings are milled as separate parts. Two passes build up
each part's building list: first group_touching_buildings combines
footprints that physically touch (shared walls, multi-way relations),
then merge_isolated_small_parts pulls in a nearby neighbor for any group
still too small to stand alone on its own.
"""

from __future__ import annotations

from shapely.affinity import translate
from shapely.geometry import Polygon
from shapely.ops import unary_union

from quadwright.config import Tiers
from quadwright.model import Building, Part, Tier
from quadwright.parts.tiers import assign_tier

# Groups eligible to receive a merge: ordinary parts, or other small parts
# being folded in along the way. HERO (hand-tuned landmark) and ROTATED
# (already a complex multi-setup part) never silently absorb a neighbor.
_MERGEABLE_TARGET_TIERS = (Tier.MERGE, Tier.BLOCK)


def group_touching_buildings(buildings: list[Building]) -> list[list[Building]]:
    """Cluster buildings into connected components by footprint adjacency.

    Plain O(n^2) flood fill -- fine for the hundreds of buildings a campus
    has, not meant to scale to a planet-sized dataset.
    """
    groups: list[list[Building]] = []
    remaining = list(buildings)

    while remaining:
        group = [remaining.pop(0)]
        frontier = [group[0]]
        while frontier:
            current = frontier.pop()
            still_remaining = []
            for candidate in remaining:
                if current.footprint.intersects(candidate.footprint):
                    group.append(candidate)
                    frontier.append(candidate)
                else:
                    still_remaining.append(candidate)
            remaining = still_remaining
        groups.append(group)

    return groups


def _group_footprint(group: list[Building], footprints_mm: dict[str, Polygon]) -> Polygon:
    return unary_union([footprints_mm[b.osm_id] for b in group])


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


def merge_isolated_small_parts(
    groups: list[list[Building]],
    footprints_mm: dict[str, Polygon],
    heights_mm: dict[str, float],
    tool_diameter_mm: float,
    tiers: Tiers,
) -> list[list[Building]]:
    """Fold each still-too-small group into its nearest reachable neighbor.

    group_touching_buildings only joins footprints that literally touch,
    so most real buildings -- a little apart, not sharing a wall -- stay
    singleton groups and tier MERGE anyway. This closes that gap: a MERGE
    group repeatedly absorbs whichever other group is nearest (by gap
    distance, not centroid, so long thin buildings aren't penalized) as
    long as that neighbor is within `merge_below_tool_diameters` tool
    diameters -- reusing the same tolerance that defines "too small to
    stand alone" as the search radius for "close enough to combine with".
    On real unc-charlotte data, 651 of 661 isolated small buildings have
    a neighbor within 3 tool diameters, so this threshold does real work.

    A HERO (hand-tuned landmark) or ROTATED (already a complex part)
    group is never a merge *target* -- it can keep its own identity even
    while sitting right next to a tiny building that needs a home.
    """
    search_radius_mm = tool_diameter_mm * tiers.merge_below_tool_diameters

    live_groups = [list(g) for g in groups]
    footprints = [_group_footprint(g, footprints_mm) for g in live_groups]
    group_tiers = [
        _group_tier(g, fp, heights_mm, tool_diameter_mm, tiers)
        for g, fp in zip(live_groups, footprints, strict=True)
    ]

    i = 0
    while i < len(live_groups):
        if group_tiers[i] != Tier.MERGE:
            i += 1
            continue

        nearest_j = None
        nearest_distance = None
        for j in range(len(live_groups)):
            if j == i or group_tiers[j] not in _MERGEABLE_TARGET_TIERS:
                continue
            distance = footprints[i].distance(footprints[j])
            if distance <= search_radius_mm and (
                nearest_distance is None or distance < nearest_distance
            ):
                nearest_j, nearest_distance = j, distance

        if nearest_j is None:
            i += 1  # no reachable neighbor to merge with; stays isolated
            continue

        live_groups[i] = live_groups[i] + live_groups[nearest_j]
        footprints[i] = _group_footprint(live_groups[i], footprints_mm)
        group_tiers[i] = _group_tier(
            live_groups[i], footprints[i], heights_mm, tool_diameter_mm, tiers
        )
        del live_groups[nearest_j]
        del footprints[nearest_j]
        del group_tiers[nearest_j]
        if nearest_j < i:
            i -= 1  # everything after the deleted index shifted down by one

    return live_groups


def build_parts(
    buildings: list[Building],
    footprints_mm: dict[str, Polygon],
    heights_mm: dict[str, float],
    tool_diameter_mm: float,
    tiers: Tiers,
    species: str = "maple",
) -> list[Part]:
    """Group buildings (touching, then nearby-if-still-small), one Part per group.

    `footprints_mm`/`heights_mm` map each building's osm_id to its already
    campus-mm-scaled footprint/height (see `quadwright.mesh.scale.scale_buildings`).
    A merged part's height is its tallest member's height, since the whole
    group is milled from one blank. Output is in part-local mm (ADR-0003).
    `species` should be the campus config's `materials.buildings`.
    """
    groups = group_touching_buildings(buildings)
    groups = merge_isolated_small_parts(groups, footprints_mm, heights_mm, tool_diameter_mm, tiers)

    parts: list[Part] = []
    for index, group in enumerate(groups):
        group_footprint = _group_footprint(group, footprints_mm)
        min_x, min_y = group_footprint.bounds[:2]
        footprint_local = translate(group_footprint, xoff=-min_x, yoff=-min_y)
        height_mm = max(heights_mm[b.osm_id] for b in group)
        tier = _group_tier(group, footprint_local, heights_mm, tool_diameter_mm, tiers)
        parts.append(
            Part(
                id=f"part-{index:04d}",
                building_ids=tuple(b.osm_id for b in group),
                footprint_local=footprint_local,
                height_mm=height_mm,
                tier=tier,
                position_on_base=(min_x, min_y),
                species=species,
            )
        )
    return parts
