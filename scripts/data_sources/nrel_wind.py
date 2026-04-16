"""Download NREL wind resource map (80m hub height, 2km)."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def download_nrel_wind(args):
    """
    Download NREL wind resource.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments with:
        - output_dir: output directory
        - force_redownload: force re-download
        - dry_run: print steps without executing
    """
    output_dir = args.output_dir / "nrel_wind"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "nrel_wind_80m.tif"

    if output_file.exists() and not args.force_redownload:
        logger.info(f"NREL wind resource already exists at {output_file}")
        return

    logger.info("NREL wind resource download not yet implemented")
    logger.info("Please download manually from:")
    logger.info("  https://data.nrel.gov/submissions/4")
    logger.info("  Select: 80m hub height wind speed")
    logger.info("  Download for Oregon and Washington")
    logger.info(f"  Place file at: {output_file}")

    if args.dry_run:
        logger.info(f"[DRY RUN] Would download NREL wind resource to {output_file}")
