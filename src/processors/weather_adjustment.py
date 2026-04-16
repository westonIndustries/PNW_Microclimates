"""
Weather adjustment processor for the Regional Microclimate Modeling Engine.

Applies optional weather year adjustment to effective HDD values by scaling
them with the ratio of actual to normal station HDD for a specified year.

The adjustment factor is computed per station:
    adjustment = actual_station_hdd / normal_station_hdd

Then applied to all cells assigned to that station:
    effective_hdd_adjusted = effective_hdd × adjustment

This allows calibration runs to reflect observed weather rather than
climate normals.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import STATION_HDD_NORMALS

logger = logging.getLogger(__name__)


def compute_weather_adjustment_factors(
    weather_year: int,
    weather_data_dir: Optional[Path] = None,
) -> dict[str, float]:
    """
    Compute weather adjustment factors per station for a given year.

    The adjustment factor for each station is:
        adjustment = actual_station_hdd / normal_station_hdd

    where:
    - actual_station_hdd: observed HDD for the weather_year at that station
    - normal_station_hdd: 1991-2020 climate normal HDD from config.py

    Parameters
    ----------
    weather_year : int
        The year for which to compute adjustment factors (e.g., 2024).
    weather_data_dir : Path, optional
        Directory containing actual HDD data by station and year.
        If None, defaults to data/weather/ or raises an error if not found.

    Returns
    -------
    dict[str, float]
        Mapping of station ICAO code to adjustment factor.
        Example: {"KPDX": 1.05, "KEUG": 0.98, ...}

    Raises
    ------
    FileNotFoundError
        If weather data for the specified year cannot be found.
    ValueError
        If a station has no actual HDD data for the specified year.
    """
    if weather_data_dir is None:
        weather_data_dir = Path("data/weather/")

    # Construct path to weather data file for the specified year
    # Expected format: data/weather/actual_hdd_{year}.csv
    # CSV columns: station_code, actual_hdd
    weather_file = weather_data_dir / f"actual_hdd_{weather_year}.csv"

    if not weather_file.exists():
        raise FileNotFoundError(
            f"Weather data file not found: {weather_file}. "
            f"Please ensure actual HDD data for {weather_year} is available."
        )

    # Load actual HDD data
    try:
        actual_hdd_df = pd.read_csv(weather_file)
    except Exception as e:
        raise ValueError(
            f"Failed to read weather data from {weather_file}: {e}"
        )

    # Validate required columns
    if "station_code" not in actual_hdd_df.columns or "actual_hdd" not in actual_hdd_df.columns:
        raise ValueError(
            f"Weather data file must contain 'station_code' and 'actual_hdd' columns. "
            f"Found columns: {list(actual_hdd_df.columns)}"
        )

    # Build adjustment factors
    adjustment_factors = {}
    for station_code, normal_hdd in STATION_HDD_NORMALS.items():
        station_data = actual_hdd_df[actual_hdd_df["station_code"] == station_code]

        if station_data.empty:
            raise ValueError(
                f"No actual HDD data found for station {station_code} in {weather_year}. "
                f"Available stations: {actual_hdd_df['station_code'].unique().tolist()}"
            )

        actual_hdd = station_data["actual_hdd"].iloc[0]

        # Compute adjustment factor
        if normal_hdd <= 0:
            logger.warning(
                f"Station {station_code} has non-positive normal HDD ({normal_hdd}). "
                f"Skipping adjustment for this station."
            )
            adjustment_factors[station_code] = 1.0
        else:
            adjustment_factors[station_code] = actual_hdd / normal_hdd

        logger.debug(
            f"Station {station_code}: actual_hdd={actual_hdd}, "
            f"normal_hdd={normal_hdd}, adjustment={adjustment_factors[station_code]:.4f}"
        )

    logger.info(
        f"Computed weather adjustment factors for {len(adjustment_factors)} stations "
        f"for year {weather_year}"
    )

    return adjustment_factors


def apply_weather_adjustment(
    terrain_df: pd.DataFrame,
    adjustment_factors: dict[str, float],
) -> pd.DataFrame:
    """
    Apply weather adjustment to a terrain attributes DataFrame.

    For each row, the adjustment factor is looked up by the station code
    in the base_station column, and effective_hdd is scaled accordingly.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with columns: base_station, effective_hdd, and others.
        Typically loaded from terrain_attributes.csv or produced by
        combine_corrections_cells.py.
    adjustment_factors : dict[str, float]
        Mapping of station ICAO code to adjustment factor.

    Returns
    -------
    pd.DataFrame
        Copy of terrain_df with two new columns:
        - effective_hdd_adjusted: adjusted HDD values
        - weather_adjustment_factor: the factor applied to each row
        Original effective_hdd column is retained.

    Raises
    ------
    KeyError
        If a station in terrain_df is not found in adjustment_factors.
    """
    df = terrain_df.copy()

    # Validate that all stations in the DataFrame have adjustment factors
    missing_stations = set(df["base_station"].unique()) - set(adjustment_factors.keys())
    if missing_stations:
        raise KeyError(
            f"Adjustment factors not found for stations: {missing_stations}. "
            f"Available stations: {list(adjustment_factors.keys())}"
        )

    # Map adjustment factors to each row
    df["weather_adjustment_factor"] = df["base_station"].map(adjustment_factors)

    # Apply adjustment: effective_hdd_adjusted = effective_hdd × adjustment_factor
    df["effective_hdd_adjusted"] = df["effective_hdd"] * df["weather_adjustment_factor"]

    logger.info(
        f"Applied weather adjustment to {len(df)} rows. "
        f"Mean adjustment factor: {df['weather_adjustment_factor'].mean():.4f}"
    )

    return df


def adjust_effective_hdd(
    terrain_df: pd.DataFrame,
    weather_year: Optional[int] = None,
    weather_data_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Optionally adjust effective HDD values based on actual weather for a given year.

    This is the main entry point for weather adjustment. If weather_year is None,
    the DataFrame is returned unchanged. Otherwise, adjustment factors are computed
    and applied.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with columns: base_station, effective_hdd, and others.
    weather_year : int, optional
        Year for which to apply weather adjustment (e.g., 2024).
        If None, no adjustment is applied and the original DataFrame is returned.
    weather_data_dir : Path, optional
        Directory containing actual HDD data by station and year.
        If None, defaults to data/weather/.

    Returns
    -------
    pd.DataFrame
        DataFrame with weather adjustment applied (if weather_year is not None).
        If weather_year is None, returns the input DataFrame unchanged.
        If adjustment is applied, includes effective_hdd_adjusted and
        weather_adjustment_factor columns.

    Raises
    ------
    FileNotFoundError
        If weather data for the specified year cannot be found.
    ValueError
        If a station has no actual HDD data for the specified year.
    KeyError
        If a station in terrain_df is not found in adjustment_factors.
    """
    if weather_year is None:
        logger.info("No weather year specified. Returning DataFrame unchanged.")
        return terrain_df

    logger.info(f"Applying weather adjustment for year {weather_year}")

    # Compute adjustment factors
    adjustment_factors = compute_weather_adjustment_factors(
        weather_year=weather_year,
        weather_data_dir=weather_data_dir,
    )

    # Apply adjustment
    adjusted_df = apply_weather_adjustment(
        terrain_df=terrain_df,
        adjustment_factors=adjustment_factors,
    )

    return adjusted_df
