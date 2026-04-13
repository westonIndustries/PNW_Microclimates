"""
Region registry loader and generator.

Responsibilities
----------------
(a) **Generate** — if ``REGION_REGISTRY_CSV`` does not exist or contains only
    headers, build it from ``zipcodes_orwa.csv`` by assigning every OR/WA zip
    code to region R1, computing the nearest NOAA station via haversine, and
    writing the result.

(b) **Load** — read the CSV, group by ``region_code``, and return a dict of
    region definitions used by the pipeline at startup.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import (
    REGION_REGISTRY_CSV,
    STATION_COORDS,
    STATION_HDD_NORMALS,
    ZIPCODES_CSV,
)


# ---------------------------------------------------------------------------
# Haversine helpers
# ---------------------------------------------------------------------------

_EARTH_RADIUS_KM = 6_371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in km between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = (
        math.radians(lat1),
        math.radians(lon1),
        math.radians(lat2),
        math.radians(lon2),
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _nearest_station(lat: float, lon: float) -> str:
    """Return the ICAO code of the nearest NOAA station to *(lat, lon)*."""
    best_code: str | None = None
    best_dist = float("inf")
    for code in STATION_HDD_NORMALS:
        slat, slon = STATION_COORDS[code]
        d = _haversine_km(lat, lon, slat, slon)
        if d < best_dist:
            best_dist = d
            best_code = code
    assert best_code is not None
    return best_code


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _csv_has_data(path: Path) -> bool:
    """Return True if *path* exists and contains at least one data row."""
    if not path.exists():
        return False
    with open(path, "r") as fh:
        lines = [line.strip() for line in fh if line.strip()]
    return len(lines) > 1  # header + at least one data row


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_region_registry() -> pd.DataFrame:
    """Build ``region_registry.csv`` from the zip-code centroid file.

    Raises
    ------
    FileNotFoundError
        If ``zipcodes_orwa.csv`` does not exist or has no data rows.
    """
    if not _csv_has_data(ZIPCODES_CSV):
        raise FileNotFoundError(
            f"Zip-code centroid file '{ZIPCODES_CSV}' is missing or empty. "
            "Run task 7.3 (boundary processing) first to generate it."
        )

    zips = pd.read_csv(ZIPCODES_CSV)

    # Assign all zip codes to a single region
    zips["region_code"] = "R1"
    zips["region_name"] = "region_1"
    zips["lidar_vintage"] = 2021

    # Compute nearest NOAA station for each zip code centroid
    zips["base_station"] = zips.apply(
        lambda row: _nearest_station(row["centroid_lat"], row["centroid_lon"]),
        axis=1,
    )

    # Select and order output columns
    registry = zips[
        ["zip_code", "state", "region_code", "region_name", "base_station", "lidar_vintage"]
    ].copy()

    # Write to CSV
    REGION_REGISTRY_CSV.parent.mkdir(parents=True, exist_ok=True)
    registry.to_csv(REGION_REGISTRY_CSV, index=False)

    return registry


def load_region_registry() -> dict[str, dict[str, Any]]:
    """Load (and optionally generate) the region registry.

    Returns
    -------
    dict
        Keyed by ``region_code`` (e.g. ``"R1"``).  Each value is a dict with:

        - ``region_name`` — human-readable name
        - ``base_stations`` — unique list of ICAO station codes
        - ``bounding_box`` — dict with ``minx``, ``miny``, ``maxx``, ``maxy``
          (padded by 0.5° from the centroid extremes)
        - ``lidar_vintage`` — int year
        - ``zip_codes`` — list of zip-code strings
    """
    # Generate if the CSV is missing or header-only
    if not _csv_has_data(REGION_REGISTRY_CSV):
        generate_region_registry()

    registry_df = pd.read_csv(REGION_REGISTRY_CSV, dtype={"zip_code": str})

    # Merge centroid coordinates for bounding-box computation
    if _csv_has_data(ZIPCODES_CSV):
        centroids = pd.read_csv(ZIPCODES_CSV, dtype={"zip_code": str})
        registry_df = registry_df.merge(
            centroids[["zip_code", "centroid_lon", "centroid_lat"]],
            on="zip_code",
            how="left",
        )
    else:
        # Fallback: no centroids available — bounding box will be empty
        registry_df["centroid_lon"] = float("nan")
        registry_df["centroid_lat"] = float("nan")

    regions: dict[str, dict[str, Any]] = {}

    for region_code, group in registry_df.groupby("region_code"):
        # Bounding box from centroid extremes, padded by 0.5°
        lons = group["centroid_lon"].dropna()
        lats = group["centroid_lat"].dropna()

        if len(lons) > 0 and len(lats) > 0:
            bbox = {
                "minx": float(lons.min()) - 0.5,
                "miny": float(lats.min()) - 0.5,
                "maxx": float(lons.max()) + 0.5,
                "maxy": float(lats.max()) + 0.5,
            }
        else:
            bbox = {"minx": 0.0, "miny": 0.0, "maxx": 0.0, "maxy": 0.0}

        regions[str(region_code)] = {
            "region_name": str(group["region_name"].iloc[0]),
            "base_stations": sorted(group["base_station"].unique().tolist()),
            "bounding_box": bbox,
            "lidar_vintage": int(group["lidar_vintage"].iloc[0]),
            "zip_codes": group["zip_code"].tolist(),
        }

    return regions
