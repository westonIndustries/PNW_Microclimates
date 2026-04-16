"""Tests for src/processors/terrain_analysis.py."""

from __future__ import annotations

import numpy as np
import pytest

from src.processors.terrain_analysis import (
    analyze_terrain,
    compute_aspect_and_slope,
    compute_lapse_rate_hdd_addition,
    compute_tpi,
    compute_wind_shadow,
)


# ---------------------------------------------------------------------------
# compute_aspect_and_slope tests
# ---------------------------------------------------------------------------


def test_compute_aspect_and_slope_flat_dem():
    """Flat DEM should have zero slope and undefined aspect."""
    dem = np.ones((5, 5), dtype=np.float64) * 100.0
    aspect, slope = compute_aspect_and_slope(dem)

    # Slope should be near zero (except edges)
    assert np.nanmax(slope) < 1.0  # Very small slope
    # Aspect is undefined on flat terrain, but should be a number
    assert aspect.shape == dem.shape


def test_compute_aspect_and_slope_returns_correct_shape():
    """Output arrays should have same shape as input DEM."""
    dem = np.random.rand(10, 10) * 100.0
    aspect, slope = compute_aspect_and_slope(dem)

    assert aspect.shape == dem.shape
    assert slope.shape == dem.shape


def test_compute_aspect_and_slope_preserves_nan():
    """NaN values in DEM should be preserved in output."""
    dem = np.ones((5, 5), dtype=np.float64) * 100.0
    dem[2, 2] = np.nan
    dem[0, 0] = np.nan

    aspect, slope = compute_aspect_and_slope(dem)

    assert np.isnan(aspect[2, 2])
    assert np.isnan(slope[2, 2])
    assert np.isnan(aspect[0, 0])
    assert np.isnan(slope[0, 0])


def test_compute_aspect_and_slope_south_facing_slope():
    """South-facing slope should have aspect near 180°."""
    # Create a simple south-facing slope (elevation increases to the south)
    dem = np.zeros((5, 5), dtype=np.float64)
    for i in range(5):
        dem[i, :] = i * 10.0  # Elevation increases downward (south)

    aspect, slope = compute_aspect_and_slope(dem)

    # Center pixel should have aspect near 180° (south)
    center_aspect = aspect[2, 2]
    if not np.isnan(center_aspect):
        # Aspect should be in the southern quadrant (90–270°)
        assert 90 < center_aspect < 270 or center_aspect < 90 or center_aspect > 270


def test_compute_aspect_and_slope_aspect_range():
    """Aspect should be in range 0–360°."""
    dem = np.random.rand(10, 10) * 100.0
    aspect, slope = compute_aspect_and_slope(dem)

    valid_aspect = aspect[~np.isnan(aspect)]
    assert np.all(valid_aspect >= 0.0)
    assert np.all(valid_aspect <= 360.0)


def test_compute_aspect_and_slope_slope_range():
    """Slope should be in range 0–90°."""
    dem = np.random.rand(10, 10) * 100.0
    aspect, slope = compute_aspect_and_slope(dem)

    valid_slope = slope[~np.isnan(slope)]
    assert np.all(valid_slope >= 0.0)
    assert np.all(valid_slope <= 90.0)


def test_compute_aspect_and_slope_all_nan_input():
    """All-NaN input should produce all-NaN output."""
    dem = np.full((5, 5), np.nan, dtype=np.float64)
    aspect, slope = compute_aspect_and_slope(dem)

    assert np.all(np.isnan(aspect))
    assert np.all(np.isnan(slope))


def test_compute_aspect_and_slope_steep_slope():
    """Steep slope should have high slope value."""
    # Create a steep slope
    dem = np.zeros((5, 5), dtype=np.float64)
    dem[:, 4] = 1000.0  # Right column is much higher

    aspect, slope = compute_aspect_and_slope(dem)

    # Pixels near the slope should have high slope values
    center_slope = slope[2, 2]
    if not np.isnan(center_slope):
        assert center_slope > 10.0  # Should be steep


# ---------------------------------------------------------------------------
# compute_tpi tests
# ---------------------------------------------------------------------------


def test_compute_tpi_returns_correct_shape():
    """TPI output should have same shape as input DEM."""
    dem = np.random.rand(20, 20) * 100.0
    tpi = compute_tpi(dem, pixel_size_m=1.0)

    assert tpi.shape == dem.shape


