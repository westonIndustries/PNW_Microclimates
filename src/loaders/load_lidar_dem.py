"""
LiDAR DEM loader.

Opens the GeoTIFF at ``LIDAR_DEM_RASTER``, replaces nodata pixels with
``numpy.nan``, and returns the elevation array along with its spatial
metadata.
"""

from __future__ import annotations

import numpy as np
import rasterio

from src.config import LIDAR_DEM_RASTER


def load_lidar_dem() -> tuple[np.ndarray, rasterio.transform.Affine, rasterio.crs.CRS]:
    """Load the LiDAR DEM raster and return ``(array, transform, crs)``.

    The returned array is **float64** with nodata pixels set to ``numpy.nan``.

    Raises
    ------
    FileNotFoundError
        If the GeoTIFF does not exist at the configured path.
    """
    path = LIDAR_DEM_RASTER.resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"LiDAR DEM file not found: {path}"
        )

    with rasterio.open(path) as dataset:
        array = dataset.read(1).astype(np.float64)
        nodata = dataset.nodata
        transform = dataset.transform
        crs = dataset.crs

    if nodata is not None:
        array[array == nodata] = np.nan

    return array, transform, crs
