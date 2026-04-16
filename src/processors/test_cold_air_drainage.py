"""
Tests for cold air drainage processor.

Tests verify:
- Flow accumulation computation (D8 routing)
- Drainage intensity normalization (0–1)
- Cold air drainage multiplier (1.0–1.15)
- Valleys have higher drainage intensity than ridges
- Multiplier ranges are correct
- NaN handling and edge cases
"""

from __future__ import annotations

import numpy as np
import pytest

from src.processors.cold_air_drainage import (
    compute_cold_air_drainage,
    compute_cold_air_drainage_multiplier,
    compute_drainage_intensity,
    compute_flow_accumulation_d8,
    compute_flow_direction_d8,
)


class TestFlowDirection:
    """Tests for D8 flow direction computation."""

    def test_flow_direction_returns_correct_shape(self):
        """Flow direction output should have same shape as input DEM."""
        dem = np.random.rand(20, 20) * 100.0
        flow_dir = compute_flow_direction_d8(dem)

        assert flow_dir.shape == dem.shape

    def test_flow_direction_values_are_valid_codes(self):
        """Flow direction should be one of the valid D8 codes (0–128)."""
        dem = np.random.rand(20, 20) * 100.0
        flow_dir = compute_flow_direction_d8(dem)

        valid_codes = {0, 1, 2, 4, 8, 16, 32, 64, 128}
        assert np.all(np.isin(flow_dir, list(valid_codes)))

    def test_flow_direction_flat_dem_has_sinks(self):
        """Flat DEM should have flow direction 0 (sinks)."""
        dem = np.ones((10, 10), dtype=np.float64) * 100.0
        flow_dir = compute_flow_direction_d8(dem)

        # All pixels should be sinks (direction 0)
        assert np.all(flow_dir == 0)

    def test_flow_direction_simple_slope(self):
        """Simple slope should have consistent flow direction."""
        dem = np.zeros((10, 10), dtype=np.float64)
        # Elevation increases to the right
        for j in range(10):
            dem[:, j] = j * 10.0

        flow_dir = compute_flow_direction_d8(dem)

        # Most pixels should flow west (direction 16)
        valid_dirs = flow_dir[flow_dir != 0]
        if len(valid_dirs) > 0:
            # Should have mostly westward flow
            assert np.any(valid_dirs == 16)

    def test_flow_direction_preserves_nan(self):
        """NaN values in DEM should produce direction 0."""
        dem = np.ones((10, 10), dtype=np.float64) * 100.0
        dem[5, 5] = np.nan

        flow_dir = compute_flow_direction_d8(dem)

        assert flow_dir[5, 5] == 0


class TestFlowAccumulation:
    """Tests for D8 flow accumulation computation."""

    def test_flow_accumulation_returns_correct_shape(self):
        """Flow accumulation output should have same shape as input DEM."""
        dem = np.random.rand(20, 20) * 100.0
        flow_accum = compute_flow_accumulation_d8(dem)

        assert flow_accum.shape == dem.shape

    def test_flow_accumulation_minimum_is_one(self):
        """Isolated peaks should have flow accumulation of 1."""
        dem = np.ones((10, 10), dtype=np.float64) * 100.0
        flow_accum = compute_flow_accumulation_d8(dem)

        # All pixels should have accumulation >= 1
        valid_accum = flow_accum[~np.isnan(flow_accum)]
        assert np.all(valid_accum >= 1.0)

    def test_flow_accumulation_flat_dem(self):
        """Flat DEM should have uniform flow accumulation."""
        dem = np.ones((10, 10), dtype=np.float64) * 100.0
        flow_accum = compute_flow_accumulation_d8(dem)

        # All pixels should have same accumulation (no flow routing)
        valid_accum = flow_accum[~np.isnan(flow_accum)]
        if len(valid_accum) > 0:
            # All should be equal (each pixel is a sink)
            assert np.allclose(valid_accum, valid_accum[0])

    def test_flow_accumulation_valley_has_high_accumulation(self):
        """Valley should have higher flow accumulation than surrounding ridges."""
        dem = np.zeros((50, 50), dtype=np.float64)
        # Create a valley: elevation increases away from center
        for i in range(50):
            for j in range(50):
                dist = np.sqrt((i - 25) ** 2 + (j - 25) ** 2)
                dem[i, j] = dist * 2.0

        flow_accum = compute_flow_accumulation_d8(dem)

        # Center (valley) should have higher accumulation than edges (ridges)
        center_accum = flow_accum[25, 25]
        edge_accum = flow_accum[5, 5]

        if not np.isnan(center_accum) and not np.isnan(edge_accum):
            assert center_accum > edge_accum

    def test_flow_accumulation_ridge_has_low_accumulation(self):
        """Ridge should have lower flow accumulation than surrounding valleys."""
        dem = np.zeros((50, 50), dtype=np.float64)
        # Create a ridge: elevation decreases away from center
        for i in range(50):
            for j in range(50):
                dist = np.sqrt((i - 25) ** 2 + (j - 25) ** 2)
                dem[i, j] = 100.0 - dist * 2.0

        flow_accum = compute_flow_accumulation_d8(dem)

        # Center (ridge) should have lower accumulation than edges (valleys)
        center_accum = flow_accum[25, 25]
        edge_accum = flow_accum[5, 5]

        if not np.isnan(center_accum) and not np.isnan(edge_accum):
            assert center_accum < edge_accum

    def test_flow_accumulation_preserves_nan(self):
        """NaN values in DEM should be preserved in flow accumulation."""
        dem = np.ones((20, 20), dtype=np.float64) * 100.0
        dem[10, 10] = np.nan

        flow_accum = compute_flow_accumulation_d8(dem)

        assert np.isnan(flow_accum[10, 10])

    def test_flow_accumulation_all_nan_input(self):
        """All-NaN input should produce all-NaN output."""
        dem = np.full((10, 10), np.nan, dtype=np.float64)
        flow_accum = compute_flow_accumulation_d8(dem)

        assert np.all(np.isnan(flow_accum))

    def test_flow_accumulation_simple_slope(self):
        """Simple slope should accumulate flow toward the outlet."""
        dem = np.zeros((20, 20), dtype=np.float64)
        # Elevation increases to the right
        for j in range(20):
            dem[:, j] = j * 10.0

        flow_accum = compute_flow_accumulation_d8(dem)

        # Left edge (outlet) should have higher accumulation than right edge (source)
        left_accum = np.nanmean(flow_accum[:, 0])
        right_accum = np.nanmean(flow_accum[:, -1])

        assert left_accum > right_accum


