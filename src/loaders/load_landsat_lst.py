"""
Landsat 9 LST loader.

Loads a Landsat 9 Collection 2 Level-2 LST GeoTIFF, applies the Collection 2
scale factor (0.00341802) and offset (149.0) to convert to Kelvin, then
subtracts 273.15 to produce a Celsius array.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio

from src.config import LANDSAT_LST_RASTER

logger = logging.getLogger(__name__)

# Landsat 9 Collection 2 Level-2 LST scale factor and offset
LST_SCALE_FACTOR = 0.00341802
LST_OFFSET = 149.0

# Kelvin to Celsius conversion
KELVIN_TO_CELSIUS = 273.15


def load_landsat_lst() -> tuple[np.ndarray, rasterio.transform.Affine, rasterio.crs.CRS] | None:
    """Load Landsat 9 Collection 2 Level-2 LST and convert to Celsius.

    Reads the LST GeoTIFF at the path specified by LANDSAT_LST_RASTER,
    applies the Collection 2 scale factor (0.00341802) and offset (149.0)
    to convert from digital numbers to Kelvin, then subtracts 273.15 to
    produce a Celsius array.

    Returns
    -------
    tuple[np.ndarray, rasterio.transform.Affine, rasterio.crs.CRS] | None
        (lst_celsius_array, transform, crs) where lst_celsius_array is float64
        with land surface temperature values in degrees Celsius. Returns None
        if the file is not available.

    Notes
    -----
    If the file is not available, a warning is logged and None is returned.
    The caller should handle the None case and proceed without Landsat
    calibration.
    """
    path = LANDSAT_LST_RASTER.resolve()

    if not path.exists():
        logger.warning(
            f"Landsat 9 LST file not found at {path}. "
            "Proceeding without Landsat calibration."
        )
        return None

    with rasterio.open(path) as dataset:
        # Read the LST band as float64
        lst_dn = dataset.read(1).astype(np.float64)
        transform = dataset.transform
        crs = dataset.crs

    # Apply Collection 2 scale factor and offset to convert to Kelvin
    lst_kelvin = lst_dn * LST_SCALE_FACTOR + LST_OFFSET

    # Convert from Kelvin to Celsius
    lst_celsius = lst_kelvin - KELVIN_TO_CELSIUS

    return lst_celsius, transform, crs
