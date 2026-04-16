"""Download Landsat 9 LST from Microsoft Planetary Computer."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def download_landsat(args):
    """
    Download Landsat 9 LST.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments with:
        - region: region name
        - output_dir: output directory
        - force_redownload: force re-download
        - dry_run: print steps without executing
    """
    output_dir = args.output_dir / "landsat"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Landsat 9 LST download not yet implemented")
    logger.info("This requires pystac-client and access to Microsoft Planetary Computer")
    logger.info("Installation: pip install pystac-client")
    logger.info("Query: https://planetarycomputer.microsoft.com/")
    logger.info(f"Output directory: {output_dir}")

    if args.dry_run:
        logger.info(f"[DRY RUN] Would download Landsat 9 LST to {output_dir}")
