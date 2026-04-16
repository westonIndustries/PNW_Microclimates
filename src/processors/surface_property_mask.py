"""
Surface property mask builder for boundary layer physics.

Constructs arrays of surface properties (roughness length, displacement height,
albedo, emissivity) from NLCD land cover classification. Computes roughness
gradients and identifies transition zones where wind shear corrections apply.
"""

import numpy as np
from scipy import ndimage
from src.config import (
    NLCD_SURFACE_PROPERTIES,
    NLCD_DISPLACEMENT_HEIGHT_M,
    ROUGHNESS_GRADIENT_THRESHOLD,
    Z0_RURAL_REFERENCE,
)


def build_surface_mask(nlcd_array: np.ndarray) -> dict:
    """
    Build a surface property mask from NLCD land cover classification.

    Converts a 2D NLCD class array into a dictionary of 2D property arrays
    (z0, displacement height, albedo, emissivity) and computes roughness
    gradients and transition zones for boundary layer physics.

    Parameters
    ----------
    nlcd_array : np.ndarray
        2D array of NLCD 2021 land cover class codes (integer values 11–95).
        Shape: (rows, cols). May contain NaN for nodata pixels.

    Returns
    -------
    dict
        Dictionary with the following keys:
        - 'z0_m': 2D array of roughness length in meters (float64)
        - 'displacement_height_m': 2D array of displacement height in meters (float64)
        - 'albedo': 2D array of surface albedo 0.0–1.0 (float64)
        - 'emissivity': 2D array of thermal emissivity 0.0–1.0 (float64)
        - 'nlcd_class': 2D array of NLCD class codes (int, same as input)
        - 'roughness_gradient': 2D array of spatial z0 gradient magnitude (float64)
        - 'roughness_transition_zone': 2D boolean array identifying pixels where
          roughness gradient exceeds ROUGHNESS_GRADIENT_THRESHOLD

    Notes
    -----
    - Nodata pixels (NaN) in the input are preserved as NaN in all output arrays.
    - Roughness gradient is computed using the Sobel operator on the log(z0) field
      to capture relative changes in roughness length.
    - Transition zones are pixels where the gradient magnitude exceeds the threshold,
      indicating a sharp change in surface roughness (e.g., forest edge, urban-rural
      boundary). These zones require wind shear corrections in the boundary layer.
    """

    # Identify nodata pixels (NaN values)
    nodata_mask = np.isnan(nlcd_array)

    # Initialize output arrays
    rows, cols = nlcd_array.shape
    z0_m = np.full((rows, cols), np.nan, dtype=np.float64)
    displacement_height_m = np.full((rows, cols), np.nan, dtype=np.float64)
    albedo = np.full((rows, cols), np.nan, dtype=np.float64)
    emissivity = np.full((rows, cols), np.nan, dtype=np.float64)
    nlcd_class = np.full((rows, cols), np.nan, dtype=np.float64)

    # Convert NLCD array to integer for indexing (handle NaN by filling with 0 temporarily)
    nlcd_int = np.where(nodata_mask, 0, nlcd_array.astype(int))

    # Map NLCD classes to surface properties
    for nlcd_code, props in NLCD_SURFACE_PROPERTIES.items():
        mask = nlcd_int == nlcd_code
        z0_m[mask] = props["z0_m"]
        albedo[mask] = props["albedo"]
        emissivity[mask] = props["emissivity"]
        nlcd_class[mask] = nlcd_code

    # Map NLCD classes to displacement heights
    for nlcd_code, d in NLCD_DISPLACEMENT_HEIGHT_M.items():
        mask = nlcd_int == nlcd_code
        displacement_height_m[mask] = d

    # Restore nodata mask (set NaN for pixels that were nodata in input)
    z0_m[nodata_mask] = np.nan
    displacement_height_m[nodata_mask] = np.nan
    albedo[nodata_mask] = np.nan
    emissivity[nodata_mask] = np.nan
    nlcd_class[nodata_mask] = np.nan

    # Compute roughness gradient using Sobel operator on log(z0)
    # Use log scale to capture relative changes in roughness
    z0_log = np.log(np.where(z0_m > 0, z0_m, Z0_RURAL_REFERENCE))
    z0_log[nodata_mask] = np.nan

    # Compute Sobel gradients (x and y components)
    # Use mode='constant' with cval=0 to handle edges
    sobel_x = ndimage.sobel(z0_log, axis=1)
    sobel_y = ndimage.sobel(z0_log, axis=0)

    # Compute gradient magnitude
    roughness_gradient = np.sqrt(sobel_x**2 + sobel_y**2)

    # Set gradient to NaN for nodata pixels
    roughness_gradient[nodata_mask] = np.nan

    # Identify roughness transition zones
    # A pixel is in a transition zone if its gradient exceeds the threshold
    roughness_transition_zone = roughness_gradient > ROUGHNESS_GRADIENT_THRESHOLD

    # Set transition zone to False for nodata pixels
    roughness_transition_zone[nodata_mask] = False

    return {
        "z0_m": z0_m,
        "displacement_height_m": displacement_height_m,
        "albedo": albedo,
        "emissivity": emissivity,
        "nlcd_class": nlcd_class,
        "roughness_gradient": roughness_gradient,
        "roughness_transition_zone": roughness_transition_zone,
    }
