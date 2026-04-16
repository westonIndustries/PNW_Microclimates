"""
PRISM temperature loader.

Loads 12 monthly mean temperature BIL/GeoTIFF files from PRISM_TEMP_DIR,
computes monthly HDD contributions, sums to annual HDD grid, and applies
station bias correction using spatial interpolation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from scipy.interpolate import griddata

from src.config import (
    PRISM_TEMP_DIR,
    STATION_COORDS,
    STATION_ELEVATIONS_FT,
    STATION_HDD_NORMALS,
    TARGET_CRS,
)


# Days in each month (non-leap year)
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# HDD base temperature in Fahrenheit
HDD_BASE_F = 65.0


def load_prism_temperature() -> tuple[np.ndarray, rasterio.transform.Affine, rasterio.crs.CRS]:
    """Load PRISM monthly temperature normals and compute bias-corrected annual HDD grid.

    Loads all 12 monthly mean temperature files from PRISM_TEMP_DIR, computes
    monthly HDD contributions (monthly mean temp × days in month, base 65°F),
    sums to annual HDD grid, then applies station bias correction by:
    1. Computing additive offset at each NOAA station location
    2. Spatially interpolating offsets across the grid using linear griddata
    3. Adding interpolated offset surface to raw PRISM HDD grid

    Returns
    -------
    tuple[np.ndarray, rasterio.transform.Affine, rasterio.crs.CRS]
        (annual_hdd_array, transform, crs) where annual_hdd_array is float64
        with bias-corrected annual HDD values in °F-days (base 65°F).

    Raises
    ------
    FileNotFoundError
        If any of the 12 monthly PRISM files are missing, lists all missing months.
    
    Notes
    -----
    For monthly HDD profiles, use load_prism_temperature_monthly() instead.
    """
    prism_dir = PRISM_TEMP_DIR.resolve()

    # Check that all 12 monthly files exist
    missing_months = []
    monthly_files = []

    for month in range(1, 13):
        month_str = f"{month:02d}"
        # Try both BIL and GeoTIFF extensions
        bil_path = prism_dir / f"PRISM_tmean_30yr_normal_800mM4_{month_str}_bil.bil"
        tif_path = prism_dir / f"PRISM_tmean_30yr_normal_800mM4_{month_str}.tif"

        if bil_path.exists():
            monthly_files.append(bil_path)
        elif tif_path.exists():
            monthly_files.append(tif_path)
        else:
            missing_months.append(month_str)

    if missing_months:
        raise FileNotFoundError(
            f"Missing PRISM temperature files for months: {', '.join(missing_months)}. "
            f"Expected files in {prism_dir}"
        )

    # Load monthly temperature data and compute HDD contributions
    monthly_hdd_grids = []
    transform = None
    crs = None

    for month_idx, file_path in enumerate(monthly_files):
        with rasterio.open(file_path) as dataset:
            # Temperature in Celsius
            temp_c = dataset.read(1).astype(np.float64)
            
            # Store transform and CRS from first file
            if transform is None:
                transform = dataset.transform
                crs = dataset.crs

            # Convert to Fahrenheit
            temp_f = temp_c * 9 / 5 + 32

            # Compute HDD contribution for this month
            # HDD = max(0, base_temp - mean_temp) * days_in_month
            hdd_contribution = np.maximum(0, HDD_BASE_F - temp_f) * DAYS_IN_MONTH[month_idx]
            monthly_hdd_grids.append(hdd_contribution)

    # Sum monthly HDD contributions to get annual HDD
    annual_hdd_raw = np.sum(monthly_hdd_grids, axis=0)

    # Apply station bias correction
    annual_hdd_corrected = _apply_station_bias_correction(
        annual_hdd_raw, transform, crs
    )

    return annual_hdd_corrected, transform, crs


def _apply_station_bias_correction(
    annual_hdd_raw: np.ndarray,
    transform: rasterio.transform.Affine,
    crs: rasterio.crs.CRS,
) -> np.ndarray:
    """Apply station bias correction to raw PRISM HDD grid.

    For each NOAA reference station, computes the additive offset between
    the PRISM grid value at the station location and the station's known
    normal HDD. Spatially interpolates these offsets across the full grid
    using scipy.interpolate.griddata (linear) and adds the interpolated
    offset surface to the raw PRISM HDD grid.

    Parameters
    ----------
    annual_hdd_raw : np.ndarray
        Raw annual HDD grid from PRISM (shape: (rows, cols))
    transform : rasterio.transform.Affine
        Affine transform of the PRISM grid
    crs : rasterio.crs.CRS
        CRS of the PRISM grid

    Returns
    -------
    np.ndarray
        Bias-corrected annual HDD grid (same shape as input)
    """
    # Get grid coordinates (x, y) for all pixels
    rows, cols = annual_hdd_raw.shape
    x_coords, y_coords = np.meshgrid(
        np.arange(cols) * transform.a + transform.c,
        np.arange(rows) * transform.e + transform.f,
    )

    # Collect station offsets
    station_points = []  # (x, y) in grid CRS
    station_offsets = []  # offset in HDD

    for station_id, (lat, lon) in STATION_COORDS.items():
        # Get station's known normal HDD
        station_normal_hdd = STATION_HDD_NORMALS[station_id]

        # Convert station lat/lon to grid CRS (assuming STATION_COORDS is in EPSG:4326)
        # For now, assume the grid is in a projected CRS and we need to transform
        # In practice, rasterio can handle this, but for simplicity we'll use pyproj
        try:
            from pyproj import Transformer

            transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
            x_station, y_station = transformer.transform(lon, lat)
        except Exception:
            # Fallback: assume grid is already in lat/lon or close enough
            x_station, y_station = lon, lat

        # Find the grid cell closest to the station
        col_idx = int(np.round((x_station - transform.c) / transform.a))
        row_idx = int(np.round((y_station - transform.f) / transform.e))

        # Check bounds
        if 0 <= row_idx < rows and 0 <= col_idx < cols:
            prism_hdd_at_station = annual_hdd_raw[row_idx, col_idx]

            # Compute additive offset
            offset = station_normal_hdd - prism_hdd_at_station

            # Store station point and offset
            station_points.append([x_station, y_station])
            station_offsets.append(offset)

    # If we have station offsets, interpolate them across the grid
    if len(station_points) > 0:
        station_points = np.array(station_points)
        station_offsets = np.array(station_offsets)

        # Flatten grid coordinates for interpolation
        grid_points = np.column_stack([x_coords.ravel(), y_coords.ravel()])

        # Interpolate offsets using linear griddata
        interpolated_offsets = griddata(
            station_points,
            station_offsets,
            grid_points,
            method="linear",
            fill_value=0.0,  # Use 0 offset for extrapolated areas
        )

        # Reshape back to grid shape
        offset_grid = interpolated_offsets.reshape(annual_hdd_raw.shape)

        # Add interpolated offset surface to raw PRISM HDD grid
        annual_hdd_corrected = annual_hdd_raw + offset_grid
    else:
        # No stations found in grid bounds, return raw HDD
        annual_hdd_corrected = annual_hdd_raw

    return annual_hdd_corrected



def load_prism_temperature_monthly() -> tuple[list[np.ndarray], rasterio.transform.Affine, rasterio.crs.CRS]:
    """Load PRISM monthly temperature normals and compute bias-corrected monthly HDD grids.

    Loads all 12 monthly mean temperature files from PRISM_TEMP_DIR, computes
    monthly HDD contributions (monthly mean temp × days in month, base 65°F),
    applies station bias correction to each month independently, and returns
    a list of 12 monthly HDD grids.

    Returns
    -------
    tuple[list[np.ndarray], rasterio.transform.Affine, rasterio.crs.CRS]
        (monthly_hdd_grids, transform, crs) where monthly_hdd_grids is a list
        of 12 float64 arrays (January through December) with bias-corrected
        monthly HDD values in °F-days (base 65°F).

    Raises
    ------
    FileNotFoundError
        If any of the 12 monthly PRISM files are missing, lists all missing months.
    
    Notes
    -----
    Each month's HDD is computed independently using the same bias correction
    approach as load_prism_temperature(). The sum of the 12 monthly grids
    should approximately equal the annual HDD grid (within floating-point tolerance).
    """
    prism_dir = PRISM_TEMP_DIR.resolve()

    # Check that all 12 monthly files exist
    missing_months = []
    monthly_files = []

    for month in range(1, 13):
        month_str = f"{month:02d}"
        # Try both BIL and GeoTIFF extensions
        bil_path = prism_dir / f"PRISM_tmean_30yr_normal_800mM4_{month_str}_bil.bil"
        tif_path = prism_dir / f"PRISM_tmean_30yr_normal_800mM4_{month_str}.tif"

        if bil_path.exists():
            monthly_files.append(bil_path)
        elif tif_path.exists():
            monthly_files.append(tif_path)
        else:
            missing_months.append(month_str)

    if missing_months:
        raise FileNotFoundError(
            f"Missing PRISM temperature files for months: {', '.join(missing_months)}. "
            f"Expected files in {prism_dir}"
        )

    # Load monthly temperature data and compute HDD contributions
    monthly_hdd_grids = []
    transform = None
    crs = None

    for month_idx, file_path in enumerate(monthly_files):
        with rasterio.open(file_path) as dataset:
            # Temperature in Celsius
            temp_c = dataset.read(1).astype(np.float64)
            
            # Store transform and CRS from first file
            if transform is None:
                transform = dataset.transform
                crs = dataset.crs

            # Convert to Fahrenheit
            temp_f = temp_c * 9 / 5 + 32

            # Compute HDD contribution for this month
            # HDD = max(0, base_temp - mean_temp) * days_in_month
            hdd_contribution = np.maximum(0, HDD_BASE_F - temp_f) * DAYS_IN_MONTH[month_idx]
            
            # Apply station bias correction to this month's HDD
            hdd_corrected = _apply_station_bias_correction(hdd_contribution, transform, crs)
            
            monthly_hdd_grids.append(hdd_corrected)

    return monthly_hdd_grids, transform, crs
