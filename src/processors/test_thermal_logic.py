"""Tests for src/processors/thermal_logic.py."""

from __future__ import annotations

import numpy as np
import pytest

from src.processors.thermal_logic import (
    blend_with_landsat_calibration,
    compute_solar_aspect_multiplier,
    compute_surface_albedo,
    compute_thermal_logic,
    compute_uhi_offset,
)


# ---------------------------------------------------------------------------
# compute_surface_albedo tests
# ---------------------------------------------------------------------------


def test_compute_surface_albedo_zero_impervious():
    """Zero imperviousness (vegetation) should give maximum albedo (0.20)."""
    impervious = np.zeros((3, 3), dtype=np.float64)
    albedo = compute_surface_albedo(impervious)

    assert np.allclose(albedo, 0.20, atol=1e-6)


def test_compute_surface_albedo_full_impervious():
    """100% imperviousness (asphalt) should give minimum albedo (0.05)."""
    impervious = np.full((3, 3), 100.0, dtype=np.float64)
    albedo = compute_surface_albedo(impervious)

    assert np.allclose(albedo, 0.05, atol=1e-6)


def test_compute_surface_albedo_50_percent():
    """50% imperviousness should give albedo of 0.125."""
    impervious = np.full((3, 3), 50.0, dtype=np.float64)
    albedo = compute_surface_albedo(impervious)

    expected = 0.20 - (50.0 / 100.0) * 0.15
    assert np.allclose(albedo, expected, atol=1e-6)


def test_compute_surface_albedo_preserves_nan():
    """NaN values in imperviousness should be preserved in albedo."""
    impervious = np.full((3, 3), 50.0, dtype=np.float64)
    impervious[1, 1] = np.nan

    albedo = compute_surface_albedo(impervious)

    assert np.isnan(albedo[1, 1])
    assert not np.isnan(albedo[0, 0])


def test_compute_surface_albedo_range():
    """Albedo should always be in range [0.05, 0.20]."""
    impervious = np.random.rand(10, 10) * 100.0
    albedo = compute_surface_albedo(impervious)

    valid_albedo = albedo[~np.isnan(albedo)]
    assert np.all(valid_albedo >= 0.05)
    assert np.all(valid_albedo <= 0.20)


def test_compute_surface_albedo_monotonic():
    """Albedo should decrease monotonically with imperviousness."""
    impervious = np.array([[0.0, 25.0, 50.0, 75.0, 100.0]], dtype=np.float64)
    albedo = compute_surface_albedo(impervious)

    # Check that albedo decreases from left to right
    for i in range(len(albedo[0]) - 1):
        assert albedo[0, i] > albedo[0, i + 1]


# ---------------------------------------------------------------------------
# compute_solar_aspect_multiplier tests
# ---------------------------------------------------------------------------


def test_compute_solar_aspect_multiplier_south_facing():
    """South-facing slope (180°) should have multiplier 1.2."""
    aspect = np.full((3, 3), 180.0, dtype=np.float64)
    multiplier = compute_solar_aspect_multiplier(aspect)

    assert np.allclose(multiplier, 1.2, atol=1e-6)


def test_compute_solar_aspect_multiplier_north_facing():
    """North-facing slope (0° or 360°) should have multiplier 0.8."""
    aspect_0 = np.full((3, 3), 0.0, dtype=np.float64)
    multiplier_0 = compute_solar_aspect_multiplier(aspect_0)
    assert np.allclose(multiplier_0, 0.8, atol=1e-6)

    aspect_360 = np.full((3, 3), 360.0, dtype=np.float64)
    multiplier_360 = compute_solar_aspect_multiplier(aspect_360)
    assert np.allclose(multiplier_360, 0.8, atol=1e-6)


def test_compute_solar_aspect_multiplier_east_west():
    """East (90°) and west (270°) facing slopes should have multiplier 1.0."""
    aspect_90 = np.full((3, 3), 90.0, dtype=np.float64)
    multiplier_90 = compute_solar_aspect_multiplier(aspect_90)
    assert np.allclose(multiplier_90, 1.0, atol=1e-6)

    aspect_270 = np.full((3, 3), 270.0, dtype=np.float64)
    multiplier_270 = compute_solar_aspect_multiplier(aspect_270)
    assert np.allclose(multiplier_270, 1.0, atol=1e-6)


