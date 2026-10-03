"""Convert resolved buildings from real-world meters into model-scale millimeters (FR-06).

Everything upstream of this module works in meters; everything downstream
is in millimeters at model scale, per CLAUDE.md's naming convention
("_m" suffix means meters, everything else is mm).
"""

from __future__ import annotations

from shapely import affinity
from shapely.geometry import Polygon

from quadwright.config import Scale


def compute_scale_mm_per_m(scale: Scale, bbox_width_m: float, bbox_height_m: float) -> float:
    """Work out how many model millimeters correspond to one real-world meter.

    `bbox_width_m`/`bbox_height_m` are the campus bounding box's extent in
    local UTM meters (west-east, south-north) -- see
    `quadwright.geo.footprints.campus_bbox_local`. `scale` is validated so
    that exactly one of `scale.ratio` / `scale.target_size_mm` is set (see
    quadwright.config.Scale), so you only need to handle those two cases.

    TODO(you): implement the scale math:
    - If `scale.ratio` is set (e.g. 2500 means "1:2500"), it's direct:
      1 real meter -> 1000 / ratio model millimeters.
    - If `scale.target_size_mm` is set instead, the whole campus must fit
      inside that (width_mm, height_mm) box. Scaling width and height by
      *different* factors would stretch every building out of shape, so
      pick one uniform factor -- and decide how to pick it so the campus
      still fits both dimensions of the target box. (Hint: compute what
      factor each dimension alone would allow, then think about which of
      the two keeps you inside the box.)

    `vertical_exaggeration` does NOT belong here -- that only scales
    height, applied separately where height_mm gets computed.
    """
    raise NotImplementedError("compute_scale_mm_per_m: implement the scale math")


def to_model_mm(
    footprint_m: Polygon, origin_m: tuple[float, float], scale_mm_per_m: float
) -> Polygon:
    """Move a footprint so it's relative to the campus origin, then scale meters to mm."""
    origin_x_m, origin_y_m = origin_m
    shifted = affinity.translate(footprint_m, xoff=-origin_x_m, yoff=-origin_y_m)
    return affinity.scale(shifted, xfact=scale_mm_per_m, yfact=scale_mm_per_m, origin=(0, 0))