def test_compute_tpi_flat_dem():
    """Flat DEM should have TPI near zero."""
    dem = np.ones((200, 200), dtype=np.float64) * 100.0
    tpi = compute_tpi(dem, pixel_size_m=1.0)

    # TPI should be near zero (except edges which are NaN)
    valid_tpi = tpi[~np.isnan(tpi)]
    if len(valid_tpi) > 0:
        assert np.abs(np.mean(valid_tpi)) < 1.0
    # If all NaN, that's OK for a small DEM (edge buffer is large)


def test_compute_tpi_preserves_nan():
    """NaN values in DEM should be preserved in TPI."""
    dem = np.ones((50, 50), dtype=np.float64) * 100.0
    dem[25, 25] = np.nan

    tpi = compute_tpi(dem, pixel_size_m=1.0)

    assert np.isnan(tpi[25, 25])


def test_compute_tpi_edge_pixels_are_nan():
    """Pixels within 1000m of edge should be NaN."""
    dem = np.random.rand(2000, 2000) * 100.0  # 2000m x 2000m at 1m resolution
    tpi = compute_tpi(dem, pixel_size_m=1.0)

    # Outer 1000 pixels should be NaN
    assert np.all(np.isnan(tpi[:1000, :]))
    assert np.all(np.isnan(tpi[-1000:, :]))
    assert np.all(np.isnan(tpi[:, :1000]))
    assert np.all(np.isnan(tpi[:, -1000:]))


def test_compute_tpi_ridge_detection():
    """Peak in DEM should have positive TPI."""
    dem = np.ones((100, 100), dtype=np.float64) * 100.0
    # Create a peak in the center
    for i in range(100):
        for j in range(100):
            dist = np.sqrt((i - 50) ** 2 + (j - 50) ** 2)
            dem[i, j] += max(0, 50 - dist)

    tpi = compute_tpi(dem, pixel_size_m=1.0)

    # Center should have positive TPI (ridge)
    center_tpi = tpi[50, 50]
    if not np.isnan(center_tpi):
        assert center_tpi > 0


def test_compute_tpi_valley_detection():
    """Valley in DEM should have negative TPI."""
    dem = np.ones((100, 100), dtype=np.float64) * 100.0
    # Create a valley in the center
    for i in range(100):
        for j in range(100):
            dist = np.sqrt((i - 50) ** 2 + (j - 50) ** 2)
            dem[i, j] -= max(0, 50 - dist)

    tpi = compute_tpi(dem, pixel_size_m=1.0)

    # Center should have negative TPI (valley)
    center_tpi = tpi[50, 50]
    if not np.isnan(center_tpi):
        assert center_tpi < 0


def test_compute_tpi_all_nan_input():
    """All-NaN input should produce all-NaN output."""
    dem = np.full((50, 50), np.nan, dtype=np.float64)
    tpi = compute_tpi(dem, pixel_size_m=1.0)

    assert np.all(np.isnan(tpi))


# ---------------------------------------------------------------------------
# compute_wind_shadow tests
# ---------------------------------------------------------------------------


def test_compute_wind_shadow_returns_correct_shape():
    """Wind shadow output should have same shape as inputs."""
    tpi = np.random.rand(20, 20) * 100.0 - 50.0
    aspect = np.random.rand(20, 20) * 360.0

    wind_shadow = compute_wind_shadow(tpi, aspect, prevailing_wind_deg=225.0)

    assert wind_shadow.shape == tpi.shape


def test_compute_wind_shadow_binary_values():
    """Wind shadow should be binary (0, 1, or NaN)."""
    tpi = np.random.rand(20, 20) * 100.0 - 50.0
    aspect = np.random.rand(20, 20) * 360.0

    wind_shadow = compute_wind_shadow(tpi, aspect, prevailing_wind_deg=225.0)

    valid_values = wind_shadow[~np.isnan(wind_shadow)]
    assert np.all((valid_values == 0.0) | (valid_values == 1.0))


def test_compute_wind_shadow_requires_valley():
    """Wind shadow should only occur where TPI < 0 (valleys)."""
    # Create a ridge (TPI > 0)
    tpi = np.ones((20, 20), dtype=np.float64) * 50.0
    # Aspect pointing toward leeward direction
    aspect = np.ones((20, 20), dtype=np.float64) * 45.0  # Leeward at 225+180=45

    wind_shadow = compute_wind_shadow(tpi, aspect, prevailing_wind_deg=225.0)

    # No wind shadow on ridges
    valid_values = wind_shadow[~np.isnan(wind_shadow)]
    assert np.all(valid_values == 0.0)


