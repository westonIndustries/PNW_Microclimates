"""
Write daily microclimate output to Parquet and/or CSV.

Writes daily effective HDD, wind profiles, and altitude temperature/HDD
data per ZIP code to time-series Parquet or CSV files.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import DAILY_OUTPUT_DIR

logger = logging.getLogger(__name__)


def write_daily_output(
    daily_data: pd.DataFrame,
    region_name: str,
    start_date: str,
    end_date: str,
    output_format: str = "parquet",
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Write daily microclimate data to Parquet and/or CSV.

    Parameters
    ----------
    daily_data : pd.DataFrame
        Daily microclimate data with columns:
        - date, zip_code, hrrr_raw_temp_f, hrrr_adjusted_temp_f, bias_correction_f
        - daily_effective_hdd, terrain_multiplier
        - wind_speed_sfc_kt, wind_dir_sfc_deg (and for each altitude)
        - temp_sfc_raw_f, temp_sfc_adjusted_f, hdd_sfc
        - temp_{alt}_raw_f, temp_{alt}_adjusted_f, hdd_{alt} (for each altitude)
        - run_date, pipeline_version, nlcd_vintage, prism_period
    region_name : str
        Region name (e.g., "region_1")
    start_date : str
        ISO 8601 start date (YYYY-MM-DD)
    end_date : str
        ISO 8601 end date (YYYY-MM-DD)
    output_format : str, default "parquet"
        Output format: "parquet", "csv", or "both"
    output_dir : Path, optional
        Output directory. Defaults to DAILY_OUTPUT_DIR.

    Returns
    -------
    Path
        Path to the written output file (or directory if "both")
    """
    if output_dir is None:
        output_dir = DAILY_OUTPUT_DIR

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Construct filename
    filename_base = f"daily_{region_name}_{start_date}_{end_date}"

    # Ensure date column is string
    if "date" in daily_data.columns:
        daily_data["date"] = daily_data["date"].astype(str)

    # Write Parquet
    if output_format in ("parquet", "both"):
        parquet_path = output_dir / f"{filename_base}.parquet"
        logger.info(f"Writing daily output to {parquet_path}")

        try:
            daily_data.to_parquet(
                parquet_path,
                engine="pyarrow",
                compression="snappy",
                index=False,
            )
            logger.info(
                f"Wrote {len(daily_data)} rows to {parquet_path} "
                f"({parquet_path.stat().st_size / 1e6:.1f} MB)"
            )
        except Exception as e:
            logger.error(f"Failed to write Parquet file: {e}", exc_info=True)
            raise

    # Write CSV
    if output_format in ("csv", "both"):
        csv_path = output_dir / f"{filename_base}.csv"
        logger.info(f"Writing daily output to {csv_path}")

        try:
            daily_data.to_csv(csv_path, index=False)
            logger.info(
                f"Wrote {len(daily_data)} rows to {csv_path} "
                f"({csv_path.stat().st_size / 1e6:.1f} MB)"
            )
        except Exception as e:
            logger.error(f"Failed to write CSV file: {e}", exc_info=True)
            raise

    # Return path
    if output_format == "parquet":
        return parquet_path
    elif output_format == "csv":
        return csv_path
    else:
        return output_dir


def validate_daily_output(daily_data: pd.DataFrame) -> dict:
    """
    Validate daily output data.

    Checks for:
    - Required columns present
    - No NaN values in key columns
    - Reasonable value ranges
    - Consistent date format

    Parameters
    ----------
    daily_data : pd.DataFrame
        Daily microclimate data

    Returns
    -------
    dict
        Validation results with keys:
        - 'passed': bool
        - 'warnings': list of warning messages
        - 'errors': list of error messages
    """
    warnings = []
    errors = []

    # Check required columns
    required_cols = [
        "date",
        "zip_code",
        "hrrr_raw_temp_f",
        "hrrr_adjusted_temp_f",
        "daily_effective_hdd",
    ]
    for col in required_cols:
        if col not in daily_data.columns:
            errors.append(f"Missing required column: {col}")

    # Check for NaN in key columns
    for col in required_cols:
        if col in daily_data.columns:
            nan_count = daily_data[col].isna().sum()
            if nan_count > 0:
                warnings.append(f"Column {col} has {nan_count} NaN values")

    # Check value ranges
    if "daily_effective_hdd" in daily_data.columns:
        hdd_min = daily_data["daily_effective_hdd"].min()
        hdd_max = daily_data["daily_effective_hdd"].max()
        if hdd_min < 0:
            errors.append(f"daily_effective_hdd has negative values (min: {hdd_min})")
        if hdd_max > 10000:
            warnings.append(
                f"daily_effective_hdd has very high values (max: {hdd_max})"
            )

    # Check temperature ranges (°F)
    if "hrrr_adjusted_temp_f" in daily_data.columns:
        temp_min = daily_data["hrrr_adjusted_temp_f"].min()
        temp_max = daily_data["hrrr_adjusted_temp_f"].max()
        if temp_min < -50 or temp_max > 120:
            warnings.append(
                f"Temperature range unusual: {temp_min}°F to {temp_max}°F"
            )

    # Check date format
    if "date" in daily_data.columns:
        try:
            pd.to_datetime(daily_data["date"])
        except Exception as e:
            errors.append(f"Invalid date format: {e}")

    passed = len(errors) == 0

    return {
        "passed": passed,
        "warnings": warnings,
        "errors": errors,
    }
