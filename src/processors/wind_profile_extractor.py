"""
Wind profile extraction from HRRR pressure-level data.

Extracts wind speed and direction at 6 General Aviation (GA) altitude levels
by interpolating HRRR pressure-level wind fields in log-pressure space.
Also extracts temperature at each altitude for HDD computation.

Assigns extracted profiles to ZIP codes by nearest grid cell.
"""

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import xarray as xr
from scipy.interpolate import interp1d

from src.config import (
    GA_ALTITUDE_LEVELS_FT,
    HRRR_PRESSURE_LEVELS_MB,
)

logger = logging.getLogger(__name__)

# Standard atmosphere constants
GRAVITY_MS2 = 9.81
GAS_CONSTANT_JKG = 287.05
TEMP_LAPSE_RATE_KM = 0.0065  # K/m


def pressure_to_altitude_hypsometric(
    pressure_mb: float,
    surface_pressure_mb: float,
    surface_temp_k: float,
) -> float:
    """
    Convert pressure to altitude AGL using hypsometric equation.

    Accounts for day-to-day atmospheric density variations using
    surface pressure and temperature from HRRR.

    Parameters
    ----------
    pressure_mb : float
        Pressure level in millibars
    surface_pressure_mb : float
        Surface pressure from HRRR (mb)
    surface_temp_k : float
        Surface (2m) temperature from HRRR (Kelvin)

    Returns
    -------
    float
        Altitude in feet AGL
    """
    if pressure_mb >= surface_pressure_mb:
        return 0.0

    # Hypsometric equation: z = (T0 / L) * ln(P0 / P)
    # where T0 is surface temp, L is lapse rate, P0/P are pressures
    # Simplified form for small height differences:
    # z (m) = (R * T_mean / g) * ln(P0 / P)

    # Mean temperature between surface and pressure level
    # Using standard lapse rate as approximation
    height_m = (surface_temp_k / TEMP_LAPSE_RATE_KM) * np.log(
        surface_pressure_mb / pressure_mb
    )

    # Convert to feet
    return height_m * 3.28084


def interpolate_wind_to_altitude(
    u_wind_levels: np.ndarray,
    v_wind_levels: np.ndarray,
    pressure_levels_mb: np.ndarray,
    target_altitude_ft: float,
    surface_pressure_mb: float,
    surface_temp_k: float,
) -> Tuple[float, float]:
    """
    Interpolate U and V wind components to target altitude using log-pressure.

    Performs linear interpolation in log-pressure space, which is more
    physically appropriate for the atmosphere than linear pressure space.

    Parameters
    ----------
    u_wind_levels : np.ndarray
        U-wind component at pressure levels (m/s), shape (n_levels,)
    v_wind_levels : np.ndarray
        V-wind component at pressure levels (m/s), shape (n_levels,)
    pressure_levels_mb : np.ndarray
        Pressure levels (mb), shape (n_levels,), sorted descending (1000 → 500)
    target_altitude_ft : float
        Target altitude AGL (feet)
    surface_pressure_mb : float
        Surface pressure from HRRR (mb)
    surface_temp_k : float
        Surface temperature from HRRR (K)

    Returns
    -------
    Tuple[float, float]
        Interpolated (u_wind, v_wind) at target altitude (m/s)
    """
    # Convert target altitude to pressure using hypsometric equation
    # We need to find the pressure that corresponds to target_altitude_ft
    # This is the inverse of pressure_to_altitude_hypsometric

    # Use binary search or approximation
    # For simplicity, use standard atmosphere approximation:
    # P = P0 * (1 - L*z/T0)^(g/(R*L))
    # where z is in meters

    target_altitude_m = target_altitude_ft / 3.28084

    # Simplified: P/P0 = exp(-g*z / (R*T_mean))
    # Using mean temperature
    mean_temp_k = surface_temp_k - TEMP_LAPSE_RATE_KM * target_altitude_m

    target_pressure_mb = surface_pressure_mb * np.exp(
        -GRAVITY_MS2 * target_altitude_m / (GAS_CONSTANT_JKG * mean_temp_k)
    )

    # Ensure target pressure is within bounds
    target_pressure_mb = np.clip(
        target_pressure_mb,
        pressure_levels_mb.min(),
        pressure_levels_mb.max(),
    )

    # Interpolate in log-pressure space
    log_pressure_levels = np.log(pressure_levels_mb)
    log_target_pressure = np.log(target_pressure_mb)

    # Create interpolators
    u_interp = interp1d(
        log_pressure_levels,
        u_wind_levels,
        kind="linear",
        bounds_error=False,
        fill_value="extrapolate",
    )
    v_interp = interp1d(
        log_pressure_levels,
        v_wind_levels,
        kind="linear",
        bounds_error=False,
        fill_value="extrapolate",
    )

    u_wind = float(u_interp(log_target_pressure))
    v_wind = float(v_interp(log_target_pressure))

    return u_wind, v_wind


