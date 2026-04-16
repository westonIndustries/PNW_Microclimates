"""
Data acquisition orchestrator.

Main CLI entry point for downloading and preparing all input data files
from public sources. Supports individual data source downloads or batch
download of all sources.

Usage:
    python scripts/download_data.py --download-all --region region_1
    python scripts/download_data.py lidar --region region_1 --output-dir data/lidar
    python scripts/download_data.py prism --output-dir data/prism
    python scripts/download_data.py validate --output-dir data
"""

import argparse
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Download and prepare microclimate pipeline input data"
    )

    # Global options
    parser.add_argument(
        "--region",
        default="region_1",
        help="Region name (default: region_1)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Base output directory (default: data)",
    )
    parser.add_argument(
        "--force-redownload",
        action="store_true",
        help="Force re-download even if files exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print steps without executing",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Data source to download")

    # Download all
    subparsers.add_parser(
        "download-all",
        help="Download all data sources",
    )

    # Individual data sources
    subparsers.add_parser("lidar", help="Download LiDAR DEM")
    subparsers.add_parser("prism", help="Download PRISM temperature normals")
    subparsers.add_parser("nlcd", help="Download NLCD imperviousness")
    subparsers.add_parser("landsat", help="Download Landsat 9 LST")
    subparsers.add_parser("mesowest", help="Download MesoWest wind observations")
    subparsers.add_parser("nrel-wind", help="Download NREL wind resource")
    subparsers.add_parser("roads", help="Download road network shapefiles")
    subparsers.add_parser("boundaries", help="Download boundary shapefiles")
    subparsers.add_parser("noaa-stations", help="Download NOAA station metadata")

    # Validation
    subparsers.add_parser("validate", help="Validate all downloaded data files")

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Ensure output directory exists
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Handle commands
    if args.command == "download-all":
        download_all(args)
    elif args.command == "lidar":
        from scripts.data_sources.lidar_dem import download_lidar
        download_lidar(args)
    elif args.command == "prism":
        from scripts.data_sources.prism_temperature import download_prism
        download_prism(args)
    elif args.command == "nlcd":
        from scripts.data_sources.nlcd_impervious import download_nlcd
        download_nlcd(args)
    elif args.command == "landsat":
        from scripts.data_sources.landsat_lst import download_landsat
        download_landsat(args)
    elif args.command == "mesowest":
        from scripts.data_sources.mesowest_wind import download_mesowest
        download_mesowest(args)
    elif args.command == "nrel-wind":
        from scripts.data_sources.nrel_wind import download_nrel_wind
        download_nrel_wind(args)
    elif args.command == "roads":
        from scripts.data_sources.road_emissions import download_roads
        download_roads(args)
    elif args.command == "boundaries":
        from scripts.data_sources.boundary_shapefiles import download_boundaries
        download_boundaries(args)
    elif args.command == "noaa-stations":
        from scripts.data_sources.noaa_stations import download_noaa_stations
        download_noaa_stations(args)
    elif args.command == "validate":
        from scripts.validate_data import validate_all
        validate_all(args)
    else:
        parser.print_help()
        sys.exit(1)


def download_all(args):
    """Download all data sources in sequence."""
    logger.info("Starting batch download of all data sources")

    sources = [
        ("lidar", "scripts.data_sources.lidar_dem", "download_lidar"),
        ("prism", "scripts.data_sources.prism_temperature", "download_prism"),
        ("nlcd", "scripts.data_sources.nlcd_impervious", "download_nlcd"),
        ("landsat", "scripts.data_sources.landsat_lst", "download_landsat"),
        ("mesowest", "scripts.data_sources.mesowest_wind", "download_mesowest"),
        ("nrel-wind", "scripts.data_sources.nrel_wind", "download_nrel_wind"),
        ("roads", "scripts.data_sources.road_emissions", "download_roads"),
        ("boundaries", "scripts.data_sources.boundary_shapefiles", "download_boundaries"),
        ("noaa-stations", "scripts.data_sources.noaa_stations", "download_noaa_stations"),
    ]

    for source_name, module_name, func_name in sources:
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Downloading {source_name}")
            logger.info(f"{'='*60}")

            module = __import__(module_name, fromlist=[func_name])
            func = getattr(module, func_name)
            func(args)

            logger.info(f"✓ {source_name} completed successfully")
        except Exception as e:
            logger.error(f"✗ {source_name} failed: {e}", exc_info=args.verbose)
            if not args.dry_run:
                logger.warning(f"Continuing with next source...")

    logger.info(f"\n{'='*60}")
    logger.info("Batch download complete")
    logger.info(f"{'='*60}")

    # Run validation
    logger.info("\nValidating downloaded data...")
    from scripts.validate_data import validate_all
    validate_all(args)


if __name__ == "__main__":
    main()
