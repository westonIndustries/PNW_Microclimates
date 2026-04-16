"""
Write hourly microclimate output to date-partitioned Parquet files.

Writes hourly safety cubes (ZIP × hour × altitude) to Parquet format with
snappy compression, partitioned by date for efficient time-range queries.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import DAILY_OUTPUT_DIR

logger = logging.getLogger(__name__)


def write_hourly_output(
    hourly_df: pd.DataFrame,
    region_name: str,
    start_date: str,
    end_date: str,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Write hourly microclimate data to date-partitioned Parquet files.

    Partitions the hourly data by date and writes each date's data to a separate
    Parquet file for efficient time-range queries. Uses snappy compression
    to reduce file size.

    Parameters
    ----------
    hourly_df : pd.DataFrame
        Hourly microclimate DataFrame with columns:
        - datetime_utc, zip_code, altitude_ft
        - temp_adjusted_f, wind_speed_kt, wind_dir_deg
        - tke_m2s2, wind_shear_kt_per_100ft
        - hourly_hdd, density_altitude_ft, turbulence_flag
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

    # Create subdirectory for hourly data
    hourly_dir = output_dir / "hourly"
    hourly_dir.mkdir(parents=True, exist_ok=True)

    # Ensure datetime column is string
    if "datetime_utc" in hourly_df.columns:
        hourly_df["datetime_utc"] = hourly_df["datetime_utc"].astype(str)

    # Extract date from datetime for partitioning
    hourly_df["date"] = pd.to_datetime(hourly_df["datetime_utc"]).dt.date

    # Group by date and write each date to a separate Parquet file
    unique_dates = hourly_df["date"].unique()
    logger.info(
        f"Writing hourly data for {len(unique_dates)} dates to {hourly_dir}"
    )

    for date in sorted(unique_dates):
        date_data = hourly_df[hourly_df["date"] == date].drop(columns=["date"])

        # Construct filename: hourly_{region}_{date}.parquet
        filename = f"hourly_{region_name}_{date}.parquet"
        filepath = hourly_dir / filename

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
            logger.error(f"Failed to write hourly data for {date}: {e}", exc_info=True)
            raise

    # Also write a combined file for the entire date range
    combined_filename = f"hourly_{region_name}_{start_date}_{end_date}.parquet"
    combined_filepath = hourly_dir / combined_filename

    try:
        hourly_df.drop(columns=["date"]).to_parquet(
            combined_filepath,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
        logger.info(
            f"Wrote combined hourly data to {combined_filepath} "
            f"({combined_filepath.stat().st_size / 1e6:.1f} MB)"
        )
    except Exception as e:
        logger.error(f"Failed to write combined hourly data: {e}", exc_info=True)
        raise

    return hourly_dir


def write_hourly_output_csv(
    hourly_df: pd.DataFrame,
    region_name: str,
    start_date: str,
    end_date: str,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Write hourly microclimate data to CSV format (alternative to Parquet).

    Parameters
    ----------
    hourly_df : pd.DataFrame
        Hourly microclimate DataFrame
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

    # Create subdirectory for hourly data
    hourly_dir = output_dir / "hourly"
    hourly_dir.mkdir(parents=True, exist_ok=True)

    # Ensure datetime column is string
    if "datetime_utc" in hourly_df.columns:
        hourly_df["datetime_utc"] = hourly_df["datetime_utc"].astype(str)

    # Write combined CSV
    filename = f"hourly_{region_name}_{start_date}_{end_date}.csv"
    filepath = hourly_dir / filename

    try:
        hourly_df.to_csv(filepath, index=False)
        logger.info(
            f"Wrote hourly data to {filepath} "
            f"({filepath.stat().st_size / 1e6:.1f} MB)"
        )
    except Exception as e:
        logger.error(f"Failed to write hourly CSV: {e}", exc_info=True)
        raise

    return filepath


def validate_hourly_output(hourly_df: pd.DataFrame) -> dict:
    """
    Validate hourly output data.

    Checks for:
    - Required columns present
    - No NaN values in key columns
    - Reasonable value ranges
    - Correct altitude levels
    - Valid datetime format
    - All 24 hours present for complete days

    Parameters
    ----------
    hourly_df : pd.DataFrame
        Hourly microclimate DataFrame

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
        "datetime_utc",
        "zip_code",
        "altitude_ft",
        "temp_adjusted_f",
        "wind_speed_kt",
        "hourly_hdd",
        "turbulence_flag",
    ]
    for col in required_cols:
        if col not in hourly_df.columns:
            errors.append(f"Missing required column: {col}")

    # Check for NaN in key columns
    for col in required_cols:
        if col in hourly_df.columns:
            nan_count = hourly_df[col].isna().sum()
            if nan_count > 0:
                warnings.append(f"Column {col} has {nan_count} NaN values")

    # Check value ranges
    if "hourly_hdd" in hourly_df.columns:
        hdd_min = hourly_df["hourly_hdd"].min()
        hdd_max = hourly_df["hourly_hdd"].max()
        if hdd_min < 0:
            errors.append(f"hourly_hdd has negative values (min: {hdd_min})")
        if hdd_max > 2.5:
            warnings.append(f"hourly_hdd has very high values (max: {hdd_max})")

    if "temp_adjusted_f" in hourly_df.columns:
        temp_min = hourly_df["temp_adjusted_f"].min()
        temp_max = hourly_df["temp_adjusted_f"].max()
        if temp_min < -80 or temp_max > 120:
            warnings.append(
                f"Temperature range unusual: {temp_min}°F to {temp_max}°F"
            )

    # Check datetime format
    if "datetime_utc" in hourly_df.columns:
        try:
            pd.to_datetime(hourly_df["datetime_utc"])
        except Exception as e:
            errors.append(f"Invalid datetime format: {e}")

    # Check altitude levels
    if "altitude_ft" in hourly_df.columns:
        expected_altitudes = {0, 500, 1000, 3000, 6000, 9000, 12000, 18000}
        actual_altitudes = set(hourly_df["altitude_ft"].unique())
        if not actual_altitudes.issubset(expected_altitudes):
            warnings.append(
                f"Unexpected altitude levels: {actual_altitudes - expected_altitudes}"
            )

    # Check that each ZIP × hour has all 8 altitude levels
    if "datetime_utc" in hourly_df.columns and "altitude_ft" in hourly_df.columns:
        for (datetime_utc, zip_code), group in hourly_df.groupby(
            ["datetime_utc", "zip_code"]
        ):
            alt_count = len(group["altitude_ft"].unique())
            if alt_count != 8:
                warnings.append(
                    f"ZIP {zip_code} at {datetime_utc} has {alt_count} altitudes (expected 8)"
                )

    # Check that all 24 hours are present for complete days
    if "datetime_utc" in hourly_df.columns:
        hourly_df["date"] = pd.to_datetime(hourly_df["datetime_utc"]).dt.date
        for date, group in hourly_df.groupby("date"):
            hour_count = len(group["datetime_utc"].unique())
            if hour_count != 24:
                warnings.append(
                    f"Date {date} has {hour_count} hours (expected 24)"
                )

    passed = len(errors) == 0

    return {
        "passed": passed,
        "warnings": warnings,
        "errors": errors,
    }
