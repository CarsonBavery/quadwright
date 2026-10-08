"""FR-17: generate the tolerance-test coupon (pocket blank + test tenons)."""

import pytest

from quadwright.fab.coupon import (
    BLANK_THICKNESS_MM,
    NOMINAL_SIZE_MM,
    POCKET_DEPTH_MM,
    build_coupon,
    build_manifest,
)


def test_fr17_pocket_blank_is_watertight():
    coupon = build_coupon(clearances_mm=(0.1, 0.2))
    assert coupon.pockets.is_watertight


def test_fr17_tenons_are_watertight():
    coupon = build_coupon(clearances_mm=(0.1, 0.2))
    assert coupon.tenons.is_watertight


def test_fr17_pocket_volume_matches_blank_minus_pockets():
    clearances = (0.1, 0.2, 0.3)
    coupon = build_coupon(clearances_mm=clearances)
    n = len(clearances)
    blank_width = n * NOMINAL_SIZE_MM + (n + 1) * 15.0  # SPECIMEN_GAP_MM
    blank_depth = NOMINAL_SIZE_MM + 2 * 15.0
    blank_volume = blank_width * blank_depth * BLANK_THICKNESS_MM
    pocket_volume_each = NOMINAL_SIZE_MM * NOMINAL_SIZE_MM * POCKET_DEPTH_MM

    assert coupon.pockets.volume == pytest.approx(blank_volume - n * pocket_volume_each)


def test_fr17_each_tenon_is_smaller_than_the_nominal_pocket():
    # A tenon shrunk by clearance_mm on every side is (NOMINAL - 2*clearance)
    # per edge, so its volume should be strictly less than the pocket's.
    coupon = build_coupon(clearances_mm=(0.1,))
    nominal_volume = NOMINAL_SIZE_MM * NOMINAL_SIZE_MM * POCKET_DEPTH_MM
    expected = (NOMINAL_SIZE_MM - 2 * 0.1) ** 2 * POCKET_DEPTH_MM
    assert coupon.tenons.volume == pytest.approx(expected)
    assert coupon.tenons.volume < nominal_volume


def test_fr17_larger_clearance_means_a_smaller_tenon():
    tight = build_coupon(clearances_mm=(0.05,)).tenons
    loose = build_coupon(clearances_mm=(0.25,)).tenons
    assert loose.volume < tight.volume


def test_fr17_manifest_lists_every_clearance_in_order():
    manifest = build_manifest((0.05, 0.10, 0.15))
    assert "position 1: 0.05mm" in manifest
    assert "position 2: 0.10mm" in manifest
    assert "position 3: 0.15mm" in manifest
    assert (
        manifest.index("position 1") < manifest.index("position 2") < manifest.index("position 3")
    )
