"""
Generate region_1 boundary and registry data from Census TIGER/Line.

This script fetches Oregon and Washington state boundary polygons from the
Census TIGER/Line dataset, dissolves them into a single region_1 polygon,
and generates the region_registry.csv file with ZIP code assignments.

Usage:
    python scripts/generate_region1_boundary.py
    python scripts/generate_region1_boundary.py --source-dir data/boundary/sources
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
REGION_CODE = "R1"
REGION_NAME = "region_1"
STATES = ["OR", "WA"]
TARGET_CRS = "EPSG:4326"
TIGER_URL_TEMPLATE = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_{state}_state_500k.zip"

# Expected bounding box for OR/WA (EPSG:4326)
EXPECTED_BBOX = {"minx": -124.8, "miny": 41.9, "maxx": -116.9, "maxy": 49.1}


def fetch_state_boundaries(states: list[str], source_dir: Path | None = None) -> gpd.GeoDataFrame:
    """Fetch state boundary polygons from Census TIGER/Line.

    Parameters
    ----------
    states : list[str]
        List of state abbreviations (e.g., ['OR', 'WA']).
    source_dir : Path, optional
        Directory containing pre-downloaded shapefiles. If provided, will look for
        files named `cb_2023_{state}_state_500k.shp` before downloading.

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame with state boundary polygons in EPSG:4326.
    """
    gdfs = []

    for state in states:
        logger.info(f"Fetching boundary for {state}...")

        # Check if pre-downloaded file exists
        if source_dir:
            local_shp = source_dir / f"cb_2023_{state.lower()}_state_500k.shp"
            if local_shp.exists():
                logger.info(f"  Loading from local file: {local_shp}")
                gdf = gpd.read_file(local_shp)
                gdf = gdf.to_crs(TARGET_CRS)
                gdfs.append(gdf)
                continue

        # Download from Census TIGER/Line
        url = TIGER_URL_TEMPLATE.format(state=state.lower())
        logger.info(f"  Downloading from {url}")
        try:
            gdf = gpd.read_file(url)
            gdf = gdf.to_crs(TARGET_CRS)
            gdfs.append(gdf)
        except Exception as e:
            logger.error(f"  Failed to download {state} boundary: {e}")
            raise

    # Combine all state boundaries
    combined = pd.concat(gdfs, ignore_index=True)
    logger.info(f"Loaded boundaries for {len(combined)} state(s)")

    return combined


def dissolve_to_region(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Dissolve state boundaries into a single region polygon.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame with state boundary polygons.

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame with a single row containing the dissolved region polygon.
    """
    logger.info("Dissolving state boundaries into single region polygon...")

    # Dissolve all geometries into one
    dissolved = gdf.dissolve(by=None, aggfunc="first")

    # Add region metadata
    dissolved["region_code"] = REGION_CODE
    dissolved["region_name"] = REGION_NAME
    dissolved["states"] = ",".join(STATES)

    # Compute bounding box
    bounds = dissolved.geometry.total_bounds
    dissolved["bbox_minx"] = bounds[0]
    dissolved["bbox_miny"] = bounds[1]
    dissolved["bbox_maxx"] = bounds[2]
    dissolved["bbox_maxy"] = bounds[3]

    logger.info(
        f"Region bounding box: "
        f"minx={bounds[0]:.2f}, miny={bounds[1]:.2f}, "
        f"maxx={bounds[2]:.2f}, maxy={bounds[3]:.2f}"
    )

    return dissolved


def write_region_geojson(gdf: gpd.GeoDataFrame, output_path: Path) -> None:
    """Write region polygon to GeoJSON file.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame with region polygon.
    output_path : Path
        Output file path.
    """
    logger.info(f"Writing region GeoJSON to {output_path}...")

    # Prepare feature for GeoJSON
    feature = {
        "type": "Feature",
        "properties": {
            "region_code": gdf["region_code"].iloc[0],
            "region_name": gdf["region_name"].iloc[0],
            "states": gdf["states"].iloc[0],
            "bounding_box": {
                "minx": float(gdf["bbox_minx"].iloc[0]),
                "miny": float(gdf["bbox_miny"].iloc[0]),
                "maxx": float(gdf["bbox_maxx"].iloc[0]),
                "maxy": float(gdf["bbox_maxy"].iloc[0]),
            },
        },
        "geometry": json.loads(gdf.geometry.iloc[0].geom_type),
    }

    # Write as GeoJSON FeatureCollection
    feature_collection = {
        "type": "FeatureCollection",
        "features": [feature],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(feature_collection, f, indent=2)

    logger.info(f"  Wrote {output_path}")


def generate_region_registry(
    region_gdf: gpd.GeoDataFrame,
    zipcodes_csv: Path,
    output_path: Path,
) -> None:
    """Generate region_registry.csv from region and ZIP code data.

    Parameters
    ----------
    region_gdf : gpd.GeoDataFrame
        GeoDataFrame with region polygon.
    zipcodes_csv : Path
        Path to zipcodes_orwa.csv file.
    output_path : Path
        Output file path for region_registry.csv.
    """
    logger.info(f"Generating region registry from {zipcodes_csv}...")

    # Load ZIP code data
    if not zipcodes_csv.exists():
        logger.warning(f"ZIP code file not found: {zipcodes_csv}")
        logger.info("Creating minimal region registry with no ZIP codes...")
        # Create minimal registry with just the region definition
        registry_df = pd.DataFrame({
            "zip_code": [],
            "state": [],
            "region_code": [],
            "region_name": [],
            "base_station": [],
            "lidar_vintage": [],
        })
    else:
        zipcodes_df = pd.read_csv(zipcodes_csv)

        # Assign all ZIP codes to region_1
        registry_df = zipcodes_df[["zip_code", "state"]].copy()
        registry_df["region_code"] = REGION_CODE
        registry_df["region_name"] = REGION_NAME
        registry_df["base_station"] = ""  # Will be filled in by load_region_registry.py
        registry_df["lidar_vintage"] = 2021  # Default vintage

        logger.info(f"Assigned {len(registry_df)} ZIP codes to {REGION_NAME}")

    # Write registry
    output_path.parent.mkdir(parents=True, exist_ok=True)
    registry_df.to_csv(output_path, index=False)
    logger.info(f"  Wrote {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate region_1 boundary and registry from Census TIGER/Line"
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Directory containing pre-downloaded TIGER/Line shapefiles",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/boundary"),
        help="Output directory for generated files",
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Generating region_1 boundary and registry")
    logger.info("=" * 70)

    # Fetch state boundaries
    state_gdf = fetch_state_boundaries(STATES, source_dir=args.source_dir)

    # Dissolve to region
    region_gdf = dissolve_to_region(state_gdf)

    # Write region GeoJSON
    geojson_path = args.output_dir / "region_1.geojson"
    write_region_geojson(region_gdf, geojson_path)

    # Generate region registry
    zipcodes_csv = args.output_dir / "zipcodes_orwa.csv"
    registry_path = args.output_dir / "region_registry.csv"
    generate_region_registry(region_gdf, zipcodes_csv, registry_path)

    logger.info("=" * 70)
    logger.info("Region boundary generation complete!")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