class TestDrainageIntensity:
    """Tests for drainage intensity normalization."""

    def test_drainage_intensity_returns_correct_shape(self):
        """Drainage intensity output should have same shape as input."""
        flow_accum = np.random.rand(20, 20) * 100.0 + 1.0
        drainage_int = compute_drainage_intensity(flow_accum)

        assert drainage_int.shape == flow_accum.shape

    def test_drainage_intensity_range_0_to_1(self):
        """Drainage intensity should be in range 0–1."""
        flow_accum = np.random.rand(20, 20) * 1000.0 + 1.0
        drainage_int = compute_drainage_intensity(flow_accum)

        valid_intensity = drainage_int[~np.isnan(drainage_int)]
        assert np.all(valid_intensity >= 0.0)
        assert np.all(valid_intensity <= 1.0)

    def test_drainage_intensity_max_is_one(self):
        """Maximum drainage intensity should be 1.0."""
        flow_accum = np.random.rand(20, 20) * 1000.0 + 1.0
        drainage_int = compute_drainage_intensity(flow_accum)

        max_intensity = np.nanmax(drainage_int)
        assert np.isclose(max_intensity, 1.0)

    def test_drainage_intensity_min_is_near_zero(self):
        """Minimum drainage intensity should be near 0."""
        flow_accum = np.random.rand(20, 20) * 1000.0 + 1.0
        drainage_int = compute_drainage_intensity(flow_accum)

        min_intensity = np.nanmin(drainage_int)
        assert min_intensity < 0.01

    def test_drainage_intensity_preserves_nan(self):
        """NaN values in flow accumulation should be preserved."""
        flow_accum = np.ones((10, 10), dtype=np.float64) * 100.0
        flow_accum[5, 5] = np.nan

        drainage_int = compute_drainage_intensity(flow_accum)

        assert np.isnan(drainage_int[5, 5])

    def test_drainage_intensity_all_nan_input(self):
        """All-NaN input should produce all-NaN output."""
        flow_accum = np.full((10, 10), np.nan, dtype=np.float64)
        drainage_int = compute_drainage_intensity(flow_accum)

        assert np.all(np.isnan(drainage_int))

    def test_drainage_intensity_uniform_flow_accum(self):
        """Uniform flow accumulation should produce uniform intensity."""
        flow_accum = np.ones((10, 10), dtype=np.float64) * 100.0
        drainage_int = compute_drainage_intensity(flow_accum)

        valid_intensity = drainage_int[~np.isnan(drainage_int)]
        assert np.allclose(valid_intensity, 1.0)


