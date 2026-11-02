"""FR-07/FR-23: merge buildings that share a wall (or nearly do) into machinable parts."""

import pytest
from shapely.geometry import MultiPolygon, Polygon

from quadwright.config import Tiers
from quadwright.joinery.tenons import MissingClearanceError
from quadwright.model import Building, Tier
from quadwright.parts.merge import (
    build_parts,
    group_footprint,
    group_nearby_buildings,
    narrower_than_tool,
)

# Fixture value, not a fabrication claim -- these tests check build_parts'
# own wiring (grouping, tiers, setups), not a particular species' real fit.
TEST_CLEARANCE_MM = 0.15


def _square(
    osm_id: str, x: float, y: float, size: float = 10.0, name: str | None = None
) -> Building:
    corners = [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]
    return Building(osm_id=osm_id, footprint=Polygon(corners), name=name)


def _footprints(buildings: list[Building]) -> dict[str, Polygon]:
    # These fixtures are already "model mm", so footprint doubles as footprint_mm.
    return {b.osm_id: b.footprint for b in buildings}


def test_fr07_isolated_buildings_stay_separate():
    a = _square("way/1", 0, 0)
    b = _square("way/2", 1000, 1000)  # far away, never touches
    groups = group_nearby_buildings([a, b], _footprints([a, b]), max_gap_mm=0.5)
    assert sorted(len(g) for g in groups) == [1, 1]


def test_fr07_touching_buildings_merge_into_one_group():
    a = _square("way/1", 0, 0, size=10)
    b = _square("way/2", 10, 0, size=10)  # shares the x=10 edge with a
    groups = group_nearby_buildings([a, b], _footprints([a, b]), max_gap_mm=0.0)
    assert len(groups) == 1
    assert {bld.osm_id for bld in groups[0]} == {"way/1", "way/2"}


def test_fr07_transitive_touching_chain_merges_all():
    a = _square("way/1", 0, 0, size=10)
    b = _square("way/2", 10, 0, size=10)  # touches a
    c = _square("way/3", 20, 0, size=10)  # touches b, not a directly
    groups = group_nearby_buildings([a, c, b], _footprints([a, b, c]), max_gap_mm=0.0)
    assert len(groups) == 1  # order shouldn't matter
    assert {bld.osm_id for bld in groups[0]} == {"way/1", "way/2", "way/3"}


def test_fr23_buildings_within_the_gap_merge():
    a = _square("way/1", 0, 0)
    b = _square("way/2", 10.4, 0)  # 0.4mm apart: under the 0.5mm gap
    groups = group_nearby_buildings([a, b], _footprints([a, b]), max_gap_mm=0.5)
    assert len(groups) == 1


def test_fr23_buildings_beyond_the_gap_stay_separate_however_small():
    # The old FR-08 pass would have pulled these together (both tiny, 1mm
    # apart). ADR-0006: only shared walls or negligible gaps merge.
    a = _square("way/1", 0, 0, size=4)
    b = _square("way/2", 5, 0, size=4)
    groups = group_nearby_buildings([a, b], _footprints([a, b]), max_gap_mm=0.5)
    assert sorted(len(g) for g in groups) == [1, 1]


def test_fr23_group_footprint_bridges_the_gap_into_one_solid():
    a = _square("way/1", 0, 0)
    b = _square("way/2", 10.5, 0)  # exactly the gap -- the hardest case to bridge

    outline = group_footprint([a, b], _footprints([a, b]), max_gap_mm=0.5)

    assert isinstance(outline, Polygon)  # one piece of wood, not two islands
    assert outline.bounds == pytest.approx((0, 0, 20.5, 10), abs=1e-6)  # outer walls unmoved


def test_fr23_group_footprint_bridges_corner_to_corner_neighbors():
    # Diagonal offset: only the corners are 0.4mm apart, so no two walls
    # face each other and a closing alone can't hold the join (the case
    # four real unc-charlotte parts hit).
    a = _square("way/1", 0, 0)
    b = _square("way/2", 10.2828, 10.2828)  # corner gap = 0.2828 * sqrt(2) = 0.4mm

    outline = group_footprint([a, b], _footprints([a, b]), max_gap_mm=0.5)

    assert isinstance(outline, Polygon)
    assert outline.contains(a.footprint.buffer(-0.01))
    assert outline.contains(b.footprint.buffer(-0.01))


def test_fr23_group_footprint_leaves_a_single_building_untouched():
    a = _square("way/1", 0, 0)
    assert group_footprint([a], _footprints([a]), max_gap_mm=0.5).equals(a.footprint)


def test_fr23_narrower_than_tool():
    assert narrower_than_tool(Polygon([(0, 0), (20, 0), (20, 3), (0, 3)]), 3.175) is True
    assert narrower_than_tool(Polygon([(0, 0), (20, 0), (20, 4), (0, 4)]), 3.175) is False
    sliver_pair = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])])
    assert narrower_than_tool(sliver_pair, 3.175) is True


TIERS = Tiers(
    overrides={"Test Building": 1}
)  # BLOCK, isolates these tests from assign_tier's own rules


