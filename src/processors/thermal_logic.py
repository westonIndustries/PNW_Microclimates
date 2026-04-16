"""
Thermal logic processor.

Computes surface thermal properties and urban heat island (UHI) effects:
- Surface albedo: derived from NLCD imperviousness
- Solar aspect multiplier: based on slope aspect (north/south/intermediate)
- UHI offset: temperature offset from impervious surfaces
- Landsat LST calibration: optional blending with observed surface temperatures
"""

from __future__ import annotations

import logging

import numpy as np

from src import config

logger = logging.getLogger(__name__)


def compute_surface_albedo(impervious_array: np.ndarray) -> np.ndarray:
    """Compute surface albedo from NLCD imperviousness.

    Albedo decreases with imperviousness (dark asphalt absorbs more solar
    radiation than vegetation). Formula:
        surface_albedo = 0.20 - (impervious / 100) * 0.15

    Parameters
    ----------
    impervious_array : np.ndarray
        NLCD imperviousness percentage (0–100), 2D array.

    Returns
    -------
    albedo : np.ndarray
        Surface albedo (0.05–0.20), same shape as input. NaN where input is NaN.

    Notes
    -----
    - Maximum albedo (0.20) occurs at 0% imperviousness (vegetation).
    - Minimum albedo (0.05) occurs at 100% imperviousness (dark asphalt).
    - Formula: 0.20 - (impervious / 100) * (0.20 - 0.05)
    """
    # Ensure input is float
    impervious = impervious_array.astype(np.float64)

    # Compute albedo: 0.20 - (impervious / 100) * 0.15
    albedo = 0.20 - (impervious / 100.0) * 0.15

    # Preserve NaN values
    albedo[np.isnan(impervious)] = np.nan

    # Clip to valid range [0.05, 0.20] (should be automatic from formula, but ensure)
    albedo = np.clip(albedo, 0.05, 0.20)

    return albedo


def compute_solar_aspect_multiplier(aspect_array: np.ndarray) -> np.ndarray:
    """Compute solar aspect multiplier based on slope aspect.

    South-facing slopes (135–225°) receive more solar radiation and have
    multiplier 1.2. North-facing slopes (315–45°) receive less and have
    multiplier 0.8. Other aspects are interpolated linearly.

    Parameters
    ----------
    aspect_array : np.ndarray
        Aspect in degrees (0–360°, clockwise from north), 2D array.

    Returns
    -------
    multiplier : np.ndarray
        Solar aspect multiplier (0.8–1.2), same shape as input. NaN where input is NaN.

    Notes
    -----
    - North-facing: aspect 315–45° (or 0–45° and 315–360°) → multiplier 0.8
    - South-facing: aspect 135–225° → multiplier 1.2
    - Linear interpolation for intermediate aspects.
    - The interpolation is continuous and smooth across all aspect values.
    """
    aspect = aspect_array.astype(np.float64)
    multiplier = np.full_like(aspect, np.nan, dtype=np.float64)

    valid_mask = ~np.isnan(aspect)

    if not valid_mask.any():
        return multiplier

    # Initialize multiplier array for valid pixels
    mult = np.full_like(aspect, 1.0, dtype=np.float64)

    # Define aspect ranges and their multipliers
    # North-facing: 315–45° (wraps around 0°)
    # South-facing: 135–225°
    # Intermediate: linear interpolation

    # Normalize aspect to [0, 360)
    asp = aspect[valid_mask] % 360.0

    # Compute multiplier for each aspect
    # Strategy: compute distance to nearest cardinal direction and interpolate
    # North: 0° (or 360°), multiplier 0.8
    # East: 90°, multiplier 1.0
    # South: 180°, multiplier 1.2
    # West: 270°, multiplier 1.0

    # Compute angular distance to south (180°)
    dist_to_south = np.abs(asp - 180.0)
    dist_to_south = np.minimum(dist_to_south, 360.0 - dist_to_south)

    # Compute angular distance to north (0° or 360°)
    dist_to_north = np.minimum(np.abs(asp - 0.0), np.abs(asp - 360.0))

    # Compute angular distance to east/west (90° and 270°)
    dist_to_ew = np.minimum(np.abs(asp - 90.0), np.abs(asp - 270.0))

    # Linear interpolation:
    # - At south (180°): multiplier = 1.2
    # - At north (0°/360°): multiplier = 0.8
    # - At east/west (90°/270°): multiplier = 1.0
    # - Linear between these points

    # Use a simple linear model based on distance to south
    # At 0° distance (south): 1.2
    # At 90° distance (east/west): 1.0
    # At 180° distance (north): 0.8

    # Multiplier = 1.0 + 0.2 * cos(asp - 180°)
    # This gives: 1.2 at 180°, 1.0 at 90°/270°, 0.8 at 0°/360°
    mult_valid = 1.0 + 0.2 * np.cos(np.radians(asp - 180.0))

    mult[valid_mask] = mult_valid
    multiplier[valid_mask] = mult[valid_mask]

    return multiplier


