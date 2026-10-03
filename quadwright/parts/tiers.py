"""Assign a machining detail tier to each part (FR-07).

The tier drives how much per-part work later stages do: MERGE means the
footprint is too small to stand alone and should be combined with a
neighbor; ROTATED means the part needs extra machining setups (see
`quadwright.model.Setup`) beyond just the top face.
"""

from __future__ import annotations

from shapely.geometry import Polygon

from quadwright.config import Tiers
from quadwright.model import Tier


def assign_tier(
    footprint_mm: Polygon, height_mm: float, name: str | None, tool_diameter_mm: float, tiers: Tiers
) -> Tier:
    """Pick a Tier for one (possibly already-merged) part footprint, in model mm.

    `name` is checked against `tiers.overrides` first (see
    configs/campuses/*.yaml, e.g. `tiers.overrides: {"Clock Tower": 3}`) --
    a human already decided that building's tier, so it always wins.
    HERO only ever comes from an override; there's no automatic rule for
    "hand-tuned landmark".

    Otherwise, two independent thresholds (both in tool diameters):
    - `merge_below_tool_diameters`: a footprint only slightly bigger than
      the tool can't be milled usefully on its own. The *longest* side
      being small doesn't save it if it's a sliver, so this compares the
      footprint's narrowest bounding-box side against
      `tool_diameter_mm * tiers.merge_below_tool_diameters`.
    - `rotate_above_tool_diameters`: ROTATED parts get extra machining
      setups for their sides (see Setup.face_up: "north"/"south"/"east"/
      "west"), which is a *height* problem -- a block too tall to reach
      its lower side details from one orientation. Compares `height_mm`
      against `tool_diameter_mm * tiers.rotate_above_tool_diameters`.

    Clearing the rotate threshold wins over the merge check (a part can be
    both "too small" and "too tall", e.g. a narrow spire -- ROTATED is the
    more actionable signal), otherwise falling short of the merge
    threshold means MERGE, and anything left over is a plain BLOCK.
    """
    if name is not None and name in tiers.overrides:
        return Tier(tiers.overrides[name])

    min_x, min_y, max_x, max_y = footprint_mm.bounds
    narrowest_side_mm = min(max_x - min_x, max_y - min_y)

    if height_mm > tool_diameter_mm * tiers.rotate_above_tool_diameters:
        return Tier.ROTATED
    if narrowest_side_mm < tool_diameter_mm * tiers.merge_below_tool_diameters:
        return Tier.MERGE
    return Tier.BLOCK
