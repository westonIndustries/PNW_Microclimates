"""
Aggregate microclimate cells to ZIP code level.

For each ZIP code, computes aggregate statistics across all cells:
- zip_effective_hdd: mean of all cell_effective_hdd values
- cell_hdd_min: minimum cell_effective_hdd
- cell_hdd_max: maximum cell_effective_hdd
- cell_hdd_std: standard deviation of cell_effective_hdd
- num_cells: count of cells in the ZIP code
- Mean values for all correction columns

Returns a DataFrame with one aggregate row per ZIP code with cell_id = "aggregate".
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src import config
from src.validation.qa_checks import verify_aggregate_hdd_consistency

logger = logging.getLogger(__name__)


def aggregate_cells_to_zip(
    cells_df: pd.DataFrame,
    zip_code: str,
    base_station: str,
    region_code: str,
) -> pd.DataFrame:
    """Aggregate cell-level data to ZIP code level.

    For each ZIP code, computes mean, min, max, and std of cell_effective_hdd
    across all cells, plus mean values for all correction columns. Returns a
    single aggregate row with cell_id = "aggregate".

    Parameters
    ----------
    cells_df : pd.DataFrame
        DataFrame with one row per cell, as produced by
        compute_effective_hdd_per_cell(). Must contain:
        - cell_id: cell identifier (e.g., 'cell_001')
        - cell_effective_hdd: effective HDD for the cell
        - All correction columns (base_hdd, terrain_multiplier, etc.)
    zip_code : str
        ZIP code for this aggregation.
    base_station : str
        NOAA station code (e.g., 'KPDX').
    region_code : str
        Region code (e.g., 'R1').

    Returns
    -------
    pd.DataFrame
        DataFrame with a single row (the ZIP code aggregate) containing:
        - microclimate_id: unique identifier with cell_id = "aggregate"
        - zip_code: ZIP code
        - cell_id: "aggregate"
        - cell_type: None (aggregate rows have no cell type)
        - cell_area_sqm: None (aggregate rows have no cell area)
        - base_hdd: mean across all cells
        - terrain_multiplier: mean across all cells
        - elevation_hdd_addition: mean across all cells
        - uhi_offset_f: mean across all cells
        - uhi_hdd_reduction: mean across all cells
        - traffic_heat_offset_f: mean across all cells
        - traffic_heat_hdd_reduction: mean across all cells
        - wind_infiltration_mult: mean across all cells
        - mean_wind_ms: mean across all cells
        - mean_elevation_ft: mean across all cells
        - mean_impervious_pct: mean across all cells
        - surface_albedo: mean across all cells
        - cell_effective_hdd: mean of all cell_effective_hdd values
        - num_cells: count of cells in the ZIP code
        - cell_hdd_min: minimum cell_effective_hdd
        - cell_hdd_max: maximum cell_effective_hdd
        - cell_hdd_std: standard deviation of cell_effective_hdd
        - num_valid_pixels: sum of all cell num_valid_pixels
        - run_date: copied from first cell row (set by caller)
        - pipeline_version: copied from first cell row (from config)
        - lidar_vintage: copied from first cell row (set by caller)
        - nlcd_vintage: copied from first cell row (from config)
        - prism_period: copied from first cell row (from config)

    Notes
    -----
    - If cells_df is empty, returns an empty DataFrame.
    - NaN values in numeric columns are excluded from mean/min/max/std computations.
    - The aggregate row has cell_id = "aggregate" and cell_type = None.
    - Verification check: aggregate cell_effective_hdd should equal mean of all
      cell_effective_hdd values (within floating-point tolerance).
    """
    if cells_df.empty:
        logger.warning(f"No cells found for ZIP code {zip_code}. Returning empty DataFrame.")
        return pd.DataFrame()

    # Extract numeric columns for aggregation
    # These are the columns that should be averaged across cells
    numeric_cols = [
        "base_hdd",
        "terrain_multiplier",
        "elevation_hdd_addition",
        "uhi_offset_f",
        "uhi_hdd_reduction",
        "traffic_heat_offset_f",
        "traffic_heat_hdd_reduction",
        "wind_infiltration_mult",
        "mean_wind_ms",
        "mean_elevation_ft",
        "mean_impervious_pct",
        "surface_albedo",
    ]

    # Compute aggregates
    num_cells = len(cells_df)
    cell_hdd_values = cells_df["cell_effective_hdd"].dropna()

    # Compute statistics for cell_effective_hdd
    zip_effective_hdd = cell_hdd_values.mean() if len(cell_hdd_values) > 0 else np.nan
    cell_hdd_min = cell_hdd_values.min() if len(cell_hdd_values) > 0 else np.nan
    cell_hdd_max = cell_hdd_values.max() if len(cell_hdd_values) > 0 else np.nan
    cell_hdd_std = cell_hdd_values.std() if len(cell_hdd_values) > 1 else np.nan

    # Compute means for all numeric correction columns
    agg_row = {
        "microclimate_id": f"{region_code}_{zip_code}_{base_station}_aggregate",
        "zip_code": zip_code,
        "cell_id": "aggregate",
        "cell_type": None,
        "cell_area_sqm": None,
        "cell_effective_hdd": zip_effective_hdd,
        "num_cells": num_cells,
        "cell_hdd_min": cell_hdd_min,
        "cell_hdd_max": cell_hdd_max,
        "cell_hdd_std": cell_hdd_std,
        "num_valid_pixels": int(cells_df["num_valid_pixels"].sum()),
    }

    # Add means for all numeric columns
    for col in numeric_cols:
        if col in cells_df.columns:
            agg_row[col] = cells_df[col].mean()
        else:
            agg_row[col] = np.nan

    # Copy metadata columns from the first cell row
    metadata_cols = ["run_date", "pipeline_version", "lidar_vintage", "nlcd_vintage", "prism_period"]
    for col in metadata_cols:
        if col in cells_df.columns:
            agg_row[col] = cells_df[col].iloc[0]

    # Create DataFrame with single row
    agg_df = pd.DataFrame([agg_row])

    logger.info(
        f"Aggregated {num_cells} cells for ZIP {zip_code}. "
        f"Aggregate effective HDD: {zip_effective_hdd:.1f} HDD "
        f"(range: {cell_hdd_min:.1f}–{cell_hdd_max:.1f}, std: {cell_hdd_std:.1f})"
    )

    return agg_df


def aggregate_all_cells_to_zip(
    all_cells_df: pd.DataFrame,
    region_code: str,
) -> tuple[pd.DataFrame, dict]:
    """Aggregate all cells to ZIP code level and verify consistency.

    Processes all cells in the DataFrame, grouping by ZIP code and base station,
    computing aggregates for each ZIP code, and running verification checks.

    Parameters
    ----------
    all_cells_df : pd.DataFrame
        DataFrame with all cell-level rows from combine_corrections_cells.
        Must contain: zip_code, base_station, cell_id, cell_effective_hdd,
        and all correction columns.
    region_code : str
        Region code (e.g., 'R1').

    Returns
    -------
    tuple[pd.DataFrame, dict]
        - DataFrame with all cell-level rows plus one aggregate row per ZIP code
        - Dictionary with verification results (check_name -> QACheckResult)

    Notes
    -----
    - Verification check: aggregate cell_effective_hdd must equal mean of all
      cell_effective_hdd values (within floating-point tolerance).
    - Mismatches are flagged in the returned verification results.
    """
    if all_cells_df.empty:
        logger.warning("No cells found for aggregation. Returning empty DataFrame.")
        return pd.DataFrame(), {}

    # Group by ZIP code and base station
    agg_dfs = []

    for (zip_code, base_station), group in all_cells_df.groupby(["zip_code", "base_station"]):
        agg_df = aggregate_cells_to_zip(
            cells_df=group,
            zip_code=zip_code,
            base_station=base_station,
            region_code=region_code,
        )
        if not agg_df.empty:
            agg_dfs.append(agg_df)

    # Combine all cells and aggregates
    if agg_dfs:
        all_agg_df = pd.concat(agg_dfs, ignore_index=True)
    else:
        all_agg_df = pd.DataFrame()

    # Combine cell-level and aggregate rows
    combined_df = pd.concat([all_cells_df, all_agg_df], ignore_index=True)

    # Run verification check
    verification_result = verify_aggregate_hdd_consistency(combined_df)

    if not verification_result.passed:
        logger.warning(f"Aggregate HDD consistency check failed: {verification_result.num_issues} issues")
        for issue in verification_result.issues:
            logger.warning(f"  - {issue}")
    else:
        logger.info("Aggregate HDD consistency check passed")

    return combined_df, {"aggregate_hdd_consistency": verification_result}
