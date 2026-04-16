"""
Tests for uncertainty quantification and error propagation in effective HDD calculations.

Tests verify that:
1. Bounds are computed correctly using error propagation formulas
2. Bounds are physically reasonable (low < nominal < high)
3. Bounds scale appropriately with input uncertainties
4. Bounds work with scalar, array, and Series inputs
5. Aggregate bounds are computed correctly from cell-level bounds
"""

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from src.processors.uncertainty_quantification import (
    compute_effective_hdd_bounds,
    compute_effective_hdd_bounds_per_cell,
    compute_aggregate_bounds,
    validate_bounds_physically_reasonable,
    BASE_HDD_UNCERTAINTY,
    TERRAIN_MULT_UNCERTAINTY,
    ELEV_ADDITION_UNCERTAINTY,
    UHI_REDUCTION_UNCERTAINTY,
    TRAFFIC_REDUCTION_UNCERTAINTY,
)
from src.processors.combine_corrections import compute_effective_hdd


# ============================================================================
# Unit Tests
# ============================================================================


class TestComputeEffectiveHDDBounds:
    """Test compute_effective_hdd_bounds with various input types."""

    def test_scalar_inputs_basic(self):
        """Test with scalar inputs: bounds should be symmetric around nominal."""
        base_hdd = 5000.0
        terrain_mult = 1.05
        elev_addition = 200.0
        uhi_reduction = 150.0
        traffic_reduction = 50.0

        low, high = compute_effective_hdd_bounds(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )

        # Compute nominal value
        nominal = compute_effective_hdd(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )

        # Bounds should be symmetric
        assert isinstance(low, float)
        assert isinstance(high, float)
        assert low < nominal < high
        assert abs((nominal - low) - (high - nominal)) < 1.0  # Symmetric within 1 HDD

    def test_array_inputs(self):
        """Test with numpy array inputs."""
        base_hdd = np.array([4000.0, 5000.0, 6000.0])
        terrain_mult = np.array([0.95, 1.05, 1.15])
        elev_addition = np.array([100.0, 200.0, 300.0])
        uhi_reduction = np.array([100.0, 150.0, 200.0])
        traffic_reduction = np.array([25.0, 50.0, 75.0])

        low, high = compute_effective_hdd_bounds(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )

        # Check output types and shapes
        assert isinstance(low, np.ndarray)
        assert isinstance(high, np.ndarray)
        assert low.shape == base_hdd.shape
        assert high.shape == base_hdd.shape

        # Check bounds are valid for each element
        nominal = compute_effective_hdd(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )
        assert np.all(low < nominal)
        assert np.all(high > nominal)

    def test_series_inputs(self):
        """Test with pandas Series inputs."""
        base_hdd = pd.Series([4000.0, 5000.0, 6000.0])
        terrain_mult = pd.Series([0.95, 1.05, 1.15])
        elev_addition = pd.Series([100.0, 200.0, 300.0])
        uhi_reduction = pd.Series([100.0, 150.0, 200.0])
        traffic_reduction = pd.Series([25.0, 50.0, 75.0])

        low, high = compute_effective_hdd_bounds(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )

        # Check output types
        assert isinstance(low, pd.Series)
        assert isinstance(high, pd.Series)

        # Check bounds are valid
        nominal = compute_effective_hdd(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )
        assert (low < nominal).all()
        assert (high > nominal).all()

    def test_bounds_physically_reasonable(self):
        """Test that bounds satisfy low < nominal < high."""
        base_hdd = np.array([3000.0, 5000.0, 7000.0])
        terrain_mult = np.array([0.90, 1.00, 1.20])
        elev_addition = np.array([0.0, 200.0, 500.0])
        uhi_reduction = np.array([0.0, 100.0, 300.0])
        traffic_reduction = np.array([0.0, 50.0, 150.0])

        low, high = compute_effective_hdd_bounds(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )

        nominal = compute_effective_hdd(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )

        # Validate bounds
        assert validate_bounds_physically_reasonable(nominal, low, high)

    def test_zero_base_hdd(self):
        """Test with zero base HDD (edge case)."""
        base_hdd = 0.0
        terrain_mult = 1.0
        elev_addition = 0.0
        uhi_reduction = 0.0
        traffic_reduction = 0.0

        low, high = compute_effective_hdd_bounds(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )

        # Bounds should still be valid
        assert low <= 0.0 <= high

    def test_high_uncertainty_inputs(self):
        """Test with high uncertainty values."""
        base_hdd = 5000.0
        terrain_mult = 1.05
        elev_addition = 200.0
        uhi_reduction = 150.0
        traffic_reduction = 50.0

        # Use high uncertainty values
        low, high = compute_effective_hdd_bounds(
            base_hdd,
            terrain_mult,
            elev_addition,
            uhi_reduction,
            traffic_reduction,
            base_hdd_sigma=500.0,  # High uncertainty
            terrain_mult_sigma=0.15,
            elev_addition_sigma=150.0,
            uhi_reduction_sigma=200.0,
            traffic_reduction_sigma=150.0,
        )

        nominal = compute_effective_hdd(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )

        # Bounds should be wider with higher uncertainty
        uncertainty = (high - low) / 2
        assert uncertainty > 300.0  # Should be significantly wider

    def test_custom_uncertainty_values(self):
        """Test that custom uncertainty values affect bound width."""
        base_hdd = 5000.0
        terrain_mult = 1.05
        elev_addition = 200.0
        uhi_reduction = 150.0
        traffic_reduction = 50.0

        # Compute with default uncertainties
        low1, high1 = compute_effective_hdd_bounds(
            base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
        )
        width1 = high1 - low1

        # Compute with doubled uncertainties
        low2, high2 = compute_effective_hdd_bounds(
            base_hdd,
            terrain_mult,
            elev_addition,
            uhi_reduction,
            traffic_reduction,
            base_hdd_sigma=BASE_HDD_UNCERTAINTY * 2,
            terrain_mult_sigma=TERRAIN_MULT_UNCERTAINTY * 2,
            elev_addition_sigma=ELEV_ADDITION_UNCERTAINTY * 2,
            uhi_reduction_sigma=UHI_REDUCTION_UNCERTAINTY * 2,
            traffic_reduction_sigma=TRAFFIC_REDUCTION_UNCERTAINTY * 2,
        )
        width2 = high2 - low2

        # Doubled uncertainties should produce wider bounds
        assert width2 > width1


