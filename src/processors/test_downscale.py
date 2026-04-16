"""Tests for src/processors/downscale.py."""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import Affine

from src.processors.downscale import reproject_to_lidar_grid


# ---------------------------------------------------------------------------
# reproject_to_lidar_grid tests
# ---------------------------------------------------------------------------


def test_reproject_to_lidar_grid_returns_correct_shape():
    """reproject_to_lidar_grid returns array with LiDAR shape."""
    # Create a simple source raster (2x2)
    src_array = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    src_transform = Affine.identity()
    src_crs = CRS.from_epsg(26910)

    # Create target LiDAR grid (4x4)
    lidar_transform = Affine.identity()
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = (4, 4)

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    assert result.shape == lidar_shape
    assert result.dtype == np.float64


def test_reproject_to_lidar_grid_preserves_values_same_grid():
    """When source and target grids are identical, values are preserved."""
    # Create a simple source raster
    src_array = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    src_transform = Affine.identity()
    src_crs = CRS.from_epsg(26910)

    # Use the same grid for target
    lidar_transform = Affine.identity()
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = src_array.shape

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    # Values should be approximately preserved (bilinear interpolation)
    np.testing.assert_allclose(result, src_array, rtol=0.1)


def test_reproject_to_lidar_grid_handles_nan_values():
    """NaN values in source array are preserved in output."""
    # Create a source raster with NaN
    src_array = np.array([[1.0, np.nan], [3.0, 4.0]], dtype=np.float64)
    src_transform = Affine.identity()
    src_crs = CRS.from_epsg(26910)

    lidar_transform = Affine.identity()
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = src_array.shape

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    # Result should contain NaN values
    assert np.isnan(result).any()


def test_reproject_to_lidar_grid_upsamples_correctly():
    """Upsampling from coarse to fine grid produces reasonable values."""
    # Create a 2x2 source raster with uniform values
    src_array = np.array([[10.0, 10.0], [10.0, 10.0]], dtype=np.float64)
    src_transform = Affine.identity()
    src_crs = CRS.from_epsg(26910)

    # Upsample to 4x4
    lidar_transform = Affine.identity()
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = (4, 4)

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    # All non-NaN values should be close to 10.0
    valid_values = result[~np.isnan(result)]
    assert len(valid_values) > 0
    np.testing.assert_allclose(valid_values, 10.0, rtol=0.1)


def test_reproject_to_lidar_grid_downsamples_correctly():
    """Downsampling from fine to coarse grid produces reasonable values."""
    # Create a 4x4 source raster with uniform values
    src_array = np.array(
        [
            [5.0, 5.0, 5.0, 5.0],
            [5.0, 5.0, 5.0, 5.0],
            [5.0, 5.0, 5.0, 5.0],
            [5.0, 5.0, 5.0, 5.0],
        ],
        dtype=np.float64,
    )
    src_transform = Affine.identity()
    src_crs = CRS.from_epsg(26910)

    # Downsample to 2x2
    lidar_transform = Affine.identity()
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = (2, 2)

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    # All non-NaN values should be close to 5.0
    valid_values = result[~np.isnan(result)]
    assert len(valid_values) > 0
    np.testing.assert_allclose(valid_values, 5.0, rtol=0.1)


def test_reproject_to_lidar_grid_different_crs():
    """Reprojection between different CRS works correctly."""
    # Create a simple source raster in EPSG:4326
    src_array = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    src_transform = Affine.identity()
    src_crs = CRS.from_epsg(4326)

    # Target in EPSG:26910
    lidar_transform = Affine.identity()
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = (2, 2)

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    # Should return an array of the correct shape
    assert result.shape == lidar_shape
    assert result.dtype == np.float64


def test_reproject_to_lidar_grid_output_dtype_is_float64():
    """Output array is always float64."""
    # Create a source raster with integer dtype
    src_array = np.array([[1, 2], [3, 4]], dtype=np.int32)
    src_transform = Affine.identity()
    src_crs = CRS.from_epsg(26910)

    lidar_transform = Affine.identity()
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = (2, 2)

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    assert result.dtype == np.float64


def test_reproject_to_lidar_grid_with_offset_transform():
    """Reprojection with offset transforms works correctly."""
    # Create a source raster with an offset transform
    src_array = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    src_transform = Affine.translation(100, 200)  # Offset origin
    src_crs = CRS.from_epsg(26910)

    # Target with different offset
    lidar_transform = Affine.translation(100, 200)
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = (2, 2)

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    assert result.shape == lidar_shape
    assert result.dtype == np.float64


def test_reproject_to_lidar_grid_large_array():
    """Reprojection works with larger arrays."""
    # Create a larger source raster (100x100)
    src_array = np.random.rand(100, 100).astype(np.float64)
    src_transform = Affine.identity()
    src_crs = CRS.from_epsg(26910)

    # Target larger grid (200x200)
    lidar_transform = Affine.identity()
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = (200, 200)

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    assert result.shape == lidar_shape
    assert result.dtype == np.float64
    # Some values should be valid (not all NaN)
    assert not np.all(np.isnan(result))


def test_reproject_to_lidar_grid_all_nan_source():
    """When source is all NaN, output is all NaN."""
    src_array = np.full((2, 2), np.nan, dtype=np.float64)
    src_transform = Affine.identity()
    src_crs = CRS.from_epsg(26910)

    lidar_transform = Affine.identity()
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = (2, 2)

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    # All values should be NaN
    assert np.all(np.isnan(result))


def test_reproject_to_lidar_grid_mixed_values():
    """Reprojection with mixed valid and NaN values works correctly."""
    # Create a source raster with mixed values
    src_array = np.array(
        [[1.0, np.nan], [np.nan, 4.0]],
        dtype=np.float64,
    )
    src_transform = Affine.identity()
    src_crs = CRS.from_epsg(26910)

    lidar_transform = Affine.identity()
    lidar_crs = CRS.from_epsg(26910)
    lidar_shape = (2, 2)

    result = reproject_to_lidar_grid(
        src_array,
        src_transform,
        src_crs,
        lidar_transform,
        lidar_crs,
        lidar_shape,
    )

    # Result should have both valid and NaN values
    assert np.isnan(result).any()
    assert (~np.isnan(result)).any()