def test_fr07_build_parts_merges_footprints_and_takes_the_tallest_height():
    a = _square("way/1", 100, 0, size=10, name="Test Building")
    b = _square("way/2", 110, 0, size=10)
    footprints_mm = {"way/1": a.footprint, "way/2": b.footprint}
    heights_mm = {"way/1": 15.0, "way/2": 40.0}

    parts = build_parts(
        [a, b],
        footprints_mm,
        heights_mm,
        tool_diameter_mm=3.175,
        tiers=TIERS,
        clearance_mm=TEST_CLEARANCE_MM,
    )

    assert len(parts) == 1
    part = parts[0]
    assert set(part.building_ids) == {"way/1", "way/2"}
    assert part.height_mm == 40.0
    assert part.tier == Tier.BLOCK
    assert part.position_on_base == (100.0, 0.0)
    assert part.footprint_local.bounds[:2] == (0.0, 0.0)  # translated to its own local origin


def test_fr12_build_parts_uses_the_configured_species():
    a = _square("way/1", 0, 0, name="Test Building")
    footprints_mm, heights_mm = {"way/1": a.footprint}, {"way/1": 10.0}

    parts = build_parts(
        [a],
        footprints_mm,
        heights_mm,
        tool_diameter_mm=3.175,
        tiers=TIERS,
        species="walnut",
        clearance_mm=TEST_CLEARANCE_MM,
    )

    assert parts[0].species == "walnut"


def test_fr18_build_parts_raises_without_a_measured_clearance():
    a = _square("way/1", 0, 0, name="Test Building")
    footprints_mm, heights_mm = {"way/1": a.footprint}, {"way/1": 10.0}

    with pytest.raises(MissingClearanceError):
        build_parts([a], footprints_mm, heights_mm, tool_diameter_mm=3.175, tiers=TIERS)


def test_fr18_build_parts_attaches_a_joint():
    a = _square("way/1", 0, 0, name="Test Building")
    footprints_mm, heights_mm = {"way/1": a.footprint}, {"way/1": 10.0}

    parts = build_parts(
        [a],
        footprints_mm,
        heights_mm,
        tool_diameter_mm=3.175,
        tiers=TIERS,
        clearance_mm=TEST_CLEARANCE_MM,
    )

    assert parts[0].joint is not None
    assert parts[0].joint.clearance_mm == TEST_CLEARANCE_MM


def test_fr16_build_parts_assigns_setups_from_the_tier():
    block = _square("way/1", 0, 0, name="Test Building")  # BLOCK via TIERS override
    hero_tiers = Tiers(overrides={"Landmark": 3})
    hero = _square("way/2", 1000, 1000, name="Landmark")

    block_parts = build_parts(
        [block],
        {"way/1": block.footprint},
        {"way/1": 10.0},
        3.175,
        TIERS,
        clearance_mm=TEST_CLEARANCE_MM,
    )
    hero_parts = build_parts(
        [hero],
        {"way/2": hero.footprint},
        {"way/2": 10.0},
        3.175,
        hero_tiers,
        clearance_mm=TEST_CLEARANCE_MM,
    )

    assert [s.face_up for s in block_parts[0].setups] == ["top"]
    assert [s.face_up for s in hero_parts[0].setups] == ["top", "north", "south", "east", "west"]


def test_fr07_build_parts_assigns_sequential_ids():
    a = _square("way/1", 0, 0, name="Test Building")
    b = _square("way/2", 1000, 1000, name="Test Building")
    footprints_mm = {"way/1": a.footprint, "way/2": b.footprint}
    heights_mm = {"way/1": 10.0, "way/2": 10.0}

    parts = build_parts(
        [a, b],
        footprints_mm,
        heights_mm,
        tool_diameter_mm=3.175,
        tiers=TIERS,
        clearance_mm=TEST_CLEARANCE_MM,
    )

    assert {p.id for p in parts} == {"part-0000", "part-0001"}


TOOL_DIAMETER_MM = 3.175


def test_fr23_build_parts_drops_parts_narrower_than_the_tool():
    shed = _square("way/1", 0, 0, size=2)  # 2mm < 3.175mm tool
    hall = _square("way/2", 100, 100, size=20)
    buildings = [shed, hall]

    parts = build_parts(
        buildings,
        _footprints(buildings),
        {"way/1": 5.0, "way/2": 5.0},
        TOOL_DIAMETER_MM,
        Tiers(),
        clearance_mm=TEST_CLEARANCE_MM,
    )

    assert [p.building_ids for p in parts] == [("way/2",)]
    assert parts[0].id == "part-0000"  # numbered after dropping


def test_fr23_build_parts_keeps_a_tiny_building_that_shares_a_wall():
    # A 2mm shed is too narrow alone, but touching the hall it rides along.
    hall = _square("way/1", 0, 0, size=20)
    shed = _square("way/2", 20, 0, size=2)
    buildings = [hall, shed]

    parts = build_parts(
        buildings,
        _footprints(buildings),
        {"way/1": 5.0, "way/2": 2.0},
        TOOL_DIAMETER_MM,
        Tiers(),
        clearance_mm=TEST_CLEARANCE_MM,
    )

    assert len(parts) == 1
    assert set(parts[0].building_ids) == {"way/1", "way/2"}