class TestComputeEffectiveHDDBoundsPerCell:
    """Test compute_effective_hdd_bounds_per_cell with DataFrames."""

    def test_single_cell(self):
        """Test with a single cell."""
        cell_df = pd.DataFrame(
            {
                "prism_annual_hdd": [5000.0],
                "hdd_terrain_mult": [1.05],
                "hdd_elev_addition": [200.0],
                "hdd_uhi_reduction": [150.0],
                "hdd_traffic_reduction": [50.0],
            }
        )

        result = compute_effective_hdd_bounds_per_cell(cell_df)

        # Check that new columns were added
        assert "effective_hdd_low" in result.columns
        assert "effective_hdd_high" in result.columns
        assert len(result) == 1

        # Check bounds are valid
        assert result["effective_hdd_low"].iloc[0] < result["effective_hdd_high"].iloc[0]

    def test_multiple_cells(self):
        """Test with multiple cells."""
        cell_df = pd.DataFrame(
            {
                "prism_annual_hdd": [4000.0, 5000.0, 6000.0],
                "hdd_terrain_mult": [0.95, 1.05, 1.15],
                "hdd_elev_addition": [100.0, 200.0, 300.0],
                "hdd_uhi_reduction": [100.0, 150.0, 200.0],
                "hdd_traffic_reduction": [25.0, 50.0, 75.0],
            }
        )

        result = compute_effective_hdd_bounds_per_cell(cell_df)

        # Check output
        assert len(result) == 3
        assert "effective_hdd_low" in result.columns
        assert "effective_hdd_high" in result.columns

        # Check all bounds are valid
        for idx in range(len(result)):
            assert result["effective_hdd_low"].iloc[idx] < result["effective_hdd_high"].iloc[idx]

    def test_custom_column_names(self):
        """Test with custom column names."""
        cell_df = pd.DataFrame(
            {
                "base": [5000.0],
                "terrain": [1.05],
                "elev": [200.0],
                "uhi": [150.0],
                "traffic": [50.0],
            }
        )

        result = compute_effective_hdd_bounds_per_cell(
            cell_df,
            base_hdd_col="base",
            terrain_mult_col="terrain",
            elev_addition_col="elev",
            uhi_reduction_col="uhi",
            traffic_reduction_col="traffic",
        )

        assert "effective_hdd_low" in result.columns
        assert "effective_hdd_high" in result.columns

    def test_missing_column_raises_error(self):
        """Test that missing column raises KeyError."""
        cell_df = pd.DataFrame(
            {
                "prism_annual_hdd": [5000.0],
                "hdd_terrain_mult": [1.05],
                # Missing other columns
            }
        )

        with pytest.raises(KeyError):
            compute_effective_hdd_bounds_per_cell(cell_df)


