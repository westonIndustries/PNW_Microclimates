"""Download ODOT and WSDOT road network shapefiles with AADT."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def download_roads(args):
    """
    Download road network shapefiles.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments with:
        - output_dir: output directory
        - force_redownload: force re-download
        - dry_run: print steps without executing
    """
    output_dir = args.output_dir / "roads"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Road network download not yet implemented")
    logger.info("Please download manually from:")
    logger.info("  Oregon: https://www.oregon.gov/odot/")
    logger.info("  Washington: https://www.wsdot.wa.gov/")
    logger.info("  Look for: Road network shapefiles with AADT (Annual Average Daily Traffic)")
    logger.info(f"  Place files at: {output_dir}")

    if args.dry_run:
        logger.info(f"[DRY RUN] Would download road networks to {output_dir}")
