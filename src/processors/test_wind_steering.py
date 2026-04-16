"""
Tests for wind_steering processor.

Tests cover:
- Merging NREL and MesoWest wind data
- Stagnation multiplier computation
- Wind infiltration multiplier computation
- Gorge floor application
"""

from __future__ import annotations

import numpy as np
import pytest
import rasterio.transform

from src.processors.wind_steering import (
    compute_stagnation_multiplier,
    compute_wind_infiltration_multiplier,
    compute_wind_steering,
    merge_wind_data,
)


class TestMergeWindData:
    """Tests for merge_wind_data function."""

    def test_merge_with_no_mesowest_data(self):
        """When no MesoWest data, should return NREL grid unchanged."""
        nrel_wind = np.array([[3.0, 4.0], [5.0, 6.0]], dtype=np.float64)
        transform = rasterio.transform.Affine(1.0, 0.0, 0.0, 0.0, -1.0, 0.0)
        mesowest_wind = {}
        dem_shape = (2, 2)

        result = merge_wind_data(nrel_wind, transform, mesowest_wind, dem_shape)

        np.testing.assert_array_equal(result, nrel_wind)

    def test_merge_with_mesowest_data(self):
        """When MesoWest data available, should blend with NREL."""
        nrel_wind = np.array(
            [[3.0, 4.0, 3.5], [5.0, 6.0, 5.5], [4.0, 5.0, 4.5]],
            dtype=np.float64,
        )
        transform = rasterio.transform.Affine(1.0, 0.0, 0.0, 0.0, -1.0, 0.0)

        # MesoWest data for multiple stations (need at least 4 for 2D interpolation)
        mesowest_wind = {
            "KPDX": {"mean_wind_ms": 7.0, "p90_wind_ms": 10.0},
            "KEUG": {"mean_wind_ms": 6.5, "p90_wind_ms": 9.5},
            "KSLE": {"mean_wind_ms": 6.0, "p90_wind_ms": 9.0},
            "KAST": {"mean_wind_ms": 7.5, "p90_wind_ms": 10.5},
        }
        dem_shape = (3, 3)

        result = merge_wind_data(nrel_wind, transform, mesowest_wind, dem_shape)

        # Result should have same shape as NREL
        assert result.shape == nrel_wind.shape
        # Result should not be all NaN
        assert not np.all(np.isnan(result))

    def test_merge_preserves_nrel_nans(self):
        """NaN values in NREL grid should remain NaN in output."""
        nrel_wind = np.array([[3.0, np.nan], [5.0, 6.0]], dtype=np.float64)
        transform = rasterio.transform.Affine(1.0, 0.0, 0.0, 0.0, -1.0, 0.0)
        mesowest_wind = {}
        dem_shape = (2, 2)

        result = merge_wind_data(nrel_wind, transform, mesowest_wind, dem_shape)

        assert np.isnan(result[0, 1])


