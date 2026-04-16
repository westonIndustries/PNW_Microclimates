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

Includes uncertainty quantification to compute lower and upper bounds on effective HDD
values, quantifying the uncertainty in the final microclimate estimates.
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
from src.processors.uncertainty_quantification import compute_effective_hdd_bounds

logger = logging.getLogger(__name__)


def compute_effective_hdd_per_cell(
    cells_gdf: gpd.GeoDataFrame,
    base_hdd_array: np.ndarray,
    base_cdd_array: Optional[np.ndarray] = None,
    terrain_mult_array: np.ndarray = None,
    elev_addition_array: np.ndarray = None,
    uhi_offset_array: np.ndarray = None,
    traffic_heat_offset_array: np.ndarray = None,
    wind_infiltration_mult_array: np.ndarray = None,
    mean_wind_array: np.ndarray = None,
    mean_elevation_array: np.ndarray = None,
    mean_impervious_array: np.ndarray = None,
    surface_albedo_array: np.ndarray = None,
    lidar_transform: Affine = None,
    lidar_shape: tuple[int, int] = None,
    zip_code: str = None,
    base_station: str = None,
    region_code: str = None,
    cold_air_drainage_mult_array: Optional[np.ndarray] = None,
    flow_accumulation_array: Optional[np.ndarray] = None,
    drainage_intensity_array: Optional[np.ndarray] = None,
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
    cold_air_drainage_mult_array : np.ndarray, optional
        Cold air drainage multiplier (1.0–1.15), 2D array. If provided,
        applied to effective HDD after terrain corrections.
    flow_accumulation_array : np.ndarray, optional
        Flow accumulation (raw count of upslope cells), 2D array. If provided,
        included in output columns.
    drainage_intensity_array : np.ndarray, optional
        Drainage intensity (normalized 0–1), 2D array. If provided,
        included in output columns.

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
        - cold_air_drainage_mult: mean cold air drainage multiplier within cell (if provided)
        - flow_accumulation: mean flow accumulation within cell (if provided)
        - drainage_intensity: mean drainage intensity within cell (if provided)
        - mean_wind_ms: mean wind speed within cell
        - mean_elevation_ft: mean elevation within cell
        - mean_impervious_pct: mean imperviousness within cell
        - surface_albedo: mean surface albedo within cell
        - cell_effective_hdd: final effective HDD for the cell
        - cell_effective_hdd_low: lower bound on effective HDD (±1σ uncertainty)
        - cell_effective_hdd_high: upper bound on effective HDD (±1σ uncertainty)
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
        cell_effective_hdd = base_hdd × terrain_mult × cold_air_drainage_mult
                           + elev_addition
                           − uhi_hdd_reduction
                           − traffic_heat_hdd_reduction
    - Cold air drainage multiplier (if provided) is applied AFTER terrain position
      corrections but BEFORE final effective_hdd computation.
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

        # Extract cold air drainage multiplier if provided
        mean_cold_air_drainage_mult = 1.0  # Default: no cold air drainage correction
        mean_flow_accum = np.nan
        mean_drainage_int = np.nan

        if cold_air_drainage_mult_array is not None:
            cold_air_drainage_mult_cell = cold_air_drainage_mult_array[mask]
            mean_cold_air_drainage_mult = np.nanmean(cold_air_drainage_mult_cell) if num_valid_pixels > 0 else 1.0

        if flow_accumulation_array is not None:
            flow_accum_cell = flow_accumulation_array[mask]
            mean_flow_accum = np.nanmean(flow_accum_cell) if num_valid_pixels > 0 else np.nan

        if drainage_intensity_array is not None:
            drainage_int_cell = drainage_intensity_array[mask]
            mean_drainage_int = np.nanmean(drainage_int_cell) if num_valid_pixels > 0 else np.nan

        # Compute HDD reductions
        # UHI HDD reduction: uhi_offset_f × 180 (HDD per °F)
        uhi_hdd_reduction = mean_uhi_offset * config.HDD_PER_DEGREE_F if not np.isnan(mean_uhi_offset) else 0.0

        # Traffic HDD reduction: traffic_heat_offset_f × 180
        traffic_hdd_reduction = mean_traffic_heat_offset * config.HDD_PER_DEGREE_F if not np.isnan(mean_traffic_heat_offset) else 0.0

        # Compute effective HDD using the formula:
        # cell_effective_hdd = base_hdd × terrain_mult × cold_air_drainage_mult
        #                    + elev_addition
        #                    − uhi_hdd_reduction
        #                    − traffic_heat_hdd_reduction
        if not np.isnan(mean_base_hdd) and not np.isnan(mean_terrain_mult):
            cell_effective_hdd = (
                mean_base_hdd * mean_terrain_mult * mean_cold_air_drainage_mult
                + mean_elev_addition
                - uhi_hdd_reduction
                - traffic_hdd_reduction
            )
        else:
            cell_effective_hdd = np.nan

        # Compute uncertainty bounds on effective HDD
        # Note: cold_air_drainage_mult is not included in uncertainty propagation
        # as it is a deterministic correction based on DEM flow accumulation
        cell_effective_hdd_low = np.nan
        cell_effective_hdd_high = np.nan
        if not np.isnan(cell_effective_hdd):
            cell_effective_hdd_low, cell_effective_hdd_high = compute_effective_hdd_bounds(
                mean_base_hdd,
                mean_terrain_mult,
                mean_elev_addition,
                uhi_hdd_reduction,
                traffic_hdd_reduction,
            )

        # Compute CDD (Cooling Degree Days) if base_cdd_array is provided
        # CDD formula: effective_cdd = base_cdd × terrain_mult + elev_addition + uhi_addition + traffic_addition
        # Note: UHI and traffic INCREASE CDD (opposite of HDD)
        cell_effective_cdd = np.nan
        mean_base_cdd = np.nan
        uhi_cdd_addition = 0.0
        traffic_cdd_addition = 0.0

        if base_cdd_array is not None:
            base_cdd_cell = base_cdd_array[mask]
            mean_base_cdd = np.nanmean(base_cdd_cell) if num_valid_pixels > 0 else np.nan

            # For CDD, UHI and traffic INCREASE cooling demand (opposite of HDD)
            uhi_cdd_addition = mean_uhi_offset * config.CDD_PER_DEGREE_F if not np.isnan(mean_uhi_offset) else 0.0
            traffic_cdd_addition = mean_traffic_heat_offset * config.CDD_PER_DEGREE_F if not np.isnan(mean_traffic_heat_offset) else 0.0

            # Compute effective CDD
            # Note: elevation addition is negative for higher elevations (cooler = less cooling demand)
            if not np.isnan(mean_base_cdd) and not np.isnan(mean_terrain_mult):
                cell_effective_cdd = (
                    mean_base_cdd * mean_terrain_mult
                    + mean_elev_addition  # Negative for higher elevations
                    + uhi_cdd_addition
                    + traffic_cdd_addition
                )

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
            "cold_air_drainage_mult": mean_cold_air_drainage_mult,
            "flow_accumulation": mean_flow_accum,
            "drainage_intensity": mean_drainage_int,
            "mean_wind_ms": mean_wind,
            "mean_elevation_ft": mean_elevation,
            "mean_impervious_pct": mean_impervious,
            "surface_albedo": mean_albedo,
            "cell_effective_hdd": cell_effective_hdd,
            "cell_effective_hdd_low": cell_effective_hdd_low,
            "cell_effective_hdd_high": cell_effective_hdd_high,
            "base_cdd": mean_base_cdd,
            "uhi_cdd_addition": uhi_cdd_addition,
            "traffic_cdd_addition": traffic_cdd_addition,
            "cell_effective_cdd": cell_effective_cdd,
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



def compute_monthly_effective_hdd_per_cell(
    cells_gdf: gpd.GeoDataFrame,
    monthly_base_hdd_arrays: list[np.ndarray],
    terrain_mult_array: np.ndarray,
    elev_addition_array: np.ndarray,
    uhi_offset_array: np.ndarray,
    traffic_heat_offset_array: np.ndarray,
    lidar_transform: Affine,
    lidar_shape: tuple[int, int],
    zip_code: str,
    base_station: str,
    region_code: str,
) -> pd.DataFrame:
    """Compute monthly effective HDD for each microclimate cell.

    For each cell in the GeoDataFrame, extracts the mean value of all correction
    arrays within the cell geometry, applies the effective HDD formula for each
    month independently, and returns a DataFrame with one row per cell containing
    12 monthly HDD columns (effective_hdd_jan through effective_hdd_dec).

    Parameters
    ----------
    cells_gdf : gpd.GeoDataFrame
        GeoDataFrame with cell geometries. Must have columns:
        - geometry: cell polygon
        - cell_id: unique cell identifier (e.g., 'cell_001')
        - cell_area_sqm: area of the cell in square meters
        - cell_type: optional, dominant characteristic (e.g., 'urban', 'rural')
    monthly_base_hdd_arrays : list[np.ndarray]
        List of 12 monthly base HDD grids (January through December), 2D arrays.
    terrain_mult_array : np.ndarray
        Terrain position multiplier (windward/leeward/valley/ridge), 2D array.
    elev_addition_array : np.ndarray
        Elevation HDD addition (lapse rate), 2D array.
    uhi_offset_array : np.ndarray
        UHI temperature offset in °F, 2D array.
    traffic_heat_offset_array : np.ndarray
        Traffic heat temperature offset in °F, 2D array.
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
        - terrain_multiplier: mean terrain multiplier within cell
        - elevation_hdd_addition: mean elevation addition within cell
        - uhi_offset_f: mean UHI offset within cell
        - traffic_heat_offset_f: mean traffic heat offset within cell
        - effective_hdd_jan through effective_hdd_dec: monthly effective HDD values
        - effective_hdd_annual: sum of all 12 monthly values
        - num_valid_pixels: count of valid 1m pixels within cell

    Notes
    -----
    - Each month's HDD is computed independently using the formula:
        monthly_hdd = base_monthly_hdd × terrain_mult
                    + elev_addition
                    − uhi_hdd_reduction
                    − traffic_hdd_reduction
    - The annual effective HDD is the sum of all 12 monthly values.
    - NaN values in raster arrays are excluded from the mean computation.
    """
    month_names = [
        "jan", "feb", "mar", "apr", "may", "jun",
        "jul", "aug", "sep", "oct", "nov", "dec"
    ]
    
    rows = []

    for idx, cell_row in cells_gdf.iterrows():
        cell_geom = cell_row.geometry
        cell_id = cell_row["cell_id"]
        cell_area_sqm = cell_row["cell_area_sqm"]
        cell_type = cell_row.get("cell_type", None)

        # Create a mask for pixels within this cell
        mask = ~geometry_mask(
            [cell_geom],
            out_shape=lidar_shape,
            transform=lidar_transform,
            invert=False,
        )

        # Extract values within the cell for correction arrays
        terrain_mult_cell = terrain_mult_array[mask]
        elev_addition_cell = elev_addition_array[mask]
        uhi_offset_cell = uhi_offset_array[mask]
        traffic_heat_offset_cell = traffic_heat_offset_array[mask]

        # Count valid pixels (non-NaN in terrain_mult)
        valid_mask = ~np.isnan(terrain_mult_cell)
        num_valid_pixels = np.sum(valid_mask)

        # Compute means for correction arrays
        mean_terrain_mult = np.nanmean(terrain_mult_cell) if num_valid_pixels > 0 else np.nan
        mean_elev_addition = np.nanmean(elev_addition_cell) if num_valid_pixels > 0 else np.nan
        mean_uhi_offset = np.nanmean(uhi_offset_cell) if num_valid_pixels > 0 else np.nan
        mean_traffic_heat_offset = np.nanmean(traffic_heat_offset_cell) if num_valid_pixels > 0 else np.nan

        # Compute HDD reductions
        uhi_hdd_reduction = mean_uhi_offset * config.HDD_PER_DEGREE_F if not np.isnan(mean_uhi_offset) else 0.0
        traffic_hdd_reduction = mean_traffic_heat_offset * config.HDD_PER_DEGREE_F if not np.isnan(mean_traffic_heat_offset) else 0.0

        # Create microclimate_id
        microclimate_id = f"{region_code}_{zip_code}_{base_station}_cell_{cell_id}"

        # Build base row
        row = {
            "microclimate_id": microclimate_id,
            "zip_code": zip_code,
            "cell_id": cell_id,
            "cell_type": cell_type,
            "cell_area_sqm": cell_area_sqm,
            "terrain_multiplier": mean_terrain_mult,
            "elevation_hdd_addition": mean_elev_addition,
            "uhi_offset_f": mean_uhi_offset,
            "traffic_heat_offset_f": mean_traffic_heat_offset,
            "num_valid_pixels": int(num_valid_pixels),
        }

        # Compute monthly effective HDD values
        monthly_hdd_values = []
        for month_idx, monthly_base_hdd_array in enumerate(monthly_base_hdd_arrays):
            # Extract monthly base HDD within cell
            monthly_base_hdd_cell = monthly_base_hdd_array[mask]
            mean_monthly_base_hdd = np.nanmean(monthly_base_hdd_cell) if num_valid_pixels > 0 else np.nan

            # Compute monthly effective HDD
            if not np.isnan(mean_monthly_base_hdd) and not np.isnan(mean_terrain_mult):
                monthly_effective_hdd = (
                    mean_monthly_base_hdd * mean_terrain_mult
                    + mean_elev_addition
                    - uhi_hdd_reduction
                    - traffic_hdd_reduction
                )
            else:
                monthly_effective_hdd = np.nan

            # Add to row with month name
            month_name = month_names[month_idx]
            row[f"effective_hdd_{month_name}"] = monthly_effective_hdd
            monthly_hdd_values.append(monthly_effective_hdd)

        # Compute annual effective HDD as sum of monthly values
        valid_monthly_values = [v for v in monthly_hdd_values if not np.isnan(v)]
        if valid_monthly_values:
            row["effective_hdd_annual"] = sum(valid_monthly_values)
        else:
            row["effective_hdd_annual"] = np.nan

        rows.append(row)

    # Create DataFrame
    df = pd.DataFrame(rows)

    logger.info(
        f"Computed monthly effective HDD for {len(df)} cells in ZIP {zip_code}. "
        f"Mean annual effective HDD: {df['effective_hdd_annual'].mean():.1f} HDD"
    )

    return df