def compute_uhi_offset(
    surface_albedo: np.ndarray,
    solar_irradiance_wm2: float = None,
) -> np.ndarray:
    """Compute UHI temperature offset from surface albedo.

    The UHI offset is the temperature increase above rural baseline due to
    impervious surfaces absorbing solar radiation. Formula:
        uhi_offset_f = (0.20 - surface_albedo) * solar_irradiance_wm2 / 5.5 * 9/5

    Parameters
    ----------
    surface_albedo : np.ndarray
        Surface albedo (0.05–0.20), 2D array.
    solar_irradiance_wm2 : float, optional
        Solar irradiance in W/m² (default: from config.SOLAR_IRRADIANCE_WM2).

    Returns
    -------
    uhi_offset_f : np.ndarray
        UHI temperature offset in °F, same shape as input. NaN where input is NaN.

    Notes
    -----
    - The constant 5.5 is an empirical conversion factor from solar radiation
      to temperature increase.
    - The factor 9/5 converts from Celsius to Fahrenheit.
    - Higher albedo (vegetation) → lower UHI offset.
    - Lower albedo (asphalt) → higher UHI offset.
    """
    if solar_irradiance_wm2 is None:
        solar_irradiance_wm2 = config.SOLAR_IRRADIANCE_WM2

    albedo = surface_albedo.astype(np.float64)

    # Compute UHI offset: (0.20 - albedo) * irradiance / 5.5 * 9/5
    uhi_offset = (0.20 - albedo) * solar_irradiance_wm2 / 5.5 * (9.0 / 5.0)

    # Preserve NaN values
    uhi_offset[np.isnan(albedo)] = np.nan

    return uhi_offset


def blend_with_landsat_calibration(
    nlcd_uhi_offset_f: np.ndarray,
    landsat_lst_array: np.ndarray | None,
    impervious_array: np.ndarray,
    zip_code: str | None = None,
) -> tuple[np.ndarray, str | None]:
    """Blend NLCD-derived UHI offset with Landsat-observed offset.

    If Landsat LST is available, compute the observed UHI offset as the
    difference between urban (imperviousness ≥ 50%) and rural (imperviousness ≤ 10%)
    pixels. Blend with NLCD-derived offset using 70% NLCD, 30% Landsat.

    Parameters
    ----------
    nlcd_uhi_offset_f : np.ndarray
        NLCD-derived UHI offset in °F, 2D array.
    landsat_lst_array : np.ndarray | None
        Landsat LST in °C, 2D array. If None, no calibration is performed.
    impervious_array : np.ndarray
        NLCD imperviousness percentage (0–100), 2D array.
    zip_code : str | None
        ZIP code for logging purposes (optional).

    Returns
    -------
    calibrated_uhi_offset_f : np.ndarray
        Calibrated UHI offset in °F, same shape as input.
    calibration_warning : str | None
        Warning message if observed difference exceeds modeled offset by > 1.5°C,
        otherwise None.

    Notes
    -----
    - Urban pixels: imperviousness ≥ 50%
    - Rural pixels: imperviousness ≤ 10%
    - If fewer than 10 valid urban or rural pixels, no calibration is performed.
    - Blend: 0.70 * nlcd_offset + 0.30 * landsat_offset
    - Warning threshold: |observed_offset - modeled_offset| > 1.5°C
    """
    if landsat_lst_array is None:
        # No Landsat data available
        return nlcd_uhi_offset_f.copy(), None

    landsat_lst = landsat_lst_array.astype(np.float64)
    impervious = impervious_array.astype(np.float64)
    nlcd_offset = nlcd_uhi_offset_f.astype(np.float64)

    # Define urban and rural pixels
    urban_mask = (impervious >= 50.0) & ~np.isnan(landsat_lst)
    rural_mask = (impervious <= 10.0) & ~np.isnan(landsat_lst)

    # Check if we have enough valid pixels
    num_urban = np.sum(urban_mask)
    num_rural = np.sum(rural_mask)

    if num_urban < 10 or num_rural < 10:
        # Not enough pixels for reliable calibration
        logger.warning(
            f"Insufficient Landsat pixels for calibration (urban: {num_urban}, rural: {num_rural}). "
            f"Using NLCD-derived UHI offset unchanged."
        )
        return nlcd_offset.copy(), None

    # Compute mean LST for urban and rural pixels
    mean_urban_lst = np.nanmean(landsat_lst[urban_mask])
    mean_rural_lst = np.nanmean(landsat_lst[rural_mask])

    # Observed UHI offset in °C
    observed_uhi_offset_c = mean_urban_lst - mean_rural_lst

    # Convert NLCD offset from °F to °C for comparison
    nlcd_offset_c = nlcd_offset[~np.isnan(nlcd_offset)]
    if len(nlcd_offset_c) > 0:
        mean_nlcd_offset_c = np.nanmean(nlcd_offset_c) * (5.0 / 9.0)
    else:
        mean_nlcd_offset_c = 0.0

    # Check for calibration warning
    calibration_warning = None
    offset_diff_c = observed_uhi_offset_c - mean_nlcd_offset_c
    if abs(offset_diff_c) > 1.5:
        zip_str = f" (ZIP {zip_code})" if zip_code else ""
        calibration_warning = (
            f"Landsat-observed UHI offset ({observed_uhi_offset_c:.2f}°C) differs from "
            f"NLCD-modeled offset ({mean_nlcd_offset_c:.2f}°C) by {abs(offset_diff_c):.2f}°C{zip_str}"
        )
        logger.warning(calibration_warning)

    # Convert observed offset from °C to °F
    observed_uhi_offset_f = observed_uhi_offset_c * (9.0 / 5.0)

    # Blend: 70% NLCD, 30% Landsat
    # Use mean NLCD offset for blending
    mean_nlcd_offset_f = np.nanmean(nlcd_offset[~np.isnan(nlcd_offset)])
    calibrated_offset_f = 0.70 * mean_nlcd_offset_f + 0.30 * observed_uhi_offset_f

    # Create output array with calibrated offset
    calibrated_uhi_offset = nlcd_offset.copy()
    # Replace with calibrated value where we have valid data
    valid_mask = ~np.isnan(nlcd_offset)
    calibrated_uhi_offset[valid_mask] = calibrated_offset_f

    return calibrated_uhi_offset, calibration_warning