class TestComputeAggregateBounds:
    """Test compute_aggregate_bounds for ZIP-code aggregates."""

    def test_single_cell_aggregate(self):
        """Test aggregate bounds with a single cell."""
        cell_df = pd.DataFrame(
            {
                "effective_hdd_low": [4800.0],
                "effective_hdd_high": [5200.0],
            }
        )

        agg_low, agg_high = compute_aggregate_bounds(cell_df)

        # With single cell, aggregate should equal the cell bounds
        assert agg_low == 4800.0
        assert agg_high == 5200.0

    def test_multiple_cells_aggregate(self):
        """Test aggregate bounds with multiple cells."""
        cell_df = pd.DataFrame(
            {
                "effective_hdd_low": [4800.0, 4900.0, 5000.0],
                "effective_hdd_high": [5200.0, 5300.0, 5400.0],
            }
        )

        agg_low, agg_high = compute_aggregate_bounds(cell_df)

        # Aggregate should be mean of cell bounds
        assert agg_low == pytest.approx(4900.0)
        assert agg_high == pytest.approx(5300.0)

    def test_custom_column_names(self):
        """Test with custom column names."""
        cell_df = pd.DataFrame(
            {
                "low_bound": [4800.0, 4900.0],
                "high_bound": [5200.0, 5300.0],
            }
        )

        agg_low, agg_high = compute_aggregate_bounds(
            cell_df, effective_hdd_low_col="low_bound", effective_hdd_high_col="high_bound"
        )

        assert agg_low == pytest.approx(4850.0)
        assert agg_high == pytest.approx(5250.0)


class TestValidateBoundsPhysicallyReasonable:
    """Test validate_bounds_physically_reasonable."""

    def test_valid_bounds_scalar(self):
        """Test with valid scalar bounds."""
        assert validate_bounds_physically_reasonable(5000.0, 4800.0, 5200.0)

    def test_valid_bounds_array(self):
        """Test with valid array bounds."""
        nominal = np.array([4000.0, 5000.0, 6000.0])
        low = np.array([3800.0, 4800.0, 5800.0])
        high = np.array([4200.0, 5200.0, 6200.0])

        assert validate_bounds_physically_reasonable(nominal, low, high)

    def test_valid_bounds_series(self):
        """Test with valid Series bounds."""
        nominal = pd.Series([4000.0, 5000.0, 6000.0])
        low = pd.Series([3800.0, 4800.0, 5800.0])
        high = pd.Series([4200.0, 5200.0, 6200.0])

        assert validate_bounds_physically_reasonable(nominal, low, high)

    def test_invalid_bounds_low_too_high(self):
        """Test with invalid bounds (low > nominal)."""
        assert not validate_bounds_physically_reasonable(5000.0, 5100.0, 5200.0)

    def test_invalid_bounds_high_too_low(self):
        """Test with invalid bounds (high < nominal)."""
        assert not validate_bounds_physically_reasonable(5000.0, 4800.0, 4900.0)

    def test_invalid_bounds_reversed(self):
        """Test with reversed bounds (low > high)."""
        assert not validate_bounds_physically_reasonable(5000.0, 5200.0, 4800.0)

    def test_tolerance_parameter(self):
        """Test that tolerance parameter allows small violations."""
        # Bounds are slightly invalid but within tolerance
        assert validate_bounds_physically_reasonable(5000.0, 5000.1, 5000.2, tolerance=1.0)


# ============================================================================
# Property-Based Tests (Hypothesis)
# ============================================================================


@given(
    base_hdd=st.floats(min_value=2000, max_value=8000, allow_nan=False, allow_infinity=False),
    terrain_mult=st.floats(min_value=0.8, max_value=1.3, allow_nan=False, allow_infinity=False),
    elev_addition=st.floats(min_value=-500, max_value=1000, allow_nan=False, allow_infinity=False),
    uhi_reduction=st.floats(min_value=0, max_value=500, allow_nan=False, allow_infinity=False),
    traffic_reduction=st.floats(min_value=0, max_value=300, allow_nan=False, allow_infinity=False),
)
@settings(suppress_health_check=[HealthCheck.filter_too_much], max_examples=100)
def test_bounds_always_physically_reasonable(
    base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
):
    """
    **Validates: Requirements 11.5**

    Property: For any valid input combination, bounds must satisfy low < nominal < high.
    This ensures uncertainty quantification produces physically meaningful results.
    """
    low, high = compute_effective_hdd_bounds(
        base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
    )

    nominal = compute_effective_hdd(
        base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
    )

    # Bounds must be physically reasonable
    assert validate_bounds_physically_reasonable(nominal, low, high)


