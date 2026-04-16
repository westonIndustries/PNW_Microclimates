"""
Wind steering processor.

Merges NREL 10 m wind grid with MesoWest station observations via spatial
interpolation. Computes stagnation multiplier (applied to UHI offset) and
wind infiltration multiplier (applied to HDD) based on wind speed and wind
shadow. Applies Gorge floor for high-wind corridor stations.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy.interpolate import griddata

from src.config import (
    GORGE_STATIONS,
    MESOWEST_WIND_DIR,
    PREVAILING_WIND_DEG,
    STATION_COORDS,
    STATION_HDD_NORMALS,
    TARGET_CRS,
)

logger = logging.getLogger(__name__)


def merge_wind_data(
    nrel_wind_array: np.ndarray,
    nrel_transform: rasterio.transform.Affine,
    mesowest_wind: dict[str, dict],
    dem_shape: tuple[int, int],
) -> np.ndarray:
    """Merge NREL 10 m wind grid with MesoWest station observations.

    Combines the NREL 2 km gridded wind resource (already downscaled to 1 m
    LiDAR resolution) with MesoWest station point observations via spatial
    interpolation. The merged grid represents the best estimate of surface
    wind speed at each 1 m pixel.

    Parameters
    ----------
    nrel_wind_array : np.ndarray
        NREL 10 m wind speed grid (m/s), shape (rows, cols), already downscaled
        to 1 m resolution and clipped to region boundary.
    nrel_transform : rasterio.transform.Affine
        Affine transform of the NREL wind grid (1 m resolution).
    mesowest_wind : dict[str, dict]
        MesoWest wind data keyed by station ID, with keys:
        - ``mean_wind_ms``: annual mean wind speed (m/s)
        - ``p90_wind_ms``: 90th-percentile wind speed (m/s)
    dem_shape : tuple[int, int]
        Shape of the DEM (rows, cols) — the merged wind grid will have this shape.

    Returns
    -------
    np.ndarray
        Merged wind speed grid (m/s), shape (rows, cols), with NREL and
        MesoWest data blended via spatial interpolation.

    Notes
    -----
    - If no MesoWest stations are available, returns the NREL grid unchanged.
    - Station coordinates are looked up from ``STATION_COORDS`` in config.
    - Interpolation uses ``scipy.interpolate.griddata`` with linear method.
    - Pixels with NaN in the NREL grid remain NaN in the output.
    """
    # If no MesoWest data, return NREL grid as-is
    if not mesowest_wind:
        logger.warning("No MesoWest wind data available; using NREL grid unchanged")
        return nrel_wind_array.copy()

    # Extract station coordinates and wind speeds
    station_ids = []
    station_coords_list = []
    station_winds = []

    for station_id, wind_data in mesowest_wind.items():
        if station_id not in STATION_COORDS:
            logger.warning(f"Station {station_id} not in STATION_COORDS; skipping")
            continue

        lat, lon = STATION_COORDS[station_id]
        mean_wind = wind_data.get("mean_wind_ms")

        if mean_wind is None or np.isnan(mean_wind):
            logger.warning(f"Station {station_id} has invalid wind speed; skipping")
            continue

        station_ids.append(station_id)
        station_coords_list.append((lon, lat))
        station_winds.append(mean_wind)

    if not station_coords_list:
        logger.warning("No valid MesoWest stations; using NREL grid unchanged")
        return nrel_wind_array.copy()

    logger.info(f"Merging NREL wind with {len(station_ids)} MesoWest stations")

    # Create a grid of pixel coordinates (in geographic space)
    rows, cols = dem_shape
    row_indices, col_indices = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")

    # Convert pixel coordinates to geographic coordinates using the transform
    x_coords = nrel_transform.c + col_indices * nrel_transform.a
    y_coords = nrel_transform.f + row_indices * nrel_transform.e

    # Stack into (N, 2) array for griddata
    pixel_coords = np.column_stack([x_coords.ravel(), y_coords.ravel()])

    # Interpolate station wind speeds to the full grid
    station_coords_array = np.array(station_coords_list)
    station_winds_array = np.array(station_winds)

    interpolated_winds = griddata(
        station_coords_array,
        station_winds_array,
        pixel_coords,
        method="linear",
        fill_value=np.nan,
    )

    interpolated_winds = interpolated_winds.reshape(rows, cols)

    # Blend NREL and interpolated MesoWest data
    # Use MesoWest where available (not NaN), otherwise use NREL
    merged_wind = nrel_wind_array.copy()
    valid_interp = ~np.isnan(interpolated_winds)
    merged_wind[valid_interp] = interpolated_winds[valid_interp]

    logger.info(f"Merged wind grid: {np.nanmean(merged_wind):.2f} m/s mean")

    return merged_wind


def compute_stagnation_multiplier(
    wind_speed_ms: np.ndarray,
    wind_shadow: np.ndarray,
) -> np.ndarray:
    """Compute wind stagnation multiplier applied to UHI offset.

    The stagnation multiplier modulates the UHI temperature offset based on
    wind speed and wind shadow:
    - Wind speed > 5 m/s and NOT in wind shadow: multiplier = 0.7× (wind disperses UHI)
    - Wind speed 3–5 m/s: multiplier = 1.0× (baseline)
    - Wind speed < 3 m/s and in wind shadow: multiplier = 1.3× (UHI trapped)

    Parameters
    ----------
    wind_speed_ms : np.ndarray
        Wind speed grid (m/s), shape (rows, cols).
    wind_shadow : np.ndarray
        Wind shadow binary mask (1 = in shadow, 0 = not in shadow), shape (rows, cols).

    Returns
    -------
    np.ndarray
        Stagnation multiplier grid, shape (rows, cols), with values 0.7, 1.0, or 1.3.
        NaN where inputs are NaN.

    Notes
    -----
    - Multiplier is applied to the UHI offset: ``uhi_offset_adjusted = uhi_offset × multiplier``
    - Wind shadow is a binary mask from terrain_analysis.compute_wind_shadow()
    """
    multiplier = np.full_like(wind_speed_ms, 1.0, dtype=np.float64)

    # High wind, not in shadow: 0.7× (wind disperses UHI)
    high_wind_exposed = (wind_speed_ms > 5.0) & (wind_shadow == 0)
    multiplier[high_wind_exposed] = 0.7

    # Low wind, in shadow: 1.3× (UHI trapped)
    low_wind_sheltered = (wind_speed_ms < 3.0) & (wind_shadow == 1)
    multiplier[low_wind_sheltered] = 1.3

    # Set to NaN where inputs are NaN
    multiplier[np.isnan(wind_speed_ms) | np.isnan(wind_shadow)] = np.nan

    return multiplier


def compute_wind_infiltration_multiplier(
    wind_speed_ms: np.ndarray,
    base_station: str,
) -> np.ndarray:
    """Compute wind infiltration multiplier applied to HDD.

    Adds 1.5% to effective HDD for each 1 m/s above 3 m/s (sheltered suburban
    baseline). Formula: ``wind_infiltration_mult = 1.0 + 0.015 × max(0, wind_speed_ms - 3)``

    Columbia River Gorge ZIP codes (served by stations KDLS and KTTD) receive
    a floor of 1.15, reflecting the high-wind corridor effect.

    Parameters
    ----------
    wind_speed_ms : np.ndarray
        Wind speed grid (m/s), shape (rows, cols).
    base_station : str
        ICAO code of the base weather station for this region (e.g., "KPDX").
        Used to determine if Gorge floor applies.

    Returns
    -------
    np.ndarray
        Wind infiltration multiplier grid, shape (rows, cols), with values ≥ 1.0.
        NaN where wind_speed_ms is NaN.

    Notes
    -----
    - Multiplier is applied to HDD: ``effective_hdd_adjusted = effective_hdd × multiplier``
    - Gorge floor (1.15) applies only to ZIP codes served by KDLS or KTTD stations.
    """
    # Base formula: 1.0 + 0.015 × max(0, wind_speed_ms - 3)
    excess_wind = np.maximum(0.0, wind_speed_ms - 3.0)
    multiplier = 1.0 + 0.015 * excess_wind

    # Apply Gorge floor if this is a Gorge station
    if base_station in GORGE_STATIONS:
        multiplier = np.maximum(multiplier, 1.15)
        logger.info(f"Applying Gorge floor (1.15) for station {base_station}")

    # Set to NaN where wind_speed_ms is NaN
    multiplier[np.isnan(wind_speed_ms)] = np.nan

    return multiplier


def compute_wind_steering(
    nrel_wind_array: np.ndarray,
    nrel_transform: rasterio.transform.Affine,
    mesowest_wind: dict[str, dict],
    wind_shadow: np.ndarray,
    dem_shape: tuple[int, int],
    base_station: str,
) -> dict[str, np.ndarray]:
    """Compute wind steering corrections: stagnation and infiltration multipliers.

    Merges NREL and MesoWest wind data, computes stagnation multiplier (applied
    to UHI offset) and wind infiltration multiplier (applied to HDD), and applies
    Gorge floor for high-wind corridor stations.

    Parameters
    ----------
    nrel_wind_array : np.ndarray
        NREL 10 m wind speed grid (m/s), already downscaled to 1 m resolution.
    nrel_transform : rasterio.transform.Affine
        Affine transform of the NREL wind grid.
    mesowest_wind : dict[str, dict]
        MesoWest wind data keyed by station ID.
    wind_shadow : np.ndarray
        Wind shadow binary mask from terrain_analysis.
    dem_shape : tuple[int, int]
        Shape of the DEM (rows, cols).
    base_station : str
        ICAO code of the base weather station (e.g., "KPDX").

    Returns
    -------
    dict[str, np.ndarray]
        Dictionary with keys:
        - ``mean_wind_ms``: Mean annual surface wind speed (m/s)
        - ``wind_infiltration_mult``: HDD multiplier from wind-driven infiltration
        - ``stagnation_multiplier``: Applied to UHI offset (0.7, 1.0, or 1.3)

    Notes
    -----
    - All output arrays have shape (rows, cols) matching the DEM.
    - NaN values are preserved from input arrays.
    """
    # Merge NREL and MesoWest wind data
    merged_wind = merge_wind_data(
        nrel_wind_array,
        nrel_transform,
        mesowest_wind,
        dem_shape,
    )

    # Compute stagnation multiplier
    stagnation_mult = compute_stagnation_multiplier(merged_wind, wind_shadow)

    # Compute wind infiltration multiplier
    infiltration_mult = compute_wind_infiltration_multiplier(merged_wind, base_station)

    logger.info(
        f"Wind steering: mean={np.nanmean(merged_wind):.2f} m/s, "
        f"stagnation_mult={np.nanmean(stagnation_mult):.3f}, "
        f"infiltration_mult={np.nanmean(infiltration_mult):.3f}"
    )

    return {
        "mean_wind_ms": merged_wind,
        "wind_infiltration_mult": infiltration_mult,
        "stagnation_multiplier": stagnation_mult,
    }
