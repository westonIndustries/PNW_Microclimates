"""Download Census TIGER/Line boundary shapefiles."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def download_boundaries(args):
    """
    Download boundary shapefiles.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments with:
        - output_dir: output directory
        - force_redownload: force re-download
        - dry_run: print steps without executing
    """
    output_dir = args.output_dir / "boundary"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Boundary shapefile download not yet implemented")
    logger.info("Please download manually from:")
    logger.info("  https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html")
    logger.info("  Select: State Boundaries (for OR/WA)")
    logger.info("  Select: ZIP Code Tabulation Areas (ZCTA)")
    logger.info(f"  Place files at: {output_dir}")

    if args.dry_run:
        logger.info(f"[DRY RUN] Would download boundary shapefiles to {output_dir}")
