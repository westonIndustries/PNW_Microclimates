"""
Combine terrain, elevation, UHI, and traffic corrections into effective HDD and CDD.

This module provides the core formulas for computing effective heating degree days (HDD)
and cooling degree days (CDD) by combining the atmospheric base with all terrain and
surface corrections.
"""

import numpy as np
import pandas as pd


def compute_effective_hdd(
    base_hdd: float | np.ndarray | pd.Series,
    terrain_mult: float | np.ndarray | pd.Series,
    elev_addition: float | np.ndarray | pd.Series,
    uhi_reduction: float | np.ndarray | pd.Series,
    traffic_reduction: float | np.ndarray | pd.Series,
) -> float | np.ndarray | pd.Series:
    """
    Compute effective HDD by combining all corrections.

    Formula:
        effective_hdd = base_hdd × terrain_mult + elev_addition − uhi_reduction − traffic_reduction

    Parameters
    ----------
    base_hdd : float, np.ndarray, or pd.Series
        Atmospheric base HDD (°F-days, base 65°F) from PRISM or HRRR.
    terrain_mult : float, np.ndarray, or pd.Series
        Terrain position multiplier (windward/leeward/valley/ridge).
        Typical range: 0.95–1.20.
    elev_addition : float, np.ndarray, or pd.Series
        HDD addition from elevation lapse rate above base station (°F-days).
        Computed as: (elevation_ft − station_elevation_ft) / 1000 × 630.
    uhi_reduction : float, np.ndarray, or pd.Series
        HDD reduction from urban heat island effect (positive value = reduction).
        Computed as: uhi_offset_f × 180.
    traffic_reduction : float, np.ndarray, or pd.Series
        HDD reduction from anthropogenic road heat (positive value = reduction).
        Computed as: road_temp_offset_f × 180.

    Returns
    -------
    float, np.ndarray, or pd.Series
        Effective HDD with all corrections applied. Type matches input type.

    Notes
    -----
    - All inputs must have compatible shapes for broadcasting.
    - Negative effective_hdd values are physically possible (e.g., in warm urban areas)
      but are flagged in QA checks as implausible for PNW climate if < 2,000 or > 8,000.
    - The formula is additive for corrections, not multiplicative, to preserve
      physical meaning of temperature offsets.
    """
    effective_hdd = base_hdd * terrain_mult + elev_addition - uhi_reduction - traffic_reduction
    return effective_hdd


def compute_effective_cdd(
    base_cdd: float | np.ndarray | pd.Series,
    terrain_mult: float | np.ndarray | pd.Series,
    elev_addition: float | np.ndarray | pd.Series,
    uhi_addition: float | np.ndarray | pd.Series,
    traffic_addition: float | np.ndarray | pd.Series,
) -> float | np.ndarray | pd.Series:
    """
    Compute effective CDD (Cooling Degree Days) by combining all corrections.

    CDD is the inverse of HDD: higher temperatures increase cooling demand.
    UHI and traffic heat INCREASE CDD (warming effect in summer), opposite of HDD.

    Formula:
        effective_cdd = base_cdd × terrain_mult + elev_addition + uhi_addition + traffic_addition

    Parameters
    ----------
    base_cdd : float, np.ndarray, or pd.Series
        Atmospheric base CDD (°F-days, base 65°F) from PRISM or HRRR.
    terrain_mult : float, np.ndarray, or pd.Series
        Terrain position multiplier (windward/leeward/valley/ridge).
        Typical range: 0.95–1.20. Same as HDD.
    elev_addition : float | np.ndarray | pd.Series
        CDD addition from elevation lapse rate above base station (°F-days).
        Computed as: (elevation_ft − station_elevation_ft) / 1000 × 630.
        Negative for higher elevations (cooler = less cooling demand).
    uhi_addition : float | np.ndarray | pd.Series
        CDD addition from urban heat island effect (positive value = increase).
        Computed as: uhi_offset_f × 180.
        Opposite sign from HDD (UHI reduces HDD, increases CDD).
    traffic_addition : float | np.ndarray | pd.Series
        CDD addition from anthropogenic road heat (positive value = increase).
        Computed as: road_temp_offset_f × 180.
        Opposite sign from HDD (traffic reduces HDD, increases CDD).

    Returns
    -------
    float, np.ndarray, or pd.Series
        Effective CDD with all corrections applied. Type matches input type.

    Notes
    -----
    - All inputs must have compatible shapes for broadcasting.
    - CDD values are typically 0–2,000 for PNW climate (much lower than HDD).
    - The formula is additive for corrections, not multiplicative, to preserve
      physical meaning of temperature offsets.
    - UHI and traffic heat have opposite signs in CDD vs HDD:
      - HDD: effective_hdd = base_hdd × terrain_mult + elev - uhi - traffic
      - CDD: effective_cdd = base_cdd × terrain_mult + elev + uhi + traffic
    """
    effective_cdd = base_cdd * terrain_mult + elev_addition + uhi_addition + traffic_addition
    return effective_cdd