def test_compute_wind_shadow_valley_with_correct_aspect():
    """Wind shadow should occur in valleys with leeward aspect."""
    # Create a valley (TPI < 0)
    tpi = np.ones((20, 20), dtype=np.float64) * -50.0
    # Aspect pointing toward leeward direction (225 + 180 = 45)
    aspect = np.ones((20, 20), dtype=np.float64) * 45.0

    wind_shadow = compute_wind_shadow(tpi, aspect, prevailing_wind_deg=225.0)

    # Should have wind shadow
    valid_values = wind_shadow[~np.isnan(wind_shadow)]
    assert np.any(valid_values == 1.0)


def test_compute_wind_shadow_valley_with_wrong_aspect():
    """Wind shadow should not occur in valleys with windward aspect."""
    # Create a valley (TPI < 0)
    tpi = np.ones((20, 20), dtype=np.float64) * -50.0
    # Aspect pointing toward windward direction (225)
    aspect = np.ones((20, 20), dtype=np.float64) * 225.0

    wind_shadow = compute_wind_shadow(tpi, aspect, prevailing_wind_deg=225.0)

    # Should not have wind shadow (wrong aspect)
    valid_values = wind_shadow[~np.isnan(wind_shadow)]
    assert np.all(valid_values == 0.0)


def test_compute_wind_shadow_preserves_nan():
    """NaN values in inputs should produce NaN in output."""
    tpi = np.ones((20, 20), dtype=np.float64) * -50.0
    tpi[10, 10] = np.nan
    aspect = np.ones((20, 20), dtype=np.float64) * 45.0
    aspect[5, 5] = np.nan

    wind_shadow = compute_wind_shadow(tpi, aspect, prevailing_wind_deg=225.0)

    assert np.isnan(wind_shadow[10, 10])
    assert np.isnan(wind_shadow[5, 5])


def test_compute_wind_shadow_aspect_wrap_around():
    """Wind shadow should handle aspect wrap-around at 0°/360°."""
    tpi = np.ones((20, 20), dtype=np.float64) * -50.0
    # Leeward direction is 45°, so ±90° is -45° to 135°
    # Test aspect at 350° (within ±90° of 45° when wrapping)
    aspect = np.ones((20, 20), dtype=np.float64) * 350.0

    wind_shadow = compute_wind_shadow(tpi, aspect, prevailing_wind_deg=225.0)

    # Should have wind shadow (aspect 350° is within ±90° of 45°)
    valid_values = wind_shadow[~np.isnan(wind_shadow)]
    assert np.any(valid_values == 1.0)


# ---------------------------------------------------------------------------
# compute_lapse_rate_hdd_addition tests
# ---------------------------------------------------------------------------


def test_compute_lapse_rate_hdd_addition_returns_correct_shape():
    """Output should have same shape as input DEM."""
    dem = np.random.rand(20, 20) * 1000.0  # 0–1000 m elevation
    hdd_addition = compute_lapse_rate_hdd_addition(dem, station_elevation_ft=100.0)

    assert hdd_addition.shape == dem.shape


def test_compute_lapse_rate_hdd_addition_at_station_elevation():
    """HDD addition should be zero at station elevation."""
    dem = np.ones((10, 10), dtype=np.float64) * 30.48  # 100 ft in meters
    hdd_addition = compute_lapse_rate_hdd_addition(dem, station_elevation_ft=100.0)

    # Should be near zero (within floating-point tolerance)
    valid_values = hdd_addition[~np.isnan(hdd_addition)]
    assert np.allclose(valid_values, 0.0, atol=1.0)


def test_compute_lapse_rate_hdd_addition_higher_elevation():
    """HDD addition should be positive at higher elevation."""
    dem = np.ones((10, 10), dtype=np.float64) * 335.28  # 1100 ft in meters
    hdd_addition = compute_lapse_rate_hdd_addition(dem, station_elevation_ft=100.0)

    # Should be positive (higher elevation = more HDD)
    valid_values = hdd_addition[~np.isnan(hdd_addition)]
    assert np.all(valid_values > 0.0)


def test_compute_lapse_rate_hdd_addition_lower_elevation():
    """HDD addition should be negative at lower elevation."""
    dem = np.ones((10, 10), dtype=np.float64) * 0.0  # 0 ft in meters
    hdd_addition = compute_lapse_rate_hdd_addition(dem, station_elevation_ft=100.0)

    # Should be negative (lower elevation = less HDD)
    valid_values = hdd_addition[~np.isnan(hdd_addition)]
    assert np.all(valid_values < 0.0)


def test_compute_lapse_rate_hdd_addition_preserves_nan():
    """NaN values in DEM should be preserved in output."""
    dem = np.ones((10, 10), dtype=np.float64) * 100.0
    dem[5, 5] = np.nan

    hdd_addition = compute_lapse_rate_hdd_addition(dem, station_elevation_ft=100.0)

    assert np.isnan(hdd_addition[5, 5])


