"""
NLCD imperviousness loader.

Loads the NLCD imperviousness GeoTIFF, replaces sentinel values (127, 255)
with numpy.nan, clips valid values to 0–100, and returns the processed array
along with its spatial metadata.
"""

from __future__ import annotations

import numpy as np
import rasterio

from src.config import NLCD_IMPERVIOUS_RASTER


# Sentinel values that indicate nodata or invalid imperviousness
SENTINEL_VALUES = {127, 255}

# Valid range for imperviousness percentage
MIN_VALID_IMPERVIOUS = 0
MAX_VALID_IMPERVIOUS = 100


def load_nlcd_impervious() -> tuple[np.ndarray, rasterio.transform.Affine, rasterio.crs.CRS]:
    """Load the NLCD imperviousness raster and process sentinel values.

    Loads the NLCD imperviousness GeoTIFF at the path specified by
    NLCD_IMPERVIOUS_RASTER in config.py. Replaces sentinel values (127, 255)
    with numpy.nan, clips valid values to the range 0–100, and returns the
    processed array as float64 along with its spatial metadata.

    The NLCD imperviousness dataset represents the percentage of developed
    impervious surface (asphalt, concrete, rooftops) at 30 m resolution.
    Valid values range from 0 (no impervious surface) to 100 (fully impervious).
    Sentinel values 127 and 255 indicate nodata or areas outside the study region.

    Returns
    -------
    tuple[np.ndarray, rasterio.transform.Affine, rasterio.crs.CRS]
        A tuple of:
        - **array**: Imperviousness percentage (0–100), float64, with sentinel
          values replaced by nan
        - **transform**: Affine transform of the raster
        - **crs**: Coordinate reference system

    Raises
    ------
    FileNotFoundError
        If the GeoTIFF does not exist at the configured path.
    """
    path = NLCD_IMPERVIOUS_RASTER.resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"NLCD imperviousness file not found: {path}"
        )

    with rasterio.open(path) as dataset:
        array = dataset.read(1).astype(np.float64)
        transform = dataset.transform
        crs = dataset.crs

    # Replace sentinel values with nan first
    for sentinel in SENTINEL_VALUES:
        array[array == sentinel] = np.nan

    # Clip valid values to 0–100 range
    # Values outside this range (but not nan) are clipped to the valid range
    # Use np.where to preserve nan values
    valid_mask = ~np.isnan(array)
    array[valid_mask] = np.clip(array[valid_mask], MIN_VALID_IMPERVIOUS, MAX_VALID_IMPERVIOUS)

    return array, transform, crs
