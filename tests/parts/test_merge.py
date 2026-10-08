"""FR-07: merge touching buildings into machinable parts."""

import pytest
from shapely.geometry import Polygon

from quadwright.config import Tiers
from quadwright.joinery.tenons import MissingClearanceError
from quadwright.model import Building, Tier
from quadwright.parts.merge import build_parts, group_touching_buildings, merge_isolated_small_parts

# Fixture value, not a fabrication claim -- these tests check build_parts'
# own wiring (grouping, tiers, setups), not a particular species' real fit.
TEST_CLEARANCE_MM = 0.15


def _square(
    osm_id: str, x: float, y: float, size: float = 10.0, name: str | None = None
) -> Building:
    corners = [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]
    return Building(osm_id=osm_id, footprint=Polygon(corners), name=name)


def test_fr07_isolated_buildings_stay_separate():
    a = _square("way/1", 0, 0)
    b = _square("way/2", 1000, 1000)  # far away, never touches
    groups = group_touching_buildings([a, b])
    assert sorted(len(g) for g in groups) == [1, 1]


def test_fr07_touching_buildings_merge_into_one_group():
    a = _square("way/1", 0, 0, size=10)
    b = _square("way/2", 10, 0, size=10)  # shares the x=10 edge with a
    groups = group_touching_buildings([a, b])
    assert len(groups) == 1
    assert {bld.osm_id for bld in groups[0]} == {"way/1", "way/2"}


def test_fr07_transitive_touching_chain_merges_all():
    a = _square("way/1", 0, 0, size=10)
    b = _square("way/2", 10, 0, size=10)  # touches a
    c = _square("way/3", 20, 0, size=10)  # touches b, not a directly
    groups = group_touching_buildings([a, c, b])  # order shouldn't matter
    assert len(groups) == 1
    assert {bld.osm_id for bld in groups[0]} == {"way/1", "way/2", "way/3"}


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
DEFAULT_TIERS = Tiers()  # merge_below_tool_diameters=3 -> 9.525mm threshold at this tool size


def _footprints_and_heights(buildings: list[Building], height_mm: float = 30.0):
    footprints_mm = {b.osm_id: b.footprint for b in buildings}
    heights_mm = {b.osm_id: height_mm for b in buildings}
    return footprints_mm, heights_mm


def test_fr08_merges_isolated_small_neighbors_within_search_radius():
    # Each 5x5 square alone is tier MERGE (narrowest side 5 < 9.525), but
    # diagonally offset so their union's bounding box is 11x11 -- clearing
    # the threshold once combined. The gap between them (~1.4mm) is well
    # inside the 9.525mm search radius.
    a = _square("way/1", 0, 0, size=5)
    b = _square("way/2", 6, 6, size=5)
    footprints_mm, heights_mm = _footprints_and_heights([a, b])

    groups = merge_isolated_small_parts(
        [[a], [b]], footprints_mm, heights_mm, TOOL_DIAMETER_MM, DEFAULT_TIERS
    )

    assert len(groups) == 1
    assert {bld.osm_id for bld in groups[0]} == {"way/1", "way/2"}


def test_fr08_does_not_merge_across_a_gap_beyond_the_search_radius():
    a = _square("way/1", 0, 0, size=5)
    b = _square("way/2", 1000, 1000, size=5)  # far beyond the 9.525mm search radius
    footprints_mm, heights_mm = _footprints_and_heights([a, b])

    groups = merge_isolated_small_parts(
        [[a], [b]], footprints_mm, heights_mm, TOOL_DIAMETER_MM, DEFAULT_TIERS
    )

    assert sorted(len(g) for g in groups) == [1, 1]


def test_fr08_never_absorbs_into_a_hero_neighbor():
    # "Landmark" is tiny too, but a human already decided it's HERO -- it
    # must keep its own identity even though it's the only nearby group.
    tiny = _square("way/1", 0, 0, size=5)
    landmark = _square("way/2", 6, 6, size=5, name="Landmark")
    footprints_mm, heights_mm = _footprints_and_heights([tiny, landmark])
    tiers = Tiers(overrides={"Landmark": 3})

    groups = merge_isolated_small_parts(
        [[tiny], [landmark]], footprints_mm, heights_mm, TOOL_DIAMETER_MM, tiers
    )

    assert sorted(len(g) for g in groups) == [1, 1]


def test_fr07_build_parts_end_to_end_rescues_isolated_small_buildings():
    # No tier overrides here -- exercises the real assign_tier thresholds
    # together with both merge passes, the way `build` actually calls it.
    a = _square("way/1", 0, 0, size=5)
    b = _square("way/2", 6, 6, size=5)
    footprints_mm, heights_mm = _footprints_and_heights([a, b])

    parts = build_parts(
        [a, b],
        footprints_mm,
        heights_mm,
        TOOL_DIAMETER_MM,
        DEFAULT_TIERS,
        clearance_mm=TEST_CLEARANCE_MM,
    )

    assert len(parts) == 1
    assert parts[0].tier == Tier.BLOCK
