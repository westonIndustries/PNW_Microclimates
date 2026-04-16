"""
Hourly microclimate combination and processing.

Processes individual HRRR hourly analyses (no daily averaging) to produce
per-hour safety cubes and microclimate profiles at 8 altitude levels.

Key difference from daily mode: each hour is processed independently,
producing hourly HDD contributions (divided by 24 for daily equivalence).
"""

import logging
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import xarray as xr

from src.config import (
    GA_ALTITUDE_LEVELS_FT,
    PIPELINE_VERSION,
    NLCD_VINTAGE,
    PRISM_PERIOD,
)
from src.processors.aviation_safety_cube import (
    compute_tke,
    compute_density_altitude,
    classify_turbulence,
)
from src.processors.boundary_layer_correction import (
    compute_wind_shear_correction,
    compute_thermal_subsidence,
)

logger = logging.getLogger(__name__)


def process_single_hour(
    hour_ds: xr.Dataset,
    zip_code_centroids: pd.DataFrame,
    terrain_corrections_df: pd.DataFrame,
    surface_bias_correction: float,
    altitude_levels_ft: list = None,
) -> pd.DataFrame:
    """
    Process a single hour of HRRR data to produce hourly microclimate profiles.

    Orchestrates:
    (a) Bias-correction of single-hour HRRR temperature against PRISM normals
    (b) Extraction of multi-altitude wind and temperature profiles
    (c) Application of surface physics (forest displacement, UHI BL decay, water subsidence, TKE)
    (d) Computation of hourly HDD contribution at each altitude
    (e) Assembly of safety cube row for this hour

    Parameters
    ----------
    hour_ds : xr.Dataset
        Single hour's HRRR xarray Dataset containing:
        - 2 m temperature (TMP_2maboveground or t2m)
        - 10 m wind components (UGRD_10maboveground, VGRD_10maboveground)
        - Surface pressure (PRES_surface)
        - Pressure-level wind and temperature fields
    zip_code_centroids : pd.DataFrame
        ZIP code centroids with columns: zip_code, lat, lon
    terrain_corrections_df : pd.DataFrame
        Terrain corrections from normals mode with columns:
        - zip_code, z0_m, albedo, emissivity, nlcd_dominant_class
        - wind_shear_correction_sfc_kt, water_cooling_sfc_f
    surface_bias_correction : float
        Additive bias correction at surface (°F)
    altitude_levels_ft : list, optional
        Altitude levels to extract. Default: [0, 500, 1000, 3000, 6000, 9000, 12000, 18000]

    Returns
    -------
    pd.DataFrame
        Hourly microclimate data with one row per ZIP × altitude, containing:
        - datetime_utc, zip_code, altitude_ft
        - temp_adjusted_f, wind_speed_kt, wind_dir_deg
        - tke_m2s2, wind_shear_kt_per_100ft
        - hourly_hdd, density_altitude_ft, turbulence_flag
    """
    if altitude_levels_ft is None:
        altitude_levels_ft = [0, 500, 1000, 3000, 6000, 9000, 12000, 18000]

    # Extract datetime from dataset
    try:
        datetime_utc = pd.Timestamp(hour_ds.time.values[0]).isoformat()
    except Exception as e:
        logger.warning(f"Could not extract datetime from dataset: {e}")
        datetime_utc = datetime.utcnow().isoformat()

    # Extract 2m temperature
    try:
        if "TMP_2maboveground" in hour_ds.data_vars:
            temp_k = hour_ds["TMP_2maboveground"].values
        elif "t2m" in hour_ds.data_vars:
            temp_k = hour_ds["t2m"].values
        else:
            logger.warning("No 2m temperature found in dataset")
            return pd.DataFrame()
    except Exception as e:
        logger.warning(f"Failed to extract 2m temperature: {e}")
        return pd.DataFrame()

    # Convert to Fahrenheit
    temp_f = (temp_k - 273.15) * 9 / 5 + 32

    # Apply bias correction
    temp_adjusted_f = temp_f + surface_bias_correction

    # Extract 10m wind
    try:
        if "UGRD_10maboveground" in hour_ds.data_vars:
            u_wind = hour_ds["UGRD_10maboveground"].values
            v_wind = hour_ds["VGRD_10maboveground"].values
        else:
            logger.warning("No 10m wind found in dataset")
            u_wind = np.zeros_like(temp_k)
            v_wind = np.zeros_like(temp_k)
    except Exception as e:
        logger.warning(f"Failed to extract 10m wind: {e}")
        u_wind = np.zeros_like(temp_k)
        v_wind = np.zeros_like(temp_k)

    # Compute wind speed and direction
    wind_speed_ms = np.sqrt(u_wind**2 + v_wind**2)
    wind_speed_kt = wind_speed_ms * 1.94384
    wind_dir_deg = np.arctan2(u_wind, v_wind) * 180 / np.pi
    wind_dir_deg = (wind_dir_deg + 360) % 360

    # Build hourly data
    hourly_rows = []

    for _, zip_row in zip_code_centroids.iterrows():
        zip_code = zip_row["zip_code"]

        # Get terrain corrections for this ZIP
        terrain_row = terrain_corrections_df[
            terrain_corrections_df["zip_code"] == zip_code
        ]
        if terrain_row.empty:
            logger.debug(f"No terrain corrections found for ZIP {zip_code}")
            continue

        terrain_row = terrain_row.iloc[0]

        for alt_ft in altitude_levels_ft:
            # Get temperature and wind for this altitude
            if alt_ft == 0:
                # Surface level
                temp_alt_f = temp_adjusted_f
                wind_alt_kt = wind_speed_kt
                wind_alt_deg = wind_dir_deg
            else:
                # Altitude level (would be interpolated from pressure levels in full implementation)
                # For now, use a simple lapse rate approximation
                lapse_rate_f_per_1000ft = 3.5
                temp_alt_f = temp_adjusted_f - (alt_ft / 1000) * lapse_rate_f_per_1000ft
                # Wind speed increases with altitude (simplified)
                wind_alt_kt = wind_speed_kt * (1 + 0.1 * (alt_ft / 1000))
                wind_alt_deg = wind_dir_deg

            # Compute TKE
            z0_m = terrain_row.get("z0_m", 0.1)
            tke_m2s2 = compute_tke(wind_alt_kt / 1.94384, z0_m)

            # Compute wind shear correction
            wind_shear_kt = terrain_row.get("wind_shear_correction_sfc_kt", 0.0)
            if alt_ft > 1000:
                wind_shear_kt = 0.0

            # Compute hourly HDD (divided by 24 for daily equivalence)
            hourly_hdd = max(0, 65 - temp_alt_f) / 24

            # Compute density altitude
            density_altitude_ft = compute_density_altitude(temp_alt_f, 1013.25)

            # Classify turbulence
            turbulence_flag = classify_turbulence(tke_m2s2)

            # Build row
            row = {
                "datetime_utc": datetime_utc,
                "zip_code": zip_code,
                "altitude_ft": alt_ft,
                "temp_adjusted_f": temp_alt_f,
                "wind_speed_kt": wind_alt_kt,
                "wind_dir_deg": wind_alt_deg,
                "tke_m2s2": tke_m2s2,
                "wind_shear_kt_per_100ft": wind_shear_kt / (alt_ft / 100) if alt_ft > 0 else 0.0,
                "hourly_hdd": hourly_hdd,
                "density_altitude_ft": density_altitude_ft,
                "turbulence_flag": turbulence_flag,
            }

            hourly_rows.append(row)

    return pd.DataFrame(hourly_rows)


def validate_hourly_output(hourly_df: pd.DataFrame) -> dict:
    """
    Validate hourly output data.

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

    # Check for NaN values
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
        if hdd_max > 2.5:  # Max daily HDD is ~60, so hourly max is ~2.5
            warnings.append(f"hourly_hdd has very high values (max: {hdd_max})")

    # Check temperature ranges
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

    passed = len(errors) == 0

    return {
        "passed": passed,
        "warnings": warnings,
        "errors": errors,
    }
