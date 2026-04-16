"""
Write terrain attributes CSV with cell-level and ZIP-code aggregate rows.

This module combines cell-level microclimate data with ZIP-code aggregates,
producing a pre-computed lookup table for downstream models to join on.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


def write_terrain_attributes(
    cells_df: pd.DataFrame,
    region_code: str,
    output_path: Path,
    pipeline_version: str = "1.0.0",
    lidar_vintage: int = 2021,
    nlcd_vintage: int = 2021,
    prism_period: str = "1991-2020",
) -> None:
    """
    Write terrain attributes CSV with cell-level and ZIP-code aggregate rows.

    Parameters
    ----------
    cells_df : pd.DataFrame
        Cell-level data with columns:
        - zip_code: str
        - cell_id: str
        - cell_type: str (optional)
        - cell_area_sqm: float
        - base_station: str
        - effective_hdd: float
        - All correction columns (hdd_terrain_mult, hdd_elev_addition, etc.)
        - mean_elevation_ft, mean_wind_ms, mean_impervious_pct, etc.
    region_code : str
        Region code (e.g., "R1")
    output_path : Path
        Path to write terrain_attributes.csv
    pipeline_version : str
        Semantic version of the pipeline
    lidar_vintage : int
        Year of LiDAR DEM used
    nlcd_vintage : int
        NLCD release year
    prism_period : str
        PRISM climate normal period (e.g., "1991-2020")
    """
    if cells_df.empty:
        logger.warning("cells_df is empty; no output written")
        return

    # Ensure required columns exist
    required_cols = [
        "zip_code",
        "cell_id",
        "base_station",
        "effective_hdd",
        "cell_area_sqm",
    ]
    missing = [col for col in required_cols if col not in cells_df.columns]
    if missing:
        raise ValueError(f"Missing required columns in cells_df: {missing}")

    # Create a copy to avoid modifying the input
    df = cells_df.copy()

    # Ensure numeric columns are float64
    numeric_cols = [
        "effective_hdd",
        "effective_cdd",
        "cell_area_sqm",
        "hdd_terrain_mult",
        "hdd_elev_addition",
        "hdd_uhi_reduction",
        "mean_elevation_ft",
        "mean_wind_ms",
        "wind_infiltration_mult",
        "prism_annual_hdd",
        "lst_summer_c",
        "mean_impervious_pct",
        "surface_albedo",
        "uhi_offset_f",
        "road_heat_flux_wm2",
        "road_temp_offset_f",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Add versioning columns
    run_date = datetime.now(timezone.utc).isoformat()
    df["run_date"] = run_date
    df["pipeline_version"] = pipeline_version
    df["lidar_vintage"] = lidar_vintage
    df["nlcd_vintage"] = nlcd_vintage
    df["prism_period"] = prism_period

    # Create cell-level rows with microclimate_id
    cell_rows = []
    for _, row in df.iterrows():
        zip_code = str(row["zip_code"]).zfill(5)
        cell_id = str(row["cell_id"])
        base_station = str(row["base_station"])
        microclimate_id = f"{region_code}_{zip_code}_{base_station}_cell_{cell_id}"

        cell_row = row.to_dict()
        cell_row["microclimate_id"] = microclimate_id
        cell_row["zip_code"] = zip_code
        cell_rows.append(cell_row)

    cell_rows_df = pd.DataFrame(cell_rows)

    # Create ZIP-code aggregate rows
    aggregate_rows = []
    for zip_code, group in df.groupby("zip_code"):
        zip_code = str(zip_code).zfill(5)
        base_station = group["base_station"].iloc[0]  # Assume same station per ZIP
        microclimate_id = f"{region_code}_{zip_code}_{base_station}_aggregate"

        # Compute aggregates
        agg_row = {
            "microclimate_id": microclimate_id,
            "zip_code": zip_code,
            "cell_id": "aggregate",
            "cell_type": None,
            "cell_area_sqm": None,
            "base_station": base_station,
            "effective_hdd": group["effective_hdd"].mean(),
            "num_cells": len(group),
            "cell_hdd_min": group["effective_hdd"].min(),
            "cell_hdd_max": group["effective_hdd"].max(),
            "cell_hdd_std": group["effective_hdd"].std(),
            "run_date": run_date,
            "pipeline_version": pipeline_version,
            "lidar_vintage": lidar_vintage,
            "nlcd_vintage": nlcd_vintage,
            "prism_period": prism_period,
        }

        # Average all numeric correction columns
        for col in numeric_cols:
            if col in group.columns and col != "effective_hdd":
                agg_row[col] = group[col].mean()

        # Copy string/categorical columns from first row
        for col in group.columns:
            if col not in agg_row and col not in numeric_cols:
                agg_row[col] = group[col].iloc[0]

        aggregate_rows.append(agg_row)

    aggregate_rows_df = pd.DataFrame(aggregate_rows)

    # Combine cell and aggregate rows
    output_df = pd.concat([cell_rows_df, aggregate_rows_df], ignore_index=True)

    # Define column order (cell-level columns first, then aggregates, then metadata)
    base_cols = [
        "microclimate_id",
        "zip_code",
        "cell_id",
        "cell_type",
        "cell_area_sqm",
        "base_station",
        "terrain_position",
        "mean_elevation_ft",
        "dominant_aspect_deg",
        "mean_wind_ms",
        "wind_infiltration_mult",
        "prism_annual_hdd",
        "lst_summer_c",
        "mean_impervious_pct",
        "surface_albedo",
        "uhi_offset_f",
        "road_heat_flux_wm2",
        "road_temp_offset_f",
        "hdd_terrain_mult",
        "hdd_elev_addition",
        "hdd_uhi_reduction",
        "effective_hdd",
        "effective_hdd_jan",
        "effective_hdd_feb",
        "effective_hdd_mar",
        "effective_hdd_apr",
        "effective_hdd_may",
        "effective_hdd_jun",
        "effective_hdd_jul",
        "effective_hdd_aug",
        "effective_hdd_sep",
        "effective_hdd_oct",
        "effective_hdd_nov",
        "effective_hdd_dec",
        "effective_hdd_annual",
        "base_cdd",
        "uhi_cdd_addition",
        "traffic_cdd_addition",
        "effective_cdd",
        "num_cells",
        "cell_hdd_min",
        "cell_hdd_max",
        "cell_hdd_std",
        "cell_cdd_min",
        "cell_cdd_max",
        "cell_cdd_std",
        "run_date",
        "pipeline_version",
        "lidar_vintage",
        "nlcd_vintage",
        "prism_period",
    ]

    # Keep only columns that exist in output_df
    cols_to_write = [col for col in base_cols if col in output_df.columns]
    # Add any remaining columns not in base_cols
    remaining_cols = [col for col in output_df.columns if col not in cols_to_write]
    cols_to_write.extend(remaining_cols)

    output_df = output_df[cols_to_write]

    # Write to CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_path, index=False)

    logger.info(
        f"Wrote {len(output_df)} rows to {output_path} "
        f"({len(cell_rows_df)} cell-level, {len(aggregate_rows_df)} ZIP-code aggregates)"
    )


def validate_terrain_attributes(df: pd.DataFrame) -> List[str]:
    """
    Validate terrain attributes output for consistency and plausibility.

    Parameters
    ----------
    df : pd.DataFrame
        Terrain attributes DataFrame

    Returns
    -------
    List[str]
        List of validation warnings/errors
    """
    issues = []

    # Check for required columns
    required = ["microclimate_id", "zip_code", "cell_id", "effective_hdd"]
    for col in required:
        if col not in df.columns:
            issues.append(f"Missing required column: {col}")

    # Check effective_hdd range
    if "effective_hdd" in df.columns:
        out_of_range = df[
            (df["effective_hdd"] < 2000) | (df["effective_hdd"] > 8000)
        ]
        if not out_of_range.empty:
            issues.append(
                f"{len(out_of_range)} rows have effective_hdd outside 2000-8000 range"
            )

    # Check effective_cdd range (typically 0-2000 for PNW)
    if "effective_cdd" in df.columns:
        out_of_range_cdd = df[
            (df["effective_cdd"] < 0) | (df["effective_cdd"] > 3000)
        ]
        if not out_of_range_cdd.empty:
            issues.append(
                f"{len(out_of_range_cdd)} rows have effective_cdd outside 0-3000 range"
            )

    # Check for NaN in critical columns
    critical_cols = ["microclimate_id", "zip_code", "effective_hdd"]
    for col in critical_cols:
        if col in df.columns:
            nan_count = df[col].isna().sum()
            if nan_count > 0:
                issues.append(f"{nan_count} NaN values in {col}")

    # Check aggregate consistency: ZIP aggregate effective_hdd should equal mean of cells
    if "cell_id" in df.columns and "effective_hdd" in df.columns:
        for zip_code in df[df["cell_id"] == "aggregate"]["zip_code"].unique():
            agg_row = df[(df["zip_code"] == zip_code) & (df["cell_id"] == "aggregate")]
            cell_rows = df[(df["zip_code"] == zip_code) & (df["cell_id"] != "aggregate")]

            if not agg_row.empty and not cell_rows.empty:
                agg_hdd = agg_row["effective_hdd"].iloc[0]
                cell_mean_hdd = cell_rows["effective_hdd"].mean()
                if not np.isclose(agg_hdd, cell_mean_hdd, rtol=1e-5):
                    issues.append(
                        f"ZIP {zip_code} aggregate HDD ({agg_hdd:.1f}) "
                        f"!= mean of cells ({cell_mean_hdd:.1f})"
                    )

    # Check CDD aggregate consistency (if CDD column present)
    if "cell_id" in df.columns and "effective_cdd" in df.columns:
        for zip_code in df[df["cell_id"] == "aggregate"]["zip_code"].unique():
            agg_row = df[(df["zip_code"] == zip_code) & (df["cell_id"] == "aggregate")]
            cell_rows = df[(df["zip_code"] == zip_code) & (df["cell_id"] != "aggregate")]

            if not agg_row.empty and not cell_rows.empty:
                agg_cdd = agg_row["effective_cdd"].iloc[0]
                cell_mean_cdd = cell_rows["effective_cdd"].mean()
                if not np.isclose(agg_cdd, cell_mean_cdd, rtol=1e-5):
                    issues.append(
                        f"ZIP {zip_code} aggregate CDD ({agg_cdd:.1f}) "
                        f"!= mean of cells ({cell_mean_cdd:.1f})"
                    )

    return issues
