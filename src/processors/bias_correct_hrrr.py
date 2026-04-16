"""
HRRR bias correction module.

Applies additive bias correction to HRRR daily temperature fields so they
inherit PRISM's terrain-aware station calibration:

    hrrr_adjusted = hrrr_raw + (prism_normal - hrrr_climatology)

The bias correction ensures consistency between HRRR (high-resolution daily
atmospheric data) and PRISM (30-year climate normals with station calibration).

When fewer than HRRR_MIN_CLIM_YEARS years of HRRR climatology are available,
the module falls back to using the raw HRRR monthly mean as the climatology
reference, with a warning logged.
"""

import logging
from datetime import datetime
from typing import Optional

import numpy as np
import xarray as xr

from src.config import HRRR_MIN_CLIM_YEARS

logger = logging.getLogger(__name__)


def bias_correct(
    hrrr_daily_temp: xr.DataArray,
    prism_monthly_normal: xr.DataArray,
    hrrr_climatology: Optional[xr.DataArray] = None,
    fallback_to_raw_mean: bool = True,
) -> xr.DataArray:
    """
    Apply additive bias correction to HRRR daily temperature.

    Corrects HRRR daily temperature fields to match PRISM's terrain-aware
    station calibration using an additive offset:

        hrrr_adjusted = hrrr_raw + (prism_normal - hrrr_climatology)

    This ensures that:
    - HRRR inherits PRISM's station-level accuracy
    - Daily variations from HRRR are preserved
    - Spatial patterns from HRRR are maintained
    - The correction is physically meaningful (additive temperature offset)

    Parameters
    ----------
    hrrr_daily_temp : xr.DataArray
        HRRR daily mean 2m temperature (°F or °C, must match prism_monthly_normal).
        Shape: (y, x) for a single day, or (time, y, x) for multiple days.
        Should have spatial dimensions (typically 'y', 'x' or lat/lon).

    prism_monthly_normal : xr.DataArray
        PRISM 30-year monthly mean temperature normal (°F or °C).
        Shape: (y, x) matching the HRRR grid after downscaling.
        Should be the same units as hrrr_daily_temp.

    hrrr_climatology : xr.DataArray, optional
        HRRR multi-year climatology (mean) for the target month (°F or °C).
        Shape: (y, x) matching the HRRR grid.
        If None and fallback_to_raw_mean=True, uses raw HRRR monthly mean.
        If None and fallback_to_raw_mean=False, raises ValueError.

    fallback_to_raw_mean : bool, default True
        If True and hrrr_climatology is None, compute climatology as the
        raw HRRR daily mean for the target month (fallback when < 3 years cached).
        If False and hrrr_climatology is None, raises ValueError.

    Returns
    -------
    xr.DataArray
        Bias-corrected HRRR daily temperature with same shape and coordinates
        as hrrr_daily_temp. Units match input (°F or °C).

    Raises
    ------
    ValueError
        If hrrr_climatology is None, fallback_to_raw_mean is False, and
        climatology cannot be computed.
    ValueError
        If input arrays have incompatible shapes or missing spatial dimensions.

    Notes
    -----
    - The bias correction is additive (not multiplicative) because temperature
      offsets are more physically meaningful than ratios for near-surface fields.
    - If hrrr_climatology is not provided, the fallback uses the raw HRRR daily
      mean as the climatology reference. This is appropriate when fewer than
      HRRR_MIN_CLIM_YEARS years are cached.
    - The correction preserves NaN values from the input arrays.
    - Spatial dimensions must match between hrrr_daily_temp and prism_monthly_normal.

    Examples
    --------
    >>> import xarray as xr
    >>> import numpy as np
    >>> # Create sample data
    >>> hrrr_temp = xr.DataArray(
    ...     np.random.randn(100, 100) + 50,  # ~50°F
    ...     dims=['y', 'x'],
    ...     name='temperature'
    ... )
    >>> prism_normal = xr.DataArray(
    ...     np.random.randn(100, 100) + 48,  # ~48°F
    ...     dims=['y', 'x'],
    ...     name='prism_normal'
    ... )
    >>> hrrr_clim = xr.DataArray(
    ...     np.random.randn(100, 100) + 49,  # ~49°F
    ...     dims=['y', 'x'],
    ...     name='climatology'
    ... )
    >>> # Apply bias correction
    >>> corrected = bias_correct(hrrr_temp, prism_normal, hrrr_clim)
    >>> print(corrected.mean().values)  # Should be close to prism_normal mean
    """
    # Validate input shapes
    if hrrr_daily_temp.shape[-2:] != prism_monthly_normal.shape[-2:]:
        raise ValueError(
            f"HRRR daily temp shape {hrrr_daily_temp.shape[-2:]} does not match "
            f"PRISM normal shape {prism_monthly_normal.shape[-2:]}"
        )

    # Handle climatology fallback
    if hrrr_climatology is None:
        if fallback_to_raw_mean:
            logger.warning(
                "HRRR climatology not provided. Using raw HRRR daily mean as fallback. "
                "This is appropriate when fewer than %d years of HRRR data are cached.",
                HRRR_MIN_CLIM_YEARS,
            )
            # Use the raw HRRR daily mean as the climatology reference
            hrrr_climatology = hrrr_daily_temp.mean(dim="time", skipna=True)
        else:
            raise ValueError(
                "hrrr_climatology is None and fallback_to_raw_mean is False. "
                "Either provide hrrr_climatology or set fallback_to_raw_mean=True."
            )

    # Validate climatology shape
    if hrrr_climatology.shape != prism_monthly_normal.shape:
        raise ValueError(
            f"HRRR climatology shape {hrrr_climatology.shape} does not match "
            f"PRISM normal shape {prism_monthly_normal.shape}"
        )

    # Compute bias correction: (prism_normal - hrrr_climatology)
    bias_correction = prism_monthly_normal - hrrr_climatology

    # Apply correction: hrrr_adjusted = hrrr_raw + bias_correction
    hrrr_adjusted = hrrr_daily_temp + bias_correction

    # Preserve metadata
    hrrr_adjusted.attrs.update(hrrr_daily_temp.attrs)
    hrrr_adjusted.attrs["bias_correction_applied"] = True
    hrrr_adjusted.attrs["bias_correction_method"] = "additive"
    hrrr_adjusted.attrs["bias_correction_formula"] = (
        "hrrr_adjusted = hrrr_raw + (prism_normal - hrrr_climatology)"
    )

    return hrrr_adjusted


