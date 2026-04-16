"""Download NOAA station metadata."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def download_noaa_stations(args):
    """
    Download NOAA station metadata.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments with:
        - output_dir: output directory
        - force_redownload: force re-download
        - dry_run: print steps without executing
    """
    output_dir = args.output_dir / "noaa"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "station_metadata.csv"

    if output_file.exists() and not args.force_redownload:
        logger.info(f"NOAA station metadata already exists at {output_file}")
        return

    logger.info("NOAA station metadata download not yet implemented")
    logger.info("Please download manually from:")
    logger.info("  https://www.ncei.noaa.gov/products/land-based-station-data-climate-normals/")
    logger.info("  Select: 1991-2020 Climate Normals")
    logger.info("  Download station list with coordinates and HDD normals")
    logger.info(f"  Place file at: {output_file}")

    if args.dry_run:
        logger.info(f"[DRY RUN] Would download NOAA station metadata to {output_file}")
