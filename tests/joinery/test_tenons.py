"""FR-18: build each Part's Joint from a measured clearance_mm."""

import pytest
from shapely.geometry import Point, Polygon, box

from quadwright.joinery import tenons
from quadwright.joinery.tenons import MissingClearanceError, _needs_dowel_fallback, build_joint


def test_fr18_needs_dowel_fallback_below_threshold():
    narrow = box(0, 0, 20, 1.0)  # narrowest side well under 2 tool diameters
    assert _needs_dowel_fallback(narrow, tool_diameter_mm=3.175) is True


def test_fr18_needs_dowel_fallback_above_threshold():
    roomy = box(0, 0, 20, 20)
    assert _needs_dowel_fallback(roomy, tool_diameter_mm=3.175) is False


def test_fr18_missing_clearance_raises():
    with pytest.raises(MissingClearanceError, match="maple"):
        build_joint(box(0, 0, 10, 10), "maple", None, tool_diameter_mm=3.0)


def test_fr18_tenon_shrinks_inward_by_clearance_on_every_edge(monkeypatch):
    monkeypatch.setattr(tenons, "_needs_dowel_fallback", lambda *_a: False)
    footprint = box(0, 0, 20, 20)

    joint = build_joint(footprint, "maple", clearance_mm=2.0, tool_diameter_mm=3.0)

    assert joint.kind == "tenon"
    assert isinstance(joint.tenon_shape, Polygon)
    assert joint.tenon_shape.bounds == pytest.approx((2.0, 2.0, 18.0, 18.0))


def test_fr18_dowel_fallback_places_two_points_inside_the_footprint(monkeypatch):
    monkeypatch.setattr(tenons, "_needs_dowel_fallback", lambda *_a: True)
    footprint = box(0, 0, 20, 10)  # wider than tall

    joint = build_joint(footprint, "maple", clearance_mm=0.15, tool_diameter_mm=3.0)

    assert joint.kind == "dowels"
    assert len(joint.dowel_points) == 2
    for x, y in joint.dowel_points:
        assert footprint.contains(Point(x, y))
    (x1, y1), (x2, y2) = joint.dowel_points
    assert y1 == y2  # placed along the wider axis
    assert x1 != x2
