"""FR-16: pick the machining setups a part needs, by tier."""

from quadwright.model import Tier
from quadwright.parts.setups import assign_setups


def test_fr16_block_gets_a_single_top_setup():
    setups = assign_setups(Tier.BLOCK)
    assert len(setups) == 1
    assert setups[0].index == 0
    assert setups[0].face_up == "top"


def test_fr16_merge_gets_a_single_top_setup():
    # Still its own standalone part once it survives build_parts's merge
    # passes, just a simple one -- same as BLOCK.
    setups = assign_setups(Tier.MERGE)
    assert len(setups) == 1
    assert setups[0].face_up == "top"


def test_fr16_rotated_gets_top_plus_all_four_sides():
    setups = assign_setups(Tier.ROTATED)
    assert [s.face_up for s in setups] == ["top", "north", "south", "east", "west"]
    assert [s.index for s in setups] == [0, 1, 2, 3, 4]


def test_fr16_hero_gets_the_same_full_set_as_rotated():
    assert assign_setups(Tier.HERO) == assign_setups(Tier.ROTATED)


def test_fr16_setups_have_no_mesh_path_yet():
    # Per-setup mesh export (one STL per machining orientation) is a
    # later increment; for now these are just the plan, not files.
    for setup in assign_setups(Tier.ROTATED):
        assert setup.mesh_path is None