def test_compute_solar_aspect_multiplier_range():
    """Multiplier should always be in range [0.8, 1.2]."""
    aspect = np.random.rand(10, 10) * 360.0
    multiplier = compute_solar_aspect_multiplier(aspect)

    valid_mult = multiplier[~np.isnan(multiplier)]
    assert np.all(valid_mult >= 0.8)
    assert np.all(valid_mult <= 1.2)


def test_compute_solar_aspect_multiplier_preserves_nan():
    """NaN values in aspect should be preserved in multiplier."""
    aspect = np.full((3, 3), 180.0, dtype=np.float64)
    aspect[1, 1] = np.nan

    multiplier = compute_solar_aspect_multiplier(aspect)

    assert np.isnan(multiplier[1, 1])
    assert not np.isnan(multiplier[0, 0])


def test_compute_solar_aspect_multiplier_continuity():
    """Multiplier should vary smoothly with aspect."""
    aspect = np.array([[0.0, 45.0, 90.0, 135.0, 180.0]], dtype=np.float64)
    multiplier = compute_solar_aspect_multiplier(aspect)

    # Check that multiplier increases from 0° to 180°
    for i in range(len(multiplier[0]) - 1):
        assert multiplier[0, i] <= multiplier[0, i + 1]


# ---------------------------------------------------------------------------
# compute_uhi_offset tests
# ---------------------------------------------------------------------------


def test_compute_uhi_offset_zero_albedo():
    """Zero albedo (hypothetical) should give maximum UHI offset."""
    albedo = np.zeros((3, 3), dtype=np.float64)
    uhi_offset = compute_uhi_offset(albedo)

    # UHI offset = (0.20 - 0) * 200 / 5.5 * 9/5
    expected = 0.20 * 200.0 / 5.5 * (9.0 / 5.0)
    assert np.allclose(uhi_offset, expected, atol=1e-6)


def test_compute_uhi_offset_max_albedo():
    """Maximum albedo (0.20) should give zero UHI offset."""
    albedo = np.full((3, 3), 0.20, dtype=np.float64)
    uhi_offset = compute_uhi_offset(albedo)

    assert np.allclose(uhi_offset, 0.0, atol=1e-6)


def test_compute_uhi_offset_mid_albedo():
    """Mid-range albedo should give proportional UHI offset."""
    albedo = np.full((3, 3), 0.125, dtype=np.float64)
    uhi_offset = compute_uhi_offset(albedo)

    # UHI offset = (0.20 - 0.125) * 200 / 5.5 * 9/5
    expected = (0.20 - 0.125) * 200.0 / 5.5 * (9.0 / 5.0)
    assert np.allclose(uhi_offset, expected, atol=1e-6)


def test_compute_uhi_offset_preserves_nan():
    """NaN values in albedo should be preserved in UHI offset."""
    albedo = np.full((3, 3), 0.125, dtype=np.float64)
    albedo[1, 1] = np.nan

    uhi_offset = compute_uhi_offset(albedo)

    assert np.isnan(uhi_offset[1, 1])
    assert not np.isnan(uhi_offset[0, 0])


def test_compute_uhi_offset_non_negative():
    """UHI offset should always be non-negative (albedo ≤ 0.20)."""
    albedo = np.random.rand(10, 10) * 0.20
    uhi_offset = compute_uhi_offset(albedo)

    valid_offset = uhi_offset[~np.isnan(uhi_offset)]
    assert np.all(valid_offset >= 0.0)


# ---------------------------------------------------------------------------
# blend_with_landsat_calibration tests
# ---------------------------------------------------------------------------