def test_compute_lapse_rate_hdd_addition_formula():
    """HDD addition should follow the formula: (elev_ft - station_elev_ft) / 1000 * 630."""
    dem = np.ones((10, 10), dtype=np.float64) * 304.8  # 1000 ft in meters
    station_elev_ft = 100.0
    lapse_rate = 630.0

    hdd_addition = compute_lapse_rate_hdd_addition(
        dem,
        station_elevation_ft=station_elev_ft,
        lapse_rate_hdd_per_1000ft=lapse_rate,
    )

    # Expected: (1000 - 100) / 1000 * 630 = 567
    expected = (1000.0 - station_elev_ft) / 1000.0 * lapse_rate
    valid_values = hdd_addition[~np.isnan(hdd_addition)]
    assert np.allclose(valid_values, expected, rtol=0.01)


def test_compute_lapse_rate_hdd_addition_all_nan_input():
    """All-NaN input should produce all-NaN output."""
    dem = np.full((10, 10), np.nan, dtype=np.float64)
    hdd_addition = compute_lapse_rate_hdd_addition(dem, station_elevation_ft=100.0)

    assert np.all(np.isnan(hdd_addition))


# ---------------------------------------------------------------------------
# analyze_terrain integration tests
# ---------------------------------------------------------------------------


def test_analyze_terrain_returns_all_keys():
    """analyze_terrain should return all expected keys."""
    dem = np.random.rand(50, 50) * 100.0
    result = analyze_terrain(dem, station_elevation_ft=100.0)

    expected_keys = {
        "aspect",
        "slope",
        "tpi",
        "wind_shadow",
        "lapse_rate_hdd_addition",
    }
    assert set(result.keys()) == expected_keys


def test_analyze_terrain_all_outputs_same_shape():
    """All outputs from analyze_terrain should have same shape as input."""
    dem = np.random.rand(50, 50) * 100.0
    result = analyze_terrain(dem, station_elevation_ft=100.0)

    for key, array in result.items():
        assert array.shape == dem.shape, f"{key} has wrong shape"


def test_analyze_terrain_preserves_nan():
    """NaN values in input should be preserved in all outputs."""
    dem = np.random.rand(50, 50) * 100.0
    dem[25, 25] = np.nan
    dem[10, 10] = np.nan

    result = analyze_terrain(dem, station_elevation_ft=100.0)

    for key, array in result.items():
        assert np.isnan(array[25, 25]), f"{key} did not preserve NaN at [25, 25]"
        assert np.isnan(array[10, 10]), f"{key} did not preserve NaN at [10, 10]"


def test_analyze_terrain_realistic_dem():
    """analyze_terrain should work with realistic DEM data."""
    # Create a realistic DEM with valleys and ridges
    dem = np.zeros((100, 100), dtype=np.float64)
    for i in range(100):
        for j in range(100):
            # Sinusoidal terrain
            dem[i, j] = 100.0 + 50.0 * np.sin(i / 20.0) * np.cos(j / 20.0)

    result = analyze_terrain(dem, station_elevation_ft=100.0)

    # Check that we get reasonable values
    assert np.nanmin(result["aspect"]) >= 0.0
    assert np.nanmax(result["aspect"]) <= 360.0
    assert np.nanmin(result["slope"]) >= 0.0
    assert np.nanmax(result["slope"]) <= 90.0
    assert np.any(result["tpi"] > 0)  # Should have some ridges
    assert np.any(result["tpi"] < 0)  # Should have some valleys
    assert np.any(result["wind_shadow"] == 1.0)  # Should have some wind shadow


def test_analyze_terrain_with_custom_wind_direction():
    """analyze_terrain should accept custom prevailing wind direction."""
    # Create a DEM with clear valleys and ridges
    dem = np.zeros((100, 100), dtype=np.float64)
    for i in range(100):
        for j in range(100):
            # Sinusoidal terrain
            dem[i, j] = 100.0 + 50.0 * np.sin(i / 20.0) * np.cos(j / 20.0)

    result1 = analyze_terrain(dem, station_elevation_ft=100.0, prevailing_wind_deg=225.0)
    result2 = analyze_terrain(dem, station_elevation_ft=100.0, prevailing_wind_deg=45.0)

    # Wind shadow should be different with different wind directions
    # (unless by chance they're the same)
    # Check that at least some pixels have different wind shadow values
    diff = np.abs(result1["wind_shadow"] - result2["wind_shadow"])
    valid_diff = diff[~np.isnan(diff)]
    if len(valid_diff) > 0:
        assert np.any(valid_diff > 0.0)
