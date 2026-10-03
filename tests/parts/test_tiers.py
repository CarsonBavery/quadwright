"""FR-07: assign a machining detail tier to each part."""

from shapely.geometry import Polygon

from quadwright.config import Tiers
from quadwright.model import Tier
from quadwright.parts.tiers import assign_tier

TOOL_DIAMETER_MM = 3.175  # matches configs/campuses/example-university.yaml
TIERS = Tiers(
    merge_below_tool_diameters=3, rotate_above_tool_diameters=20, overrides={"Clock Tower": 3}
)

TINY_SQUARE_MM = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])  # ~1mm, far below the merge threshold
ORDINARY_SQUARE_MM = Polygon([(0, 0), (50, 0), (50, 50), (0, 50)])  # well clear of both thresholds


def test_fr07_override_wins_even_for_a_tiny_footprint():
    # A hand-tuned HERO call overrides the automatic rules entirely.
    tier = assign_tier(
        TINY_SQUARE_MM,
        height_mm=5.0,
        name="Clock Tower",
        tool_diameter_mm=TOOL_DIAMETER_MM,
        tiers=TIERS,
    )
    assert tier == Tier.HERO


def test_fr07_tiny_footprint_is_merge():
    tier = assign_tier(
        TINY_SQUARE_MM, height_mm=30.0, name=None, tool_diameter_mm=TOOL_DIAMETER_MM, tiers=TIERS
    )
    assert tier == Tier.MERGE


def test_fr07_very_tall_part_is_rotated():
    tier = assign_tier(
        ORDINARY_SQUARE_MM,
        height_mm=500.0,
        name=None,
        tool_diameter_mm=TOOL_DIAMETER_MM,
        tiers=TIERS,
    )
    assert tier == Tier.ROTATED


def test_fr07_ordinary_part_is_block():
    tier = assign_tier(
        ORDINARY_SQUARE_MM,
        height_mm=30.0,
        name=None,
        tool_diameter_mm=TOOL_DIAMETER_MM,
        tiers=TIERS,
    )
    assert tier == Tier.BLOCK
