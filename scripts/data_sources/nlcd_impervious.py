"""Download NLCD 2021 imperviousness (30m) from MRLC."""

import logging
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


def download_nlcd(args):
    """
    Download NLCD 2021 imperviousness from MRLC.

    Uses PyGeoHydro to access NLCD data via MRLC GeoServer.
    Downloads imperviousness layer at 30m resolution.

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
    output_dir = Path(args.output_dir) / "nlcd"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "nlcd_2021_impervious.tif"

    if output_file.exists() and not args.force_redownload:
        logger.info(f"✓ NLCD imperviousness already exists at {output_file}")
        return

    if args.dry_run:
        logger.info(f"[DRY RUN] Would download NLCD imperviousness to {output_file}")
        return

    try:
        import pygeohydro as gh
        from shapely.geometry import box
    except ImportError:
        logger.error("pygeohydro not installed")
        logger.info("Install with: pip install pygeohydro")
        logger.info("\nAlternatively, download manually from:")
        logger.info("  https://www.mrlc.gov/data/type/urban-imperviousness")
        logger.info("  Select: NLCD 2021 Imperviousness")
        logger.info(f"  Place file at: {output_file}")
        return

    # Get region bounds
    if args.region not in REGION_BOUNDS:
        logger.error(f"Unknown region: {args.region}")
        logger.info(f"Available regions: {list(REGION_BOUNDS.keys())}")
        return

    bounds = REGION_BOUNDS[args.region]

    logger.info(f"Downloading NLCD 2021 imperviousness for {args.region}...")
    logger.info(f"Bounds: ({bounds['south']}, {bounds['west']}) to ({bounds['north']}, {bounds['east']})")

    try:
        # Create bounding box geometry
        bbox = box(bounds["west"], bounds["south"], bounds["east"], bounds["north"])

        logger.info("Fetching from MRLC GeoServer...")
        
        # Request imperviousness layer only (30m resolution)
        nlcd_data = gh.nlcd(
            bbox,
            resolution=30,
            years={"impervious": 2021, "cover": None, "canopy": None},
        )

        logger.info("✓ Downloaded from MRLC")

        # Extract imperviousness array
        impervious_array = nlcd_data.impervious.values

        # Replace nodata with NaN
        impervious_array = np.where(
            impervious_array == 0, np.nan, impervious_array
        ).astype(np.float32)

        # Save to GeoTIFF using rasterio
        import rasterio
        from rasterio.transform import from_bounds

        # Get bounds from xarray
        coords = nlcd_data.impervious.coords
        y_vals = coords["y"].values
        x_vals = coords["x"].values

        # Create transform
        transform = from_bounds(
            x_vals.min(),
            y_vals.min(),
            x_vals.max(),
            y_vals.max(),
            impervious_array.shape[1],
            impervious_array.shape[0],
        )

        # Write to GeoTIFF
        with rasterio.open(
            output_file,
            "w",
            driver="GTiff",
            height=impervious_array.shape[0],
            width=impervious_array.shape[1],
            count=1,
            dtype=impervious_array.dtype,
            crs="EPSG:4326",
            transform=transform,
            nodata=np.nan,
        ) as dst:
            dst.write(impervious_array, 1)

        logger.info(f"✓ Saved to: {output_file}")
        logger.info(f"  Shape: {impervious_array.shape}")
        logger.info(f"  Dtype: {impervious_array.dtype}")
        logger.info(f"  CRS: EPSG:4326 (WGS84)")
        logger.info(f"  Resolution: 30m")
        logger.info(f"  Year: 2021")

    except Exception as e:
        logger.error(f"Failed to download NLCD imperviousness: {e}")
        logger.info("\nTroubleshooting:")
        logger.info("1. Check internet connection")
        logger.info("2. MRLC GeoServer may be temporarily unavailable")
        logger.info("3. Request may be too large (try smaller region)")
        logger.info("\nAlternative: Download manually from:")
        logger.info("  https://www.mrlc.gov/data/type/urban-imperviousness")
        if args.verbose:
            logger.exception("Full traceback:")
