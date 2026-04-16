"""Tests for src/processors/boundary_layer_correction.py."""

from __future__ import annotations

import numpy as np
import pytest

from src.config import (
    VON_KARMAN,
    BL_DECAY_HEIGHT_FT,
    ROUGHNESS_GRADIENT_THRESHOLD,
)
from src.processors.boundary_layer_correction import (
    compute_wind_shear_correction,
    compute_thermal_subsidence,
)


# ---------------------------------------------------------------------------
# compute_wind_shear_correction tests
# ---------------------------------------------------------------------------


def test_wind_shear_correction_zero_above_1000ft():
    """Wind shear correction should be zero above 1,000 ft AGL."""
    correction = compute_wind_shear_correction(
        wind_speed_ms=5.0,
        z_agl_ft=1500.0,
        z0_local=0.5,
        z0_upwind=0.05,
        u_star=0.3,
    )
    assert correction == 0.0


def test_wind_shear_correction_zero_outside_transition_zone():
    """Wind shear correction should be zero outside transition zones.
    
    **Validates: Requirements 23.3, 23.6**
    """
    # Roughness gradient below threshold
    correction = compute_wind_shear_correction(
        wind_speed_ms=5.0,
        z_agl_ft=500.0,
        z0_local=0.05,
        z0_upwind=0.04,  # Gradient = 0.01 < threshold (0.3)
        u_star=0.3,
    )
    assert correction == 0.0


def test_wind_shear_correction_negative_in_transition_to_rough():
    """Wind shear correction should be negative when transitioning to rougher surface.
    
    In the log-law profile, higher z0 produces lower wind speed at a given height.
    So transitioning to rougher surface (higher z0) means lower wind speed.
    
    **Validates: Requirements 23.3, 23.6**
    """
    # Transition from smooth (grass) to rough (forest)
    correction = compute_wind_shear_correction(
        wind_speed_ms=5.0,
        z_agl_ft=100.0,
        z0_local=1.5,  # Forest (rough)
        z0_upwind=0.05,  # Grass (smooth)
        u_star=0.3,
    )
    # Should be negative (wind speed decreases over rougher surface)
    assert correction < 0.0


def test_wind_shear_correction_positive_in_transition_to_smooth():
    """Wind shear correction should be positive when transitioning to smoother surface.
    
    In the log-law profile, lower z0 produces higher wind speed at a given height.
    So transitioning to smoother surface (lower z0) means higher wind speed.
    
    **Validates: Requirements 23.3, 23.6**
    """
    # Transition from rough (forest) to smooth (water)
    correction = compute_wind_shear_correction(
        wind_speed_ms=5.0,
        z_agl_ft=100.0,
        z0_local=0.001,  # Water (smooth)
        z0_upwind=1.5,  # Forest (rough)
        u_star=0.3,
    )
    # Should be positive (wind speed increases over smoother surface)
    assert correction > 0.0


def test_wind_shear_correction_zero_at_surface():
    """Wind shear correction should be small near the surface (z ≈ z0)."""
    correction = compute_wind_shear_correction(
        wind_speed_ms=5.0,
        z_agl_ft=1.0,  # Very close to surface
        z0_local=1.5,
        z0_upwind=0.05,
        u_star=0.3,
    )
    # Should be close to zero (log-law singularity near z0)
    assert abs(correction) < 0.5


def test_wind_shear_correction_increases_with_altitude():
    """Wind shear correction magnitude should increase with altitude (up to 1,000 ft).
    
    **Validates: Requirements 23.3, 23.6**
    """
    z_values = [50.0, 200.0, 500.0, 1000.0]
    corrections = [
        compute_wind_shear_correction(
            wind_speed_ms=5.0,
            z_agl_ft=z,
            z0_local=1.5,
            z0_upwind=0.05,
            u_star=0.3,
        )
        for z in z_values
    ]

    # Corrections should increase in magnitude with altitude (log-law effect)
    # Note: corrections may be negative, so we check magnitude
    for i in range(len(corrections) - 1):
        # Allow small tolerance for numerical precision
        assert abs(corrections[i + 1]) >= abs(corrections[i]) - 0.01


def test_wind_shear_correction_output_in_knots():
    """Wind shear correction should be returned in knots."""
    correction = compute_wind_shear_correction(
        wind_speed_ms=5.0,
        z_agl_ft=500.0,
        z0_local=1.5,
        z0_upwind=0.05,
        u_star=0.3,
    )
    # Correction should be in reasonable knot range (not m/s)
    # For typical boundary layer, expect < 10 knots correction
    assert abs(correction) < 20.0