def interpolate_temperature_to_altitude(
    temp_levels: np.ndarray,
    pressure_levels_mb: np.ndarray,
    target_altitude_ft: float,
    surface_pressure_mb: float,
    surface_temp_k: float,
) -> float:
    """
    Interpolate temperature to target altitude using log-pressure.

    Parameters
    ----------
    temp_levels : np.ndarray
        Temperature at pressure levels (K), shape (n_levels,)
    pressure_levels_mb : np.ndarray
        Pressure levels (mb), shape (n_levels,), sorted descending
    target_altitude_ft : float
        Target altitude AGL (feet)
    surface_pressure_mb : float
        Surface pressure from HRRR (mb)
    surface_temp_k : float
        Surface temperature from HRRR (K)

    Returns
    -------
    float
        Interpolated temperature at target altitude (K)
    """
    target_altitude_m = target_altitude_ft / 3.28084
    mean_temp_k = surface_temp_k - TEMP_LAPSE_RATE_KM * target_altitude_m
    target_pressure_mb = surface_pressure_mb * np.exp(
        -GRAVITY_MS2 * target_altitude_m / (GAS_CONSTANT_JKG * mean_temp_k)
    )

    target_pressure_mb = np.clip(
        target_pressure_mb,
        pressure_levels_mb.min(),
        pressure_levels_mb.max(),
    )

    log_pressure_levels = np.log(pressure_levels_mb)
    log_target_pressure = np.log(target_pressure_mb)

    temp_interp = interp1d(
        log_pressure_levels,
        temp_levels,
        kind="linear",
        bounds_error=False,
        fill_value="extrapolate",
    )

    temp_k = float(temp_interp(log_target_pressure))
    return temp_k


def wind_speed_direction_from_components(
    u_wind: float,
    v_wind: float,
) -> Tuple[float, float]:
    """
    Compute wind speed and direction from U and V components.

    Parameters
    ----------
    u_wind : float
        U-wind component (m/s, positive east)
    v_wind : float
        V-wind component (m/s, positive north)

    Returns
    -------
    Tuple[float, float]
        (wind_speed_ms, wind_direction_deg)
        Wind direction is in degrees true (0° = north, 90° = east, etc.)
    """
    wind_speed_ms = np.sqrt(u_wind**2 + v_wind**2)

    # Wind direction: atan2(u, v) gives angle from north, clockwise
    wind_direction_deg = np.degrees(np.arctan2(u_wind, v_wind))
    if wind_direction_deg < 0:
        wind_direction_deg += 360.0

    return wind_speed_ms, wind_direction_deg