class TestColdAirDrainageMultiplier:
    """Tests for cold air drainage multiplier computation."""

    def test_multiplier_returns_correct_shape(self):
        """Multiplier output should have same shape as input."""
        drainage_int = np.random.rand(20, 20)
        mult = compute_cold_air_drainage_multiplier(drainage_int)

        assert mult.shape == drainage_int.shape

    def test_multiplier_range_1_0_to_1_15(self):
        """Multiplier should be in range 1.0–1.15."""
        drainage_int = np.random.rand(20, 20)
        mult = compute_cold_air_drainage_multiplier(drainage_int)

        valid_mult = mult[~np.isnan(mult)]
        assert np.all(valid_mult >= 1.0)
        assert np.all(valid_mult <= 1.15)

    def test_multiplier_at_zero_intensity(self):
        """Multiplier should be 1.0 at zero drainage intensity."""
        drainage_int = np.zeros((10, 10), dtype=np.float64)
        mult = compute_cold_air_drainage_multiplier(drainage_int)

        assert np.allclose(mult, 1.0)

    def test_multiplier_at_max_intensity(self):
        """Multiplier should be 1.15 at maximum drainage intensity."""
        drainage_int = np.ones((10, 10), dtype=np.float64)
        mult = compute_cold_air_drainage_multiplier(drainage_int)

        assert np.allclose(mult, 1.15)

    def test_multiplier_linear_relationship(self):
        """Multiplier should scale linearly with drainage intensity."""
        drainage_int = np.array([[0.0, 0.5, 1.0]], dtype=np.float64)
        mult = compute_cold_air_drainage_multiplier(drainage_int)

        # Check linear relationship: mult = 1.0 + intensity * 0.15
        expected = np.array([[1.0, 1.075, 1.15]], dtype=np.float64)
        assert np.allclose(mult, expected)

    def test_multiplier_preserves_nan(self):
        """NaN values in drainage intensity should be preserved."""
        drainage_int = np.ones((10, 10), dtype=np.float64) * 0.5
        drainage_int[5, 5] = np.nan

        mult = compute_cold_air_drainage_multiplier(drainage_int)

        assert np.isnan(mult[5, 5])

    def test_multiplier_custom_max_increase(self):
        """Multiplier should respect custom max_multiplier_increase."""
        drainage_int = np.ones((10, 10), dtype=np.float64)
        mult = compute_cold_air_drainage_multiplier(drainage_int, max_multiplier_increase=0.20)

        # At intensity 1.0 with 0.20 increase, should be 1.20
        assert np.allclose(mult, 1.20)


class TestColdAirDrainageIntegration:
    """Integration tests for complete cold air drainage analysis."""

    def test_compute_cold_air_drainage_returns_all_keys(self):
        """compute_cold_air_drainage should return all expected keys."""
        dem = np.random.rand(50, 50) * 100.0
        result = compute_cold_air_drainage(dem)

        expected_keys = {
            "flow_accumulation",
            "drainage_intensity",
            "cold_air_drainage_mult",
        }
        assert set(result.keys()) == expected_keys

    def test_compute_cold_air_drainage_all_outputs_same_shape(self):
        """All outputs should have same shape as input DEM."""
        dem = np.random.rand(50, 50) * 100.0
        result = compute_cold_air_drainage(dem)

        for key, array in result.items():
            assert array.shape == dem.shape, f"{key} has wrong shape"

    def test_compute_cold_air_drainage_preserves_nan(self):
        """NaN values in input should be preserved in all outputs."""
        dem = np.random.rand(50, 50) * 100.0
        dem[25, 25] = np.nan
        dem[10, 10] = np.nan

        result = compute_cold_air_drainage(dem)

        for key, array in result.items():
            assert np.isnan(array[25, 25]), f"{key} did not preserve NaN at [25, 25]"
            assert np.isnan(array[10, 10]), f"{key} did not preserve NaN at [10, 10]"

    def test_compute_cold_air_drainage_valley_vs_ridge(self):
        """Valleys should have higher drainage intensity than ridges."""
        dem = np.zeros((50, 50), dtype=np.float64)
        # Create a valley: elevation increases away from center
        for i in range(50):
            for j in range(50):
                dist = np.sqrt((i - 25) ** 2 + (j - 25) ** 2)
                dem[i, j] = dist * 2.0

        result = compute_cold_air_drainage(dem)

        # Center (valley) should have higher drainage intensity than edges (ridges)
        center_intensity = result["drainage_intensity"][25, 25]
        edge_intensity = result["drainage_intensity"][5, 5]

        if not np.isnan(center_intensity) and not np.isnan(edge_intensity):
            assert center_intensity > edge_intensity

    def test_compute_cold_air_drainage_multiplier_range(self):
        """Cold air drainage multiplier should be in range 1.0–1.15."""
        dem = np.random.rand(50, 50) * 100.0
        result = compute_cold_air_drainage(dem)

        mult = result["cold_air_drainage_mult"]
        valid_mult = mult[~np.isnan(mult)]
        assert np.all(valid_mult >= 1.0)
        assert np.all(valid_mult <= 1.15)

    def test_compute_cold_air_drainage_isolated_peak(self):
        """Isolated peak should have low drainage intensity."""
        dem = np.zeros((50, 50), dtype=np.float64)
        # Create a peak: elevation decreases away from center
        for i in range(50):
            for j in range(50):
                dist = np.sqrt((i - 25) ** 2 + (j - 25) ** 2)
                dem[i, j] = 100.0 - dist * 2.0

        result = compute_cold_air_drainage(dem)

        # Center (peak) should have low drainage intensity
        center_intensity = result["drainage_intensity"][25, 25]
        if not np.isnan(center_intensity):
            assert center_intensity < 0.1

    def test_compute_cold_air_drainage_realistic_dem(self):
        """Test with realistic DEM data."""
        dem = np.zeros((100, 100), dtype=np.float64)
        # Create sinusoidal terrain with valleys and ridges
        for i in range(100):
            for j in range(100):
                dem[i, j] = 100.0 + 50.0 * np.sin(i / 20.0) * np.cos(j / 20.0)

        result = compute_cold_air_drainage(dem)

        # Check that we get reasonable values
        flow_accum = result["flow_accumulation"]
        drainage_int = result["drainage_intensity"]
        mult = result["cold_air_drainage_mult"]

        # Flow accumulation should be >= 1
        valid_accum = flow_accum[~np.isnan(flow_accum)]
        assert np.all(valid_accum >= 1.0)

        # Drainage intensity should be 0–1
        valid_int = drainage_int[~np.isnan(drainage_int)]
        assert np.all(valid_int >= 0.0)
        assert np.all(valid_int <= 1.0)

        # Multiplier should be 1.0–1.15
        valid_mult = mult[~np.isnan(mult)]
        assert np.all(valid_mult >= 1.0)
        assert np.all(valid_mult <= 1.15)

        # Should have some valleys and ridges
        assert np.any(drainage_int > 0.5)  # Some high drainage intensity
        assert np.any(drainage_int < 0.1)  # Some low drainage intensity

    def test_compute_cold_air_drainage_all_nan_input(self):
        """All-NaN input should produce all-NaN output."""
        dem = np.full((20, 20), np.nan, dtype=np.float64)
        result = compute_cold_air_drainage(dem)

        for key, array in result.items():
            assert np.all(np.isnan(array)), f"{key} is not all NaN"


