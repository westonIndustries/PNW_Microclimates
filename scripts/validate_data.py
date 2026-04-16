"""Validate all downloaded data files."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_all(args):
    """
    Validate all downloaded data files.

    Parameters
    ----------
    args : argparse.Namespace
        Command-line arguments with:
        - output_dir: output directory
        - dry_run: print steps without executing
    """
    logger.info("Starting data validation")

    data_dir = args.output_dir
    checks = {
        "LiDAR DEM": data_dir / "lidar" / "dem_1m.tif",
        "PRISM temperature": data_dir / "prism",
        "NLCD imperviousness": data_dir / "nlcd" / "nlcd_2021_impervious_l48_20230405.tif",
        "NREL wind": data_dir / "nrel_wind" / "nrel_wind_80m.tif",
        "Boundaries": data_dir / "boundary",
        "NOAA stations": data_dir / "noaa" / "station_metadata.csv",
    }

    results = {}
    for name, path in checks.items():
        if isinstance(path, Path) and path.is_dir():
            exists = path.exists() and any(path.iterdir())
        else:
            exists = path.exists()

        status = "✓" if exists else "✗"
        results[name] = exists
        logger.info(f"{status} {name}: {path}")

    # Summary
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    logger.info(f"\nValidation: {passed}/{total} checks passed")

    if passed < total:
        logger.warning("Some data files are missing. Please download them manually.")
        logger.info("Run: python scripts/download_data.py --help for more information")

    return passed == total
