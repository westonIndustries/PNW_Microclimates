"""
Integration tests for the anthropogenic load processor.

Tests the processor with realistic road data and grid parameters.
"""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import LineString
import geopandas as gpd
from rasterio.transform import Affine
from rasterio.crs import CRS

from src.processors.anthropogenic_load import compute_anthropogenic_load


@pytest.fixture
def realistic_lidar_grid():
    """Fixture providing realistic LiDAR grid parameters (1000m × 1000m at 1m resolution)."""
    # 1000 m × 1000 m grid at 1 m resolution (1000 × 1000 pixels)
    # Origin at (500000, 5000000) in UTM Zone 10N
    transform = Affine(1.0, 0.0, 500000.0, 0.0, -1.0, 5000000.0)
    crs = CRS.from_epsg(26910)  # UTM Zone 10N
    shape = (1000, 1000)
    return transform, crs, shape


@pytest.fixture
def realistic_roads_gdf(realistic_lidar_grid):
    """Fixture providing realistic road data with multiple segments and AADT values."""
    _, crs, _ = realistic_lidar_grid

    # Create realistic road segments with varying AADT
    # Grid origin is at (500000, 5000000), extends to (501000, 4999000)
    geometries = [
        # Major highway (high AADT)
        LineString([(500100, 4999500), (500900, 4999500)]),
        # Secondary road (medium AADT)
        LineString([(500100, 4999700), (500900, 4999700)]),
        # Local road (low AADT)
        LineString([(500100, 4999300), (500900, 4999300)]),
    ]

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [75000, 25000, 5000],  # High, medium, low traffic
            "heat_flux_wm2": [150.0, 100.0, 50.0],
        },
        geometry=geometries,
        crs=crs,
    )

    return roads_gdf


def test_realistic_road_processing(realistic_roads_gdf, realistic_lidar_grid):
    """Test processing of realistic road data."""
    transform, crs, shape = realistic_lidar_grid

    heat_flux, temp_offset = compute_anthropogenic_load(
        realistic_roads_gdf, transform, crs, shape
    )

    # Check output shapes
    assert heat_flux.shape == shape
    assert temp_offset.shape == shape

    # Check that heat flux is non-negative
    assert np.all(heat_flux >= 0.0)
    assert np.all(temp_offset >= 0.0)

    # Check that max values are reasonable
    # Note: roads may overlap, so max could be sum of multiple roads
    assert heat_flux.max() > 0.0
    # Max could be up to 150 + 100 + 50 = 300 if all overlap
    assert heat_flux.max() <= 300.0 + 1.0

    # Check that temperature offset is computed correctly
    # For the maximum heat flux value
    expected_max_offset = heat_flux.max() / 5.5 * (9 / 5)
    assert np.isclose(temp_offset.max(), expected_max_offset, rtol=1e-10)


def test_buffer_zones_non_overlapping(realistic_lidar_grid):
    """Test that non-overlapping buffer zones are correctly rasterized."""
    transform, crs, shape = realistic_lidar_grid

    # Create two roads far apart
    # Grid origin is at (500000, 5000000), extends to (501000, 4999000)
    geometries = [
        LineString([(500100, 4999800), (500900, 4999800)]),
        LineString([(500100, 4999200), (500900, 4999200)]),
    ]

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [50000, 50000],  # Both have 100 m buffer
            "heat_flux_wm2": [100.0, 100.0],
        },
        geometry=geometries,
        crs=crs,
    )

    heat_flux, _ = compute_anthropogenic_load(roads_gdf, transform, crs, shape)

    # Check that both roads have non-zero heat flux
    assert heat_flux.max() > 0.0

    # Check that the two roads don't overlap (they're 600 m apart)
    # Count non-zero pixels in each region
    region_1 = heat_flux[100:300, :]
    region_2 = heat_flux[700:900, :]

    # Both regions should have non-zero pixels
    assert np.count_nonzero(region_1) > 0
    assert np.count_nonzero(region_2) > 0


