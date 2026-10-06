"""Summarize parts by tier, for the physical kit (FR-12).

Meant to travel with the kit: a woodworker's at-a-glance view of how
many blanks of each size/complexity to prep. Deliberately not a board-
footage or cost estimate -- that needs real stock dimensions and a yield
assumption this project doesn't have data for yet.
"""

from __future__ import annotations

from collections import Counter

from quadwright.model import Part, Tier

_TIER_ORDER = (Tier.HERO, Tier.ROTATED, Tier.BLOCK, Tier.MERGE)


def build_tier_report(parts: list[Part]) -> str:
    """Render a human-readable summary of parts grouped by tier."""
    lines = [f"Tier report: {len(parts)} part(s)", ""]

    for tier in _TIER_ORDER:
        tier_parts = [p for p in parts if p.tier == tier]
        if not tier_parts:
            continue
        lines.extend(_tier_section(tier, tier_parts))
        lines.append("")

    lines.append("Species:")
    for species, count in Counter(p.species for p in parts).most_common():
        lines.append(f"  {species}: {count} part(s)")

    return "\n".join(lines)


def _tier_section(tier: Tier, tier_parts: list[Part]) -> list[str]:
    total_buildings = sum(len(p.building_ids) for p in tier_parts)
    heights = [p.height_mm for p in tier_parts]
    widths = [p.footprint_local.bounds[2] - p.footprint_local.bounds[0] for p in tier_parts]
    depths = [p.footprint_local.bounds[3] - p.footprint_local.bounds[1] for p in tier_parts]

    return [
        f"{tier.name} ({len(tier_parts)} part(s), {total_buildings} building(s)):",
        f"  height mm:    min {min(heights):.1f}  max {max(heights):.1f}  avg {_mean(heights):.1f}",
        f"  footprint mm: width {min(widths):.1f}-{max(widths):.1f}  "
        f"depth {min(depths):.1f}-{max(depths):.1f}",
    ]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)
