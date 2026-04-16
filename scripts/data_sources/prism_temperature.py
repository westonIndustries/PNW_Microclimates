"""Download PRISM temperature normals (800m, 12 monthly files)."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def download_prism(args):
    """
    Download PRISM temperature normals.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments with:
        - output_dir: output directory
        - force_redownload: force re-download
        - dry_run: print steps without executing
    """
    output_dir = args.output_dir / "prism"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if all 12 months exist
    months = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
    all_exist = all((output_dir / f"PRISM_tmean_30yr_normal_800mM{m}_01_bil.bil").exists() for m in months)

    if all_exist and not args.force_redownload:
        logger.info(f"PRISM temperature normals already exist at {output_dir}")
        return

    logger.info("PRISM temperature download not yet implemented")
    logger.info("Please download manually from:")
    logger.info("  https://www.prism.oregonstate.edu/")
    logger.info("  Select: 30-year Normal (1991-2020)")
    logger.info("  Select: Mean Temperature")
    logger.info("  Download all 12 monthly files")
    logger.info(f"  Place files at: {output_dir}")

    if args.dry_run:
        logger.info(f"[DRY RUN] Would download PRISM temperature to {output_dir}")
