"""Download 1m LiDAR DEM from OpenTopography (USGS 3DEP)."""

import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Region bounds (Oregon and Washington)
REGION_BOUNDS = {
    "region_1": {
        "south": 42.0,
        "north": 49.0,
        "west": -124.5,
        "east": -116.5,
    }
}


def download_lidar(args):
    """
    Download 1m LiDAR DEM from OpenTopography.

    Uses the bmi-topography library to access USGS 3DEP data via
    OpenTopography REST API. Data is automatically cached locally.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments with:
        - region: region name
        - output_dir: output directory
        - force_redownload: force re-download
        - dry_run: print steps without executing
        - verbose: enable verbose logging
    """
    output_dir = Path(args.output_dir) / "lidar"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "dem_1m.tif"

    if output_file.exists() and not args.force_redownload:
        logger.info(f"✓ LiDAR DEM already exists at {output_file}")
        return

    if args.dry_run:
        logger.info(f"[DRY RUN] Would download LiDAR DEM to {output_file}")
        return

    # Check for API key
    api_key = os.environ.get("OPENTOPOGRAPHY_API_KEY")
    if not api_key:
        logger.warning("OPENTOPOGRAPHY_API_KEY environment variable not set")
        logger.info("Get a free API key from: https://opentopography.org")
        logger.info("Then set: export OPENTOPOGRAPHY_API_KEY=your_key_here")
        logger.info("\nAlternatively, download manually from:")
        logger.info("  https://portal.opentopography.org/raster?source=USGS%203DEP%20Raster")
        logger.info(f"  Place file at: {output_file}")
        return

    try:
        from bmi_topography import Topography
    except ImportError:
        logger.error("bmi-topography not installed")
        logger.info("Install with: pip install bmi-topography")
        return

    # Get region bounds
    if args.region not in REGION_BOUNDS:
        logger.error(f"Unknown region: {args.region}")
        logger.info(f"Available regions: {list(REGION_BOUNDS.keys())}")
        return

    bounds = REGION_BOUNDS[args.region]

    logger.info(f"Downloading 1m LiDAR DEM for {args.region}...")
    logger.info(f"Bounds: ({bounds['south']}, {bounds['west']}) to ({bounds['north']}, {bounds['east']})")

    try:
        # Create Topography instance
        params = {
            "dem_type": "USGS1m",
            "south": bounds["south"],
            "north": bounds["north"],
            "west": bounds["west"],
            "east": bounds["east"],
            "output_format": "GTiff",
            "cache_dir": str(output_dir / ".cache"),
        }

        topo = Topography(**params)

        # Fetch data (automatically cached)
        logger.info("Fetching from OpenTopography...")
        filepath = topo.fetch()
        logger.info(f"✓ Downloaded to cache: {filepath}")

        # Load and save to final location
        logger.info("Loading and processing DEM...")
        da = topo.load()

        # Extract array and replace nodata with NaN
        array = da.values[0]  # Remove band dimension
        array = np.where(array == 0, np.nan, array).astype(np.float32)

        # Save to output file using rasterio
        import rasterio
        from rasterio.transform import from_bounds

        # Get bounds from xarray
        coords = da.coords
        y_vals = coords["y"].values
        x_vals = coords["x"].values

        # Create transform
        transform = from_bounds(
            x_vals.min(),
            y_vals.min(),
            x_vals.max(),
            y_vals.max(),
            array.shape[1],
            array.shape[0],
        )

        # Write to GeoTIFF
        with rasterio.open(
            output_file,
            "w",
            driver="GTiff",
            height=array.shape[0],
            width=array.shape[1],
            count=1,
            dtype=array.dtype,
            crs="EPSG:4326",
            transform=transform,
            nodata=np.nan,
        ) as dst:
            dst.write(array, 1)

        logger.info(f"✓ Saved to: {output_file}")
        logger.info(f"  Shape: {array.shape}")
        logger.info(f"  Dtype: {array.dtype}")
        logger.info(f"  CRS: EPSG:4326 (WGS84)")

    except Exception as e:
        logger.error(f"Failed to download LiDAR DEM: {e}")
        logger.info("\nTroubleshooting:")
        logger.info("1. Check API key: export OPENTOPOGRAPHY_API_KEY=your_key")
        logger.info("2. Get free key: https://opentopography.org")
        logger.info("3. Check internet connection")
        logger.info("4. Check request size (max 250 km² for 1m DEM)")
        if args.verbose:
            logger.exception("Full traceback:")
