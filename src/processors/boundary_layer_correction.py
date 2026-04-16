"""
Boundary Layer Corrections — Wind Shear and Thermal Subsidence

Implements two core boundary layer correction functions for the microclimate pipeline:

1. compute_wind_shear_correction — Log-law wind shear correction at roughness transition zones
2. compute_thermal_subsidence — Exponential thermal subsidence over water bodies

These functions model localized wind shear and thermal effects in the lowest 1,000 ft AGL,
critical for aviation safety and microclimate forecasting.
"""

import numpy as np
from src.config import (
    VON_KARMAN,
    BL_DECAY_HEIGHT_FT,
    ROUGHNESS_GRADIENT_THRESHOLD,
)


def compute_wind_shear_correction(
    wind_speed_ms: float,
    z_agl_ft: float,
    z0_local: float,
    z0_upwind: float,
    u_star: float,
) -> float:
    """
    Compute wind shear correction at roughness transition zones.

    At roughness transition zones (where Δz₀ exceeds a threshold), the wind profile
    changes abruptly. This function computes the difference between the log-law wind
    profile at the local roughness length and the upwind roughness length, representing
    the wind speed adjustment due to the roughness transition.

    The log-law wind profile is:
        u(z) = (u_star / κ) × ln(z / z₀)

    where κ = 0.41 (von Kármán constant).

    The wind shear correction is:
        Δu = u_local(z) − u_upwind(z)

    This correction is applied only at altitudes ≤ 1,000 ft AGL and only in roughness
    transition zones (where |z0_local − z0_upwind| exceeds a threshold).

    Parameters
    ----------
    wind_speed_ms : float
        Reference wind speed at a known height (typically 10 m AGL), in m/s.
        Used to compute u_star if not provided directly.
    z_agl_ft : float
        Target altitude above ground level, in feet.
    z0_local : float
        Local roughness length, in meters (from NLCD surface properties).
    z0_upwind : float
        Upwind roughness length, in meters (from NLCD surface properties).
    u_star : float
        Friction velocity, in m/s. If zero or None, computed from wind_speed_ms
        and reference height (10 m).

    Returns
    -------
    float
        Wind speed correction in knots (positive = increase, negative = decrease).
        Returns 0.0 if altitude > 1,000 ft or if not in a transition zone.

    Notes
    -----
    - Correction is zero above 1,000 ft AGL.
    - Correction is zero if the roughness gradient is below the threshold.
    - Wind speed is converted from m/s to knots (1 m/s = 1.944 knots).
    - If u_star is 0 or None, assumes reference wind at 10 m AGL and computes
      u_star = wind_speed_ms × κ / ln(10 / z0_upwind).
    """
    # Correction only applies at altitudes ≤ 1,000 ft AGL
    if z_agl_ft > 1000.0:
        return 0.0

    # Check if this is a transition zone (roughness gradient exceeds threshold)
    roughness_gradient = abs(z0_local - z0_upwind)
    if roughness_gradient < ROUGHNESS_GRADIENT_THRESHOLD:
        return 0.0

    # Convert altitude from feet to meters
    z_agl_m = z_agl_ft * 0.3048

    # Compute friction velocity if not provided
    if u_star is None or u_star == 0:
        # Assume reference wind at 10 m AGL
        z_ref = 10.0
        if z_ref <= 0 or z0_upwind <= 0:
            return 0.0
        u_star = wind_speed_ms * VON_KARMAN / np.log(z_ref / z0_upwind)

    # Ensure altitude is above roughness length
    if z_agl_m <= z0_local or z_agl_m <= z0_upwind:
        return 0.0

    # Compute wind speed at local roughness length
    if z0_local > 0:
        u_local = (u_star / VON_KARMAN) * np.log(z_agl_m / z0_local)
    else:
        u_local = 0.0

    # Compute wind speed at upwind roughness length
    if z0_upwind > 0:
        u_upwind = (u_star / VON_KARMAN) * np.log(z_agl_m / z0_upwind)
    else:
        u_upwind = 0.0

    # Compute correction in m/s
    correction_ms = u_local - u_upwind

    # Convert to knots (1 m/s = 1.944 knots)
    correction_kt = correction_ms * 1.944

    return correction_kt


def compute_thermal_subsidence(
    temp_f: float,
    z_agl_ft: float,
    is_water: bool,
) -> float:
    """
    Compute thermal subsidence correction over water bodies.

    Over water bodies, cool water temperatures suppress convective mixing in the
    boundary layer, creating a thermal sink effect. This function computes the
    temperature reduction due to thermal subsidence using exponential decay with height.

    The thermal subsidence correction is:
        T_correction = T_surface_anomaly × exp(−z / H_bl)

    where H_bl = 500 ft is the boundary layer decay height.

    This correction is applied only at altitudes ≤ 1,000 ft AGL and only over water
    pixels (NLCD class 11 = Open Water).

    Parameters
    ----------
    temp_f : float
        Temperature anomaly (land temperature − water temperature), in °F.
        Positive values indicate land is warmer than water (typical case).
    z_agl_ft : float
        Altitude above ground level, in feet.
    is_water : bool
        True if the pixel is water (NLCD class 11), False otherwise.

    Returns
    -------
    float
        Temperature correction in °F (negative = cooling).
        Returns 0.0 if altitude > 1,000 ft or if not over water.

    Notes
    -----
    - Correction is zero above 1,000 ft AGL.
    - Correction is zero over non-water pixels.
    - At z = 0 (surface), returns −temp_f (full cooling).
    - At z = H_bl (500 ft), returns −temp_f × exp(−1) ≈ −0.368 × temp_f.
    - At z ≥ 1,000 ft, returns 0.0 (thermal subsidence effect negligible).
    - The correction is negative (cooling) when temp_f is positive (land warmer than water).
    """
    # Correction only applies at altitudes ≤ 1,000 ft AGL
    if z_agl_ft > 1000.0:
        return 0.0

    # Correction only applies over water pixels
    if not is_water:
        return 0.0

    # Exponential decay with altitude
    decay_factor = np.exp(-z_agl_ft / BL_DECAY_HEIGHT_FT)

    # Return negative correction (cooling)
    return -temp_f * decay_factor