def test_blend_with_landsat_calibration_no_landsat():
    """No Landsat data should return NLCD offset unchanged."""
    nlcd_offset = np.full((3, 3), 2.0, dtype=np.float64)
    impervious = np.full((3, 3), 50.0, dtype=np.float64)

    calibrated, warning = blend_with_landsat_calibration(
        nlcd_offset, None, impervious
    )

    assert np.allclose(calibrated, nlcd_offset)
    assert warning is None


def test_blend_with_landsat_calibration_insufficient_pixels():
    """Insufficient urban/rural pixels should return NLCD offset unchanged."""
    nlcd_offset = np.full((3, 3), 2.0, dtype=np.float64)
    impervious = np.full((3, 3), 50.0, dtype=np.float64)
    landsat_lst = np.full((3, 3), 25.0, dtype=np.float64)

    # Only 1 urban pixel (imperviousness >= 50%), not enough
    impervious[0, 0] = 60.0
    impervious[1:, :] = 5.0  # Rural

    calibrated, warning = blend_with_landsat_calibration(
        nlcd_offset, landsat_lst, impervious
    )

    # Should return NLCD offset unchanged
    assert np.allclose(calibrated, nlcd_offset)
    assert warning is None


def test_blend_with_landsat_calibration_with_data():
    """With sufficient urban/rural pixels, should blend offsets."""
    nlcd_offset = np.full((10, 10), 2.0, dtype=np.float64)
    impervious = np.full((10, 10), 5.0, dtype=np.float64)  # Rural baseline
    landsat_lst = np.full((10, 10), 25.0, dtype=np.float64)

    # Create urban pixels (imperviousness >= 50%)
    impervious[0:5, 0:5] = 60.0
    landsat_lst[0:5, 0:5] = 30.0  # Urban LST 5°C higher

    calibrated, warning = blend_with_landsat_calibration(
        nlcd_offset, landsat_lst, impervious
    )

    # Should have blended the offset
    assert not np.allclose(calibrated, nlcd_offset)
    # Calibrated should be between NLCD and Landsat-observed
    assert np.all(calibrated >= 0.0)


def test_blend_with_landsat_calibration_warning_threshold():
    """Large difference between observed and modeled should trigger warning."""
    nlcd_offset = np.full((10, 10), 1.0, dtype=np.float64)  # Small offset
    impervious = np.full((10, 10), 5.0, dtype=np.float64)
    landsat_lst = np.full((10, 10), 25.0, dtype=np.float64)

    # Create urban pixels with large LST difference
    impervious[0:5, 0:5] = 60.0
    landsat_lst[0:5, 0:5] = 30.0  # 5°C difference (> 1.5°C threshold)

    calibrated, warning = blend_with_landsat_calibration(
        nlcd_offset, landsat_lst, impervious
    )

    # Should have a warning
    assert warning is not None
    assert "differs" in warning.lower()


# ---------------------------------------------------------------------------
# compute_thermal_logic tests
# ---------------------------------------------------------------------------


def test_compute_thermal_logic_returns_dict():
    """compute_thermal_logic should return a dict with expected keys."""
    impervious = np.full((3, 3), 50.0, dtype=np.float64)
    aspect = np.full((3, 3), 180.0, dtype=np.float64)

    result = compute_thermal_logic(impervious, aspect)

    assert isinstance(result, dict)
    assert "surface_albedo" in result
    assert "solar_aspect_mult" in result
    assert "uhi_offset_f" in result
    assert "calibration_warning" in result


def test_compute_thermal_logic_output_shapes():
    """All output arrays should have same shape as inputs."""
    impervious = np.random.rand(10, 10) * 100.0
    aspect = np.random.rand(10, 10) * 360.0

    result = compute_thermal_logic(impervious, aspect)

    assert result["surface_albedo"].shape == impervious.shape
    assert result["solar_aspect_mult"].shape == aspect.shape
    assert result["uhi_offset_f"].shape == impervious.shape