def test_wind_shear_correction_with_computed_ustar():
    """Wind shear correction should work when u_star is computed from wind speed."""
    correction = compute_wind_shear_correction(
        wind_speed_ms=5.0,
        z_agl_ft=500.0,
        z0_local=1.5,
        z0_upwind=0.05,
        u_star=0.0,  # Will be computed
    )
    # Should produce a valid correction
    assert isinstance(correction, float)
    assert not np.isnan(correction)


def test_wind_shear_correction_zero_with_zero_wind():
    """Wind shear correction should be zero with zero wind speed."""
    correction = compute_wind_shear_correction(
        wind_speed_ms=0.0,
        z_agl_ft=500.0,
        z0_local=1.5,
        z0_upwind=0.05,
        u_star=0.0,
    )
    assert correction == 0.0


def test_wind_shear_correction_symmetry():
    """Wind shear correction should be antisymmetric for reversed transitions.
    
    **Validates: Requirements 23.3, 23.6**
    """
    # Transition from smooth to rough
    correction_smooth_to_rough = compute_wind_shear_correction(
        wind_speed_ms=5.0,
        z_agl_ft=500.0,
        z0_local=1.5,
        z0_upwind=0.05,
        u_star=0.3,
    )

    # Transition from rough to smooth (reversed)
    correction_rough_to_smooth = compute_wind_shear_correction(
        wind_speed_ms=5.0,
        z_agl_ft=500.0,
        z0_local=0.05,
        z0_upwind=1.5,
        u_star=0.3,
    )

    # Should be approximately opposite
    assert np.isclose(
        correction_smooth_to_rough, -correction_rough_to_smooth, atol=0.1
    )


# ---------------------------------------------------------------------------
# compute_thermal_subsidence tests
# ---------------------------------------------------------------------------


def test_thermal_subsidence_zero_above_1000ft():
    """Thermal subsidence should be zero above 1,000 ft AGL.
    
    **Validates: Requirements 23.4, 23.6**
    """
    correction = compute_thermal_subsidence(
        temp_f=5.0,
        z_agl_ft=1500.0,
        is_water=True,
    )
    assert correction == 0.0


def test_thermal_subsidence_zero_over_non_water():
    """Thermal subsidence should be zero over non-water pixels.
    
    **Validates: Requirements 23.4, 23.6**
    """
    correction = compute_thermal_subsidence(
        temp_f=5.0,
        z_agl_ft=500.0,
        is_water=False,
    )
    assert correction == 0.0


def test_thermal_subsidence_negative_over_water():
    """Thermal subsidence should be negative (cooling) over water.
    
    **Validates: Requirements 23.4, 23.6**
    """
    correction = compute_thermal_subsidence(
        temp_f=5.0,
        z_agl_ft=500.0,
        is_water=True,
    )
    # Should be negative (cooling)
    assert correction < 0.0


def test_thermal_subsidence_maximum_at_surface():
    """Thermal subsidence should be maximum (most negative) at surface.
    
    **Validates: Requirements 23.4, 23.6**
    """
    correction_surface = compute_thermal_subsidence(
        temp_f=5.0,
        z_agl_ft=0.0,
        is_water=True,
    )

    correction_500ft = compute_thermal_subsidence(
        temp_f=5.0,
        z_agl_ft=500.0,
        is_water=True,
    )

    # Surface correction should be more negative (larger magnitude)
    assert abs(correction_surface) > abs(correction_500ft)


def test_thermal_subsidence_exponential_decay():
    """Thermal subsidence should decay exponentially with altitude.
    
    **Validates: Requirements 23.4, 23.6**
    """
    temp_anomaly = 5.0
    z_values = [0.0, 250.0, 500.0, 750.0, 1000.0]

    corrections = [
        compute_thermal_subsidence(
            temp_f=temp_anomaly,
            z_agl_ft=z,
            is_water=True,
        )
        for z in z_values
    ]

    # Corrections should decay exponentially (magnitude decreases)
    for i in range(len(corrections) - 1):
        assert abs(corrections[i + 1]) < abs(corrections[i])


def test_thermal_subsidence_at_decay_height():
    """Thermal subsidence at H_bl should be exp(-1) ≈ 0.368 of surface value.
    
    **Validates: Requirements 23.4, 23.6**
    """
    temp_anomaly = 5.0

    correction_surface = compute_thermal_subsidence(
        temp_f=temp_anomaly,
        z_agl_ft=0.0,
        is_water=True,
    )

    correction_at_hbl = compute_thermal_subsidence(
        temp_f=temp_anomaly,
        z_agl_ft=BL_DECAY_HEIGHT_FT,
        is_water=True,
    )

    # At H_bl, correction should be exp(-1) ≈ 0.368 of surface value
    expected_ratio = np.exp(-1)
    actual_ratio = abs(correction_at_hbl) / abs(correction_surface)

    assert np.isclose(actual_ratio, expected_ratio, atol=0.01)


