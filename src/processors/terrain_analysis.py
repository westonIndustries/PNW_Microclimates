"""
Terrain analysis processor.

Computes terrain-derived features from a LiDAR DEM:
- Aspect: direction of slope in degrees (0–360°, clockwise from north)
- Slope: steepness in degrees (0–90°)
- TPI: Topographic Position Index (elevation minus mean elevation in annulus)
- Wind shadow: binary mask for areas sheltered from prevailing wind
- Lapse rate HDD addition: elevation-based HDD correction
"""

from __future__ import annotations

import logging

import numpy as np
from scipy import ndimage
from scipy.ndimage import distance_transform_edt

from src import config

logger = logging.getLogger(__name__)


def compute_aspect_and_slope(dem: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute aspect and slope from a DEM using gradient.

    Aspect is computed as the direction of the steepest descent, in degrees
    clockwise from north (0–360°). Slope is the magnitude of the gradient,
    converted to degrees.

    Parameters
    ----------
    dem : np.ndarray
        Digital elevation model (2D array). NaN values are preserved.

    Returns
    -------
    aspect : np.ndarray
        Aspect in degrees (0–360°), same shape as dem. NaN where dem is NaN.
    slope : np.ndarray
        Slope in degrees (0–90°), same shape as dem. NaN where dem is NaN.

    Notes
    -----
    - Aspect is computed using atan2(dy, dx) where dy and dx are gradients.
    - Aspect is converted from mathematical convention (0° = east, CCW) to
      geographic convention (0° = north, CW).
    - Slope is computed as arctan(gradient_magnitude).
    - Edge pixels (where gradient cannot be computed) are set to NaN.
    """
    # Create a copy to avoid modifying the input
    dem_filled = dem.copy()

    # Replace NaN with a fill value for gradient computation
    valid_mask = ~np.isnan(dem)
    if not valid_mask.any():
        # All NaN input
        return np.full_like(dem, np.nan), np.full_like(dem, np.nan)

    # Use nearest valid value to fill NaN for gradient computation
    dem_filled[~valid_mask] = np.nanmean(dem)

    # Compute gradients using Sobel operator (3x3 kernel)
    # dy: gradient in y direction (rows), dx: gradient in x direction (cols)
    dy, dx = np.gradient(dem_filled)

    # Compute slope as arctan of gradient magnitude
    gradient_magnitude = np.sqrt(dx**2 + dy**2)
    slope_rad = np.arctan(gradient_magnitude)
    slope_deg = np.degrees(slope_rad)

    # Compute aspect from gradients
    # atan2(dy, dx) gives angle in mathematical convention (0° = east, CCW)
    # Convert to geographic convention (0° = north, CW):
    # aspect_geo = 90 - atan2(dy, dx) in degrees
    aspect_rad = np.arctan2(dy, dx)
    aspect_deg = 90.0 - np.degrees(aspect_rad)

    # Normalize aspect to 0–360°
    aspect_deg = aspect_deg % 360.0

    # Set edge pixels and original NaN locations to NaN
    aspect_deg[~valid_mask] = np.nan
    slope_deg[~valid_mask] = np.nan

    # Set edge pixels (where gradient is undefined) to NaN
    aspect_deg[0, :] = np.nan
    aspect_deg[-1, :] = np.nan
    aspect_deg[:, 0] = np.nan
    aspect_deg[:, -1] = np.nan
    slope_deg[0, :] = np.nan
    slope_deg[-1, :] = np.nan
    slope_deg[:, 0] = np.nan
    slope_deg[:, -1] = np.nan

    return aspect_deg, slope_deg


def compute_tpi(dem: np.ndarray, pixel_size_m: float = 1.0) -> np.ndarray:
    """Compute Topographic Position Index (TPI).

    TPI is the elevation at a pixel minus the mean elevation within an annulus
    (ring) of inner radius 300 m and outer radius 1,000 m. Positive TPI
    indicates ridges; negative TPI indicates valleys.

    Parameters
    ----------
    dem : np.ndarray
        Digital elevation model (2D array). NaN values are preserved.
    pixel_size_m : float, optional
        Pixel size in meters (default: 1.0 m for LiDAR DEM).

    Returns
    -------
    tpi : np.ndarray
        TPI array, same shape as dem. NaN where dem is NaN or where the
        annulus extends beyond the raster edge.

    Notes
    -----
    - Inner radius: 300 m
    - Outer radius: 1,000 m
    - Pixels within 1,000 m of the raster edge are set to NaN.
    - Uses a fast approximation: mean in outer neighborhood minus mean in
      inner neighborhood, normalized by area ratio.
    """
    from scipy.ndimage import uniform_filter

    # Convert radii from meters to pixels
    inner_radius_px = 300.0 / pixel_size_m
    outer_radius_px = 1000.0 / pixel_size_m

    # Create a copy to avoid modifying the input
    dem_filled = dem.copy()
    valid_mask = ~np.isnan(dem)

    if not valid_mask.any():
        # All NaN input
        return np.full_like(dem, np.nan)

    # Fill NaN with mean for computation
    dem_filled[~valid_mask] = np.nanmean(dem)

    # Fast approximation using uniform filters
    # Outer neighborhood size (square approximation of circle)
    outer_size = int(2 * outer_radius_px) + 1
    if outer_size % 2 == 0:
        outer_size += 1

    # Inner neighborhood size
    inner_size = int(2 * inner_radius_px) + 1
    if inner_size % 2 == 0:
        inner_size += 1

    # Compute means using uniform filter (fast)
    mean_outer = uniform_filter(dem_filled, size=outer_size, mode="nearest")
    mean_inner = uniform_filter(dem_filled, size=inner_size, mode="nearest")

    # Approximate annulus mean
    # Area of outer circle and inner circle
    outer_area = np.pi * outer_radius_px**2
    inner_area = np.pi * inner_radius_px**2
    annulus_area = outer_area - inner_area

    # Annulus mean ≈ (outer_mean * outer_area - inner_mean * inner_area) / annulus_area
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_annulus = (mean_outer * outer_area - mean_inner * inner_area) / annulus_area

    # Compute TPI
    tpi = dem_filled - mean_annulus

    # Set to NaN where original dem was NaN
    tpi[~valid_mask] = np.nan

    # Set to NaN where annulus extends beyond edge (within outer_radius of edge)
    edge_buffer = int(np.ceil(outer_radius_px))
    tpi[:edge_buffer, :] = np.nan
    tpi[-edge_buffer:, :] = np.nan
    tpi[:, :edge_buffer] = np.nan
    tpi[:, -edge_buffer:] = np.nan

    return tpi


def compute_wind_shadow(
    tpi: np.ndarray,
    aspect: np.ndarray,
    prevailing_wind_deg: float = None,
) -> np.ndarray:
    """Compute wind shadow mask.

    Wind shadow identifies areas where terrain blocks the prevailing wind.
    A pixel is in wind shadow if:
    - TPI < 0 (valley), AND
    - Aspect is within ±90° of (prevailing_wind_deg + 180°)

    The +180° accounts for the fact that wind shadow is on the leeward side
    (opposite the wind direction).

    Parameters
    ----------
    tpi : np.ndarray
        Topographic Position Index array.
    aspect : np.ndarray
        Aspect array in degrees (0–360°).
    prevailing_wind_deg : float, optional
        Prevailing wind direction in degrees (default: from config.PREVAILING_WIND_DEG).

    Returns
    -------
    wind_shadow : np.ndarray
        Binary mask (1 = in wind shadow, 0 = not in wind shadow, NaN = invalid).
        Same shape as tpi and aspect.

    Notes
    -----
    - Wind shadow is on the leeward side, which is 180° opposite the wind direction.
    - "Within ±90°" means the aspect is within 90° on either side of the leeward direction.
    """
    if prevailing_wind_deg is None:
        prevailing_wind_deg = config.PREVAILING_WIND_DEG

    # Leeward direction is 180° opposite the wind direction
    leeward_deg = (prevailing_wind_deg + 180.0) % 360.0

    # Compute angular distance from leeward direction
    # Handle wrap-around at 0°/360°
    angular_diff = np.abs(aspect - leeward_deg)
    angular_diff = np.minimum(angular_diff, 360.0 - angular_diff)

    # Wind shadow: TPI < 0 AND aspect within ±90° of leeward direction
    wind_shadow = (tpi < 0) & (angular_diff <= 90.0)

    # Set to NaN where inputs are NaN
    wind_shadow = wind_shadow.astype(float)
    wind_shadow[np.isnan(tpi) | np.isnan(aspect)] = np.nan

    return wind_shadow


def compute_lapse_rate_hdd_addition(
    dem: np.ndarray,
    station_elevation_ft: float,
    lapse_rate_hdd_per_1000ft: float = None,
    pixel_size_m: float = 1.0,
) -> np.ndarray:
    """Compute HDD addition from elevation lapse rate.

    HDD increases with elevation at a rate of approximately 630 HDD per
    1,000 ft above the base weather station.

    Parameters
    ----------
    dem : np.ndarray
        Digital elevation model in meters (2D array).
    station_elevation_ft : float
        Base weather station elevation in feet above sea level.
    lapse_rate_hdd_per_1000ft : float, optional
        HDD increase per 1,000 ft elevation gain (default: from config).
    pixel_size_m : float, optional
        Pixel size in meters (default: 1.0 m).

    Returns
    -------
    hdd_addition : np.ndarray
        HDD addition array, same shape as dem. NaN where dem is NaN.

    Notes
    -----
    - Formula: (elevation_ft - station_elevation_ft) / 1000 * lapse_rate_hdd_per_1000ft
    - Negative values (lower elevation) result in negative HDD addition (reduction).
    """
    if lapse_rate_hdd_per_1000ft is None:
        lapse_rate_hdd_per_1000ft = config.LAPSE_RATE_HDD_PER_1000FT

    # Convert DEM from meters to feet
    dem_ft = dem * 3.28084

    # Compute elevation difference from station
    elevation_diff_ft = dem_ft - station_elevation_ft

    # Compute HDD addition
    hdd_addition = (elevation_diff_ft / 1000.0) * lapse_rate_hdd_per_1000ft

    # Preserve NaN values
    hdd_addition[np.isnan(dem)] = np.nan

    return hdd_addition


def analyze_terrain(
    dem: np.ndarray,
    station_elevation_ft: float,
    pixel_size_m: float = 1.0,
    prevailing_wind_deg: float = None,
) -> dict[str, np.ndarray]:
    """Perform complete terrain analysis on a DEM.

    Computes aspect, slope, TPI, wind shadow, and lapse rate HDD addition
    in a single call.

    Parameters
    ----------
    dem : np.ndarray
        Digital elevation model (2D array) in meters.
    station_elevation_ft : float
        Base weather station elevation in feet above sea level.
    pixel_size_m : float, optional
        Pixel size in meters (default: 1.0 m for LiDAR DEM).
    prevailing_wind_deg : float, optional
        Prevailing wind direction in degrees (default: from config).

    Returns
    -------
    dict
        Dictionary with keys:
        - 'aspect': Aspect in degrees (0–360°)
        - 'slope': Slope in degrees (0–90°)
        - 'tpi': Topographic Position Index
        - 'wind_shadow': Binary wind shadow mask (1 = shadow, 0 = not)
        - 'lapse_rate_hdd_addition': HDD addition from elevation

    Notes
    -----
    - All output arrays have the same shape as the input dem.
    - NaN values in the input dem are preserved in all outputs.
    """
    logger.info("Starting terrain analysis...")

    # Compute aspect and slope
    aspect, slope = compute_aspect_and_slope(dem)
    logger.debug(f"Aspect range: {np.nanmin(aspect):.1f}–{np.nanmax(aspect):.1f}°")
    logger.debug(f"Slope range: {np.nanmin(slope):.1f}–{np.nanmax(slope):.1f}°")

    # Compute TPI
    tpi = compute_tpi(dem, pixel_size_m=pixel_size_m)
    logger.debug(f"TPI range: {np.nanmin(tpi):.1f}–{np.nanmax(tpi):.1f} m")

    # Compute wind shadow
    wind_shadow = compute_wind_shadow(tpi, aspect, prevailing_wind_deg=prevailing_wind_deg)
    wind_shadow_pct = 100.0 * np.nansum(wind_shadow) / np.sum(~np.isnan(wind_shadow))
    logger.debug(f"Wind shadow coverage: {wind_shadow_pct:.1f}%")

    # Compute lapse rate HDD addition
    hdd_addition = compute_lapse_rate_hdd_addition(
        dem,
        station_elevation_ft,
        pixel_size_m=pixel_size_m,
    )
    logger.debug(
        f"Lapse rate HDD addition range: {np.nanmin(hdd_addition):.0f}–{np.nanmax(hdd_addition):.0f} HDD"
    )

    logger.info("Terrain analysis complete.")

    return {
        "aspect": aspect,
        "slope": slope,
        "tpi": tpi,
        "wind_shadow": wind_shadow,
        "lapse_rate_hdd_addition": hdd_addition,
    }
