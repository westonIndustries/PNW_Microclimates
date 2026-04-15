"""
MesoWest wind loader.

Loads per-station wind observation CSV files from ``MESOWEST_WIND_DIR``,
aggregates to annual mean wind speed and 90th-percentile wind speed per station,
and returns a dictionary keyed by station ID.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import MESOWEST_WIND_DIR, STATION_HDD_NORMALS

logger = logging.getLogger(__name__)


def load_mesowest_wind() -> dict[str, dict]:
    """Load MesoWest wind observations and aggregate to annual statistics.

    Loads all CSV files from ``MESOWEST_WIND_DIR`` matching station IDs in
    ``STATION_HDD_NORMALS``. For each station, computes:
    - ``mean_wind_ms``: annual mean wind speed (m/s)
    - ``p90_wind_ms``: 90th-percentile wind speed (m/s)

    Returns
    -------
    dict[str, dict]
        Dictionary keyed by station ID (e.g., ``"KPDX"``), with values being
        dicts containing ``mean_wind_ms`` and ``p90_wind_ms`` keys.

    Raises
    ------
    FileNotFoundError
        If ``MESOWEST_WIND_DIR`` does not exist.

    Notes
    -----
    - Expected CSV columns: ``date_time``, ``wind_speed_set_1`` (m/s)
    - Missing or invalid wind speed values are skipped
    - Stations with no valid observations are excluded from the output
    """
    wind_dir = MESOWEST_WIND_DIR.resolve()

    if not wind_dir.exists():
        raise FileNotFoundError(
            f"MesoWest wind directory not found: {wind_dir}"
        )

    result = {}

    # Iterate over all known stations
    for station_id in STATION_HDD_NORMALS.keys():
        csv_path = wind_dir / f"{station_id}.csv"

        if not csv_path.exists():
            logger.warning(f"Wind CSV not found for station {station_id}: {csv_path}")
            continue

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            logger.warning(f"Failed to read wind CSV for station {station_id}: {e}")
            continue

        # Validate required columns
        if "wind_speed_set_1" not in df.columns:
            logger.warning(
                f"Wind CSV for station {station_id} missing 'wind_speed_set_1' column"
            )
            continue

        # Extract wind speed column and drop NaN values
        wind_speeds = pd.to_numeric(df["wind_speed_set_1"], errors="coerce")
        wind_speeds = wind_speeds.dropna()

        if len(wind_speeds) == 0:
            logger.warning(f"No valid wind speed observations for station {station_id}")
            continue

        # Compute statistics
        mean_wind = float(wind_speeds.mean())
        p90_wind = float(wind_speeds.quantile(0.90))

        result[station_id] = {
            "mean_wind_ms": mean_wind,
            "p90_wind_ms": p90_wind,
        }

        logger.info(
            f"Station {station_id}: mean={mean_wind:.2f} m/s, p90={p90_wind:.2f} m/s"
        )

    if not result:
        logger.warning("No valid MesoWest wind data loaded for any station")

    return result