def test_thermal_subsidence_proportional_to_temp_anomaly():
    """Thermal subsidence should be proportional to temperature anomaly.
    
    **Validates: Requirements 23.4, 23.6**
    """
    correction_5f = compute_thermal_subsidence(
        temp_f=5.0,
        z_agl_ft=500.0,
        is_water=True,
    )

    correction_10f = compute_thermal_subsidence(
        temp_f=10.0,
        z_agl_ft=500.0,
        is_water=True,
    )

    # Correction should scale linearly with temperature anomaly
    assert np.isclose(correction_10f / correction_5f, 2.0, atol=0.01)


def test_thermal_subsidence_zero_with_zero_anomaly():
    """Thermal subsidence should be zero with zero temperature anomaly."""
    correction = compute_thermal_subsidence(
        temp_f=0.0,
        z_agl_ft=500.0,
        is_water=True,
    )
    assert correction == 0.0


def test_thermal_subsidence_positive_anomaly():
    """Thermal subsidence with positive anomaly should be negative (cooling).
    
    **Validates: Requirements 23.4, 23.6**
    """
    correction = compute_thermal_subsidence(
        temp_f=5.0,
        z_agl_ft=500.0,
        is_water=True,
    )
    assert correction < 0.0


def test_thermal_subsidence_negative_anomaly():
    """Thermal subsidence with negative anomaly should be positive (warming).
    
    **Validates: Requirements 23.4, 23.6**
    """
    correction = compute_thermal_subsidence(
        temp_f=-5.0,
        z_agl_ft=500.0,
        is_water=True,
    )
    assert correction > 0.0


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("z_agl_ft", [0.0, 250.0, 500.0, 750.0, 1000.0, 1500.0])
def test_wind_shear_correction_always_zero_above_1000ft(z_agl_ft):
    """Property: Wind shear correction is zero for all altitudes > 1,000 ft.
    
    **Validates: Requirements 23.3, 23.6**
    """
    if z_agl_ft > 1000.0:
        correction = compute_wind_shear_correction(
            wind_speed_ms=5.0,
            z_agl_ft=z_agl_ft,
            z0_local=1.5,
            z0_upwind=0.05,
            u_star=0.3,
        )
        assert correction == 0.0


@pytest.mark.parametrize("z_agl_ft", [0.0, 250.0, 500.0, 750.0, 1000.0, 1500.0])
def test_thermal_subsidence_always_zero_above_1000ft(z_agl_ft):
    """Property: Thermal subsidence is zero for all altitudes > 1,000 ft.
    
    **Validates: Requirements 23.4, 23.6**
    """
    if z_agl_ft > 1000.0:
        correction = compute_thermal_subsidence(
            temp_f=5.0,
            z_agl_ft=z_agl_ft,
            is_water=True,
        )
        assert correction == 0.0


@pytest.mark.parametrize("is_water", [True, False])
def test_thermal_subsidence_zero_over_non_water_pixels(is_water):
    """Property: Thermal subsidence is zero for all non-water pixels.
    
    **Validates: Requirements 23.4, 23.6**
    """
    if not is_water:
        correction = compute_thermal_subsidence(
            temp_f=5.0,
            z_agl_ft=500.0,
            is_water=is_water,
        )
        assert correction == 0.0


@pytest.mark.parametrize("z0_gradient", [0.01, 0.1, 0.2, 0.25, 0.3, 0.5, 1.0])
def test_wind_shear_correction_zero_below_threshold(z0_gradient):
    """Property: Wind shear correction is zero when roughness gradient < threshold.
    
    **Validates: Requirements 23.3, 23.6**
    """
    if z0_gradient < ROUGHNESS_GRADIENT_THRESHOLD:
        correction = compute_wind_shear_correction(
            wind_speed_ms=5.0,
            z_agl_ft=500.0,
            z0_local=0.05 + z0_gradient,
            z0_upwind=0.05,
            u_star=0.3,
        )
        assert correction == 0.0


@pytest.mark.parametrize("z_agl_ft", [0.0, 100.0, 250.0, 500.0, 750.0, 1000.0])
def test_thermal_subsidence_monotonic_decay(z_agl_ft):
    """Property: Thermal subsidence magnitude decreases monotonically with altitude.
    
    **Validates: Requirements 23.4, 23.6**
    """
    if z_agl_ft < 1000.0:
        correction_current = compute_thermal_subsidence(
            temp_f=5.0,
            z_agl_ft=z_agl_ft,
            is_water=True,
        )

        correction_higher = compute_thermal_subsidence(
            temp_f=5.0,
            z_agl_ft=z_agl_ft + 100.0,
            is_water=True,
        )

        # Magnitude should decrease with altitude
        assert abs(correction_higher) <= abs(correction_current)
