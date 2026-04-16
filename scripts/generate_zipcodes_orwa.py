"""
Generate merged ZIP code boundary layer for Oregon and Washington.

This script builds a merged ZIP code boundary layer from three sources in
priority order:
1. Oregon Metro RLIS (most accurate for Portland metro area)
2. OpenDataSoft US ZIP Boundaries (better attributes than Census)
3. Census TIGER/Line ZCTA (fallback for full coverage)

Usage:
    python scripts/generate_zipcodes_orwa.py
    python scripts/generate_zipcodes_orwa.py --source-dir data/boundary/sources
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
TARGET_CRS = "EPSG:4326"
STATES = ["OR", "WA"]
REGION_CODE = "R1"

# Census TIGER/Line ZCTA URLs
TIGER_ZCTA_URL_TEMPLATE = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_zcta520_500k.zip"


def load_rlis_zipcodes(source_dir: Path) -> gpd.GeoDataFrame | None:
    """Load Oregon Metro RLIS ZIP code boundaries if available.

    Parameters
    ----------
    source_dir : Path
        Directory containing source files.

    Returns
    -------
    gpd.GeoDataFrame or None
        GeoDataFrame with RLIS ZIP codes, or None if file not found.
    """
    rlis_path = source_dir / "rlis_zipcodes.geojson"

    if not rlis_path.exists():
        logger.info("RLIS ZIP codes not found (optional)")
        return None

    logger.info(f"Loading RLIS ZIP codes from {rlis_path}...")
    gdf = gpd.read_file(rlis_path)
    gdf = gdf.to_crs(TARGET_CRS)

    # Ensure required columns
    if "zip_code" not in gdf.columns:
        if "ZIPCODE" in gdf.columns:
            gdf["zip_code"] = gdf["ZIPCODE"].astype(str).str.zfill(5)
        else:
            logger.warning("  RLIS file missing zip_code column, skipping")
            return None

    gdf["source"] = "rlis"
    logger.info(f"  Loaded {len(gdf)} RLIS ZIP codes")

    return gdf


def load_opendata_zipcodes(source_dir: Path) -> gpd.GeoDataFrame | None:
    """Load OpenDataSoft US ZIP code boundaries if available.

    Parameters
    ----------
    source_dir : Path
        Directory containing source files.

    Returns
    -------
    gpd.GeoDataFrame or None
        GeoDataFrame with OpenDataSoft ZIP codes, or None if file not found.
    """
    opendata_path = source_dir / "opendata_zipcodes_orwa.geojson"

    if not opendata_path.exists():
        logger.info("OpenDataSoft ZIP codes not found (optional)")
        return None

    logger.info(f"Loading OpenDataSoft ZIP codes from {opendata_path}...")
    gdf = gpd.read_file(opendata_path)
    gdf = gdf.to_crs(TARGET_CRS)

    # Ensure required columns
    if "zip_code" not in gdf.columns:
        if "code" in gdf.columns:
            gdf["zip_code"] = gdf["code"].astype(str).str.zfill(5)
        else:
            logger.warning("  OpenDataSoft file missing zip_code column, skipping")
            return None

    gdf["source"] = "opendata"
    logger.info(f"  Loaded {len(gdf)} OpenDataSoft ZIP codes")

    return gdf


def load_census_zcta(states: list[str]) -> gpd.GeoDataFrame:
    """Load Census TIGER/Line ZCTA boundaries.

    Parameters
    ----------
    states : list[str]
        List of state abbreviations to filter.

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame with Census ZCTA boundaries.
    """
    logger.info("Loading Census TIGER/Line ZCTA boundaries...")

    # Download ZCTA data
    gdf = gpd.read_file(TIGER_ZCTA_URL_TEMPLATE)
    gdf = gdf.to_crs(TARGET_CRS)

    # Rename ZCTA5CE20 to zip_code
    if "ZCTA5CE20" in gdf.columns:
        gdf["zip_code"] = gdf["ZCTA5CE20"].astype(str).str.zfill(5)
    elif "ZCTA5CE23" in gdf.columns:
        gdf["zip_code"] = gdf["ZCTA5CE23"].astype(str).str.zfill(5)
    else:
        raise ValueError("Census ZCTA file missing expected ZCTA column")

    gdf["source"] = "census"
    logger.info(f"  Loaded {len(gdf)} Census ZCTA boundaries")

    return gdf


def filter_to_states(gdf: gpd.GeoDataFrame, states: list[str]) -> gpd.GeoDataFrame:
    """Filter ZIP codes to specified states using spatial join with state boundaries.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame with ZIP code boundaries.
    states : list[str]
        List of state abbreviations.

    Returns
    -------
    gpd.GeoDataFrame
        Filtered GeoDataFrame with only ZIP codes in specified states.
    """
    logger.info(f"Filtering ZIP codes to states: {', '.join(states)}...")

    # Load state boundaries
    state_url = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip"
    state_gdf = gpd.read_file(state_url)
    state_gdf = state_gdf.to_crs(TARGET_CRS)

    # Filter to target states
    state_gdf = state_gdf[state_gdf["STUSPS"].isin(states)]

    # Spatial join to find ZIP codes in target states
    joined = gpd.sjoin(gdf, state_gdf[["STUSPS", "geometry"]], how="inner", predicate="intersects")
    joined = joined.rename(columns={"STUSPS": "state"})

    # Keep only unique ZIP codes (take first match if multiple states)
    joined = joined.drop_duplicates(subset=["zip_code"], keep="first")

    logger.info(f"  Filtered to {len(joined)} ZIP codes in {', '.join(states)}")

    return joined


def merge_zipcodes(
    rlis_gdf: gpd.GeoDataFrame | None,
    opendata_gdf: gpd.GeoDataFrame | None,
    census_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Merge ZIP code boundaries from multiple sources with priority.

    Parameters
    ----------
    rlis_gdf : gpd.GeoDataFrame or None
        RLIS ZIP codes (highest priority).
    opendata_gdf : gpd.GeoDataFrame or None
        OpenDataSoft ZIP codes (medium priority).
    census_gdf : gpd.GeoDataFrame
        Census ZCTA boundaries (fallback).

    Returns
    -------
    gpd.GeoDataFrame
        Merged GeoDataFrame with all ZIP codes.
    """
    logger.info("Merging ZIP code boundaries from multiple sources...")

    # Start with RLIS if available
    if rlis_gdf is not None:
        merged = rlis_gdf.copy()
        used_zips = set(merged["zip_code"].unique())
    else:
        merged = gpd.GeoDataFrame()
        used_zips = set()

    # Add OpenDataSoft ZIP codes not in RLIS
    if opendata_gdf is not None:
        opendata_new = opendata_gdf[~opendata_gdf["zip_code"].isin(used_zips)]
        merged = pd.concat([merged, opendata_new], ignore_index=True)
        used_zips.update(opendata_new["zip_code"].unique())

    # Add Census ZCTA ZIP codes not in RLIS or OpenDataSoft
    census_new = census_gdf[~census_gdf["zip_code"].isin(used_zips)]
    merged = pd.concat([merged, census_new], ignore_index=True)

    logger.info(f"  Merged {len(merged)} total ZIP codes")
    logger.info(f"    - RLIS: {len(merged[merged['source'] == 'rlis']) if 'source' in merged.columns else 0}")
    logger.info(f"    - OpenDataSoft: {len(merged[merged['source'] == 'opendata']) if 'source' in merged.columns else 0}")
    logger.info(f"    - Census: {len(merged[merged['source'] == 'census']) if 'source' in merged.columns else 0}")

    return merged


