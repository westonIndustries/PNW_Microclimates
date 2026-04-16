"""
Daily microclimate combination and orchestration.

Orchestrates the daily pipeline: load HRRR → bias correct → extract wind profiles
→ combine with terrain corrections → compute daily effective HDD per ZIP code.

Produces daily effective HDD and multi-altitude wind/temperature profiles.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import xarray as xr

from src.config import (
    GA_ALTITUDE_LEVELS_FT,
    HRRR_MIN_CLIM_YEARS,
    PIPELINE_VERSION,
    NLCD_VINTAGE,
    PRISM_PERIOD,
)
from src.loaders.load_hrrr import HRRRLoader
from src.loaders.load_prism_temperature import load_prism_temperature
from src.processors.bias_correct_hrrr import bias_correct
from src.processors.wind_profile_extractor import extract_wind_profiles
from src.processors.boundary_layer_correction import (
    compute_wind_shear_correction,
    compute_thermal_subsidence,
)
from src.processors.aviation_safety_cube import build_safety_cube

logger = logging.getLogger(__name__)


def compute_daily_effective_hdd(
    hrrr_adjusted_temp_f: float,
    terrain_multiplier: float,
    elevation_hdd_addition: float,
    uhi_hdd_reduction: float,
    traffic_hdd_reduction: float,
) -> float:
    """
    Compute daily effective HDD for a ZIP code.

    Formula:
        daily_effective_hdd = max(0, 65 - hrrr_adjusted_temp_f) × terrain_mult
                            + elevation_hdd_addition
                            - uhi_hdd_reduction
                            - traffic_hdd_reduction

    Parameters
    ----------
    hrrr_adjusted_temp_f : float
        Bias-corrected HRRR daily mean temperature (°F)
    terrain_multiplier : float
        Terrain position multiplier (from normals mode)
    elevation_hdd_addition : float
        HDD addition from elevation lapse rate (°F-days)
    uhi_hdd_reduction : float
        HDD reduction from UHI effect (°F-days)
    traffic_hdd_reduction : float
        HDD reduction from traffic heat (°F-days)

    Returns
    -------
    float
        Daily effective HDD (°F-days)
    """
    base_hdd = max(0, 65 - hrrr_adjusted_temp_f)
    daily_hdd = (
        base_hdd * terrain_multiplier
        + elevation_hdd_addition
        - uhi_hdd_reduction
        - traffic_hdd_reduction
    )
    return max(0, daily_hdd)


def compute_altitude_hdd(temp_adjusted_f: float) -> float:
    """
    Compute HDD at altitude (no surface corrections).

    Formula:
        hdd_altitude = max(0, 65 - temp_adjusted_f)

    Parameters
    ----------
    temp_adjusted_f : float
        Bias-corrected temperature at altitude (°F)

    Returns
    -------
    float
        HDD at altitude (°F-days)
    """
    return max(0, 65 - temp_adjusted_f)


def apply_boundary_layer_corrections(
    temp_adjusted_f: float,
    wind_speed_ms: float,
    z_agl_ft: float,
    z0_local: float = 0.1,
    z0_upwind: float = 0.03,
    is_water: bool = False,
) -> Tuple[float, float]:
    """
    Apply boundary layer corrections (wind shear and thermal subsidence) at ≤ 1,000 ft AGL.

    Parameters
    ----------
    temp_adjusted_f : float
        Bias-corrected temperature (°F)
    wind_speed_ms : float
        Wind speed (m/s)
    z_agl_ft : float
        Altitude above ground level (feet)
    z0_local : float, default 0.1
        Local roughness length (meters)
    z0_upwind : float, default 0.03
        Upwind roughness length (meters)
    is_water : bool, default False
        Whether the pixel is water

    Returns
    -------
    Tuple[float, float]
        (corrected_temp_f, wind_shear_correction_kt)
    """
    # Apply thermal subsidence correction (cooling over water)
    temp_anomaly = 5.0  # Typical land-water temperature difference (°F)
    thermal_correction = compute_thermal_subsidence(
        temp_anomaly, z_agl_ft, is_water
    )
    temp_corrected = temp_adjusted_f + thermal_correction

    # Apply wind shear correction (at roughness transitions)
    u_star = wind_speed_ms * 0.41 / np.log(10.0 / z0_upwind) if z0_upwind > 0 else 0
    wind_shear_correction = compute_wind_shear_correction(
        wind_speed_ms, z_agl_ft, z0_local, z0_upwind, u_star
    )

    return temp_corrected, wind_shear_correction


def run_daily_pipeline(
    region_name: str,
    start_date: str,
    end_date: str,
    terrain_corrections_df: pd.DataFrame,
    zip_code_centroids: pd.DataFrame,
    hrrr_loader: Optional[HRRRLoader] = None,
    hrrr_source: str = "s3",
    build_safety_cube_flag: bool = False,
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """
    Orchestrate the daily microclimate pipeline.

    Loads HRRR data for a date range, bias-corrects against PRISM,
    extracts wind profiles, applies terrain corrections, and computes
    daily effective HDD per ZIP code. Optionally builds a 3D aviation
    safety cube.

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
        - terrain_multiplier
        - elevation_hdd_addition
        - uhi_hdd_reduction
        - traffic_hdd_reduction
    zip_code_centroids : pd.DataFrame
        ZIP code centroids with columns: zip_code, lat, lon
    hrrr_loader : HRRRLoader, optional
        HRRR loader instance. If None, creates a new one.
    hrrr_source : str, default "s3"
        HRRR data source ("s3" or "gcs")
    build_safety_cube_flag : bool, default False
        If True, also build and return a 3D aviation safety cube

    Returns
    -------
    Tuple[pd.DataFrame, Optional[pd.DataFrame]]
        (daily_data, safety_cube) where:
        - daily_data: Daily microclimate data with columns:
          - date (ISO 8601)
          - zip_code
          - hrrr_raw_temp_f, hrrr_adjusted_temp_f, bias_correction_f
          - daily_effective_hdd, terrain_multiplier
          - wind_speed_sfc_kt, wind_dir_sfc_deg (and for each altitude)
          - temp_sfc_raw_f, temp_sfc_adjusted_f, hdd_sfc
          - temp_{alt}_raw_f, temp_{alt}_adjusted_f, hdd_{alt} (for each altitude)
          - run_date, pipeline_version, nlcd_vintage, prism_period
        - safety_cube: 3D cube (ZIP × date × altitude) if build_safety_cube_flag=True,
          else None
    """
    if hrrr_loader is None:
        hrrr_loader = HRRRLoader()

    # Parse dates
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # Load PRISM monthly normals for bias correction
    logger.info("Loading PRISM temperature normals for bias correction")
    prism_annual_hdd, prism_monthly = load_prism_temperature()

    # Download/cache HRRR data
    logger.info(f"Downloading HRRR data from {hrrr_source} for {start_date} to {end_date}")
    hrrr_loader.download_hrrr_range(start_date, end_date, source=hrrr_source)

    # Process each day
    all_results = []
    current_dt = start_dt

    while current_dt <= end_dt:
        date_str = current_dt.strftime("%Y-%m-%d")
        logger.info(f"Processing {date_str}")

        try:
            # Load hourly HRRR data for this day
            hourly_datasets = hrrr_loader.load_hourly_data(
                date_str, date_str, return_hourly=True
            )

            if not hourly_datasets:
                logger.warning(f"No HRRR data found for {date_str}")
                current_dt += timedelta(days=1)
                continue

            # Compute daily mean temperature
            temp_arrays = []
            for ds in hourly_datasets:
                if "TMP_2maboveground" in ds.data_vars:
                    temp = ds["TMP_2maboveground"].values
                elif "t2m" in ds.data_vars:
                    temp = ds["t2m"].values
                else:
                    continue
                temp_arrays.append(temp)

            if not temp_arrays:
                logger.warning(f"No 2m temperature data for {date_str}")
                current_dt += timedelta(days=1)
                continue

            hrrr_daily_temp_k = np.mean(temp_arrays, axis=0)
            hrrr_daily_temp_f = (hrrr_daily_temp_k - 273.15) * 9 / 5 + 32

            # Get HRRR climatology for this month
            month = current_dt.month
            try:
                hrrr_climatology = hrrr_loader.get_hrrr_climatology(month)
                hrrr_climatology_f = (hrrr_climatology - 273.15) * 9 / 5 + 32
            except ValueError:
                logger.warning(
                    f"Could not compute HRRR climatology for month {month}. "
                    f"Using raw HRRR mean as fallback."
                )
                hrrr_climatology_f = hrrr_daily_temp_f

            # Get PRISM normal for this month
            prism_normal_f = prism_monthly[month - 1]  # 0-indexed

            # Bias correction
            bias_correction_f = prism_normal_f - hrrr_climatology_f
            hrrr_adjusted_temp_f = hrrr_daily_temp_f + bias_correction_f

            # Extract wind profiles
            logger.debug(f"Extracting wind profiles for {date_str}")
            wind_profiles = extract_wind_profiles(
                hourly_datasets[0],  # Use first hour's dataset for structure
                zip_code_centroids,
            )

            # Combine with terrain corrections
            logger.debug(f"Combining with terrain corrections for {date_str}")
            daily_data = []

            for _, zip_row in zip_code_centroids.iterrows():
                zip_code = zip_row["zip_code"]

                # Get terrain corrections for this ZIP
                terrain_row = terrain_corrections_df[
                    terrain_corrections_df["zip_code"] == zip_code
                ]
                if terrain_row.empty:
                    logger.warning(f"No terrain corrections found for ZIP {zip_code}")
                    continue

                terrain_row = terrain_row.iloc[0]

                # Compute daily effective HDD
                daily_hdd = compute_daily_effective_hdd(
                    hrrr_adjusted_temp_f,
                    terrain_row.get("terrain_multiplier", 1.0),
                    terrain_row.get("elevation_hdd_addition", 0.0),
                    terrain_row.get("uhi_hdd_reduction", 0.0),
                    terrain_row.get("traffic_hdd_reduction", 0.0),
                )

                # Get wind profile for this ZIP
                zip_wind = wind_profiles[wind_profiles["zip_code"] == zip_code]

                # Build row
                row = {
                    "date": date_str,
                    "zip_code": zip_code,
                    "hrrr_raw_temp_f": hrrr_daily_temp_f,
                    "hrrr_adjusted_temp_f": hrrr_adjusted_temp_f,
                    "bias_correction_f": bias_correction_f,
                    "daily_effective_hdd": daily_hdd,
                    "terrain_multiplier": terrain_row.get("terrain_multiplier", 1.0),
                    "run_date": datetime.utcnow().isoformat(),
                    "pipeline_version": PIPELINE_VERSION,
                    "nlcd_vintage": NLCD_VINTAGE,
                    "prism_period": PRISM_PERIOD,
                    # Surface properties (from terrain corrections)
                    "z0_m": terrain_row.get("z0_m", 0.1),
                    "albedo": terrain_row.get("surface_albedo", 0.15),
                    "emissivity": terrain_row.get("emissivity", 0.95),
                    "roughness_transition_pct": terrain_row.get(
                        "roughness_transition_pct", 0.0
                    ),
                    "nlcd_dominant_class": terrain_row.get("nlcd_dominant_class", 0),
                    "wind_shear_correction_sfc_kt": 0.0,  # Will be computed per altitude
                    "water_cooling_sfc_f": 0.0,  # Will be computed per altitude
                }

                # Add wind profile data
                for _, wind_row in zip_wind.iterrows():
                    alt_ft = int(wind_row["altitude_ft"])
                    if alt_ft == 0:
                        row["wind_speed_sfc_kt"] = wind_row["wind_speed_ms"] * 1.94384
                        row["wind_dir_sfc_deg"] = wind_row["wind_direction_deg"]
                        row["temp_sfc_raw_f"] = hrrr_daily_temp_f
                        row["temp_sfc_adjusted_f"] = hrrr_adjusted_temp_f
                        row["hdd_sfc"] = daily_hdd
                    else:
                        # Altitude level
                        temp_adjusted_f = (
                            wind_row["temperature_f"] + bias_correction_f
                        )
                        hdd_alt = compute_altitude_hdd(temp_adjusted_f)

                        row[f"wind_speed_{alt_ft}ft_kt"] = (
                            wind_row["wind_speed_ms"] * 1.94384
                        )
                        row[f"wind_dir_{alt_ft}ft_deg"] = wind_row["wind_direction_deg"]
                        row[f"temp_{alt_ft}ft_raw_f"] = wind_row["temperature_f"]
                        row[f"temp_{alt_ft}ft_adjusted_f"] = temp_adjusted_f
                        row[f"hdd_{alt_ft}ft"] = hdd_alt

                daily_data.append(row)

            all_results.extend(daily_data)

        except Exception as e:
            logger.error(f"Error processing {date_str}: {e}", exc_info=True)

        current_dt += timedelta(days=1)

    daily_df = pd.DataFrame(all_results)

    # Build safety cube if requested
    safety_cube_df = None
    if build_safety_cube_flag:
        logger.info("Building aviation safety cube")
        safety_cube_df = build_safety_cube(daily_df)
        logger.info(f"Built safety cube with {len(safety_cube_df)} rows")

    return daily_df, safety_cube_df
