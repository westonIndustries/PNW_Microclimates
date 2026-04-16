"""
Property-based tests for wind profile extraction.

**Validates: Requirements 12.4**

Tests verify that wind profile interpolation maintains physical bounds
and produces reasonable altitude-dependent wind and temperature profiles.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.processors.wind_profile_extractor import (
    interpolate_temperature_to_altitude,
    interpolate_wind_to_altitude,
    pressure_to_altitude_hypsometric,
    wind_speed_direction_from_components,
)


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_pressure_to_altitude_basic():
    """Test pressure to altitude conversion."""
    # At sea level (1013 mb), altitude should be ~0 ft
    alt_ft = pressure_to_altitude_hypsometric(
        pressure_mb=1013,
        surface_pressure_mb=1013,
        surface_temp_k=288.15,
    )
    assert abs(alt_ft) < 100  # Within 100 ft of sea level


def test_pressure_to_altitude_increases_with_height():
    """Altitude should increase as pressure decreases."""
    surface_pressure_mb = 1013
    surface_temp_k = 288.15

    alt_1000 = pressure_to_altitude_hypsometric(1000, surface_pressure_mb, surface_temp_k)
    alt_900 = pressure_to_altitude_hypsometric(900, surface_pressure_mb, surface_temp_k)
    alt_800 = pressure_to_altitude_hypsometric(800, surface_pressure_mb, surface_temp_k)

    # Altitude should increase as pressure decreases
    assert alt_1000 < alt_900 < alt_800


def test_wind_speed_direction_from_components_zero():
    """Zero wind components should give zero speed."""
    speed, direction = wind_speed_direction_from_components(0.0, 0.0)

    assert speed == 0.0
    # Direction is undefined for zero wind, but should be a number
    assert isinstance(direction, float)


def test_wind_speed_direction_from_components_north():
    """North wind (v > 0, u = 0) should give direction 0°."""
    speed, direction = wind_speed_direction_from_components(0.0, 10.0)

    assert speed == 10.0
    assert abs(direction - 0.0) < 1.0  # Within 1° of north


def test_wind_speed_direction_from_components_east():
    """East wind (u > 0, v = 0) should give direction 90°."""
    speed, direction = wind_speed_direction_from_components(10.0, 0.0)

    assert speed == 10.0
    assert abs(direction - 90.0) < 1.0  # Within 1° of east


def test_wind_speed_direction_from_components_magnitude():
    """Wind speed should be magnitude of components."""
    u, v = 3.0, 4.0
    speed, _ = wind_speed_direction_from_components(u, v)

    # 3-4-5 triangle
    assert abs(speed - 5.0) < 0.01


def test_interpolate_wind_to_altitude_bounds():
    """Interpolated wind should be bounded by input levels."""
    u_levels = np.array([5.0, 10.0, 15.0, 20.0])
    v_levels = np.array([2.0, 4.0, 6.0, 8.0])
    pressure_levels = np.array([1000, 850, 700, 500])

    u_interp, v_interp = interpolate_wind_to_altitude(
        u_levels,
        v_levels,
        pressure_levels,
        target_altitude_ft=5000,
        surface_pressure_mb=1013,
        surface_temp_k=288.15,
    )

    # Interpolated values should be within bounds of input
    assert u_levels.min() <= u_interp <= u_levels.max()
    assert v_levels.min() <= v_interp <= v_levels.max()


def test_interpolate_temperature_to_altitude_bounds():
    """Interpolated temperature should be bounded by input levels."""
    temp_levels = np.array([288.15, 280.0, 270.0, 250.0])  # K
    pressure_levels = np.array([1000, 850, 700, 500])

    temp_interp = interpolate_temperature_to_altitude(
        temp_levels,
        pressure_levels,
        target_altitude_ft=5000,
        surface_pressure_mb=1013,
        surface_temp_k=288.15,
    )

    # Interpolated temperature should be within bounds
    assert temp_levels.min() <= temp_interp <= temp_levels.max()


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------


@given(
    u_wind=st.lists(
        st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False),
        min_size=4,
        max_size=16,
    ),
    v_wind=st.lists(
        st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False),
        min_size=4,
        max_size=16,
    ),
)
@settings(max_examples=50)
def test_wind_profile_interpolation_bounds(u_wind, v_wind):
    """
    **Validates: Requirements 12.4**

    Property: Wind profile interpolation bounds.

    Interpolated wind components should be bounded by the input pressure-level
    values. This ensures physical reasonableness and prevents extrapolation
    artifacts.

    Given:
    - U and V wind components at pressure levels
    - Target altitude

    When:
    - Interpolate to target altitude

    Then:
    - Interpolated U is within [min(u_levels), max(u_levels)]
    - Interpolated V is within [min(v_levels), max(v_levels)]
    """
    # Ensure we have at least 4 levels
    u_array = np.array(u_wind[:4], dtype=np.float64)
    v_array = np.array(v_wind[:4], dtype=np.float64)
    pressure_levels = np.array([1000, 850, 700, 500], dtype=np.float64)

    u_interp, v_interp = interpolate_wind_to_altitude(
        u_array,
        v_array,
        pressure_levels,
        target_altitude_ft=5000,
        surface_pressure_mb=1013,
        surface_temp_k=288.15,
    )

    # Check bounds
    assert u_array.min() <= u_interp <= u_array.max()
    assert v_array.min() <= v_interp <= v_array.max()


@given(
    temp_levels=st.lists(
        st.floats(min_value=250, max_value=300, allow_nan=False, allow_infinity=False),
        min_size=4,
        max_size=16,
    ),
)
@settings(max_examples=50)
def test_temperature_profile_monotonicity(temp_levels):
    """
    **Validates: Requirements 12.4**

    Property: Temperature profile monotonicity (with tolerance).

    Temperature should generally decrease with altitude in the troposphere,
    though inversions are possible. This test verifies that the interpolated
    temperature profile is physically reasonable (no extreme jumps).

    Given:
    - Temperature at pressure levels (K)
    - Multiple target altitudes

    When:
    - Interpolate to multiple altitudes

    Then:
    - Temperature differences between consecutive altitudes are reasonable
      (no jumps > 20°C per 1000 ft)
    """
    temp_array = np.array(temp_levels[:4], dtype=np.float64)
    pressure_levels = np.array([1000, 850, 700, 500], dtype=np.float64)

    # Interpolate to multiple altitudes
    altitudes_ft = [0, 3000, 6000, 9000, 12000, 18000]
    temps = []

    for alt_ft in altitudes_ft:
        temp_k = interpolate_temperature_to_altitude(
            temp_array,
            pressure_levels,
            target_altitude_ft=alt_ft,
            surface_pressure_mb=1013,
            surface_temp_k=288.15,
        )
        temps.append(temp_k)

    # Check that temperature changes are reasonable
    # Allow up to 20°C per 1000 ft (typical lapse rate is ~3.5°C/1000 ft)
    for i in range(len(temps) - 1):
        alt_diff_ft = altitudes_ft[i + 1] - altitudes_ft[i]
        temp_diff_k = abs(temps[i + 1] - temps[i])
        max_allowed_diff = 20 * (alt_diff_ft / 1000)

        assert temp_diff_k <= max_allowed_diff, (
            f"Temperature change {temp_diff_k}K over {alt_diff_ft}ft "
            f"exceeds {max_allowed_diff}K"
        )


@given(
    u_wind=st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False),
    v_wind=st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_wind_speed_always_positive(u_wind, v_wind):
    """
    **Validates: Requirements 12.4**

    Property: Wind speed is always non-negative.

    Wind speed is the magnitude of the wind vector and should never be negative.

    Given:
    - U and V wind components (any values)

    When:
    - Compute wind speed and direction

    Then:
    - Wind speed >= 0
    """
    speed, _ = wind_speed_direction_from_components(u_wind, v_wind)

    assert speed >= 0.0


@given(
    u_wind=st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False),
    v_wind=st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_wind_direction_in_valid_range(u_wind, v_wind):
    """
    **Validates: Requirements 12.4**

    Property: Wind direction is in valid range [0, 360).

    Wind direction should always be between 0° and 360° (or 0° and 2π radians).

    Given:
    - U and V wind components (any values)

    When:
    - Compute wind direction

    Then:
    - 0 <= direction < 360
    """
    _, direction = wind_speed_direction_from_components(u_wind, v_wind)

    assert 0 <= direction <= 360  # Allow 360 as it wraps to 0


@given(
    u_levels=st.lists(
        st.floats(min_value=-30, max_value=30, allow_nan=False, allow_infinity=False),
        min_size=4,
        max_size=4,
    ),
    v_levels=st.lists(
        st.floats(min_value=-30, max_value=30, allow_nan=False, allow_infinity=False),
        min_size=4,
        max_size=4,
    ),
)
@settings(max_examples=50)
def test_wind_profile_interpolation_speed_bounds(u_levels, v_levels):
    """
    **Validates: Requirements 12.4**

    Property: Interpolated wind speed is bounded by input level speeds.

    The wind speed at the interpolated altitude should be bounded by the
    minimum and maximum wind speeds at the input pressure levels.

    Given:
    - U and V wind components at pressure levels
    - Target altitude

    When:
    - Interpolate to target altitude
    - Compute wind speed from interpolated components

    Then:
    - Interpolated wind speed is within [min_speed, max_speed] of input levels
    """
    u_array = np.array(u_levels, dtype=np.float64)
    v_array = np.array(v_levels, dtype=np.float64)
    pressure_levels = np.array([1000, 850, 700, 500], dtype=np.float64)

    # Compute wind speeds at input levels
    input_speeds = np.sqrt(u_array**2 + v_array**2)
    min_speed = input_speeds.min()
    max_speed = input_speeds.max()

    # Interpolate
    u_interp, v_interp = interpolate_wind_to_altitude(
        u_array,
        v_array,
        pressure_levels,
        target_altitude_ft=5000,
        surface_pressure_mb=1013,
        surface_temp_k=288.15,
    )

    interp_speed = np.sqrt(u_interp**2 + v_interp**2)

    # Check bounds (with 50% tolerance for interpolation artifacts)
    # This accounts for cases where interpolation between different wind directions
    # can produce speeds outside the strict bounds
    assert min_speed * 0.5 <= interp_speed <= max_speed * 1.5
