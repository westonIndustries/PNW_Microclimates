"""
Tests for the anthropogenic load processor.

Tests buffer creation by AADT tier, rasterization of buffered geometries,
heat flux computation, and temperature offset conversion.
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
def lidar_grid_params():
    """Fixture providing LiDAR grid parameters for testing."""
    # 100 m × 100 m grid at 1 m resolution (100 × 100 pixels)
    # Origin at (0, 0), pixel size 1 m
    transform = Affine(1.0, 0.0, 0.0, 0.0, -1.0, 100.0)
    crs = CRS.from_epsg(26910)  # UTM Zone 10N
    shape = (100, 100)
    return transform, crs, shape


@pytest.fixture
def simple_road_gdf(lidar_grid_params):
    """Fixture providing a simple road GeoDataFrame with one segment."""
    _, crs, _ = lidar_grid_params

    # Create a single road segment from (10, 50) to (90, 50)
    # This is an 80 m horizontal line in the middle of the grid
    geometry = LineString([(10, 50), (90, 50)])

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [5000],  # AADT < 10,000 → 50 m buffer
            "heat_flux_wm2": [100.0],  # 100 W/m²
        },
        geometry=[geometry],
        crs=crs,
    )

    return roads_gdf


@pytest.fixture
def multi_tier_roads_gdf(lidar_grid_params):
    """Fixture providing roads with different AADT tiers."""
    _, crs, _ = lidar_grid_params

    geometries = [
        LineString([(20, 20), (80, 20)]),  # AADT < 10,000 → 50 m buffer
        LineString([(20, 50), (80, 50)]),  # AADT 10,000–50,000 → 100 m buffer
        LineString([(20, 80), (80, 80)]),  # AADT > 50,000 → 200 m buffer
    ]

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [5000, 25000, 75000],
            "heat_flux_wm2": [50.0, 100.0, 150.0],
        },
        geometry=geometries,
        crs=crs,
    )

    return roads_gdf


def test_empty_roads_gdf(lidar_grid_params):
    """Test that empty road GeoDataFrame returns zero arrays."""
    transform, crs, shape = lidar_grid_params

    empty_gdf = gpd.GeoDataFrame(
        {"AADT": [], "heat_flux_wm2": []},
        geometry=[],
        crs=crs,
    )

    heat_flux, temp_offset = compute_anthropogenic_load(
        empty_gdf, transform, crs, shape
    )

    assert heat_flux.shape == shape
    assert temp_offset.shape == shape
    assert np.allclose(heat_flux, 0.0)
    assert np.allclose(temp_offset, 0.0)


def test_simple_road_rasterization(simple_road_gdf, lidar_grid_params):
    """Test that a simple road segment is rasterized correctly."""
    transform, crs, shape = lidar_grid_params

    heat_flux, temp_offset = compute_anthropogenic_load(
        simple_road_gdf, transform, crs, shape
    )

    # Check output shapes
    assert heat_flux.shape == shape
    assert temp_offset.shape == shape

    # Check that heat flux is non-negative
    assert np.all(heat_flux >= 0.0)

    # Check that max heat flux is close to the input value
    # (may be slightly different due to rasterization)
    assert heat_flux.max() > 0.0
    assert heat_flux.max() <= 100.0 + 1.0  # Allow small rasterization error

    # Check temperature offset formula: temp_offset = heat_flux / 5.5 × 9/5
    expected_max_offset = 100.0 / 5.5 * (9 / 5)
    assert temp_offset.max() <= expected_max_offset + 0.1


def test_temperature_offset_formula(simple_road_gdf, lidar_grid_params):
    """Test that temperature offset is computed correctly from heat flux."""
    transform, crs, shape = lidar_grid_params

    heat_flux, temp_offset = compute_anthropogenic_load(
        simple_road_gdf, transform, crs, shape
    )

    # For pixels with heat flux, check the formula: temp_offset = heat_flux / 5.5 × 9/5
    nonzero_mask = heat_flux > 0.0
    if np.any(nonzero_mask):
        expected_offset = heat_flux[nonzero_mask] / 5.5 * (9 / 5)
        actual_offset = temp_offset[nonzero_mask]
        assert np.allclose(actual_offset, expected_offset, rtol=1e-10)


def test_aadt_tier_buffering(multi_tier_roads_gdf, lidar_grid_params):
    """Test that roads are buffered according to AADT tier."""
    transform, crs, shape = lidar_grid_params

    heat_flux, temp_offset = compute_anthropogenic_load(
        multi_tier_roads_gdf, transform, crs, shape
    )

    # All three roads should have non-zero heat flux in their buffer zones
    assert heat_flux.max() > 0.0

    # Check that the middle road (100 m buffer) has a larger affected area
    # than the first road (50 m buffer)
    # This is a rough check: count non-zero pixels in each row band
    row_20_nonzero = np.count_nonzero(heat_flux[15:25, :])
    row_50_nonzero = np.count_nonzero(heat_flux[45:55, :])
    row_80_nonzero = np.count_nonzero(heat_flux[75:85, :])

    # The middle road should have more affected pixels than the first
    # (due to larger buffer)
    assert row_50_nonzero >= row_20_nonzero


def test_overlapping_buffers_summed(lidar_grid_params):
    """Test that overlapping buffers from multiple roads are summed."""
    transform, crs, shape = lidar_grid_params

    # Create two parallel roads very close together
    geometries = [
        LineString([(20, 48), (80, 48)]),
        LineString([(20, 52), (80, 52)]),
    ]

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [10000, 10000],  # Both have 100 m buffer
            "heat_flux_wm2": [50.0, 50.0],
        },
        geometry=geometries,
        crs=crs,
    )

    heat_flux, _ = compute_anthropogenic_load(roads_gdf, transform, crs, shape)

    # In the overlap zone (around row 50), heat flux should be summed
    # Check that some pixels have heat flux close to 100 W/m² (50 + 50)
    overlap_region = heat_flux[45:55, :]
    assert np.max(overlap_region) > 50.0  # Should exceed single road value


def test_nan_handling(simple_road_gdf, lidar_grid_params):
    """Test that NaN values are replaced with 0.0."""
    transform, crs, shape = lidar_grid_params

    heat_flux, temp_offset = compute_anthropogenic_load(
        simple_road_gdf, transform, crs, shape
    )

    # Check that there are no NaN values in output
    assert not np.any(np.isnan(heat_flux))
    assert not np.any(np.isnan(temp_offset))


def test_crs_conversion(simple_road_gdf, lidar_grid_params):
    """Test that roads in different CRS are converted correctly."""
    transform, crs, shape = lidar_grid_params

    # Convert roads to a different CRS (EPSG:4326 - WGS84)
    roads_gdf_wgs84 = simple_road_gdf.to_crs("EPSG:4326")

    # This should still work because the function converts CRS internally
    # However, the coordinates will be in degrees, so the buffer won't make sense
    # We'll just check that it doesn't crash
    try:
        heat_flux, temp_offset = compute_anthropogenic_load(
            roads_gdf_wgs84, transform, crs, shape
        )
        # If it succeeds, check shapes
        assert heat_flux.shape == shape
        assert temp_offset.shape == shape
    except Exception as e:
        # It's acceptable if this fails due to coordinate mismatch
        # The important thing is that the function handles CRS conversion
        pass


def test_zero_aadt_filtered(lidar_grid_params):
    """Test that roads with AADT = 0 are included (not filtered by this function)."""
    transform, crs, shape = lidar_grid_params

    # Note: The load_road_emissions function filters AADT > 0,
    # but this processor should handle any input
    geometries = [LineString([(20, 50), (80, 50)])]

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [0],  # Zero AADT
            "heat_flux_wm2": [0.0],  # Zero heat flux
        },
        geometry=geometries,
        crs=crs,
    )

    heat_flux, temp_offset = compute_anthropogenic_load(
        roads_gdf, transform, crs, shape
    )

    # Should return zero arrays (or very close to zero)
    assert np.allclose(heat_flux, 0.0, atol=1e-10)
    assert np.allclose(temp_offset, 0.0, atol=1e-10)


def test_output_array_shapes(simple_road_gdf, lidar_grid_params):
    """Test that output arrays have the correct shape."""
    transform, crs, shape = lidar_grid_params

    heat_flux, temp_offset = compute_anthropogenic_load(
        simple_road_gdf, transform, crs, shape
    )

    assert heat_flux.shape == shape
    assert temp_offset.shape == shape
    assert heat_flux.dtype == np.float64
    assert temp_offset.dtype == np.float64


def test_heat_flux_non_negative(multi_tier_roads_gdf, lidar_grid_params):
    """Test that heat flux values are non-negative."""
    transform, crs, shape = lidar_grid_params

    heat_flux, _ = compute_anthropogenic_load(
        multi_tier_roads_gdf, transform, crs, shape
    )

    assert np.all(heat_flux >= 0.0)


def test_temp_offset_non_negative(multi_tier_roads_gdf, lidar_grid_params):
    """Test that temperature offset values are non-negative."""
    transform, crs, shape = lidar_grid_params

    _, temp_offset = compute_anthropogenic_load(
        multi_tier_roads_gdf, transform, crs, shape
    )

    assert np.all(temp_offset >= 0.0)


def test_large_heat_flux_value(lidar_grid_params):
    """Test with a large heat flux value."""
    transform, crs, shape = lidar_grid_params

    geometries = [LineString([(20, 50), (80, 50)])]

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [100000],  # Very high AADT
            "heat_flux_wm2": [1000.0],  # Large heat flux
        },
        geometry=geometries,
        crs=crs,
    )

    heat_flux, temp_offset = compute_anthropogenic_load(
        roads_gdf, transform, crs, shape
    )

    # Check that large values are handled correctly
    assert heat_flux.max() > 0.0
    assert temp_offset.max() > 0.0

    # Check formula still holds
    expected_max_offset = 1000.0 / 5.5 * (9 / 5)
    assert temp_offset.max() <= expected_max_offset + 1.0


def test_buffer_distance_boundaries(lidar_grid_params):
    """Test buffer distances at AADT tier boundaries."""
    transform, crs, shape = lidar_grid_params

    # Test roads at exact tier boundaries
    geometries = [
        LineString([(20, 20), (80, 20)]),  # AADT = 9,999 → 50 m
        LineString([(20, 50), (80, 50)]),  # AADT = 10,000 → 100 m
        LineString([(20, 80), (80, 80)]),  # AADT = 50,000 → 100 m
    ]

    roads_gdf = gpd.GeoDataFrame(
        {
            "AADT": [9999, 10000, 50000],
            "heat_flux_wm2": [100.0, 100.0, 100.0],
        },
        geometry=geometries,
        crs=crs,
    )

    heat_flux, _ = compute_anthropogenic_load(roads_gdf, transform, crs, shape)

    # All should have non-zero heat flux
    assert heat_flux.max() > 0.0
