"""FR-16: render a per-part setup checklist for the physical kit."""

from shapely.geometry import Polygon

from quadwright.model import Part, Setup, Tier
from quadwright.parts.sheets import build_setup_sheets


def _part(part_id: str, tier: Tier, setups: tuple[Setup, ...]) -> Part:
    return Part(
        id=part_id,
        building_ids=("way/1",),
        footprint_local=Polygon([(0, 0), (5, 0), (5, 5), (0, 5)]),
        height_mm=10.0,
        tier=tier,
        position_on_base=(0.0, 0.0),
        setups=setups,
    )


def test_fr16_reports_total_part_count():
    sheets = build_setup_sheets([_part("p1", Tier.BLOCK, (Setup(index=0, face_up="top"),))])
    assert "Setup sheets: 1 part(s)" in sheets


def test_fr16_lists_each_setup_with_its_face():
    setups = (
        Setup(index=0, face_up="top"),
        Setup(index=1, face_up="north"),
    )
    sheets = build_setup_sheets([_part("p1", Tier.ROTATED, setups)])

    assert "p1 (ROTATED, 2 setup(s)):" in sheets
    assert "[0] face up: top" in sheets
    assert "[1] face up: north" in sheets


def test_fr16_covers_multiple_parts_in_order():
    parts = [
        _part("p1", Tier.BLOCK, (Setup(index=0, face_up="top"),)),
        _part("p2", Tier.BLOCK, (Setup(index=0, face_up="top"),)),
    ]
    sheets = build_setup_sheets(parts)
    assert sheets.index("p1") < sheets.index("p2")
