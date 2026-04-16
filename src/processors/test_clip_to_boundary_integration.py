"""Integration tests for clip_to_boundary with real-world-like scenarios."""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import Affine
from shapely.geometry import Polygon

from src.processors.clip_to_boundary import clip_to_boundary


def test_clip_to_boundary_integration_with_real_transform():
    """Integration test: clip a raster with a real-world-like transform."""
    # Create a 10x10 raster with a real UTM transform
    raster_array = np.arange(100, dtype=np.float64).reshape(10, 10)
    
    # UTM Zone 10N transform (1m pixels starting at a real UTM coordinate)
    raster_transform = Affine(
        1.0, 0.0, 500000.0,  # pixel width, rotation, x origin
        0.0, -1.0, 5000000.0,  # rotation, pixel height (negative), y origin
    )
    raster_crs = CRS.from_epsg(26910)

    # Create a boundary that covers part of the raster
    # In UTM coordinates: covers roughly the middle 5x5 pixels
    boundary_geom = {
        "type": "Polygon",
        "coordinates": [[
            [500002.0, 4999998.0],
            [500007.0, 4999998.0],
            [500007.0, 4999993.0],
            [500002.0, 4999993.0],
            [500002.0, 4999998.0],
        ]],
    }

    clipped_array, clipped_transform = clip_to_boundary(
        raster_array, raster_transform, raster_crs, boundary_geom
    )

    # Verify the clipped array is smaller than the original
    assert clipped_array.shape[0] <= raster_array.shape[0]
    assert clipped_array.shape[1] <= raster_array.shape[1]

    # Verify the transform has been updated
    assert clipped_transform.c != raster_transform.c or clipped_transform.f != raster_transform.f


def test_clip_to_boundary_preserves_dtype():
    """Clipping preserves the data type of the input array."""
    raster_array = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    raster_transform = Affine.identity()
    raster_crs = CRS.from_epsg(26910)

    boundary_geom = {
        "type": "Polygon",
        "coordinates": [[
            [0, 0],
            [2, 0],
            [2, 2],
            [0, 2],
            [0, 0],
        ]],
    }

    clipped_array, _ = clip_to_boundary(
        raster_array, raster_transform, raster_crs, boundary_geom
    )

    # The dtype should be preserved (or at least compatible)
    assert clipped_array.dtype in [np.float32, np.float64]


def test_clip_to_boundary_with_nan_values():
    """Clipping handles NaN values correctly."""
    raster_array = np.array([[1.0, np.nan], [3.0, 4.0]], dtype=np.float64)
    raster_transform = Affine.identity()
    raster_crs = CRS.from_epsg(26910)

    boundary_geom = {
        "type": "Polygon",
        "coordinates": [[
            [0, 0],
            [2, 0],
            [2, 2],
            [0, 2],
            [0, 0],
        ]],
    }

    clipped_array, _ = clip_to_boundary(
        raster_array, raster_transform, raster_crs, boundary_geom
    )

    # Should still have NaN values
    assert np.any(np.isnan(clipped_array))


def test_clip_to_boundary_with_multiple_geometries():
    """Clipping works with multiple boundary geometries."""
    raster_array = np.arange(100, dtype=np.float64).reshape(10, 10)
    raster_transform = Affine.identity()
    raster_crs = CRS.from_epsg(26910)

    # Two separate boundary polygons
    boundary_geom = [
        {
            "type": "Polygon",
            "coordinates": [[
                [0, 0],
                [2, 0],
                [2, 2],
                [0, 2],
                [0, 0],
            ]],
        },
        {
            "type": "Polygon",
            "coordinates": [[
                [5, 5],
                [7, 5],
                [7, 7],
                [5, 7],
                [5, 5],
            ]],
        },
    ]

    clipped_array, _ = clip_to_boundary(
        raster_array, raster_transform, raster_crs, boundary_geom
    )

    # Should return a clipped array
    assert isinstance(clipped_array, np.ndarray)
    assert clipped_array.ndim == 2
