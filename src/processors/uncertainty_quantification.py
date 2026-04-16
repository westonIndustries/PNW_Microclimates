"""
Error propagation and uncertainty bounds for effective HDD calculations.

This module implements uncertainty quantification for the effective HDD formula by
propagating errors through each correction component (terrain, elevation, UHI, traffic).
The approach uses standard error propagation techniques to compute lower and upper bounds
on effective_hdd values, quantifying the uncertainty in the final microclimate estimates.

Formula:
    effective_hdd = base_hdd × terrain_mult + elev_addition − uhi_reduction − traffic_reduction

Uncertainty propagation:
    For each component, we estimate a standard deviation (σ) based on measurement/model error.
    The combined uncertainty is computed using root-sum-of-squares (RSS) of individual
    component uncertainties, accounting for the formula structure (multiplication vs. addition).
"""

import numpy as np
import pandas as pd
from typing import Tuple


# Uncertainty estimates for each correction component (in °F-days for HDD)
# These represent typical standard deviations based on data quality and model error

# Base HDD uncertainty: PRISM has ~±200 HDD uncertainty due to spatial interpolation
# and station calibration error
BASE_HDD_UNCERTAINTY = 200.0

# Terrain multiplier uncertainty: TPI-based classification has ~±0.05 uncertainty
# due to DEM resolution and classification boundary effects
TERRAIN_MULT_UNCERTAINTY = 0.05

# Elevation addition uncertainty: Lapse rate has ~±50 HDD uncertainty due to
# atmospheric variability and DEM vertical accuracy (±1-2 m)
ELEV_ADDITION_UNCERTAINTY = 50.0

# UHI reduction uncertainty: Imperviousness-based UHI has ~±100 HDD uncertainty
# due to Landsat LST calibration error and surface heterogeneity
UHI_REDUCTION_UNCERTAINTY = 100.0

# Traffic reduction uncertainty: Road heat flux has ~±75 HDD uncertainty due to
# AADT estimation error and traffic pattern variability
TRAFFIC_REDUCTION_UNCERTAINTY = 75.0


