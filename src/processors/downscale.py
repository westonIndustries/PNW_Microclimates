"""
Raster downscaling processor.

Reprojects and resamples coarse-resolution rasters (PRISM 800m, NLCD 30m,
NREL wind 2km, Landsat LST 30m) to match the LiDAR DEM's 1m grid using
bilinear interpolation. All rasters are snapped to the LiDAR DEM's CRS,
pixel size, and origin.
"""

from __future__ import annotations

import logging

import numpy as np
import rasterio.warp
from rasterio.crs import CRS
from rasterio.transform import Affine
from rasterio.warp import Resampling

logger = logging.getLogger(__name__)


def reproject_to_lidar_grid(
    src_array: np.ndarray,
    src_transform: Affine,
    src_crs: CRS,
    lidar_transform: Affine,
    lidar_crs: CRS,
    lidar_shape: tuple[int, int],
) -> np.ndarray:
    """Reproject and resample a source raster to match the LiDAR DEM grid.

    Uses bilinear interpolation to resample all continuous-value rasters
    (temperature, imperviousness, wind speed, LST) to the LiDAR DEM's
    1 m resolution, CRS, and spatial extent.

    Parameters
    ----------
    src_array : np.ndarray
        The source raster array (2D).
    src_transform : Affine
        The affine transform of the source raster.
    src_crs : CRS
        The CRS of the source raster.
    lidar_transform : Affine
        The affine transform of the target LiDAR DEM grid.
    lidar_crs : CRS
        The CRS of the target LiDAR DEM grid.
    lidar_shape : tuple[int, int]
        The shape (rows, cols) of the target LiDAR DEM grid.

    Returns
    -------
    np.ndarray
        The reprojected and resampled array with the same shape as the
        LiDAR DEM. Pixels outside the source raster extent are set to NaN.

    Notes
    -----
    - Bilinear interpolation is used for all downscaling operations.
    - The LiDAR DEM is the reference grid; all other rasters are snapped to it.
    - NaN values in the source array are preserved in the output.
    """
    # Create the destination array with the same shape as the LiDAR DEM
    dst_array = np.full(lidar_shape, np.nan, dtype=np.float64)

    # Use rasterio.warp.reproject to resample the source to the destination grid
    rasterio.warp.reproject(
        src_array.astype(np.float64),
        dst_array,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=lidar_transform,
        dst_crs=lidar_crs,
        resampling=Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )

    logger.debug(
        f"Reprojected raster from {src_array.shape} to {dst_array.shape} "
        f"(CRS: {src_crs} → {lidar_crs}, resampling: bilinear)"
    )

    return dst_array
