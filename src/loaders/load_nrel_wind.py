"""
NREL wind resource loader.

Loads the NREL wind resource GeoTIFF at 80 m hub height, applies power-law
scaling to 10 m surface wind, and returns the scaled wind array along with
its spatial metadata.
"""

from __future__ import annotations

import numpy as np
import rasterio

from src.config import NREL_WIND_RASTER


def load_nrel_wind() -> tuple[np.ndarray, rasterio.transform.Affine, rasterio.crs.CRS]:
    """Load the NREL wind resource raster and scale to 10 m surface wind.

    The NREL raster contains wind speed at 80 m hub height. This function
    applies a power-law scaling to convert to 10 m surface wind:

    .. math::
        wind_{10m} = wind_{80m} \\times (10/80)^{0.143}

    The returned array is **float64** with nodata pixels set to ``numpy.nan``.

    Returns
    -------
    tuple[np.ndarray, rasterio.transform.Affine, rasterio.crs.CRS]
        A tuple of:
        - **array**: Wind speed at 10 m (m/s), float64, with nodata as nan
        - **transform**: Affine transform of the raster
        - **crs**: Coordinate reference system

    Raises
    ------
    FileNotFoundError
        If the GeoTIFF does not exist at the configured path.
    """
    path = NREL_WIND_RASTER.resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"NREL wind resource file not found: {path}"
        )

    with rasterio.open(path) as dataset:
        array = dataset.read(1).astype(np.float64)
        nodata = dataset.nodata
        transform = dataset.transform
        crs = dataset.crs

    if nodata is not None:
        array[array == nodata] = np.nan

    # Apply power-law scaling from 80 m to 10 m
    # wind_10m = wind_80m × (10/80)^0.143
    scaling_factor = (10.0 / 80.0) ** 0.143
    array = array * scaling_factor

    return array, transform, crs
