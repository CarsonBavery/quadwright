"""FR-07: merge touching buildings into machinable parts."""

from shapely.geometry import Polygon

from quadwright.config import Tiers
from quadwright.model import Building, Tier
from quadwright.parts.merge import build_parts, group_touching_buildings


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
)  # BLOCK, sidesteps assign_tier's unfinished thresholds


def test_fr07_build_parts_merges_footprints_and_takes_the_tallest_height():
    a = _square("way/1", 100, 0, size=10, name="Test Building")
    b = _square("way/2", 110, 0, size=10)
    footprints_mm = {"way/1": a.footprint, "way/2": b.footprint}
    heights_mm = {"way/1": 15.0, "way/2": 40.0}

    parts = build_parts([a, b], footprints_mm, heights_mm, tool_diameter_mm=3.175, tiers=TIERS)

    assert len(parts) == 1
    part = parts[0]
    assert set(part.building_ids) == {"way/1", "way/2"}
    assert part.height_mm == 40.0
    assert part.tier == Tier.BLOCK
    assert part.position_on_base == (100.0, 0.0)
    assert part.footprint_local.bounds[:2] == (0.0, 0.0)  # translated to its own local origin


def test_fr07_build_parts_assigns_sequential_ids():
    a = _square("way/1", 0, 0, name="Test Building")
    b = _square("way/2", 1000, 1000, name="Test Building")
    footprints_mm = {"way/1": a.footprint, "way/2": b.footprint}
    heights_mm = {"way/1": 10.0, "way/2": 10.0}

    parts = build_parts([a, b], footprints_mm, heights_mm, tool_diameter_mm=3.175, tiers=TIERS)

    assert {p.id for p in parts} == {"part-0000", "part-0001"}