class TestStagnationMultiplier:
    """Tests for compute_stagnation_multiplier function."""

    def test_high_wind_exposed(self):
        """Wind > 5 m/s and not in shadow should give 0.7× multiplier."""
        wind_speed = np.array([[6.0, 7.0], [8.0, 9.0]], dtype=np.float64)
        wind_shadow = np.array([[0, 0], [0, 0]], dtype=np.float64)

        result = compute_stagnation_multiplier(wind_speed, wind_shadow)

        np.testing.assert_array_almost_equal(result, 0.7)

    def test_moderate_wind(self):
        """Wind 3–5 m/s should give 1.0× multiplier."""
        wind_speed = np.array([[3.0, 4.0], [5.0, 4.5]], dtype=np.float64)
        wind_shadow = np.array([[0, 0], [0, 1]], dtype=np.float64)

        result = compute_stagnation_multiplier(wind_speed, wind_shadow)

        np.testing.assert_array_almost_equal(result, 1.0)

    def test_low_wind_sheltered(self):
        """Wind < 3 m/s and in shadow should give 1.3× multiplier."""
        wind_speed = np.array([[1.0, 2.0], [2.5, 0.5]], dtype=np.float64)
        wind_shadow = np.array([[1, 1], [1, 1]], dtype=np.float64)

        result = compute_stagnation_multiplier(wind_speed, wind_shadow)

        np.testing.assert_array_almost_equal(result, 1.3)

    def test_mixed_conditions(self):
        """Mixed wind speeds and shadow conditions should give mixed multipliers."""
        wind_speed = np.array([[6.0, 2.0], [4.0, 1.0]], dtype=np.float64)
        wind_shadow = np.array([[0, 1], [0, 1]], dtype=np.float64)

        result = compute_stagnation_multiplier(wind_speed, wind_shadow)

        # [0,0]: 6.0 m/s, not in shadow → 0.7
        # [0,1]: 2.0 m/s, in shadow → 1.3 (< 3 and in shadow)
        # [1,0]: 4.0 m/s, not in shadow → 1.0 (3-5 range)
        # [1,1]: 1.0 m/s, in shadow → 1.3 (< 3 and in shadow)
        expected = np.array([[0.7, 1.3], [1.0, 1.3]], dtype=np.float64)
        np.testing.assert_array_almost_equal(result, expected)

    def test_nan_handling(self):
        """NaN in inputs should produce NaN in output."""
        wind_speed = np.array([[6.0, np.nan], [4.0, 1.0]], dtype=np.float64)
        wind_shadow = np.array([[0, 0], [0, 1]], dtype=np.float64)

        result = compute_stagnation_multiplier(wind_speed, wind_shadow)

        assert np.isnan(result[0, 1])
        assert result[0, 0] == 0.7
        assert result[1, 1] == 1.3

    def test_boundary_conditions(self):
        """Test boundary values (exactly 3 m/s and 5 m/s)."""
        wind_speed = np.array([[3.0, 5.0], [5.1, 2.9]], dtype=np.float64)
        wind_shadow = np.array([[0, 0], [0, 1]], dtype=np.float64)

        result = compute_stagnation_multiplier(wind_speed, wind_shadow)

        # 3.0 m/s is not < 3, so should be 1.0 (not sheltered)
        assert result[0, 0] == 1.0
        # 5.0 m/s is not > 5, so should be 1.0 (not exposed)
        assert result[0, 1] == 1.0
        # 5.1 m/s is > 5 and not in shadow, so 0.7
        assert result[1, 0] == 0.7
        # 2.9 m/s is < 3 and in shadow, so 1.3
        assert result[1, 1] == 1.3


class TestWindInfiltrationMultiplier:
    """Tests for compute_wind_infiltration_multiplier function."""

    def test_baseline_wind_3ms(self):
        """Wind at 3 m/s (baseline) should give 1.0× multiplier."""
        wind_speed = np.array([[3.0, 3.0], [3.0, 3.0]], dtype=np.float64)

        result = compute_wind_infiltration_multiplier(wind_speed, "KPDX")

        np.testing.assert_array_almost_equal(result, 1.0)

    def test_wind_above_baseline(self):
        """Wind above 3 m/s should increase multiplier by 1.5% per m/s."""
        wind_speed = np.array([[4.0, 5.0], [6.0, 8.0]], dtype=np.float64)

        result = compute_wind_infiltration_multiplier(wind_speed, "KPDX")

        # 4 m/s: 1.0 + 0.015 × (4 - 3) = 1.015
        # 5 m/s: 1.0 + 0.015 × (5 - 3) = 1.030
        # 6 m/s: 1.0 + 0.015 × (6 - 3) = 1.045
        # 8 m/s: 1.0 + 0.015 × (8 - 3) = 1.075
        expected = np.array([[1.015, 1.030], [1.045, 1.075]], dtype=np.float64)
        np.testing.assert_array_almost_equal(result, expected)

    def test_wind_below_baseline(self):
        """Wind below 3 m/s should not reduce multiplier below 1.0."""
        wind_speed = np.array([[0.0, 1.0], [2.0, 2.9]], dtype=np.float64)

        result = compute_wind_infiltration_multiplier(wind_speed, "KPDX")

        np.testing.assert_array_almost_equal(result, 1.0)

    def test_gorge_floor_kdls(self):
        """KDLS station should apply Gorge floor of 1.15."""
        wind_speed = np.array([[2.0, 4.0], [6.0, 8.0]], dtype=np.float64)

        result = compute_wind_infiltration_multiplier(wind_speed, "KDLS")

        # All values should be at least 1.15
        assert np.all(result >= 1.15)
        # 8 m/s: 1.0 + 0.015 × 5 = 1.075, but floor is 1.15
        assert result[1, 1] == 1.15

    def test_gorge_floor_kttd(self):
        """KTTD station should apply Gorge floor of 1.15."""
        wind_speed = np.array([[2.0, 4.0], [6.0, 8.0]], dtype=np.float64)

        result = compute_wind_infiltration_multiplier(wind_speed, "KTTD")

        # All values should be at least 1.15
        assert np.all(result >= 1.15)

    def test_gorge_floor_not_applied_to_other_stations(self):
        """Non-Gorge stations should not apply floor."""
        wind_speed = np.array([[2.0, 4.0], [6.0, 8.0]], dtype=np.float64)

        result = compute_wind_infiltration_multiplier(wind_speed, "KPDX")

        # 2.0 m/s: 1.0 (no increase)
        assert result[0, 0] == 1.0
        # 4.0 m/s: 1.0 + 0.015 × 1 = 1.015
        assert result[0, 1] == 1.015

    def test_nan_handling(self):
        """NaN in wind speed should produce NaN in output."""
        wind_speed = np.array([[3.0, np.nan], [5.0, 6.0]], dtype=np.float64)

        result = compute_wind_infiltration_multiplier(wind_speed, "KPDX")

        assert np.isnan(result[0, 1])
        assert result[0, 0] == 1.0
        assert result[1, 0] == 1.030


