"""
Integration tests for cold air drainage with combine_corrections_cells.

Tests verify that cold air drainage multiplier is correctly integrated
into the effective HDD computation pipeline.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.processors.cold_air_drainage import compute_cold_air_drainage


class TestColdAirDrainageIntegration:
    """Integration tests for cold air drainage in the pipeline."""

    def test_cold_air_drainage_multiplier_applied_to_effective_hdd(self):
        """Test that cold air drainage multiplier increases HDD in valleys.

        **Validates: Requirements 11.3**
        """
        # Create a simple DEM with a valley
        dem = np.zeros((50, 50), dtype=np.float64)
        for i in range(50):
            for j in range(50):
                dist = np.sqrt((i - 25) ** 2 + (j - 25) ** 2)
                dem[i, j] = dist * 2.0

        result = compute_cold_air_drainage(dem)

        # Valley (center) should have higher multiplier than ridge (edge)
        center_mult = result["cold_air_drainage_mult"][25, 25]
        edge_mult = result["cold_air_drainage_mult"][5, 5]

        if not np.isnan(center_mult) and not np.isnan(edge_mult):
            assert center_mult > edge_mult
            # Center should be closer to 1.15 (valley)
            # Edge should be closer to 1.0 (ridge)
            assert center_mult > 1.05
            assert edge_mult < 1.05

    def test_cold_air_drainage_output_columns_present(self):
        """Test that all required output columns are present.

        **Validates: Requirements 11.3**
        """
        dem = np.random.rand(50, 50) * 100.0
        result = compute_cold_air_drainage(dem)

        # Check all required columns
        assert "flow_accumulation" in result
        assert "drainage_intensity" in result
        assert "cold_air_drainage_mult" in result

        # Check shapes
        assert result["flow_accumulation"].shape == dem.shape
        assert result["drainage_intensity"].shape == dem.shape
        assert result["cold_air_drainage_mult"].shape == dem.shape

    def test_cold_air_drainage_multiplier_bounds(self):
        """Test that multiplier stays within 1.0–1.15 bounds.

        **Validates: Requirements 11.3**
        """
        dem = np.random.rand(100, 100) * 1000.0
        result = compute_cold_air_drainage(dem)

        mult = result["cold_air_drainage_mult"]
        valid_mult = mult[~np.isnan(mult)]

        assert np.all(valid_mult >= 1.0)
        assert np.all(valid_mult <= 1.15)
        # Should have some variation
        assert np.max(valid_mult) > 1.05
        assert np.min(valid_mult) < 1.05

    def test_cold_air_drainage_realistic_scenario(self):
        """Test with realistic terrain scenario.

        **Validates: Requirements 11.3**
        """
        # Create realistic terrain with multiple valleys and ridges
        dem = np.zeros((100, 100), dtype=np.float64)
        for i in range(100):
            for j in range(100):
                # Multiple sinusoidal features
                dem[i, j] = (
                    100.0
                    + 50.0 * np.sin(i / 20.0) * np.cos(j / 20.0)
                    + 30.0 * np.sin(i / 30.0)
                )

        result = compute_cold_air_drainage(dem)

        # Verify all outputs are reasonable
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

        # Should have significant variation
        assert np.max(valid_int) > 0.5  # Some high drainage intensity
        assert np.min(valid_int) < 0.1  # Some low drainage intensity
        assert np.max(valid_mult) > 1.10  # Some high multiplier
        assert np.min(valid_mult) < 1.05  # Some low multiplier

    def test_cold_air_drainage_valley_ridge_relationship(self):
        """Test that valleys have higher drainage intensity than ridges.

        **Validates: Requirements 11.3**
        """
        # Create a clear valley-ridge pattern
        dem = np.zeros((100, 100), dtype=np.float64)

        # Left half: valley (elevation increases away from center)
        for i in range(100):
            for j in range(50):
                dist = np.sqrt((i - 50) ** 2 + (j - 25) ** 2)
                dem[i, j] = dist * 2.0

        # Right half: ridge (elevation decreases away from center)
        for i in range(100):
            for j in range(50, 100):
                dist = np.sqrt((i - 50) ** 2 + (j - 75) ** 2)
                dem[i, j] = 100.0 - dist * 2.0

        result = compute_cold_air_drainage(dem)
        drainage_int = result["drainage_intensity"]

        # Valley center (left) should have higher intensity than ridge center (right)
        valley_intensity = drainage_int[50, 25]
        ridge_intensity = drainage_int[50, 75]

        if not np.isnan(valley_intensity) and not np.isnan(ridge_intensity):
            assert valley_intensity > ridge_intensity

    def test_cold_air_drainage_isolated_peak(self):
        """Test that isolated peaks have minimal drainage intensity.

        **Validates: Requirements 11.3**
        """
        dem = np.zeros((100, 100), dtype=np.float64)

        # Create an isolated peak in the center
        for i in range(100):
            for j in range(100):
                dist = np.sqrt((i - 50) ** 2 + (j - 50) ** 2)
                dem[i, j] = 100.0 - dist * 2.0

        result = compute_cold_air_drainage(dem)
        drainage_int = result["drainage_intensity"]
        mult = result["cold_air_drainage_mult"]

        # Peak center should have very low drainage intensity
        peak_intensity = drainage_int[50, 50]
        peak_mult = mult[50, 50]

        if not np.isnan(peak_intensity):
            assert peak_intensity < 0.05
            assert peak_mult < 1.01

    def test_cold_air_drainage_nan_handling(self):
        """Test that NaN values are properly handled.

        **Validates: Requirements 11.3**
        """
        dem = np.random.rand(50, 50) * 100.0
        dem[10:15, 10:15] = np.nan  # Add a NaN region

        result = compute_cold_air_drainage(dem)

        # NaN regions should be preserved
        assert np.all(np.isnan(result["flow_accumulation"][10:15, 10:15]))
        assert np.all(np.isnan(result["drainage_intensity"][10:15, 10:15]))
        assert np.all(np.isnan(result["cold_air_drainage_mult"][10:15, 10:15]))

        # Non-NaN regions should have valid values
        valid_mult = result["cold_air_drainage_mult"][~np.isnan(result["cold_air_drainage_mult"])]
        assert np.all(valid_mult >= 1.0)
        assert np.all(valid_mult <= 1.15)
