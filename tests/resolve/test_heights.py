"""FR-05: rule-based height resolution for buildings."""

import pytest

from quadwright.config import Heights
from quadwright.resolve.heights import resolve_height

HEIGHTS = Heights(default_m=12.0, meters_per_level=3.5, overrides={"Old Main": 28.0})


def test_fr05_uses_override_by_name_even_with_a_height_tag():
    # The config override exists specifically to correct bad or missing OSM
    # data by hand, so it should win over whatever the tags say.
    height, source = resolve_height({"height": "10"}, "Old Main", HEIGHTS)
    assert (height, source) == (28.0, "override")


def test_fr05_uses_osm_height_tag_when_present():
    height, source = resolve_height({"height": "15.5"}, None, HEIGHTS)
    assert (height, source) == (15.5, "tag")


def test_fr05_parses_height_tag_with_unit_suffix():
    height, source = resolve_height({"height": "15.5 m"}, None, HEIGHTS)
    assert (height, source) == (15.5, "tag")


def test_fr05_falls_back_to_levels_times_meters_per_level():
    height, source = resolve_height({"building:levels": "4"}, None, HEIGHTS)
    assert height == pytest.approx(14.0)
    assert source == "levels"


def test_fr05_prefers_height_tag_over_levels():
    height, source = resolve_height({"height": "20", "building:levels": "4"}, None, HEIGHTS)
    assert (height, source) == (20.0, "tag")


def test_fr05_falls_back_to_default_when_nothing_else_matches():
    height, source = resolve_height({}, None, HEIGHTS)
    assert (height, source) == (12.0, "default")


def test_fr05_ignores_unparseable_height_tag_and_falls_through():
    # "~15" is a real OSM convention for an approximate height that
    # _parse_height_tag intentionally refuses to guess at.
    height, source = resolve_height({"height": "~15", "building:levels": "4"}, None, HEIGHTS)
    assert height == pytest.approx(14.0)
    assert source == "levels"
