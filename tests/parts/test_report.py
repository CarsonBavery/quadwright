"""FR-12: summarize parts by tier for the physical kit."""

from shapely.geometry import Polygon

from quadwright.model import Building, Part, Tier
from quadwright.parts.report import build_tier_report


def _part(part_id: str, tier: Tier, height_mm: float, size: float, species: str = "maple") -> Part:
    return Part(
        id=part_id,
        building_ids=("way/1",),
        footprint_local=Polygon([(0, 0), (size, 0), (size, size), (0, size)]),
        height_mm=height_mm,
        tier=tier,
        position_on_base=(0.0, 0.0),
        species=species,
    )


def test_fr12_reports_total_part_count():
    report = build_tier_report([_part("p1", Tier.BLOCK, 10.0, 5.0)])
    assert "Tier report: 1 part(s)" in report


def test_fr12_groups_by_tier_in_priority_order():
    parts = [
        _part("p1", Tier.MERGE, 10.0, 5.0),
        _part("p2", Tier.HERO, 20.0, 15.0),
        _part("p3", Tier.BLOCK, 12.0, 8.0),
    ]
    report = build_tier_report(parts)

    # HERO's section should come before BLOCK's, which should come before MERGE's.
    assert report.index("HERO") < report.index("BLOCK") < report.index("MERGE")


def test_fr12_omits_tiers_with_no_parts():
    report = build_tier_report([_part("p1", Tier.BLOCK, 10.0, 5.0)])
    assert "HERO" not in report
    assert "ROTATED" not in report
    assert "MERGE" not in report


def test_fr12_reports_height_and_footprint_stats():
    parts = [_part("p1", Tier.BLOCK, 10.0, 5.0), _part("p2", Tier.BLOCK, 20.0, 7.0)]
    report = build_tier_report(parts)

    assert "min 10.0" in report
    assert "max 20.0" in report
    assert "avg 15.0" in report
    assert "width 5.0-7.0" in report
    assert "depth 5.0-7.0" in report


def test_fr12_counts_buildings_per_tier_not_just_parts():
    merged = Part(
        id="p1",
        building_ids=("way/1", "way/2", "way/3"),
        footprint_local=Polygon([(0, 0), (5, 0), (5, 5), (0, 5)]),
        height_mm=10.0,
        tier=Tier.BLOCK,
        position_on_base=(0.0, 0.0),
    )
    report = build_tier_report([merged])
    assert "1 part(s), 3 building(s)" in report


def test_fr12_summarizes_species_counts():
    parts = [
        _part("p1", Tier.BLOCK, 10.0, 5.0, species="maple"),
        _part("p2", Tier.BLOCK, 10.0, 5.0, species="maple"),
        _part("p3", Tier.BLOCK, 10.0, 5.0, species="walnut"),
    ]
    report = build_tier_report(parts)

    assert "maple: 2 part(s)" in report
    assert "walnut: 1 part(s)" in report


def test_fr23_lists_buildings_skipped_as_too_narrow():
    shed = Building(osm_id="way/9", footprint=None, name="Grounds Shed")
    kiosk = Building(osm_id="way/10", footprint=None)

    report = build_tier_report([_part("p1", Tier.BLOCK, 10.0, 5.0)], skipped=[shed, kiosk])

    assert "Skipped, narrower than the tool (2 building(s)):" in report
    assert "Grounds Shed [way/9]" in report
    assert "(unnamed) [way/10]" in report


def test_fr23_no_skipped_section_when_nothing_was_dropped():
    assert "Skipped" not in build_tier_report([_part("p1", Tier.BLOCK, 10.0, 5.0)])