class TestComputeWindSteering:
    """Tests for compute_wind_steering orchestration function."""

    def test_returns_all_required_keys(self):
        """Should return dict with all required keys."""
        nrel_wind = np.array([[3.0, 4.0], [5.0, 6.0]], dtype=np.float64)
        transform = rasterio.transform.Affine(1.0, 0.0, 0.0, 0.0, -1.0, 0.0)
        mesowest_wind = {}
        wind_shadow = np.array([[0, 0], [0, 1]], dtype=np.float64)
        dem_shape = (2, 2)

        result = compute_wind_steering(
            nrel_wind,
            transform,
            mesowest_wind,
            wind_shadow,
            dem_shape,
            "KPDX",
        )

        assert "mean_wind_ms" in result
        assert "wind_infiltration_mult" in result
        assert "stagnation_multiplier" in result

    def test_output_shapes_match_dem(self):
        """All output arrays should have shape matching DEM."""
        nrel_wind = np.array([[3.0, 4.0], [5.0, 6.0]], dtype=np.float64)
        transform = rasterio.transform.Affine(1.0, 0.0, 0.0, 0.0, -1.0, 0.0)
        mesowest_wind = {}
        wind_shadow = np.array([[0, 0], [0, 1]], dtype=np.float64)
        dem_shape = (2, 2)

        result = compute_wind_steering(
            nrel_wind,
            transform,
            mesowest_wind,
            wind_shadow,
            dem_shape,
            "KPDX",
        )

        assert result["mean_wind_ms"].shape == (2, 2)
        assert result["wind_infiltration_mult"].shape == (2, 2)
        assert result["stagnation_multiplier"].shape == (2, 2)

    def test_integration_with_realistic_data(self):
        """Integration test with realistic wind and shadow data."""
        # Create a 3x3 grid with varying wind speeds
        nrel_wind = np.array(
            [[2.0, 3.0, 4.0], [3.0, 5.0, 6.0], [4.0, 6.0, 7.0]],
            dtype=np.float64,
        )
        transform = rasterio.transform.Affine(1.0, 0.0, 0.0, 0.0, -1.0, 0.0)
        mesowest_wind = {}
        # Wind shadow in valley (center)
        wind_shadow = np.array(
            [[0, 0, 0], [0, 1, 0], [0, 0, 0]], dtype=np.float64
        )
        dem_shape = (3, 3)

        result = compute_wind_steering(
            nrel_wind,
            transform,
            mesowest_wind,
            wind_shadow,
            dem_shape,
            "KPDX",
        )

        # Check that stagnation multiplier varies correctly
        # Center pixel: wind 5 m/s, in shadow → should be 1.0 (not < 3)
        assert result["stagnation_multiplier"][1, 1] == 1.0
        # Top-right: wind 4 m/s, not in shadow → should be 1.0
        assert result["stagnation_multiplier"][0, 2] == 1.0
        # Bottom-right: wind 7 m/s, not in shadow → should be 0.7
        assert result["stagnation_multiplier"][2, 2] == 0.7

        # Check infiltration multiplier
        # All should be >= 1.0
        assert np.all(result["wind_infiltration_mult"] >= 1.0)