def compute_effective_hdd_bounds(
    base_hdd: float | np.ndarray | pd.Series,
    terrain_mult: float | np.ndarray | pd.Series,
    elev_addition: float | np.ndarray | pd.Series,
    uhi_reduction: float | np.ndarray | pd.Series,
    traffic_reduction: float | np.ndarray | pd.Series,
    base_hdd_sigma: float = BASE_HDD_UNCERTAINTY,
    terrain_mult_sigma: float = TERRAIN_MULT_UNCERTAINTY,
    elev_addition_sigma: float = ELEV_ADDITION_UNCERTAINTY,
    uhi_reduction_sigma: float = UHI_REDUCTION_UNCERTAINTY,
    traffic_reduction_sigma: float = TRAFFIC_REDUCTION_UNCERTAINTY,
) -> Tuple[float | np.ndarray | pd.Series, float | np.ndarray | pd.Series]:
    """
    Compute lower and upper bounds on effective HDD using error propagation.

    This function implements uncertainty quantification by propagating errors through
    the effective HDD formula. The approach uses standard error propagation techniques:
    - For multiplicative terms (base_hdd × terrain_mult), we use relative error propagation
    - For additive/subtractive terms, we use absolute error propagation
    - Combined uncertainty is computed using root-sum-of-squares (RSS)

    The bounds represent approximately ±1 standard deviation (68% confidence interval).
    For a 95% confidence interval, multiply the uncertainty by 1.96.

    Parameters
    ----------
    base_hdd : float, np.ndarray, or pd.Series
        Atmospheric base HDD (°F-days, base 65°F) from PRISM or HRRR.
    terrain_mult : float, np.ndarray, or pd.Series
        Terrain position multiplier (windward/leeward/valley/ridge).
        Typical range: 0.95–1.20.
    elev_addition : float, np.ndarray, or pd.Series
        HDD addition from elevation lapse rate above base station (°F-days).
    uhi_reduction : float, np.ndarray, or pd.Series
        HDD reduction from urban heat island effect (positive value = reduction).
    traffic_reduction : float, np.ndarray, or pd.Series
        HDD reduction from anthropogenic road heat (positive value = reduction).
    base_hdd_sigma : float, optional
        Standard deviation of base_hdd (°F-days). Default: 200.
    terrain_mult_sigma : float, optional
        Standard deviation of terrain_mult (dimensionless). Default: 0.05.
    elev_addition_sigma : float, optional
        Standard deviation of elev_addition (°F-days). Default: 50.
    uhi_reduction_sigma : float, optional
        Standard deviation of uhi_reduction (°F-days). Default: 100.
    traffic_reduction_sigma : float, optional
        Standard deviation of traffic_reduction (°F-days). Default: 75.

    Returns
    -------
    Tuple[float/np.ndarray/pd.Series, float/np.ndarray/pd.Series]
        (effective_hdd_low, effective_hdd_high) representing the lower and upper bounds
        at approximately ±1 standard deviation. Type matches input type.

    Notes
    -----
    - The bounds are symmetric around the nominal effective_hdd value
    - Bounds represent approximately 68% confidence interval (±1σ)
    - For 95% confidence interval, multiply uncertainty by 1.96
    - Bounds may extend below zero for warm urban areas (physically possible)
    - Negative bounds are flagged in QA checks as implausible for PNW climate

    Examples
    --------
    >>> base_hdd = 5000.0
    >>> terrain_mult = 1.05
    >>> elev_addition = 200.0
    >>> uhi_reduction = 150.0
    >>> traffic_reduction = 50.0
    >>> low, high = compute_effective_hdd_bounds(
    ...     base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
    ... )
    >>> print(f"Bounds: {low:.0f} to {high:.0f}")
    """
    # Compute nominal effective HDD
    from .combine_corrections import compute_effective_hdd
    effective_hdd = compute_effective_hdd(
        base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction
    )

    # Compute uncertainty for each component using error propagation
    # For base_hdd × terrain_mult: σ_product = sqrt((σ_base × terrain_mult)² + (base_hdd × σ_terrain)²)
    base_terrain_uncertainty = np.sqrt(
        (base_hdd_sigma * terrain_mult) ** 2 + (base_hdd * terrain_mult_sigma) ** 2
    )

    # For additive/subtractive terms: σ_sum = sqrt(σ_elev² + σ_uhi² + σ_traffic²)
    additive_uncertainty = np.sqrt(
        elev_addition_sigma ** 2 + uhi_reduction_sigma ** 2 + traffic_reduction_sigma ** 2
    )

    # Combined uncertainty using root-sum-of-squares
    total_uncertainty = np.sqrt(base_terrain_uncertainty ** 2 + additive_uncertainty ** 2)

    # Compute bounds at ±1 standard deviation
    effective_hdd_low = effective_hdd - total_uncertainty
    effective_hdd_high = effective_hdd + total_uncertainty

    return effective_hdd_low, effective_hdd_high