def compute_bias_correction_field(
    prism_monthly_normal: xr.DataArray,
    hrrr_climatology: xr.DataArray,
) -> xr.DataArray:
    """
    Compute the bias correction field (prism_normal - hrrr_climatology).

    This is a utility function that returns just the bias correction field
    without applying it to HRRR data. Useful for inspecting the magnitude
    and spatial pattern of the correction.

    Parameters
    ----------
    prism_monthly_normal : xr.DataArray
        PRISM 30-year monthly mean temperature normal (°F or °C).
        Shape: (y, x)

    hrrr_climatology : xr.DataArray
        HRRR multi-year climatology (mean) for the target month (°F or °C).
        Shape: (y, x) matching PRISM grid.

    Returns
    -------
    xr.DataArray
        Bias correction field with same shape as inputs.
        Positive values indicate HRRR is too cold relative to PRISM.
        Negative values indicate HRRR is too warm relative to PRISM.

    Raises
    ------
    ValueError
        If input arrays have incompatible shapes.
    """
    if prism_monthly_normal.shape != hrrr_climatology.shape:
        raise ValueError(
            f"PRISM shape {prism_monthly_normal.shape} does not match "
            f"HRRR climatology shape {hrrr_climatology.shape}"
        )

    bias_field = prism_monthly_normal - hrrr_climatology
    bias_field.attrs["description"] = "Bias correction field (prism - hrrr_climatology)"
    bias_field.attrs["units"] = prism_monthly_normal.attrs.get("units", "unknown")

    return bias_field


def validate_bias_correction(
    hrrr_adjusted: xr.DataArray,
    prism_monthly_normal: xr.DataArray,
    tolerance_f: float = 2.0,
) -> dict:
    """
    Validate that bias correction was applied correctly.

    Checks that the bias-corrected HRRR temperature is reasonably close to
    the PRISM normal (within tolerance). Returns statistics about the
    correction for QA purposes.

    Parameters
    ----------
    hrrr_adjusted : xr.DataArray
        Bias-corrected HRRR temperature.

    prism_monthly_normal : xr.DataArray
        PRISM 30-year monthly mean temperature normal.

    tolerance_f : float, default 2.0
        Acceptable difference between corrected HRRR and PRISM (°F or °C).

    Returns
    -------
    dict
        Validation results with keys:
        - 'passed': bool, True if correction is within tolerance
        - 'mean_diff': float, mean difference (corrected - prism)
        - 'max_diff': float, maximum absolute difference
        - 'pct_within_tolerance': float, percentage of pixels within tolerance
        - 'num_outliers': int, number of pixels exceeding tolerance

    Notes
    -----
    This function is useful for QA checks after applying bias correction.
    A well-applied correction should have mean_diff close to 0 and most
    pixels within the tolerance.
    """
    # Compute difference
    diff = hrrr_adjusted - prism_monthly_normal

    # Compute statistics
    mean_diff = float(diff.mean(skipna=True).values)
    max_diff = float(np.abs(diff).max(skipna=True).values)
    within_tolerance = np.abs(diff) <= tolerance_f
    pct_within = float(100 * within_tolerance.sum() / within_tolerance.size)
    num_outliers = int((~within_tolerance).sum().values)

    passed = mean_diff < tolerance_f and pct_within > 95

    return {
        "passed": passed,
        "mean_diff": mean_diff,
        "max_diff": max_diff,
        "pct_within_tolerance": pct_within,
        "num_outliers": num_outliers,
    }
