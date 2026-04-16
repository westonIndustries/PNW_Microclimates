"""Download MesoWest wind observations."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def download_mesowest(args):
    """
    Download MesoWest wind observations.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments with:
        - output_dir: output directory
        - force_redownload: force re-download
        - dry_run: print steps without executing
    """
    output_dir = args.output_dir / "mesowest"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("MesoWest wind download not yet implemented")
    logger.info("This requires SynopticLabs API key")
    logger.info("Sign up at: https://synopticlabs.org/")
    logger.info("Set environment variable: SYNOPTIC_API_KEY=<your_key>")
    logger.info(f"Output directory: {output_dir}")

    if args.dry_run:
        logger.info(f"[DRY RUN] Would download MesoWest wind data to {output_dir}")