def compute_effective_hdd_bounds_per_cell(
    cell_df: pd.DataFrame,
    base_hdd_col: str = "prism_annual_hdd",
    terrain_mult_col: str = "hdd_terrain_mult",
    elev_addition_col: str = "hdd_elev_addition",
    uhi_reduction_col: str = "hdd_uhi_reduction",
    traffic_reduction_col: str = "hdd_traffic_reduction",
) -> pd.DataFrame:
    """
    Compute uncertainty bounds for a DataFrame of cells.

    This function applies compute_effective_hdd_bounds to each row of a DataFrame,
    adding two new columns: effective_hdd_low and effective_hdd_high.

    Parameters
    ----------
    cell_df : pd.DataFrame
        DataFrame with one row per cell, containing correction component columns.
    base_hdd_col : str, optional
        Name of the base HDD column. Default: "prism_annual_hdd".
    terrain_mult_col : str, optional
        Name of the terrain multiplier column. Default: "hdd_terrain_mult".
    elev_addition_col : str, optional
        Name of the elevation addition column. Default: "hdd_elev_addition".
    uhi_reduction_col : str, optional
        Name of the UHI reduction column. Default: "hdd_uhi_reduction".
    traffic_reduction_col : str, optional
        Name of the traffic reduction column. Default: "hdd_traffic_reduction".

    Returns
    -------
    pd.DataFrame
        Input DataFrame with two new columns added:
        - effective_hdd_low: Lower bound on effective HDD
        - effective_hdd_high: Upper bound on effective HDD

    Raises
    ------
    KeyError
        If any required column is missing from the DataFrame.
    """
    result_df = cell_df.copy()

    # Compute bounds for each row
    low, high = compute_effective_hdd_bounds(
        result_df[base_hdd_col],
        result_df[terrain_mult_col],
        result_df[elev_addition_col],
        result_df[uhi_reduction_col],
        result_df[traffic_reduction_col],
    )

    result_df["effective_hdd_low"] = low
    result_df["effective_hdd_high"] = high

    return result_df


def compute_aggregate_bounds(
    cell_df: pd.DataFrame,
    effective_hdd_low_col: str = "effective_hdd_low",
    effective_hdd_high_col: str = "effective_hdd_high",
) -> Tuple[float, float]:
    """
    Compute aggregate uncertainty bounds for a ZIP code from cell-level bounds.

    For a ZIP code aggregate, the bounds are computed as the mean of the cell-level
    bounds, which represents the uncertainty in the aggregate effective_hdd value.

    Parameters
    ----------
    cell_df : pd.DataFrame
        DataFrame with one row per cell, containing effective_hdd_low and effective_hdd_high.
    effective_hdd_low_col : str, optional
        Name of the low bound column. Default: "effective_hdd_low".
    effective_hdd_high_col : str, optional
        Name of the high bound column. Default: "effective_hdd_high".

    Returns
    -------
    Tuple[float, float]
        (aggregate_low, aggregate_high) representing the bounds on the ZIP-code aggregate.
    """
    aggregate_low = cell_df[effective_hdd_low_col].mean()
    aggregate_high = cell_df[effective_hdd_high_col].mean()
    return aggregate_low, aggregate_high


def validate_bounds_physically_reasonable(
    effective_hdd: float | np.ndarray | pd.Series,
    effective_hdd_low: float | np.ndarray | pd.Series,
    effective_hdd_high: float | np.ndarray | pd.Series,
    tolerance: float = 1e-6,
) -> bool:
    """
    Validate that bounds are physically reasonable: low < nominal < high.

    Parameters
    ----------
    effective_hdd : float, np.ndarray, or pd.Series
        Nominal effective HDD value.
    effective_hdd_low : float, np.ndarray, or pd.Series
        Lower bound on effective HDD.
    effective_hdd_high : float, np.ndarray, or pd.Series
        Upper bound on effective HDD.
    tolerance : float, optional
        Floating-point tolerance for comparisons. Default: 1e-6.

    Returns
    -------
    bool
        True if all bounds are physically reasonable (low < nominal < high),
        False otherwise.

    Notes
    -----
    - Allows for floating-point rounding errors via tolerance parameter
    - Returns False if any bound violates the ordering constraint
    """
    # Convert to numpy arrays for element-wise comparison
    if isinstance(effective_hdd, pd.Series):
        effective_hdd = effective_hdd.values
    if isinstance(effective_hdd_low, pd.Series):
        effective_hdd_low = effective_hdd_low.values
    if isinstance(effective_hdd_high, pd.Series):
        effective_hdd_high = effective_hdd_high.values

    # Check that low < nominal < high (with tolerance)
    low_valid = np.all(effective_hdd_low <= effective_hdd + tolerance)
    high_valid = np.all(effective_hdd_high >= effective_hdd - tolerance)
    ordering_valid = np.all(effective_hdd_low <= effective_hdd_high + tolerance)

    return low_valid and high_valid and ordering_valid