def add_metadata(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add metadata columns to ZIP code GeoDataFrame.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame with ZIP code boundaries.

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame with added metadata columns.
    """
    logger.info("Adding metadata columns...")

    # Add region code
    gdf["region_code"] = REGION_CODE

    # Add place name if not present
    if "po_name" not in gdf.columns:
        gdf["po_name"] = ""

    # Compute centroids
    gdf["centroid_lon"] = gdf.geometry.centroid.x
    gdf["centroid_lat"] = gdf.geometry.centroid.y

    return gdf


def write_outputs(gdf: gpd.GeoDataFrame, output_dir: Path) -> None:
    """Write ZIP code boundaries to GeoJSON and CSV files.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame with ZIP code boundaries.
    output_dir : Path
        Output directory.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write GeoJSON
    geojson_path = output_dir / "zipcodes_orwa.geojson"
    logger.info(f"Writing GeoJSON to {geojson_path}...")

    # Select columns for GeoJSON
    geojson_cols = ["zip_code", "state", "po_name", "region_code", "source"]
    geojson_gdf = gdf[geojson_cols + ["geometry"]].copy()
    geojson_gdf.to_file(geojson_path, driver="GeoJSON")

    # Write CSV
    csv_path = output_dir / "zipcodes_orwa.csv"
    logger.info(f"Writing CSV to {csv_path}...")

    csv_cols = ["zip_code", "state", "po_name", "region_code", "centroid_lon", "centroid_lat"]
    csv_gdf = gdf[csv_cols].copy()
    csv_gdf.to_csv(csv_path, index=False)

    logger.info(f"  Wrote {geojson_path}")
    logger.info(f"  Wrote {csv_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate merged ZIP code boundary layer for OR + WA"
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("data/boundary/sources"),
        help="Directory containing optional source files (RLIS, OpenDataSoft)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/boundary"),
        help="Output directory for generated files",
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Generating merged ZIP code boundaries for OR + WA")
    logger.info("=" * 70)

    # Load ZIP codes from each source
    rlis_gdf = load_rlis_zipcodes(args.source_dir)
    opendata_gdf = load_opendata_zipcodes(args.source_dir)
    census_gdf = load_census_zcta(STATES)

    # Filter Census ZCTA to target states
    census_gdf = filter_to_states(census_gdf, STATES)

    # Merge from multiple sources
    merged_gdf = merge_zipcodes(rlis_gdf, opendata_gdf, census_gdf)

    # Add metadata
    merged_gdf = add_metadata(merged_gdf)

    # Write outputs
    write_outputs(merged_gdf, args.output_dir)

    logger.info("=" * 70)
    logger.info("ZIP code boundary generation complete!")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
