"""
Hourly microclimate pipeline orchestrator.

Orchestrates the full hourly pipeline: load HRRR hourly data, process each hour,
apply terrain corrections, and write hourly safety cubes.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import TERRAIN_ATTRIBUTES_CSV
from src.loaders.load_hrrr import HRRRLoader
from src.loaders.load_prism_temperature import load_prism_temperature
from src.processors.hourly_combine import process_single_hour
from src.output.write_hourly_output import write_hourly_output

logger = logging.getLogger(__name__)


def run_hourly_pipeline(
    region_name: str,
    start_date: str,
    end_date: str,
    terrain_corrections_df: pd.DataFrame,
    zip_code_centroids: pd.DataFrame,
    hrrr_loader: Optional[HRRRLoader] = None,
    hrrr_source: str = "s3",
) -> pd.DataFrame:
    """
    Orchestrate the hourly microclimate pipeline.

    Loads HRRR hourly data for a date range, processes each hour independently,
    applies terrain corrections, and produces hourly safety cubes.

    Parameters
    ----------
    region_name : str
        Region name (e.g., "region_1")
    start_date : str
        ISO 8601 start date (YYYY-MM-DD)
    end_date : str
        ISO 8601 end date (YYYY-MM-DD)
    terrain_corrections_df : pd.DataFrame
        Terrain corrections from normals mode with columns:
        - zip_code
        - z0_m, albedo, emissivity, nlcd_dominant_class
        - wind_shear_correction_sfc_kt, water_cooling_sfc_f
    zip_code_centroids : pd.DataFrame
        ZIP code centroids with columns: zip_code, lat, lon
    hrrr_loader : HRRRLoader, optional
        HRRR loader instance. If None, creates a new one.
    hrrr_source : str, default "s3"
        HRRR data source ("s3" or "gcs")

    Returns
    -------
    pd.DataFrame
        Hourly microclimate data with columns:
        - datetime_utc (ISO 8601 timestamp with hour precision)
        - zip_code
        - altitude_ft (0, 500, 1000, 3000, 6000, 9000, 12000, 18000)
        - temp_adjusted_f, wind_speed_kt, wind_dir_deg
        - tke_m2s2, wind_shear_kt_per_100ft
        - hourly_hdd, density_altitude_ft, turbulence_flag
    """
    if hrrr_loader is None:
        hrrr_loader = HRRRLoader()

    logger.info(f"Running hourly pipeline for {region_name} from {start_date} to {end_date}")

    # Load PRISM monthly normals for bias correction
    logger.info("Loading PRISM temperature normals for bias correction")
    try:
        prism_annual_hdd, prism_monthly = load_prism_temperature()
    except Exception as e:
        logger.warning(f"Could not load PRISM normals: {e}. Using fallback.")
        prism_monthly = [4500] * 12  # Fallback: ~4500 HDD per month

    # Download/cache HRRR data
    logger.info(f"Downloading HRRR data from {hrrr_source} for {start_date} to {end_date}")
    try:
        hrrr_loader.download_hrrr_range(start_date, end_date, source=hrrr_source)
    except Exception as e:
        logger.warning(f"HRRR download failed: {e}. Attempting to use cached data.")

    # Load hourly HRRR data
    logger.info("Loading hourly HRRR data")
    try:
        hourly_datasets = hrrr_loader.load_hourly_data(
            start_date, end_date, return_hourly=True
        )
    except Exception as e:
        logger.error(f"Failed to load hourly HRRR data: {e}")
        return pd.DataFrame()

    if not hourly_datasets:
        logger.error("No hourly HRRR data available")
        return pd.DataFrame()

    logger.info(f"Loaded {len(hourly_datasets)} hourly HRRR datasets")

    # Process each hour
    all_hourly_data = []

    for i, hour_ds in enumerate(hourly_datasets):
        try:
            # Get month from dataset for PRISM normal
            try:
                hour_dt = pd.Timestamp(hour_ds.time.values[0])
                month = hour_dt.month
                prism_normal_f = prism_monthly[month - 1]
            except Exception:
                prism_normal_f = 4500  # Fallback

            # Compute bias correction (simplified: use monthly normal)
            # In full implementation, would compute HRRR climatology
            surface_bias_correction = 0.0  # Placeholder

            # Process this hour
            hourly_data = process_single_hour(
                hour_ds=hour_ds,
                zip_code_centroids=zip_code_centroids,
                terrain_corrections_df=terrain_corrections_df,
                surface_bias_correction=surface_bias_correction,
            )

            if not hourly_data.empty:
                all_hourly_data.append(hourly_data)

            if (i + 1) % 24 == 0:
                logger.info(f"Processed {i + 1} hours")

        except Exception as e:
            logger.error(f"Error processing hour {i}: {e}", exc_info=True)
            continue

    if not all_hourly_data:
        logger.error("No hourly data produced")
        return pd.DataFrame()

    # Concatenate all hourly data
    hourly_df = pd.concat(all_hourly_data, ignore_index=True)
    logger.info(f"Produced {len(hourly_df)} hourly microclimate rows")

    return hourly_df


def validate_hourly_pipeline_output(hourly_df: pd.DataFrame) -> dict:
    """
    Validate hourly pipeline output.

    Parameters
    ----------
    hourly_df : pd.DataFrame
        Hourly microclimate DataFrame

    Returns
    -------
    dict
        Validation results
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
    ]
    for col in required_cols:
        if col not in hourly_df.columns:
            errors.append(f"Missing required column: {col}")

    # Check that each hour has all 8 altitude levels per ZIP
    if "datetime_utc" in hourly_df.columns and "altitude_ft" in hourly_df.columns:
        for (datetime_utc, zip_code), group in hourly_df.groupby(
            ["datetime_utc", "zip_code"]
        ):
            alt_count = len(group["altitude_ft"].unique())
            if alt_count != 8:
                warnings.append(
                    f"ZIP {zip_code} at {datetime_utc} has {alt_count} altitudes (expected 8)"
                )

    # Check hourly HDD values
    if "hourly_hdd" in hourly_df.columns:
        hdd_max = hourly_df["hourly_hdd"].max()
        if hdd_max > 2.5:
            warnings.append(f"Hourly HDD max unusually high: {hdd_max}")

    passed = len(errors) == 0

    return {
        "passed": passed,
        "warnings": warnings,
        "errors": errors,
    }
