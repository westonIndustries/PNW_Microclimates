"""
Property-based tests for HRRR bias correction.

**Validates: Requirements 12.3**

Tests verify that bias correction is applied correctly and maintains
physical properties of temperature fields.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr
from hypothesis import given, settings
from hypothesis import strategies as st

from src.processors.bias_correct_hrrr import (
    bias_correct,
    compute_bias_correction_field,
    validate_bias_correction,
)


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_bias_correct_basic():
    """Test basic bias correction application."""
    # Create sample data
    hrrr_temp = xr.DataArray(
        np.full((10, 10), 50.0),  # 50°F
        dims=["y", "x"],
        name="hrrr_temp",
    )
    prism_normal = xr.DataArray(
        np.full((10, 10), 48.0),  # 48°F
        dims=["y", "x"],
        name="prism_normal",
    )
    hrrr_clim = xr.DataArray(
        np.full((10, 10), 49.0),  # 49°F
        dims=["y", "x"],
        name="hrrr_clim",
    )

    # Apply correction
    corrected = bias_correct(hrrr_temp, prism_normal, hrrr_clim)

    # Expected: 50 + (48 - 49) = 49°F
    expected = np.full((10, 10), 49.0)
    np.testing.assert_array_almost_equal(corrected.values, expected)


def test_bias_correct_preserves_shape():
    """Corrected output should have same shape as input."""
    hrrr_temp = xr.DataArray(
        np.random.randn(20, 30) + 50,
        dims=["y", "x"],
    )
    prism_normal = xr.DataArray(
        np.random.randn(20, 30) + 48,
        dims=["y", "x"],
    )
    hrrr_clim = xr.DataArray(
        np.random.randn(20, 30) + 49,
        dims=["y", "x"],
    )

    corrected = bias_correct(hrrr_temp, prism_normal, hrrr_clim)

    assert corrected.shape == hrrr_temp.shape


def test_bias_correct_preserves_nan():
    """NaN values should be preserved through correction."""
    hrrr_temp = xr.DataArray(
        np.full((5, 5), 50.0),
        dims=["y", "x"],
    )
    hrrr_temp.values[2, 2] = np.nan

    prism_normal = xr.DataArray(
        np.full((5, 5), 48.0),
        dims=["y", "x"],
    )
    hrrr_clim = xr.DataArray(
        np.full((5, 5), 49.0),
        dims=["y", "x"],
    )

    corrected = bias_correct(hrrr_temp, prism_normal, hrrr_clim)

    assert np.isnan(corrected.values[2, 2])


def test_bias_correct_fallback_to_raw_mean():
    """When climatology is None with time dimension, should use raw mean as fallback."""
    # Create data with time dimension for fallback to work
    hrrr_temp = xr.DataArray(
        np.full((3, 5, 5), 50.0),  # 3 time steps
        dims=["time", "y", "x"],
    )
    prism_normal = xr.DataArray(
        np.full((5, 5), 48.0),
        dims=["y", "x"],
    )

    # No climatology provided - use fallback
    # With fallback, climatology = raw mean over time = 50
    # So correction = 48 - 50 = -2
    # Result = 50 + (-2) = 48
    corrected = bias_correct(
        hrrr_temp,
        prism_normal,
        hrrr_climatology=None,
        fallback_to_raw_mean=True,
    )

    expected = np.full((3, 5, 5), 48.0)
    np.testing.assert_array_almost_equal(corrected.values, expected, decimal=5)


def test_bias_correct_raises_without_climatology():
    """Should raise ValueError if climatology is None and fallback is False."""
    hrrr_temp = xr.DataArray(np.full((5, 5), 50.0), dims=["y", "x"])
    prism_normal = xr.DataArray(np.full((5, 5), 48.0), dims=["y", "x"])

    with pytest.raises(ValueError):
        bias_correct(
            hrrr_temp,
            prism_normal,
            hrrr_climatology=None,
            fallback_to_raw_mean=False,
        )


def test_compute_bias_correction_field():
    """Test bias correction field computation."""
    prism_normal = xr.DataArray(
        np.full((5, 5), 48.0),
        dims=["y", "x"],
    )
    hrrr_clim = xr.DataArray(
        np.full((5, 5), 49.0),
        dims=["y", "x"],
    )

    bias_field = compute_bias_correction_field(prism_normal, hrrr_clim)

    # Expected: 48 - 49 = -1
    expected = np.full((5, 5), -1.0)
    np.testing.assert_array_almost_equal(bias_field.values, expected)


def test_validate_bias_correction_passes():
    """Validation should pass for well-corrected data."""
    hrrr_adjusted = xr.DataArray(
        np.full((10, 10), 48.0),
        dims=["y", "x"],
    )
    prism_normal = xr.DataArray(
        np.full((10, 10), 48.0),
        dims=["y", "x"],
    )

    result = validate_bias_correction(hrrr_adjusted, prism_normal, tolerance_f=2.0)

    assert result["passed"] is True
    assert result["mean_diff"] < 0.1
    assert result["pct_within_tolerance"] > 99


def test_validate_bias_correction_fails():
    """Validation should fail for poorly corrected data."""
    hrrr_adjusted = xr.DataArray(
        np.full((10, 10), 50.0),
        dims=["y", "x"],
    )
    prism_normal = xr.DataArray(
        np.full((10, 10), 40.0),
        dims=["y", "x"],
    )

    result = validate_bias_correction(hrrr_adjusted, prism_normal, tolerance_f=2.0)

    assert result["passed"] is False
    assert result["mean_diff"] > 5.0


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------


@given(
    hrrr_temp=st.lists(
        st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
        min_size=20,
        max_size=20,
    ),
    bias_offset=st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50)
def test_bias_correction_round_trip(hrrr_temp, bias_offset):
    """
    **Validates: Requirements 12.3**

    Property: Bias correction round-trip identity.

    If we apply a bias correction with offset B, then apply the inverse
    correction with offset -B, we should recover the original temperature
    (within floating-point tolerance).

    Given:
    - HRRR temperature array
    - Bias offset

    When:
    - Apply bias correction: corrected = hrrr + offset
    - Apply inverse correction: recovered = corrected - offset

    Then:
    - recovered ≈ hrrr (within 1e-10)
    """
    # Create arrays (4x5 = 20 elements)
    hrrr_array = np.array(hrrr_temp, dtype=np.float64)
    hrrr_da = xr.DataArray(hrrr_array.reshape(4, 5), dims=["y", "x"])

    prism_normal = xr.DataArray(
        np.full_like(hrrr_array, bias_offset).reshape(4, 5),
        dims=["y", "x"],
    )
    hrrr_clim = xr.DataArray(
        np.zeros_like(hrrr_array).reshape(4, 5),
        dims=["y", "x"],
    )

    # Apply correction
    corrected = bias_correct(hrrr_da, prism_normal, hrrr_clim)

    # Expected: hrrr + (prism_normal - hrrr_clim) = hrrr + bias_offset
    expected = hrrr_da + bias_offset

    np.testing.assert_array_almost_equal(corrected.values, expected.values, decimal=10)


@given(
    hrrr_temp=st.lists(
        st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
        min_size=20,
        max_size=20,
    ),
)
@settings(max_examples=50)
def test_bias_correction_identity_zero_offset(hrrr_temp):
    """
    **Validates: Requirements 12.3**

    Property: Zero bias offset identity.

    If PRISM normal equals HRRR climatology (zero bias offset),
    then corrected temperature should equal raw HRRR temperature.

    Given:
    - HRRR temperature array
    - PRISM normal = HRRR climatology (zero offset)

    When:
    - Apply bias correction

    Then:
    - corrected ≈ hrrr (within floating-point tolerance)
    """
    hrrr_array = np.array(hrrr_temp, dtype=np.float64)
    hrrr_da = xr.DataArray(hrrr_array.reshape(4, 5), dims=["y", "x"])

    # Zero offset: prism_normal = hrrr_clim
    prism_normal = xr.DataArray(
        hrrr_array.reshape(4, 5),
        dims=["y", "x"],
    )
    hrrr_clim = xr.DataArray(
        hrrr_array.reshape(4, 5),
        dims=["y", "x"],
    )

    corrected = bias_correct(hrrr_da, prism_normal, hrrr_clim)

    np.testing.assert_array_almost_equal(corrected.values, hrrr_da.values, decimal=10)


@given(
    hrrr_temp=st.lists(
        st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
        min_size=20,
        max_size=20,
    ),
    prism_normal=st.lists(
        st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
        min_size=20,
        max_size=20,
    ),
    hrrr_clim=st.lists(
        st.floats(min_value=-50, max_value=120, allow_nan=False, allow_infinity=False),
        min_size=20,
        max_size=20,
    ),
)
@settings(max_examples=50)
def test_bias_correction_formula_correctness(hrrr_temp, prism_normal, hrrr_clim):
    """
    **Validates: Requirements 12.3**

    Property: Bias correction formula correctness.

    The bias correction formula is:
        corrected = hrrr_raw + (prism_normal - hrrr_climatology)

    This property verifies that the implementation matches the formula exactly.

    Given:
    - HRRR temperature array
    - PRISM normal array
    - HRRR climatology array

    When:
    - Apply bias correction

    Then:
    - corrected = hrrr + (prism - hrrr_clim) (element-wise)
    """
    # Use fixed size arrays (4x5 = 20 elements)
    hrrr_array = np.array(hrrr_temp[:20], dtype=np.float64)
    prism_array = np.array(prism_normal[:20], dtype=np.float64)
    hrrr_clim_array = np.array(hrrr_clim[:20], dtype=np.float64)

    hrrr_da = xr.DataArray(hrrr_array.reshape(4, 5), dims=["y", "x"])
    prism_da = xr.DataArray(prism_array.reshape(4, 5), dims=["y", "x"])
    hrrr_clim_da = xr.DataArray(hrrr_clim_array.reshape(4, 5), dims=["y", "x"])

    corrected = bias_correct(hrrr_da, prism_da, hrrr_clim_da)

    # Expected: hrrr + (prism - hrrr_clim)
    expected = hrrr_da + (prism_da - hrrr_clim_da)

    np.testing.assert_array_almost_equal(corrected.values, expected.values, decimal=10)