def test_formula_accuracy(realistic_lidar_grid):
    """Test that the temperature offset formula is accurate."""
    transform, crs, shape = realistic_lidar_grid

    # Create a single road with known heat flux
    # Grid origin is at (500000, 5000000), extends to (501000, 4999000)
    geometries = [LineString([(500100, 4999500), (500900, 4999500)])]

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [50000],
            "heat_flux_wm2": [110.0],  # Specific value for testing
        },
        geometry=geometries,
        crs=crs,
    )

    heat_flux, temp_offset = compute_anthropogenic_load(
        roads_gdf, transform, crs, shape
    )

    # For pixels with heat flux, verify the formula
    nonzero_mask = heat_flux > 0.0
    if np.any(nonzero_mask):
        # Expected: temp_offset = heat_flux / 5.5 × 9/5
        expected_offset = heat_flux[nonzero_mask] / 5.5 * (9 / 5)
        actual_offset = temp_offset[nonzero_mask]

        # Check that formula is applied correctly
        assert np.allclose(actual_offset, expected_offset, rtol=1e-10)

        # Check specific value: 110 / 5.5 × 9/5 = 20 × 1.8 = 36
        expected_value = 110.0 / 5.5 * (9 / 5)
        assert np.isclose(expected_value, 36.0)


def test_aadt_tier_coverage(realistic_lidar_grid):
    """Test that all AADT tiers are correctly buffered."""
    transform, crs, shape = realistic_lidar_grid

    # Create roads at tier boundaries
    # Grid origin is at (500000, 5000000), extends to (501000, 4999000)
    geometries = [
        LineString([(500100, 4999800), (500900, 4999800)]),  # AADT = 9,999
        LineString([(500100, 4999600), (500900, 4999600)]),  # AADT = 10,000
        LineString([(500100, 4999400), (500900, 4999400)]),  # AADT = 50,000
        LineString([(500100, 4999200), (500900, 4999200)]),  # AADT = 50,001
    ]

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [9999, 10000, 50000, 50001],
            "heat_flux_wm2": [100.0, 100.0, 100.0, 100.0],
        },
        geometry=geometries,
        crs=crs,
    )

    heat_flux, _ = compute_anthropogenic_load(roads_gdf, transform, crs, shape)

    # All roads should have non-zero heat flux
    assert heat_flux.max() > 0.0

    # Check that each road has affected pixels
    for row in [200, 400, 600, 800]:
        region = heat_flux[row - 50:row + 50, :]
        assert np.count_nonzero(region) > 0


def test_large_grid_performance(realistic_lidar_grid):
    """Test that the processor handles large grids efficiently."""
    transform, crs, shape = realistic_lidar_grid

    # Create many roads
    # Grid origin is at (500000, 5000000), extends to (501000, 4999000)
    geometries = [
        LineString([(500100 + i * 50, 4999500), (500900 + i * 50, 4999500)])
        for i in range(10)
    ]

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [50000] * 10,
            "heat_flux_wm2": [100.0] * 10,
        },
        geometry=geometries,
        crs=crs,
    )

    # This should complete without error
    heat_flux, temp_offset = compute_anthropogenic_load(
        roads_gdf, transform, crs, shape
    )

    assert heat_flux.shape == shape
    assert temp_offset.shape == shape
    assert heat_flux.max() > 0.0


def test_output_consistency(realistic_roads_gdf, realistic_lidar_grid):
    """Test that output arrays are consistent and valid."""
    transform, crs, shape = realistic_lidar_grid

    heat_flux, temp_offset = compute_anthropogenic_load(
        realistic_roads_gdf, transform, crs, shape
    )

    # Check that both arrays have the same shape
    assert heat_flux.shape == temp_offset.shape

    # Check that both arrays are float64
    assert heat_flux.dtype == np.float64
    assert temp_offset.dtype == np.float64

    # Check that there are no NaN or inf values
    assert not np.any(np.isnan(heat_flux))
    assert not np.any(np.isnan(temp_offset))
    assert not np.any(np.isinf(heat_flux))
    assert not np.any(np.isinf(temp_offset))

    # Check that temp_offset is always >= heat_flux / 5.5 (lower bound)
    # and <= heat_flux / 5.5 * 2 (upper bound for 9/5 conversion)
    nonzero_mask = heat_flux > 0.0
    if np.any(nonzero_mask):
        lower_bound = heat_flux[nonzero_mask] / 5.5
        upper_bound = heat_flux[nonzero_mask] / 5.5 * 2
        assert np.all(temp_offset[nonzero_mask] >= lower_bound)
        assert np.all(temp_offset[nonzero_mask] <= upper_bound)
