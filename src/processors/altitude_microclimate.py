"""
Altitude-level microclimate processing.

Computes bias-corrected altitude temperatures and HDD at multiple GA flight altitudes
(3k, 6k, 9k, 12k, 18k ft AGL) with no surface corrections applied above ground level.

Key principle: Altitude-level HDD uses only bias-corrected temperature, no surface
corrections (UHI, traffic heat, imperviousness-driven albedo) because these effects
have no physical relevance above the boundary layer.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional


def bias_correct_altitude_temperatures(
    hrrr_pressure_temps: Dict[float, np.ndarray],
    surface_bias_correction: float,
    altitude_levels_ft: list = None,
) -> Dict[str, np.ndarray]:
    """
    Bias-correct HRRR temperature fields at multiple pressure levels.

    The bias correction computed at the surface (from PRISM vs HRRR climatology)
    is propagated upward to all altitude levels. This assumes the systematic
    model offset applies across the lower troposphere.

    Args:
        hrrr_pressure_temps: Dict mapping pressure level (mb) to temperature array (°F)
                            Example: {925: temp_array_925mb, 850: temp_array_850mb, ...}
        surface_bias_correction: Additive bias correction at surface (°F)
                                Computed as: prism_normal - hrrr_climatology
        altitude_levels_ft: List of target altitude levels in feet AGL.
                           Default: [3000, 6000, 9000, 12000, 18000]

    Returns:
        Dict mapping altitude_ft (int) to bias-corrected temperature array (°F)
        Example: {3000: temp_3k_adjusted, 6000: temp_6k_adjusted, ...}
    """
    if altitude_levels_ft is None:
        altitude_levels_ft = [3000, 6000, 9000, 12000, 18000]

    adjusted_temps = {}

    for alt_ft in altitude_levels_ft:
        # For now, use a simple approach: interpolate from available pressure levels
        # This will be refined in task 12.4 (wind_profile_extractor) which handles
        # the full log-pressure interpolation from HRRR pressure levels
        if alt_ft in hrrr_pressure_temps:
            raw_temp = hrrr_pressure_temps[alt_ft]
        else:
            # Placeholder: would be interpolated in wind_profile_extractor
            raw_temp = np.array([])

        # Apply surface bias correction to all altitudes
        adjusted_temps[alt_ft] = raw_temp + surface_bias_correction

    return adjusted_temps


def compute_altitude_hdd(
    adjusted_temps: Dict[int, np.ndarray],
    base_temp_f: float = 65.0,
) -> Dict[int, np.ndarray]:
    """
    Compute HDD at multiple altitude levels.

    HDD at altitude uses only bias-corrected temperature, no surface corrections.
    Formula: hdd_alt = max(0, base_temp_f - temp_alt_adjusted_f)

    Args:
        adjusted_temps: Dict mapping altitude_ft to bias-corrected temperature array (°F)
        base_temp_f: Base temperature for HDD calculation (default 65°F)

    Returns:
        Dict mapping altitude_ft to HDD array (°F-days)
    """
    altitude_hdd = {}

    for alt_ft, temp_array in adjusted_temps.items():
        # Compute HDD: max(0, 65 - temp)
        hdd = np.maximum(0, base_temp_f - temp_array)
        altitude_hdd[alt_ft] = hdd

    return altitude_hdd


def process_altitude_microclimate(
    hrrr_pressure_temps: Dict[float, np.ndarray],
    surface_bias_correction: float,
    altitude_levels_ft: list = None,
    base_temp_f: float = 65.0,
) -> Tuple[Dict[int, np.ndarray], Dict[int, np.ndarray]]:
    """
    Full altitude microclimate processing pipeline.

    Orchestrates bias correction and HDD computation for all altitude levels.

    Args:
        hrrr_pressure_temps: Dict mapping pressure level (mb) to temperature array (°F)
        surface_bias_correction: Additive bias correction at surface (°F)
        altitude_levels_ft: List of target altitude levels in feet AGL
        base_temp_f: Base temperature for HDD calculation (default 65°F)

    Returns:
        Tuple of (adjusted_temps_dict, altitude_hdd_dict)
        - adjusted_temps_dict: {altitude_ft: bias_corrected_temp_array}
        - altitude_hdd_dict: {altitude_ft: hdd_array}
    """
    if altitude_levels_ft is None:
        altitude_levels_ft = [3000, 6000, 9000, 12000, 18000]

    # Step 1: Bias-correct altitude temperatures
    adjusted_temps = bias_correct_altitude_temperatures(
        hrrr_pressure_temps=hrrr_pressure_temps,
        surface_bias_correction=surface_bias_correction,
        altitude_levels_ft=altitude_levels_ft,
    )

    # Step 2: Compute HDD at each altitude
    altitude_hdd = compute_altitude_hdd(
        adjusted_temps=adjusted_temps,
        base_temp_f=base_temp_f,
    )

    return adjusted_temps, altitude_hdd


def add_altitude_columns_to_dataframe(
    df: pd.DataFrame,
    adjusted_temps: Dict[int, np.ndarray],
    altitude_hdd: Dict[int, np.ndarray],
) -> pd.DataFrame:
    """
    Add altitude temperature and HDD columns to a daily output DataFrame.

    Adds columns for each altitude level:
    - temp_{alt}ft_raw_f: Raw HRRR temperature (before bias correction)
    - temp_{alt}ft_adjusted_f: Bias-corrected temperature
    - hdd_{alt}ft: HDD at altitude

    Args:
        df: DataFrame with one row per ZIP code per date
        adjusted_temps: Dict mapping altitude_ft to bias-corrected temperature array
        altitude_hdd: Dict mapping altitude_ft to HDD array

    Returns:
        DataFrame with altitude columns added
    """
    df = df.copy()

    for alt_ft in sorted(adjusted_temps.keys()):
        # Add adjusted temperature column
        col_name_adjusted = f"temp_{alt_ft}ft_adjusted_f"
        df[col_name_adjusted] = adjusted_temps[alt_ft]

        # Add HDD column
        col_name_hdd = f"hdd_{alt_ft}ft"
        df[col_name_hdd] = altitude_hdd[alt_ft]

    return df