def test_compute_thermal_logic_preserves_nan():
    """NaN values should be preserved in all outputs."""
    impervious = np.full((3, 3), 50.0, dtype=np.float64)
    aspect = np.full((3, 3), 180.0, dtype=np.float64)
    impervious[1, 1] = np.nan
    aspect[0, 0] = np.nan

    result = compute_thermal_logic(impervious, aspect)

    assert np.isnan(result["surface_albedo"][1, 1])
    assert np.isnan(result["solar_aspect_mult"][0, 0])
    assert np.isnan(result["uhi_offset_f"][1, 1])


def test_compute_thermal_logic_with_landsat():
    """compute_thermal_logic should accept Landsat LST for calibration."""
    impervious = np.full((10, 10), 5.0, dtype=np.float64)
    aspect = np.full((10, 10), 180.0, dtype=np.float64)
    landsat_lst = np.full((10, 10), 25.0, dtype=np.float64)

    # Create urban pixels
    impervious[0:5, 0:5] = 60.0
    landsat_lst[0:5, 0:5] = 30.0

    result = compute_thermal_logic(
        impervious, aspect, landsat_lst_array=landsat_lst
    )

    assert isinstance(result, dict)
    assert "surface_albedo" in result
    assert "solar_aspect_mult" in result
    assert "uhi_offset_f" in result
    assert "calibration_warning" in result


def test_compute_thermal_logic_consistency():
    """UHI offset should be consistent with albedo and aspect."""
    impervious = np.full((3, 3), 50.0, dtype=np.float64)
    aspect = np.full((3, 3), 180.0, dtype=np.float64)

    result = compute_thermal_logic(impervious, aspect)

    # Manually compute expected values
    expected_albedo = 0.20 - (50.0 / 100.0) * 0.15
    expected_mult = 1.2

    assert np.allclose(result["surface_albedo"], expected_albedo, atol=1e-6)
    assert np.allclose(result["solar_aspect_mult"], expected_mult, atol=1e-6)


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("impervious_pct", [0, 25, 50, 75, 100])
def test_albedo_formula_correctness(impervious_pct):
    """Albedo formula should match specification exactly."""
    impervious = np.full((3, 3), float(impervious_pct), dtype=np.float64)
    albedo = compute_surface_albedo(impervious)

    expected = 0.20 - (impervious_pct / 100.0) * 0.15
    assert np.allclose(albedo, expected, atol=1e-10)


@pytest.mark.parametrize("aspect_deg", [0, 45, 90, 135, 180, 225, 270, 315])
def test_solar_multiplier_cardinal_directions(aspect_deg):
    """Solar multiplier should match specification at cardinal directions."""
    aspect = np.full((3, 3), float(aspect_deg), dtype=np.float64)
    multiplier = compute_solar_aspect_multiplier(aspect)

    if aspect_deg == 0 or aspect_deg == 360:
        expected = 0.8  # North
    elif aspect_deg == 90 or aspect_deg == 270:
        expected = 1.0  # East/West
    elif aspect_deg == 180:
        expected = 1.2  # South
    else:
        # Intermediate values should be between 0.8 and 1.2
        assert np.all(multiplier >= 0.8)
        assert np.all(multiplier <= 1.2)
        return

    assert np.allclose(multiplier, expected, atol=1e-6)


def test_uhi_offset_formula_correctness():
    """UHI offset formula should match specification exactly."""
    albedo = np.array([[0.05, 0.125, 0.20]], dtype=np.float64)
    uhi_offset = compute_uhi_offset(albedo)

    # Formula: (0.20 - albedo) * 200 / 5.5 * 9/5
    expected = (0.20 - albedo) * 200.0 / 5.5 * (9.0 / 5.0)
    assert np.allclose(uhi_offset, expected, atol=1e-10)


def test_thermal_logic_all_nan_input():
    """All-NaN input should produce all-NaN output."""
    impervious = np.full((3, 3), np.nan, dtype=np.float64)
    aspect = np.full((3, 3), np.nan, dtype=np.float64)

    result = compute_thermal_logic(impervious, aspect)

    assert np.all(np.isnan(result["surface_albedo"]))
    assert np.all(np.isnan(result["solar_aspect_mult"]))
    assert np.all(np.isnan(result["uhi_offset_f"]))