@given(
    base_hdd=st.floats(min_value=2000, max_value=8000, allow_nan=False, allow_infinity=False),
    terrain_mult=st.floats(min_value=0.8, max_value=1.3, allow_nan=False, allow_infinity=False),
    elev_addition=st.floats(min_value=-500, max_value=1000, allow_nan=False, allow_infinity=False),
    uhi_reduction=st.floats(min_value=0, max_value=500, allow_nan=False, allow_infinity=False),
    traffic_reduction=st.floats(min_value=0, max_value=300, allow_nan=False, allow_infinity=False),
)
@settings(suppress_health_check=[HealthCheck.filter_too_much], max_examples=100)
def test_bounds_width_positive(
    base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
):
    """
    **Validates: Requirements 11.5**

    Property: Bound width (high - low) must always be positive.
    This ensures uncertainty is always quantified as a non-negative range.
    """
    low, high = compute_effective_hdd_bounds(
        base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
    )

    # Bound width must be positive
    assert high > low


@given(
    base_hdd=st.floats(min_value=2000, max_value=8000, allow_nan=False, allow_infinity=False),
    terrain_mult=st.floats(min_value=0.8, max_value=1.3, allow_nan=False, allow_infinity=False),
    elev_addition=st.floats(min_value=-500, max_value=1000, allow_nan=False, allow_infinity=False),
    uhi_reduction=st.floats(min_value=0, max_value=500, allow_nan=False, allow_infinity=False),
    traffic_reduction=st.floats(min_value=0, max_value=300, allow_nan=False, allow_infinity=False),
    uncertainty_scale=st.floats(min_value=0.5, max_value=3.0, allow_nan=False, allow_infinity=False),
)
@settings(suppress_health_check=[HealthCheck.filter_too_much], max_examples=100)
def test_bounds_scale_with_uncertainty(
    base_hdd,
    terrain_mult,
    elev_addition,
    uhi_reduction,
    traffic_reduction,
    uncertainty_scale,
):
    """
    **Validates: Requirements 11.5**

    Property: Bound width should scale monotonically with uncertainty scale factor.
    Doubling uncertainties should approximately double the bound width.
    """
    # Compute bounds with default uncertainties
    low1, high1 = compute_effective_hdd_bounds(
        base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
    )
    width1 = high1 - low1

    # Compute bounds with scaled uncertainties
    low2, high2 = compute_effective_hdd_bounds(
        base_hdd,
        terrain_mult,
        elev_addition,
        uhi_reduction,
        traffic_reduction,
        base_hdd_sigma=BASE_HDD_UNCERTAINTY * uncertainty_scale,
        terrain_mult_sigma=TERRAIN_MULT_UNCERTAINTY * uncertainty_scale,
        elev_addition_sigma=ELEV_ADDITION_UNCERTAINTY * uncertainty_scale,
        uhi_reduction_sigma=UHI_REDUCTION_UNCERTAINTY * uncertainty_scale,
        traffic_reduction_sigma=TRAFFIC_REDUCTION_UNCERTAINTY * uncertainty_scale,
    )
    width2 = high2 - low2

    # Width should scale approximately with uncertainty_scale
    # Allow some tolerance due to non-linear error propagation
    expected_width2 = width1 * uncertainty_scale
    assert abs(width2 - expected_width2) < expected_width2 * 0.1  # Within 10%


@given(
    n_cells=st.integers(min_value=1, max_value=50),
)
@settings(suppress_health_check=[HealthCheck.filter_too_much], max_examples=50)
def test_aggregate_bounds_within_cell_range(n_cells):
    """
    **Validates: Requirements 11.5**

    Property: Aggregate bounds must fall within the range of cell bounds.
    The aggregate low must be >= min(cell_low) and aggregate high must be <= max(cell_high).
    """
    # Generate random cell bounds
    cell_lows = np.random.uniform(4000, 5000, n_cells)
    cell_highs = cell_lows + np.random.uniform(100, 500, n_cells)

    cell_df = pd.DataFrame(
        {
            "effective_hdd_low": cell_lows,
            "effective_hdd_high": cell_highs,
        }
    )

    agg_low, agg_high = compute_aggregate_bounds(cell_df)

    # Aggregate bounds should be within cell range
    assert agg_low >= cell_lows.min()
    assert agg_high <= cell_highs.max()
