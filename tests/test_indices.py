import numpy as np
import pytest

from tools.indices import cloud_mask, ndvi, normalized_difference, summarize, to_reflectance


def test_normalized_difference_basic():
    assert normalized_difference(np.array([3.0]), np.array([1.0]))[0] == pytest.approx(0.5)


def test_normalized_difference_zero_denominator_is_nan():
    assert np.isnan(normalized_difference(np.array([0.0]), np.array([0.0]))[0])


def test_cloud_mask_flags_clouds_and_shadows():
    scl = np.array([[4, 9], [3, 6]], dtype=np.uint8)
    assert cloud_mask(scl).tolist() == [[True, False], [False, True]]


def test_reflectance_applies_scale_and_offset():
    dn = np.array([2000], dtype=np.uint16)
    assert to_reflectance(dn)[0] == pytest.approx(0.1)                      # defaults: 2000 * 0.0001 - 0.1


def test_reflectance_uses_the_scene_calibration():
    dn = np.array([2000], dtype=np.uint16)
    assert to_reflectance(dn, scale=0.0001, offset=0.0)[0] == pytest.approx(0.2)   # an older baseline


def test_ndvi_masks_invalid_pixels():
    nir = np.array([0.5, 0.5], dtype=np.float32)
    red = np.array([0.1, 0.1], dtype=np.float32)
    result = ndvi(nir, red, valid=np.array([True, False]))
    assert result[0] == pytest.approx(0.6667, abs=1e-3)
    assert np.isnan(result[1])


def test_summarize_all_nan():
    assert summarize(np.full((2, 2), np.nan, dtype=np.float32))["valid_fraction"] == 0.0
