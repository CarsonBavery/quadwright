"""FR-06: convert resolved buildings from meters to model-scale millimeters."""

import pytest
from shapely.geometry import Polygon

from quadwright.config import Scale
from quadwright.mesh.scale import compute_scale_mm_per_m, to_model_mm


def test_fr06_ratio_scale_is_direct():
    scale = Scale(ratio=2500)
    assert compute_scale_mm_per_m(scale, bbox_width_m=900, bbox_height_m=300) == pytest.approx(
        1000 / 2500
    )


def test_fr06_target_size_fits_the_tighter_dimension_width():
    # 900m x 300m campus into a 450x300mm box: width is the constraint
    # (450/900 = 0.5 mm/m), since height alone would allow 1.0 mm/m.
    scale = Scale(target_size_mm=(450, 300))
    assert compute_scale_mm_per_m(scale, bbox_width_m=900, bbox_height_m=300) == pytest.approx(0.5)


def test_fr06_target_size_fits_the_tighter_dimension_height():
    # 100m x 1000m campus into a 450x300mm box: height is the constraint
    # (300/1000 = 0.3 mm/m), since width alone would allow 4.5 mm/m.
    scale = Scale(target_size_mm=(450, 300))
    assert compute_scale_mm_per_m(scale, bbox_width_m=100, bbox_height_m=1000) == pytest.approx(0.3)


def test_fr06_to_model_mm_shifts_to_origin_and_scales():
    footprint_m = Polygon([(10, 20), (15, 20), (15, 25), (10, 25)])
    footprint_mm = to_model_mm(footprint_m, origin_m=(10, 20), scale_mm_per_m=2.0)
    assert list(footprint_mm.exterior.coords)[:4] == [(0, 0), (10, 0), (10, 10), (0, 10)]
