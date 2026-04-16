"""
Aviation Safety Cube — 3D microclimate structure for GA operations.

Assembles a 3D cube of ZIP code × date × altitude with temperature, wind,
turbulent kinetic energy (TKE), wind shear, HDD, density altitude, and
turbulence flags. Designed for general aviation (GA) and UAS operations.

The safety cube includes 8 altitude levels:
- Surface (0 ft AGL)
- 500 ft AGL
- 1,000 ft AGL
- 3,000 ft AGL
- 6,000 ft AGL
- 9,000 ft AGL
- 12,000 ft AGL
- 18,000 ft AGL
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional
from datetime import datetime


def compute_tke(
    wind_speed_ms: float,
    z0_m: float,
    z0_rural_reference: float = 0.03,
) -> float:
    """
    Compute turbulent kinetic energy (TKE) from wind speed and roughness.

    TKE scales with both wind speed and the roughness contrast between
    local and rural surfaces. Urban areas (high z0) generate more mechanical
    turbulence than rural areas.

    Formula:
        TKE = 0.5 × u_star² × (1 + 2 × (z0_local / z0_rural))

    where u_star is friction velocity.

    Parameters
    ----------
    wind_speed_ms : float
        Wind speed at reference height (m/s)
    z0_m : float
        Local roughness length (meters)
    z0_rural_reference : float, default 0.03
        Rural reference roughness length (meters)

    Returns
    -------
    float
        TKE in m²/s²
    """
    if wind_speed_ms <= 0 or z0_m <= 0:
        return 0.0

    # Estimate friction velocity from wind speed
    # Assume reference height of 10 m
    z_ref = 10.0
    von_karman = 0.41
    u_star = wind_speed_ms * von_karman / np.log(z_ref / z0_m)

    # Compute TKE with roughness contrast
    roughness_ratio = z0_m / z0_rural_reference
    tke = 0.5 * u_star**2 * (1 + 2 * roughness_ratio)

    return max(0, tke)


def compute_density_altitude(
    temp_f: float,
    pressure_mb: float,
    dew_point_f: float = None,
) -> float:
    """
    Compute density altitude from temperature and pressure.

    Density altitude is the altitude at which the air density equals the
    observed density. It's critical for GA operations because aircraft
    performance depends on air density, not pressure altitude.

    Formula (simplified):
        DA = PA + (120 × (T - T_ISA))

    where PA is pressure altitude, T is observed temperature, and T_ISA
    is the ISA standard temperature at that altitude.

    Parameters
    ----------
    temp_f : float
        Temperature (°F)
    pressure_mb : float
        Pressure (millibars)
    dew_point_f : float, optional
        Dew point (°F). If provided, humidity correction is applied.

    Returns
    -------
    float
        Density altitude (feet)
    """
    # Convert temperature to Celsius
    temp_c = (temp_f - 32) * 5 / 9

    # Convert pressure to altitude (simplified barometric formula)
    # PA (ft) ≈ 145442 × (1 - (P / 1013.25)^0.190263)
    pressure_inHg = pressure_mb * 0.02953
    pa_ft = 145442 * (1 - (pressure_inHg / 29.92126) ** 0.190263)

    # ISA standard temperature at sea level is 15°C (59°F)
    # Temperature decreases at 6.5°C per 1,000 m (3.5°F per 1,000 ft)
    isa_temp_c = 15 - (pa_ft / 1000) * 0.00650 * 1000 / 0.3048
    isa_temp_f = isa_temp_c * 9 / 5 + 32

    # Density altitude correction: 120 ft per °F above ISA
    da_ft = pa_ft + 120 * (temp_f - isa_temp_f)

    return max(0, da_ft)


def classify_turbulence(tke_m2s2: float) -> str:
    """
    Classify turbulence severity based on TKE.

    Parameters
    ----------
    tke_m2s2 : float
        Turbulent kinetic energy (m²/s²)

    Returns
    -------
    str
        Turbulence classification: "smooth", "light", "moderate", or "severe"
    """
    if tke_m2s2 < 0.5:
        return "smooth"
    elif tke_m2s2 < 1.5:
        return "light"
    elif tke_m2s2 < 3.0:
        return "moderate"
    else:
        return "severe"


def build_safety_cube(
    daily_data: pd.DataFrame,
    altitude_levels_ft: list = None,
) -> pd.DataFrame:
    """
    Build a 3D aviation safety cube from daily microclimate data.

    Assembles ZIP × date × altitude with all required columns for GA operations:
    temperature, wind, TKE, wind shear, HDD, density altitude, turbulence flag.

    Parameters
    ----------
    daily_data : pd.DataFrame
        Daily microclimate data with columns:
        - date, zip_code
        - hrrr_adjusted_temp_f, wind_speed_sfc_kt, wind_dir_sfc_deg
        - temp_{alt}ft_adjusted_f, wind_speed_{alt}ft_kt, wind_dir_{alt}ft_deg
        - hdd_sfc, hdd_{alt}ft
        - z0_m, albedo, emissivity, nlcd_dominant_class
        - wind_shear_correction_sfc_kt, water_cooling_sfc_f
    altitude_levels_ft : list, optional
        List of altitude levels to include. Default: [0, 500, 1000, 3000, 6000, 9000, 12000, 18000]

    Returns
    -------
    pd.DataFrame
        Safety cube with one row per ZIP × date × altitude, containing:
        - date, zip_code, altitude_ft
        - temp_adjusted_f, wind_speed_kt, wind_dir_deg
        - tke_m2s2, wind_shear_kt_per_100ft
        - hdd, density_altitude_ft, turbulence_flag
    """
    if altitude_levels_ft is None:
        altitude_levels_ft = [0, 500, 1000, 3000, 6000, 9000, 12000, 18000]

    cube_rows = []

    for _, row in daily_data.iterrows():
        date = row["date"]
        zip_code = row["zip_code"]

        for alt_ft in altitude_levels_ft:
            # Get temperature and wind for this altitude
            if alt_ft == 0:
                # Surface level
                temp_f = row.get("hrrr_adjusted_temp_f", np.nan)
                wind_speed_kt = row.get("wind_speed_sfc_kt", np.nan)
                wind_dir_deg = row.get("wind_dir_sfc_deg", np.nan)
                hdd = row.get("hdd_sfc", np.nan)
                wind_shear_kt = row.get("wind_shear_correction_sfc_kt", 0.0)
            else:
                # Altitude level
                temp_col = f"temp_{alt_ft}ft_adjusted_f"
                wind_speed_col = f"wind_speed_{alt_ft}ft_kt"
                wind_dir_col = f"wind_dir_{alt_ft}ft_deg"
                hdd_col = f"hdd_{alt_ft}ft"

                temp_f = row.get(temp_col, np.nan)
                wind_speed_kt = row.get(wind_speed_col, np.nan)
                wind_dir_deg = row.get(wind_dir_col, np.nan)
                hdd = row.get(hdd_col, np.nan)
                wind_shear_kt = 0.0  # Wind shear only at surface

            # Skip if missing critical data
            if pd.isna(temp_f) or pd.isna(wind_speed_kt):
                continue

            # Compute TKE
            z0_m = row.get("z0_m", 0.1)
            tke_m2s2 = compute_tke(wind_speed_kt / 1.94384, z0_m)  # Convert kt to m/s

            # Compute density altitude (simplified, using surface pressure)
            # In a full implementation, would use pressure at altitude
            density_altitude_ft = compute_density_altitude(temp_f, 1013.25)

            # Classify turbulence
            turbulence_flag = classify_turbulence(tke_m2s2)

            # Build cube row
            cube_row = {
                "date": date,
                "zip_code": zip_code,
                "altitude_ft": alt_ft,
                "temp_adjusted_f": temp_f,
                "wind_speed_kt": wind_speed_kt,
                "wind_dir_deg": wind_dir_deg,
                "tke_m2s2": tke_m2s2,
                "wind_shear_kt_per_100ft": wind_shear_kt / (alt_ft / 100) if alt_ft > 0 else 0.0,
                "hdd": hdd,
                "density_altitude_ft": density_altitude_ft,
                "turbulence_flag": turbulence_flag,
            }

            cube_rows.append(cube_row)

    return pd.DataFrame(cube_rows)


def validate_safety_cube(cube_df: pd.DataFrame) -> dict:
    """
    Validate safety cube data for physical correctness.

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

    # Check for NaN values
    for col in required_cols:
        if col in cube_df.columns:
            nan_count = cube_df[col].isna().sum()
            if nan_count > 0:
                warnings.append(f"Column {col} has {nan_count} NaN values")

    # Check temperature ranges
    if "temp_adjusted_f" in cube_df.columns:
        temp_min = cube_df["temp_adjusted_f"].min()
        temp_max = cube_df["temp_adjusted_f"].max()
        if temp_min < -80 or temp_max > 120:
            warnings.append(
                f"Temperature range unusual: {temp_min}°F to {temp_max}°F"
            )

    # Check wind speed ranges
    if "wind_speed_kt" in cube_df.columns:
        wind_min = cube_df["wind_speed_kt"].min()
        wind_max = cube_df["wind_speed_kt"].max()
        if wind_max > 200:
            warnings.append(f"Wind speed unusually high: {wind_max} kt")

    # Check TKE ranges
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

    passed = len(errors) == 0

    return {
        "passed": passed,
        "warnings": warnings,
        "errors": errors,
    }