def compute_thermal_logic(
    impervious_array: np.ndarray,
    aspect_array: np.ndarray,
    landsat_lst_array: np.ndarray | None = None,
    nlcd_array: np.ndarray | None = None,
    zip_code: str | None = None,
) -> dict[str, np.ndarray | str | None]:
    """Compute complete thermal logic for UHI and surface effects.

    Orchestrates the computation of surface albedo, solar aspect multiplier,
    UHI offset, and optional Landsat calibration.

    Parameters
    ----------
    impervious_array : np.ndarray
        NLCD imperviousness percentage (0–100), 2D array.
    aspect_array : np.ndarray
        Slope aspect in degrees (0–360°), 2D array.
    landsat_lst_array : np.ndarray | None, optional
        Landsat LST in °C, 2D array. If None, no calibration is performed.
    nlcd_array : np.ndarray | None, optional
        NLCD land cover class array (not currently used, reserved for future).
    zip_code : str | None, optional
        ZIP code for logging purposes.

    Returns
    -------
    dict
        Dictionary with keys:
        - 'surface_albedo': Surface albedo (0.05–0.20)
        - 'solar_aspect_mult': Solar aspect multiplier (0.8–1.2)
        - 'uhi_offset_f': UHI temperature offset in °F
        - 'calibration_warning': Warning message if Landsat calibration detected
          a significant difference, otherwise None

    Notes
    -----
    - All output arrays have the same shape as the input arrays.
    - NaN values in inputs are preserved in outputs.
    - If Landsat LST is provided, the UHI offset is calibrated using a 70/30 blend.
    """
    logger.info("Starting thermal logic computation...")

    # Compute surface albedo
    surface_albedo = compute_surface_albedo(impervious_array)
    valid_albedo = surface_albedo[~np.isnan(surface_albedo)]
    if len(valid_albedo) > 0:
        logger.debug(f"Albedo range: {np.min(valid_albedo):.3f}–{np.max(valid_albedo):.3f}")

    # Compute solar aspect multiplier
    solar_aspect_mult = compute_solar_aspect_multiplier(aspect_array)
    valid_mult = solar_aspect_mult[~np.isnan(solar_aspect_mult)]
    if len(valid_mult) > 0:
        logger.debug(f"Solar aspect multiplier range: {np.min(valid_mult):.2f}–{np.max(valid_mult):.2f}")

    # Compute UHI offset
    uhi_offset_f = compute_uhi_offset(surface_albedo)
    valid_offset = uhi_offset_f[~np.isnan(uhi_offset_f)]
    if len(valid_offset) > 0:
        logger.debug(f"UHI offset range: {np.min(valid_offset):.2f}–{np.max(valid_offset):.2f}°F")

    # Apply Landsat calibration if available
    calibration_warning = None
    if landsat_lst_array is not None:
        uhi_offset_f, calibration_warning = blend_with_landsat_calibration(
            uhi_offset_f,
            landsat_lst_array,
            impervious_array,
            zip_code=zip_code,
        )
        if calibration_warning:
            logger.warning(calibration_warning)
        else:
            logger.debug("Landsat calibration applied successfully.")

    logger.info("Thermal logic computation complete.")

    return {
        "surface_albedo": surface_albedo,
        "solar_aspect_mult": solar_aspect_mult,
        "uhi_offset_f": uhi_offset_f,
        "calibration_warning": calibration_warning,
    }
