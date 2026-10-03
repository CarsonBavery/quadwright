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

    TODO(you): implement the threshold logic for everything else, using
    `tiers.merge_below_tool_diameters` and `tiers.rotate_above_tool_diameters`
    (see quadwright.config.Tiers) against `tool_diameter_mm`. The open
    design question: which measurement should drive which threshold?

    - `merge_below_tool_diameters`: a footprint only slightly bigger than
      the tool can't be milled usefully on its own. The *longest* side
      being small doesn't save it if it's a sliver -- use the footprint's
      narrowest dimension (its tightest bounding-box side) compared
      against `tool_diameter_mm * tiers.merge_below_tool_diameters`.
    - `rotate_above_tool_diameters`: ROTATED parts get extra setups to
      machine their sides (see Setup.face_up: "north"/"south"/"east"/
      "west"), which is a *height* problem -- a block too tall to reach
      its lower side details from one orientation. Compare `height_mm`
      against `tool_diameter_mm * tiers.rotate_above_tool_diameters`.
    - Anything that clears the rotate threshold is ROTATED; anything that
      doesn't clear the merge threshold is MERGE; otherwise it's BLOCK.
    - HERO only ever comes from `tiers.overrides` -- there's no automatic
      rule for it, hand-tuned landmarks are a human judgment call.
    """
    if name is not None and name in tiers.overrides:
        return Tier(tiers.overrides[name])

    raise NotImplementedError("assign_tier: implement the threshold logic")