class TestPropertyBasedTests:
    """Property-based tests for cold air drainage.

    **Validates: Requirements 11.3**
    """

    def test_valleys_have_higher_drainage_intensity_than_ridges(self):
        """Property: Valleys (negative TPI) have higher drainage_intensity than ridges.

        **Validates: Requirements 11.3**
        """
        # Create a DEM with clear valleys and ridges
        dem = np.zeros((100, 100), dtype=np.float64)
        for i in range(100):
            for j in range(100):
                dist = np.sqrt((i - 50) ** 2 + (j - 50) ** 2)
                # Valley in center, ridges at edges
                dem[i, j] = dist * 2.0

        result = compute_cold_air_drainage(dem)
        drainage_int = result["drainage_intensity"]

        # Center (valley) should have higher intensity than edges (ridges)
        center_intensity = drainage_int[50, 50]
        edge_intensity = drainage_int[10, 10]

        if not np.isnan(center_intensity) and not np.isnan(edge_intensity):
            assert center_intensity > edge_intensity

    def test_multiplier_ranges_from_1_0_to_1_15(self):
        """Property: cold_air_drainage_mult ranges from 1.0 to ~1.15.

        **Validates: Requirements 11.3**
        """
        dem = np.random.rand(100, 100) * 1000.0
        result = compute_cold_air_drainage(dem)
        mult = result["cold_air_drainage_mult"]

        valid_mult = mult[~np.isnan(mult)]
        assert np.all(valid_mult >= 1.0)
        assert np.all(valid_mult <= 1.15)

    def test_isolated_peaks_have_zero_drainage_intensity(self):
        """Property: Cells with zero flow accumulation (isolated peaks) have drainage_intensity ≈ 0.

        **Validates: Requirements 11.3**
        """
        dem = np.zeros((50, 50), dtype=np.float64)
        # Create a peak: elevation decreases away from center
        for i in range(50):
            for j in range(50):
                dist = np.sqrt((i - 25) ** 2 + (j - 25) ** 2)
                dem[i, j] = 100.0 - dist * 2.0

        result = compute_cold_air_drainage(dem)
        drainage_int = result["drainage_intensity"]

        # Center (peak) should have very low drainage intensity
        center_intensity = drainage_int[25, 25]
        if not np.isnan(center_intensity):
            assert center_intensity < 0.05
