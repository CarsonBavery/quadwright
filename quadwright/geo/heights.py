"""Rule-based height resolution for buildings (FR-05).

Real OSM buildings rarely carry a height tag, so we fall back through
increasingly rough estimates. ADR-0005 keeps this rules-based: no ML
height model ships unless it beats this baseline on unseen campuses.
"""

from __future__ import annotations

from quadwright.config import Heights
from quadwright.model import HeightSource


def resolve_height(
    tags: dict[str, str], name: str | None, heights: Heights
) -> tuple[float, HeightSource]:
    """Pick a building's height in meters and say where it came from.

    `tags` are the raw OSM properties for one feature (e.g. may contain
    "height" and/or "building:levels"). `name` is the building's OSM name,
    used to look up `heights.overrides` (keyed by name -- see
    configs/campuses/*.yaml, e.g. `heights.overrides: {"Old Main": 28}`).

    TODO(you): implement the precedence. Return (height_m, source) where
    source is "override", "tag", "levels", or "default" (see HeightSource
    in quadwright/model.py).

    Things to weigh:
    - Should a config override win even over an explicit OSM height tag,
      or should real OSM data win when it's present? There's no one
      right answer -- pick one and the test names (test_fr05_*) will
      tell you if your reasoning matches what the test fixtures expect.
    - The OSM `height` tag is a string and sometimes has a unit suffix
      ("12.5 m"). Use `_parse_height_tag` below -- it's already handled,
      and returns None for anything it can't parse as plain meters.
    - `building:levels` is a *count* of floors, not meters -- multiply
      by `heights.meters_per_level` to convert.
    - If nothing above applies, fall back to `heights.default_m`.
    """
    raise NotImplementedError("resolve_height: implement the precedence rules")


def _parse_height_tag(value: str) -> float | None:
    """Parse an OSM `height` tag value (e.g. "12", "12.5", "12 m") to meters.

    Returns None for forms this simple baseline doesn't handle (e.g. the
    approximate "~15" or imperial "15'"), so callers can fall through to
    the next rule instead of crashing on messy real-world tag data.
    """
    text = value.strip().removesuffix("m").strip()
    try:
        return float(text)
    except ValueError:
        return None
