"""
Write aviation safety cube to date-partitioned Parquet files.

Writes 3D safety cube (ZIP × date × altitude) to Parquet format with
snappy compression, partitioned by date for efficient time-range queries.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import DAILY_OUTPUT_DIR

logger = logging.getLogger(__name__)


def write_safety_cube(
    cube_df: pd.DataFrame,
    region_name: str,
    start_date: str,
    end_date: str,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Write aviation safety cube to date-partitioned Parquet files.

    Partitions the cube by date and writes each date's data to a separate
    Parquet file for efficient time-range queries. Uses snappy compression
    to reduce file size.

    Parameters
    ----------
    cube_df : pd.DataFrame
        Safety cube DataFrame with columns:
        - date, zip_code, altitude_ft
        - temp_adjusted_f, wind_speed_kt, wind_dir_deg
        - tke_m2s2, wind_shear_kt_per_100ft
        - hdd, density_altitude_ft, turbulence_flag
    region_name : str
        Region name (e.g., "region_1")
    start_date : str
        ISO 8601 start date (YYYY-MM-DD)
    end_date : str
        ISO 8601 end date (YYYY-MM-DD)
    output_dir : Path, optional
        Output directory. Defaults to DAILY_OUTPUT_DIR.

    Returns
    -------
    Path
        Path to the output directory containing partitioned Parquet files
    """
    if output_dir is None:
        output_dir = DAILY_OUTPUT_DIR

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectory for safety cube
    cube_dir = output_dir / "safety_cube"
    cube_dir.mkdir(parents=True, exist_ok=True)

    # Ensure date column is string
    if "date" in cube_df.columns:
        cube_df["date"] = cube_df["date"].astype(str)

    # Group by date and write each date to a separate Parquet file
    unique_dates = cube_df["date"].unique()
    logger.info(
        f"Writing safety cube for {len(unique_dates)} dates to {cube_dir}"
    )

    for date in sorted(unique_dates):
        date_data = cube_df[cube_df["date"] == date]

        # Construct filename: safety_cube_{region}_{date}.parquet
        filename = f"safety_cube_{region_name}_{date}.parquet"
        filepath = cube_dir / filename

        try:
            date_data.to_parquet(
                filepath,
                engine="pyarrow",
                compression="snappy",
                index=False,
            )
            logger.info(
                f"Wrote {len(date_data)} rows to {filepath} "
                f"({filepath.stat().st_size / 1e6:.1f} MB)"
            )
        except Exception as e:
            logger.error(f"Failed to write safety cube for {date}: {e}", exc_info=True)
            raise

    # Also write a combined file for the entire date range
    combined_filename = f"safety_cube_{region_name}_{start_date}_{end_date}.parquet"
    combined_filepath = cube_dir / combined_filename

    try:
        cube_df.to_parquet(
            combined_filepath,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
        logger.info(
            f"Wrote combined safety cube to {combined_filepath} "
            f"({combined_filepath.stat().st_size / 1e6:.1f} MB)"
        )
    except Exception as e:
        logger.error(f"Failed to write combined safety cube: {e}", exc_info=True)
        raise

    return cube_dir


def write_safety_cube_csv(
    cube_df: pd.DataFrame,
    region_name: str,
    start_date: str,
    end_date: str,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Write aviation safety cube to CSV format (alternative to Parquet).

    Parameters
    ----------
    cube_df : pd.DataFrame
        Safety cube DataFrame
    region_name : str
        Region name (e.g., "region_1")
    start_date : str
        ISO 8601 start date (YYYY-MM-DD)
    end_date : str
        ISO 8601 end date (YYYY-MM-DD)
    output_dir : Path, optional
        Output directory. Defaults to DAILY_OUTPUT_DIR.

    Returns
    -------
    Path
        Path to the written CSV file
    """
    if output_dir is None:
        output_dir = DAILY_OUTPUT_DIR

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectory for safety cube
    cube_dir = output_dir / "safety_cube"
    cube_dir.mkdir(parents=True, exist_ok=True)

    # Ensure date column is string
    if "date" in cube_df.columns:
        cube_df["date"] = cube_df["date"].astype(str)

    # Write combined CSV
    filename = f"safety_cube_{region_name}_{start_date}_{end_date}.csv"
    filepath = cube_dir / filename

    try:
        cube_df.to_csv(filepath, index=False)
        logger.info(
            f"Wrote safety cube to {filepath} "
            f"({filepath.stat().st_size / 1e6:.1f} MB)"
        )
    except Exception as e:
        logger.error(f"Failed to write safety cube CSV: {e}", exc_info=True)
        raise

    return filepath


def validate_safety_cube_output(cube_df: pd.DataFrame) -> dict:
    """
    Validate safety cube output data.

    Checks for:
    - Required columns present
    - No NaN values in key columns
    - Reasonable value ranges
    - Correct altitude levels
    - Valid turbulence flags

    Parameters
    ----------
    cube_df : pd.DataFrame
        Safety cube DataFrame

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
        "altitude_ft",
        "temp_adjusted_f",
        "wind_speed_kt",
        "tke_m2s2",
        "density_altitude_ft",
        "turbulence_flag",
    ]
    for col in required_cols:
        if col not in cube_df.columns:
            errors.append(f"Missing required column: {col}")

    # Check for NaN in key columns
    for col in required_cols:
        if col in cube_df.columns:
            nan_count = cube_df[col].isna().sum()
            if nan_count > 0:
                warnings.append(f"Column {col} has {nan_count} NaN values")

    # Check value ranges
    if "temp_adjusted_f" in cube_df.columns:
        temp_min = cube_df["temp_adjusted_f"].min()
        temp_max = cube_df["temp_adjusted_f"].max()
        if temp_min < -80 or temp_max > 120:
            warnings.append(
                f"Temperature range unusual: {temp_min}°F to {temp_max}°F"
            )

    if "wind_speed_kt" in cube_df.columns:
        wind_max = cube_df["wind_speed_kt"].max()
        if wind_max > 200:
            warnings.append(f"Wind speed unusually high: {wind_max} kt")

    if "tke_m2s2" in cube_df.columns:
        tke_max = cube_df["tke_m2s2"].max()
        if tke_max > 10:
            warnings.append(f"TKE unusually high: {tke_max} m²/s²")

    # Check turbulence flag values
    if "turbulence_flag" in cube_df.columns:
        valid_flags = {"smooth", "light", "moderate", "severe"}
        invalid_flags = set(cube_df["turbulence_flag"].unique()) - valid_flags
        if invalid_flags:
            errors.append(f"Invalid turbulence flags: {invalid_flags}")

    # Check altitude levels
    if "altitude_ft" in cube_df.columns:
        expected_altitudes = {0, 500, 1000, 3000, 6000, 9000, 12000, 18000}
        actual_altitudes = set(cube_df["altitude_ft"].unique())
        if not actual_altitudes.issubset(expected_altitudes):
            warnings.append(
                f"Unexpected altitude levels: {actual_altitudes - expected_altitudes}"
            )

    # Check that each ZIP × date has all 8 altitude levels
    if "date" in cube_df.columns and "zip_code" in cube_df.columns:
        for (date, zip_code), group in cube_df.groupby(["date", "zip_code"]):
            alt_count = len(group["altitude_ft"].unique())
            if alt_count != 8:
                warnings.append(
                    f"ZIP {zip_code} on {date} has {alt_count} altitudes (expected 8)"
                )

    passed = len(errors) == 0

    return {
        "passed": passed,
        "warnings": warnings,
        "errors": errors,
    }
