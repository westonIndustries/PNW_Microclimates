"""
Combine corrections at the microclimate cell level.

For each microclimate cell, computes cell_effective_hdd by averaging all
1-meter grid cells within that cell and applying the effective HDD formula:

    cell_effective_hdd = base_hdd × terrain_multiplier
                       + elevation_hdd_addition
                       − uhi_hdd_reduction
                       − traffic_heat_hdd_reduction

where each component is the mean value for all 1m pixels within the cell.

Returns a DataFrame with one row per cell per ZIP code, including all
intermediate correction columns and cell metadata.
"""

from __future__ import annotations

import logging
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.features import geometry_mask
from rasterio.transform import Affine

from src import config

logger = logging.getLogger(__name__)


def compute_effective_hdd_per_cell(
    cells_gdf: gpd.GeoDataFrame,
    base_hdd_array: np.ndarray,
    terrain_mult_array: np.ndarray,
    elev_addition_array: np.ndarray,
    uhi_offset_array: np.ndarray,
    traffic_heat_offset_array: np.ndarray,
    wind_infiltration_mult_array: np.ndarray,
    mean_wind_array: np.ndarray,
    mean_elevation_array: np.ndarray,
    mean_impervious_array: np.ndarray,
    surface_albedo_array: np.ndarray,
    lidar_transform: Affine,
    lidar_shape: tuple[int, int],
    zip_code: str,
    base_station: str,
    region_code: str,
) -> pd.DataFrame:
    """Compute effective HDD for each microclimate cell.

    For each cell in the GeoDataFrame, extracts the mean value of all correction
    arrays within the cell geometry, applies the effective HDD formula, and
    returns a DataFrame with one row per cell.

    Parameters
    ----------
    cells_gdf : gpd.GeoDataFrame
        GeoDataFrame with cell geometries. Must have columns:
        - geometry: cell polygon
        - cell_id: unique cell identifier (e.g., 'cell_001')
        - cell_area_sqm: area of the cell in square meters
        - cell_type: optional, dominant characteristic (e.g., 'urban', 'rural')
    base_hdd_array : np.ndarray
        Base annual HDD grid (PRISM bias-corrected), 2D array.
    terrain_mult_array : np.ndarray
        Terrain position multiplier (windward/leeward/valley/ridge), 2D array.
    elev_addition_array : np.ndarray
        Elevation HDD addition (lapse rate), 2D array.
    uhi_offset_array : np.ndarray
        UHI temperature offset in °F, 2D array.
    traffic_heat_offset_array : np.ndarray
        Traffic heat temperature offset in °F, 2D array.
    wind_infiltration_mult_array : np.ndarray
        Wind infiltration multiplier, 2D array.
    mean_wind_array : np.ndarray
        Mean wind speed in m/s, 2D array.
    mean_elevation_array : np.ndarray
        Mean elevation in feet, 2D array.
    mean_impervious_array : np.ndarray
        Mean NLCD imperviousness percentage (0–100), 2D array.
    surface_albedo_array : np.ndarray
        Surface albedo (0.05–0.20), 2D array.
    lidar_transform : Affine
        Affine transform of the raster grids.
    lidar_shape : tuple[int, int]
        Shape (rows, cols) of the raster grids.
    zip_code : str
        ZIP code for this set of cells.
    base_station : str
        NOAA station code (e.g., 'KPDX').
    region_code : str
        Region code (e.g., 'R1').

    Returns
    -------
    pd.DataFrame
        DataFrame with one row per cell, containing:
        - microclimate_id: unique identifier
        - zip_code: ZIP code
        - cell_id: cell identifier
        - cell_type: dominant characteristic (if available)
        - cell_area_sqm: cell area
        - base_hdd: mean base HDD within cell
        - terrain_multiplier: mean terrain multiplier within cell
        - elevation_hdd_addition: mean elevation addition within cell
        - uhi_offset_f: mean UHI offset within cell
        - uhi_hdd_reduction: UHI HDD reduction (uhi_offset_f × 180)
        - traffic_heat_offset_f: mean traffic heat offset within cell
        - traffic_heat_hdd_reduction: traffic HDD reduction (offset × 180)
        - wind_infiltration_mult: mean wind infiltration multiplier within cell
        - mean_wind_ms: mean wind speed within cell
        - mean_elevation_ft: mean elevation within cell
        - mean_impervious_pct: mean imperviousness within cell
        - surface_albedo: mean surface albedo within cell
        - cell_effective_hdd: final effective HDD for the cell
        - num_valid_pixels: count of valid 1m pixels within cell
        - run_date: ISO 8601 timestamp (set by caller)
        - pipeline_version: pipeline version (from config)
        - lidar_vintage: LiDAR vintage (set by caller)
        - nlcd_vintage: NLCD vintage (from config)
        - prism_period: PRISM period (from config)

    Notes
    -----
    - Cells with fewer than MIN_CELL_PIXELS valid pixels are flagged in QA.
    - NaN values in raster arrays are excluded from the mean computation.
    - The effective HDD formula is:
        cell_effective_hdd = base_hdd × terrain_mult
                           + elev_addition
                           − uhi_hdd_reduction
                           − traffic_heat_hdd_reduction
    - UHI HDD reduction is computed as: uhi_offset_f × 180 (HDD per °F)
    - Traffic HDD reduction is computed as: traffic_heat_offset_f × 180
    """
    rows = []

    for idx, cell_row in cells_gdf.iterrows():
        cell_geom = cell_row.geometry
        cell_id = cell_row["cell_id"]
        cell_area_sqm = cell_row["cell_area_sqm"]
        cell_type = cell_row.get("cell_type", None)

        # Create a mask for pixels within this cell
        # geometry_mask returns True for pixels OUTSIDE the geometry, so invert it
        mask = ~geometry_mask(
            [cell_geom],
            out_shape=lidar_shape,
            transform=lidar_transform,
            invert=False,
        )

        # Extract values within the cell for each array
        base_hdd_cell = base_hdd_array[mask]
        terrain_mult_cell = terrain_mult_array[mask]
        elev_addition_cell = elev_addition_array[mask]
        uhi_offset_cell = uhi_offset_array[mask]
        traffic_heat_offset_cell = traffic_heat_offset_array[mask]
        wind_infiltration_mult_cell = wind_infiltration_mult_array[mask]
        mean_wind_cell = mean_wind_array[mask]
        mean_elevation_cell = mean_elevation_array[mask]
        mean_impervious_cell = mean_impervious_array[mask]
        surface_albedo_cell = surface_albedo_array[mask]

        # Count valid pixels (non-NaN)
        valid_mask = ~np.isnan(base_hdd_cell)
        num_valid_pixels = np.sum(valid_mask)

        # Compute means, excluding NaN values
        mean_base_hdd = np.nanmean(base_hdd_cell) if num_valid_pixels > 0 else np.nan
        mean_terrain_mult = np.nanmean(terrain_mult_cell) if num_valid_pixels > 0 else np.nan
        mean_elev_addition = np.nanmean(elev_addition_cell) if num_valid_pixels > 0 else np.nan
        mean_uhi_offset = np.nanmean(uhi_offset_cell) if num_valid_pixels > 0 else np.nan
        mean_traffic_heat_offset = np.nanmean(traffic_heat_offset_cell) if num_valid_pixels > 0 else np.nan
        mean_wind_infiltration_mult = np.nanmean(wind_infiltration_mult_cell) if num_valid_pixels > 0 else np.nan
        mean_wind = np.nanmean(mean_wind_cell) if num_valid_pixels > 0 else np.nan
        mean_elevation = np.nanmean(mean_elevation_cell) if num_valid_pixels > 0 else np.nan
        mean_impervious = np.nanmean(mean_impervious_cell) if num_valid_pixels > 0 else np.nan
        mean_albedo = np.nanmean(surface_albedo_cell) if num_valid_pixels > 0 else np.nan

        # Compute HDD reductions
        # UHI HDD reduction: uhi_offset_f × 180 (HDD per °F)
        uhi_hdd_reduction = mean_uhi_offset * config.HDD_PER_DEGREE_F if not np.isnan(mean_uhi_offset) else 0.0

        # Traffic HDD reduction: traffic_heat_offset_f × 180
        traffic_hdd_reduction = mean_traffic_heat_offset * config.HDD_PER_DEGREE_F if not np.isnan(mean_traffic_heat_offset) else 0.0

        # Compute effective HDD using the formula:
        # cell_effective_hdd = base_hdd × terrain_mult
        #                    + elev_addition
        #                    − uhi_hdd_reduction
        #                    − traffic_heat_hdd_reduction
        if not np.isnan(mean_base_hdd) and not np.isnan(mean_terrain_mult):
            cell_effective_hdd = (
                mean_base_hdd * mean_terrain_mult
                + mean_elev_addition
                - uhi_hdd_reduction
                - traffic_hdd_reduction
            )
        else:
            cell_effective_hdd = np.nan

        # Create microclimate_id
        microclimate_id = f"{region_code}_{zip_code}_{base_station}_cell_{cell_id}"

        # Build row
        row = {
            "microclimate_id": microclimate_id,
            "zip_code": zip_code,
            "cell_id": cell_id,
            "cell_type": cell_type,
            "cell_area_sqm": cell_area_sqm,
            "base_hdd": mean_base_hdd,
            "terrain_multiplier": mean_terrain_mult,
            "elevation_hdd_addition": mean_elev_addition,
            "uhi_offset_f": mean_uhi_offset,
            "uhi_hdd_reduction": uhi_hdd_reduction,
            "traffic_heat_offset_f": mean_traffic_heat_offset,
            "traffic_heat_hdd_reduction": traffic_hdd_reduction,
            "wind_infiltration_mult": mean_wind_infiltration_mult,
            "mean_wind_ms": mean_wind,
            "mean_elevation_ft": mean_elevation,
            "mean_impervious_pct": mean_impervious,
            "surface_albedo": mean_albedo,
            "cell_effective_hdd": cell_effective_hdd,
            "num_valid_pixels": int(num_valid_pixels),
        }

        rows.append(row)

    # Create DataFrame
    df = pd.DataFrame(rows)

    logger.info(
        f"Computed effective HDD for {len(df)} cells in ZIP {zip_code}. "
        f"Mean effective HDD: {df['cell_effective_hdd'].mean():.1f} HDD"
    )

    return df