def extract_wind_profiles(
    hrrr_ds: xr.Dataset,
    zip_code_centroids: pd.DataFrame,
    ga_altitudes_ft: Optional[list] = None,
) -> pd.DataFrame:
    """
    Extract wind speed/direction and temperature at GA altitudes from HRRR.

    Interpolates HRRR pressure-level wind and temperature fields to 6 GA
    altitude levels (surface, 3k, 6k, 9k, 12k, 18k ft AGL) using log-pressure
    interpolation. Assigns profiles to ZIP codes by nearest grid cell.

    Parameters
    ----------
    hrrr_ds : xr.Dataset
        HRRR xarray Dataset containing:
        - 2m temperature (K)
        - 10m U/V wind (m/s)
        - Pressure-level U/V wind (m/s) at multiple levels
        - Surface pressure (Pa)
        - Temperature at pressure levels (K)
    zip_code_centroids : pd.DataFrame
        DataFrame with columns: zip_code, lat, lon (centroid coordinates)
    ga_altitudes_ft : list, optional
        GA altitude levels in feet AGL. Defaults to GA_ALTITUDE_LEVELS_FT.

    Returns
    -------
    pd.DataFrame
        Wind profile data with columns:
        - zip_code
        - altitude_ft
        - wind_speed_ms
        - wind_direction_deg
        - temperature_k
        - temperature_f
        One row per ZIP code per altitude level.
    """
    if ga_altitudes_ft is None:
        ga_altitudes_ft = GA_ALTITUDE_LEVELS_FT

    # Extract HRRR variables
    # Note: Variable names vary by GRIB2 encoding; these are common names
    try:
        temp_2m_k = hrrr_ds["TMP_2maboveground"].values
        u_10m = hrrr_ds["UGRD_10maboveground"].values
        v_10m = hrrr_ds["VGRD_10maboveground"].values
        surface_pressure_pa = hrrr_ds["PRES_surface"].values
    except KeyError:
        # Try alternative variable names
        try:
            temp_2m_k = hrrr_ds["t2m"].values
            u_10m = hrrr_ds["u10m"].values
            v_10m = hrrr_ds["v10m"].values
            surface_pressure_pa = hrrr_ds["sp"].values
        except KeyError as e:
            raise ValueError(
                f"Could not find required HRRR variables in dataset. "
                f"Available variables: {list(hrrr_ds.data_vars)}"
            ) from e

    surface_pressure_mb = surface_pressure_pa / 100.0

    # Extract pressure-level wind and temperature
    # HRRR pressure levels: 1000, 975, 950, 925, 900, 875, 850, 825, 800, 775, 750, 700, 650, 600, 550, 500 mb
    pressure_levels_mb = np.array(HRRR_PRESSURE_LEVELS_MB)

    # Find pressure-level variables in dataset
    # These are typically named like "UGRD_isobaricInhPa" or similar
    u_pressure_vars = [v for v in hrrr_ds.data_vars if "UGRD" in v and "isobaric" in v]
    v_pressure_vars = [v for v in hrrr_ds.data_vars if "VGRD" in v and "isobaric" in v]
    temp_pressure_vars = [v for v in hrrr_ds.data_vars if "TMP" in v and "isobaric" in v]

    if not u_pressure_vars or not v_pressure_vars or not temp_pressure_vars:
        logger.warning(
            "Could not find pressure-level wind/temperature variables. "
            "Available variables: %s",
            list(hrrr_ds.data_vars),
        )
        # Return empty DataFrame with expected columns
        return pd.DataFrame(
            columns=[
                "zip_code",
                "altitude_ft",
                "wind_speed_ms",
                "wind_direction_deg",
                "temperature_k",
                "temperature_f",
            ]
        )

    # Extract pressure-level data
    # Assume first matching variable for each component
    u_pressure = hrrr_ds[u_pressure_vars[0]].values  # shape: (n_levels, y, x)
    v_pressure = hrrr_ds[v_pressure_vars[0]].values
    temp_pressure = hrrr_ds[temp_pressure_vars[0]].values

    # Get grid coordinates
    if "lat" in hrrr_ds.coords:
        lats = hrrr_ds["lat"].values
        lons = hrrr_ds["lon"].values
    elif "y" in hrrr_ds.coords and "x" in hrrr_ds.coords:
        # Assume regular grid; create coordinate arrays
        y_size, x_size = temp_2m_k.shape
        lats = np.linspace(-90, 90, y_size)
        lons = np.linspace(-180, 180, x_size)
    else:
        raise ValueError("Could not determine HRRR grid coordinates")

    # Build results
    results = []

    for _, row in zip_code_centroids.iterrows():
        zip_code = row["zip_code"]
        zip_lat = row["lat"]
        zip_lon = row["lon"]

        # Find nearest grid cell
        lat_idx = np.argmin(np.abs(lats - zip_lat))
        lon_idx = np.argmin(np.abs(lons - zip_lon))

        # Extract surface data for this grid cell
        sfc_temp_k = temp_2m_k[lat_idx, lon_idx]
        sfc_u_wind = u_10m[lat_idx, lon_idx]
        sfc_v_wind = v_10m[lat_idx, lon_idx]
        sfc_pressure_mb = surface_pressure_mb[lat_idx, lon_idx]

        # Surface level (0 ft AGL)
        sfc_speed_ms, sfc_dir_deg = wind_speed_direction_from_components(
            sfc_u_wind, sfc_v_wind
        )
        sfc_temp_f = (sfc_temp_k - 273.15) * 9 / 5 + 32

        results.append(
            {
                "zip_code": zip_code,
                "altitude_ft": 0,
                "wind_speed_ms": sfc_speed_ms,
                "wind_direction_deg": sfc_dir_deg,
                "temperature_k": sfc_temp_k,
                "temperature_f": sfc_temp_f,
            }
        )

        # Altitude levels
        for alt_ft in ga_altitudes_ft:
            if alt_ft == 0:
                continue  # Already added surface

            # Extract pressure-level data for this grid cell
            u_levels = u_pressure[:, lat_idx, lon_idx]
            v_levels = v_pressure[:, lat_idx, lon_idx]
            temp_levels = temp_pressure[:, lat_idx, lon_idx]

            # Interpolate to target altitude
            u_wind, v_wind = interpolate_wind_to_altitude(
                u_levels,
                v_levels,
                pressure_levels_mb,
                alt_ft,
                sfc_pressure_mb,
                sfc_temp_k,
            )

            temp_k = interpolate_temperature_to_altitude(
                temp_levels,
                pressure_levels_mb,
                alt_ft,
                sfc_pressure_mb,
                sfc_temp_k,
            )

            wind_speed_ms, wind_dir_deg = wind_speed_direction_from_components(
                u_wind, v_wind
            )
            temp_f = (temp_k - 273.15) * 9 / 5 + 32

            results.append(
                {
                    "zip_code": zip_code,
                    "altitude_ft": alt_ft,
                    "wind_speed_ms": wind_speed_ms,
                    "wind_direction_deg": wind_dir_deg,
                    "temperature_k": temp_k,
                    "temperature_f": temp_f,
                }
            )

    return pd.DataFrame(results)
