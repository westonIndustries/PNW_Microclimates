"""
Property-based tests for daily microclimate combination.

**Validates: Requirements 12.5**

Tests verify that daily effective HDD computation maintains physical
properties: non-negativity, temperature monotonicity with altitude,
and reasonable value ranges.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.processors.daily_combine import (
    compute_altitude_hdd,
    compute_daily_effective_hdd,
)


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_compute_daily_effective_hdd_basic():
    """Test basic daily effective HDD computation."""
    daily_hdd = compute_daily_effective_hdd(
        hrrr_adjusted_temp_f=50.0,
        terrain_multiplier=1.0,
        elevation_hdd_addition=100.0,
        uhi_hdd_reduction=50.0,
        traffic_hdd_reduction=25.0,
    )

    # Expected: max(0, 65 - 50) * 1.0 + 100 - 50 - 25 = 15 + 100 - 50 - 25 = 40
    assert abs(daily_hdd - 40.0) < 0.01


def test_compute_daily_effective_hdd_warm_day():
    """On warm days (T > 65°F), base HDD should be zero."""
    daily_hdd = compute_daily_effective_hdd(
        hrrr_adjusted_temp_f=70.0,  # Warm
        terrain_multiplier=1.0,
        elevation_hdd_addition=0.0,
        uhi_hdd_reduction=0.0,
        traffic_hdd_reduction=0.0,
    )

    # Expected: max(0, 65 - 70) * 1.0 = 0
    assert daily_hdd == 0.0


def test_compute_daily_effective_hdd_never_negative():
    """Daily effective HDD should never be negative."""
    daily_hdd = compute_daily_effective_hdd(
        hrrr_adjusted_temp_f=50.0,
        terrain_multiplier=1.0,
        elevation_hdd_addition=0.0,
        uhi_hdd_reduction=100.0,  # Large reduction
        traffic_hdd_reduction=100.0,  # Large reduction
    )

    # Even with large reductions, result should be >= 0
    assert daily_hdd >= 0.0


def test_compute_altitude_hdd_basic():
    """Test altitude HDD computation."""
    hdd = compute_altitude_hdd(temp_adjusted_f=50.0)

    # Expected: max(0, 65 - 50) = 15
    assert abs(hdd - 15.0) < 0.01


def test_compute_altitude_hdd_warm():
    """Altitude HDD should be zero on warm days."""
    hdd = compute_altitude_hdd(temp_adjusted_f=70.0)

    assert hdd == 0.0


def test_compute_altitude_hdd_never_negative():
    """Altitude HDD should never be negative."""
    hdd = compute_altitude_hdd(temp_adjusted_f=100.0)

    assert hdd >= 0.0


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------


@given(
    temp_f=st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
    terrain_mult=st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False),
    elev_add=st.floats(min_value=0, max_value=500, allow_nan=False, allow_infinity=False),
    uhi_red=st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False),
    traffic_red=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_daily_effective_hdd_non_negative(
    temp_f, terrain_mult, elev_add, uhi_red, traffic_red
):
    """
    **Validates: Requirements 12.5**

    Property: Daily effective HDD is always non-negative.

    HDD represents heating demand and cannot be negative. Even with large
    reductions from UHI and traffic effects, the result should be >= 0.

    Given:
    - HRRR adjusted temperature (°F)
    - Terrain multiplier
    - Elevation HDD addition
    - UHI HDD reduction
    - Traffic HDD reduction

    When:
    - Compute daily effective HDD

    Then:
    - daily_effective_hdd >= 0
    """
    daily_hdd = compute_daily_effective_hdd(
        hrrr_adjusted_temp_f=temp_f,
        terrain_multiplier=terrain_mult,
        elevation_hdd_addition=elev_add,
        uhi_hdd_reduction=uhi_red,
        traffic_hdd_reduction=traffic_red,
    )

    assert daily_hdd >= 0.0


@given(
    temp_f=st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_altitude_hdd_non_negative(temp_f):
    """
    **Validates: Requirements 12.5**

    Property: Altitude HDD is always non-negative.

    HDD at any altitude should be non-negative, as it represents heating demand.

    Given:
    - Temperature at altitude (°F)

    When:
    - Compute altitude HDD

    Then:
    - hdd >= 0
    """
    hdd = compute_altitude_hdd(temp_adjusted_f=temp_f)

    assert hdd >= 0.0


@given(
    temp_f=st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_altitude_hdd_formula_correctness(temp_f):
    """
    **Validates: Requirements 12.5**

    Property: Altitude HDD formula is correct.

    The formula is: hdd = max(0, 65 - temp_f)

    This property verifies the implementation matches the formula.

    Given:
    - Temperature at altitude (°F)

    When:
    - Compute altitude HDD

    Then:
    - hdd = max(0, 65 - temp_f)
    """
    hdd = compute_altitude_hdd(temp_adjusted_f=temp_f)
    expected = max(0, 65 - temp_f)

    assert abs(hdd - expected) < 1e-10


@given(
    temp_f=st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_altitude_hdd_monotonicity_with_temperature(temp_f):
    """
    **Validates: Requirements 12.5**

    Property: Altitude HDD decreases monotonically with temperature.

    As temperature increases, HDD should decrease (or stay the same).
    This is a fundamental property of the HDD formula.

    Given:
    - Temperature at altitude (°F)

    When:
    - Compute HDD at temp and temp + 1°F

    Then:
    - hdd(temp) >= hdd(temp + 1)
    """
    hdd_1 = compute_altitude_hdd(temp_adjusted_f=temp_f)
    hdd_2 = compute_altitude_hdd(temp_adjusted_f=temp_f + 1.0)

    assert hdd_1 >= hdd_2


@given(
    temp_f=st.floats(min_value=-50, max_value=65, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_altitude_hdd_below_base_temperature(temp_f):
    """
    **Validates: Requirements 12.5**

    Property: HDD below base temperature (65°F) is positive.

    When temperature is below the base temperature (65°F), HDD should be
    positive and equal to (65 - temp).

    Given:
    - Temperature below 65°F

    When:
    - Compute altitude HDD

    Then:
    - hdd = 65 - temp (exactly)
    """
    hdd = compute_altitude_hdd(temp_adjusted_f=temp_f)
    expected = 65 - temp_f

    assert abs(hdd - expected) < 1e-10


@given(
    temp_f=st.floats(min_value=65, max_value=120, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_altitude_hdd_above_base_temperature(temp_f):
    """
    **Validates: Requirements 12.5**

    Property: HDD above base temperature (65°F) is zero.

    When temperature is at or above the base temperature (65°F), HDD should
    be zero (no heating demand).

    Given:
    - Temperature >= 65°F

    When:
    - Compute altitude HDD

    Then:
    - hdd = 0
    """
    hdd = compute_altitude_hdd(temp_adjusted_f=temp_f)

    assert hdd == 0.0


@given(
    temp_f=st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
    terrain_mult=st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False),
    elev_add=st.floats(min_value=0, max_value=500, allow_nan=False, allow_infinity=False),
    uhi_red=st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False),
    traffic_red=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_daily_effective_hdd_in_reasonable_range(
    temp_f, terrain_mult, elev_add, uhi_red, traffic_red
):
    """
    **Validates: Requirements 12.5**

    Property: Daily effective HDD is non-negative and finite.

    HDD should always be a finite non-negative number. This property verifies
    that the computation produces valid numeric results.

    Given:
    - HRRR adjusted temperature
    - Terrain and correction multipliers

    When:
    - Compute daily effective HDD

    Then:
    - daily_effective_hdd is finite and >= 0
    """
    daily_hdd = compute_daily_effective_hdd(
        hrrr_adjusted_temp_f=temp_f,
        terrain_multiplier=terrain_mult,
        elevation_hdd_addition=elev_add,
        uhi_hdd_reduction=uhi_red,
        traffic_hdd_reduction=traffic_red,
    )

    # Check that result is finite and non-negative
    assert np.isfinite(daily_hdd)
    assert daily_hdd >= 0


@given(
    temp_f=st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
    terrain_mult_1=st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False),
    terrain_mult_2=st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_daily_effective_hdd_terrain_multiplier_effect(temp_f, terrain_mult_1, terrain_mult_2):
    """
    **Validates: Requirements 12.5**

    Property: Terrain multiplier scales HDD correctly.

    The terrain multiplier should scale the base HDD proportionally.
    If terrain_mult_2 > terrain_mult_1, then HDD_2 > HDD_1 (all else equal).

    Given:
    - Temperature
    - Two different terrain multipliers

    When:
    - Compute HDD with each multiplier

    Then:
    - If terrain_mult_2 > terrain_mult_1, then hdd_2 >= hdd_1
    """
    hdd_1 = compute_daily_effective_hdd(
        hrrr_adjusted_temp_f=temp_f,
        terrain_multiplier=terrain_mult_1,
        elevation_hdd_addition=0.0,
        uhi_hdd_reduction=0.0,
        traffic_hdd_reduction=0.0,
    )

    hdd_2 = compute_daily_effective_hdd(
        hrrr_adjusted_temp_f=temp_f,
        terrain_multiplier=terrain_mult_2,
        elevation_hdd_addition=0.0,
        uhi_hdd_reduction=0.0,
        traffic_hdd_reduction=0.0,
    )

    if terrain_mult_2 > terrain_mult_1:
        assert hdd_2 >= hdd_1 - 1e-10  # Allow small numerical tolerance
    elif terrain_mult_2 < terrain_mult_1:
        assert hdd_2 <= hdd_1 + 1e-10
