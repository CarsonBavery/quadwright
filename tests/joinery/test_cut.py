"""FR-19: turn a Joint's shape data into real, cuttable boss/pocket geometry."""

import pytest
from shapely.geometry import box

from quadwright.joinery.cut import (
    DOWEL_DIAMETER_MM,
    POCKET_DEPTH_MM,
    boss_for_joint,
    pocket_cutter_for_part,
)
from quadwright.mesh.extrude import extrude_box
from quadwright.model import Joint, Part, Tier

FOOTPRINT = box(0, 0, 20, 20)


def _tenon_joint(clearance_mm: float = 0.1) -> Joint:
    return Joint(
        kind="tenon", clearance_mm=clearance_mm, tenon_shape=FOOTPRINT.buffer(-clearance_mm)
    )


def _dowel_joint(clearance_mm: float = 0.1) -> Joint:
    return Joint(kind="dowels", clearance_mm=clearance_mm, dowel_points=((5.0, 10.0), (15.0, 10.0)))


def _part(joint: Joint, position_on_base: tuple[float, float] = (100.0, 50.0)) -> Part:
    return Part(
        id="part-0000",
        building_ids=("way/1",),
        footprint_local=FOOTPRINT,
        height_mm=30.0,
        tier=Tier.BLOCK,
        position_on_base=position_on_base,
        joint=joint,
    )


def test_fr19_tenon_boss_sits_below_the_part_and_overshoots_into_it():
    boss = boss_for_joint(_tenon_joint())
    assert boss.bounds[0][2] == pytest.approx(-POCKET_DEPTH_MM)
    assert boss.bounds[1][2] > 0  # overshoots past z=0, into the part's box


def test_fr19_dowel_boss_has_two_separate_pins():
    boss = boss_for_joint(_dowel_joint())
    assert len(boss.split()) == 2


def test_fr19_boss_unions_cleanly_onto_the_part():
    box_mesh = extrude_box(FOOTPRINT, height_mm=30.0)
    part_mesh = box_mesh.union(boss_for_joint(_tenon_joint()))
    assert part_mesh.is_watertight
    assert part_mesh.volume > box_mesh.volume


def test_fr19_pocket_cutter_uses_the_nominal_footprint_at_the_part_s_position():
    part = _part(_tenon_joint())
    cutter = pocket_cutter_for_part(part, base_top_mm=6.0)
    offset_x, offset_y = part.position_on_base
    assert cutter.bounds[0][:2] == pytest.approx((offset_x, offset_y))
    assert cutter.bounds[1][:2] == pytest.approx((offset_x + 20.0, offset_y + 20.0))


def test_fr19_dowel_pocket_cutter_has_two_separate_holes():
    part = _part(_dowel_joint())
    cutter = pocket_cutter_for_part(part, base_top_mm=6.0)
    assert len(cutter.split()) == 2


def test_fr19_pocket_cutter_subtracts_cleanly_from_the_base():
    base = extrude_box(box(0, 0, 400, 400), height_mm=6.0)
    part = _part(_tenon_joint(), position_on_base=(100.0, 100.0))
    pocketed = base.difference(pocket_cutter_for_part(part, base_top_mm=6.0))
    assert pocketed.is_watertight
    assert pocketed.volume < base.volume


def test_fr19_dowel_boss_pin_is_smaller_than_the_matching_pocket_hole():
    clearance_mm = 0.3
    boss_radius_mm = DOWEL_DIAMETER_MM / 2 - clearance_mm
    pin = boss_for_joint(_dowel_joint(clearance_mm)).split()[0]
    pin_radius_mm = (pin.bounds[1][0] - pin.bounds[0][0]) / 2
    assert pin_radius_mm == pytest.approx(boss_radius_mm, abs=1e-3)

    part = _part(_dowel_joint(clearance_mm))
    hole = pocket_cutter_for_part(part, base_top_mm=6.0).split()[0]
    hole_radius_mm = (hole.bounds[1][0] - hole.bounds[0][0]) / 2
    assert hole_radius_mm == pytest.approx(DOWEL_DIAMETER_MM / 2, abs=1e-3)
    assert pin_radius_mm < hole_radius_mm
