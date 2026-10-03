"""Merge touching buildings into machinable Parts (FR-07).

ADR-0004: buildings are milled as separate parts, so only buildings whose
footprints actually touch or overlap (shared walls, multi-way relations)
get combined -- an isolated small building stays its own group and may
still come out tier MERGE, which is a signal for a future pass, not
something this stage resolves by picking an arbitrary neighbor.
"""

from __future__ import annotations

from shapely.affinity import translate
from shapely.geometry import Polygon
from shapely.ops import unary_union

from quadwright.config import Tiers
from quadwright.model import Building, Part
from quadwright.parts.tiers import assign_tier


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


def build_parts(
    buildings: list[Building],
    footprints_mm: dict[str, Polygon],
    heights_mm: dict[str, float],
    tool_diameter_mm: float,
    tiers: Tiers,
) -> list[Part]:
    """Group touching buildings, then build one Part per group, in part-local mm.

    `footprints_mm`/`heights_mm` map each building's osm_id to its already
    campus-mm-scaled footprint/height (see `quadwright.mesh.scale.scale_buildings`).
    A merged part's height is its tallest member's height, since the whole
    group is milled from one blank.
    """
    parts: list[Part] = []
    for index, group in enumerate(group_touching_buildings(buildings)):
        group_footprint = unary_union([footprints_mm[b.osm_id] for b in group])
        min_x, min_y = group_footprint.bounds[:2]
        footprint_local = translate(group_footprint, xoff=-min_x, yoff=-min_y)
        height_mm = max(heights_mm[b.osm_id] for b in group)
        name = next((b.name for b in group if b.name is not None), None)
        tier = assign_tier(footprint_local, height_mm, name, tool_diameter_mm, tiers)
        parts.append(
            Part(
                id=f"part-{index:04d}",
                building_ids=tuple(b.osm_id for b in group),
                footprint_local=footprint_local,
                height_mm=height_mm,
                tier=tier,
                position_on_base=(min_x, min_y),
            )
        )
    return parts
