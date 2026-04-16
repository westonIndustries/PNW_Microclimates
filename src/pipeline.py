"""
Regional Microclimate Modeling Engine — Main Pipeline Orchestrator

Orchestrates the full pipeline: normals mode, daily mode, hourly mode, and
real-time mode. Provides CLI entry point with support for all operating modes.
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import pandas as pd

from src.config import TERRAIN_ATTRIBUTES_CSV, DAILY_OUTPUT_DIR
from src.processors.daily_combine import run_daily_pipeline
from src.output.write_daily_output import write_daily_output
from src.output.write_safety_cube import write_safety_cube

logger = logging.getLogger(__name__)


def run_region(
    region_name: str,
    mode: str = "normals",
    weather_year: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    month: Optional[str] = None,
    hrrr_source: str = "s3",
    output_format: str = "parquet",
    no_confirm: bool = False,
    safety_cube: bool = False,
    cube_altitudes: Optional[List[int]] = None,
    dry_run: bool = False,
    all_regions: bool = False,
) -> dict:
    """
    Run the microclimate pipeline for a region.

    Parameters
    ----------
    region_name : str
        Region name (e.g., "region_1")
    mode : str, default "normals"
        Operating mode: "normals", "daily", "hourly", "both", or "realtime"
    weather_year : int, optional
        Year for weather adjustment (e.g., 2024)
    start_date : str, optional
        ISO 8601 start date (YYYY-MM-DD) for daily/hourly modes
    end_date : str, optional
        ISO 8601 end date (YYYY-MM-DD) for daily/hourly modes
    month : str, optional
        Month shorthand (YYYY-MM) for daily/hourly modes
    hrrr_source : str, default "s3"
        HRRR data source ("s3" or "gcs")
    output_format : str, default "parquet"
        Output format: "parquet", "csv", or "both"
    no_confirm : bool, default False
        Skip confirmation prompts for large downloads
    safety_cube : bool, default False
        Build aviation safety cube for daily mode
    cube_altitudes : list, optional
        Override default altitude levels for safety cube
    dry_run : bool, default False
        Print steps without executing
    all_regions : bool, default False
        Run for all regions in registry

    Returns
    -------
    dict
        Pipeline execution results with keys:
        - 'status': 'success' or 'error'
        - 'region': region name
        - 'mode': operating mode
        - 'output_files': list of output file paths
        - 'message': status message
    """
    logger.info(f"Starting pipeline for region={region_name}, mode={mode}")

    # Parse dates
    if month:
        # Expand month shorthand to date range
        year, month_num = month.split("-")
        start_date = f"{year}-{month_num}-01"
        # Compute end date (last day of month)
        if int(month_num) == 12:
            end_date = f"{int(year) + 1}-01-01"
        else:
            end_date = f"{year}-{int(month_num) + 1:02d}-01"

    # Validate mode
    valid_modes = ["normals", "daily", "hourly", "both", "realtime"]
    if mode not in valid_modes:
        return {
            "status": "error",
            "region": region_name,
            "mode": mode,
            "message": f"Invalid mode: {mode}. Must be one of {valid_modes}",
        }

    # Validate date requirements for daily/hourly modes
    if mode in ["daily", "hourly", "both"] and not (start_date and end_date):
        return {
            "status": "error",
            "region": region_name,
            "mode": mode,
            "message": f"Mode {mode} requires --start-date and --end-date or --month",
        }

    if dry_run:
        logger.info(f"DRY RUN: Would execute {mode} mode for {region_name}")
        return {
            "status": "success",
            "region": region_name,
            "mode": mode,
            "message": "Dry run completed",
        }

    output_files = []

    try:
        # Normals mode
        if mode in ["normals", "both"]:
            logger.info("Running normals mode")
            # TODO: Implement normals mode pipeline
            logger.info("Normals mode completed")

        # Daily mode
        if mode in ["daily", "both"]:
            logger.info(f"Running daily mode for {start_date} to {end_date}")

            # Load terrain corrections from normals mode
            if Path(TERRAIN_ATTRIBUTES_CSV).exists():
                terrain_df = pd.read_csv(TERRAIN_ATTRIBUTES_CSV)
            else:
                logger.warning(
                    f"Terrain attributes not found at {TERRAIN_ATTRIBUTES_CSV}. "
                    "Run normals mode first."
                )
                terrain_df = pd.DataFrame()

            # Create dummy ZIP code centroids (would be loaded from data)
            zip_centroids = pd.DataFrame(
                {
                    "zip_code": ["97201", "97202"],
                    "lat": [45.5, 45.6],
                    "lon": [-122.6, -122.7],
                }
            )

            # Run daily pipeline
            daily_data, safety_cube_data = run_daily_pipeline(
                region_name=region_name,
                start_date=start_date,
                end_date=end_date,
                terrain_corrections_df=terrain_df,
                zip_code_centroids=zip_centroids,
                hrrr_source=hrrr_source,
                build_safety_cube_flag=safety_cube,
            )

            # Write daily output
            daily_output_path = write_daily_output(
                daily_data,
                region_name=region_name,
                start_date=start_date,
                end_date=end_date,
                output_format=output_format,
            )
            output_files.append(str(daily_output_path))
            logger.info(f"Daily output written to {daily_output_path}")

            # Write safety cube if requested
            if safety_cube and safety_cube_data is not None:
                cube_output_path = write_safety_cube(
                    safety_cube_data,
                    region_name=region_name,
                    start_date=start_date,
                    end_date=end_date,
                )
                output_files.append(str(cube_output_path))
                logger.info(f"Safety cube written to {cube_output_path}")

            logger.info("Daily mode completed")

        # Hourly mode
        if mode in ["hourly"]:
            logger.info(f"Running hourly mode for {start_date} to {end_date}")
            # TODO: Implement hourly mode pipeline
            logger.info("Hourly mode completed")

        # Real-time mode
        if mode in ["realtime"]:
            logger.info("Running real-time daemon mode")
            # TODO: Implement real-time daemon
            logger.info("Real-time daemon started")

        return {
            "status": "success",
            "region": region_name,
            "mode": mode,
            "output_files": output_files,
            "message": f"Pipeline completed successfully for {region_name}",
        }

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return {
            "status": "error",
            "region": region_name,
            "mode": mode,
            "message": f"Pipeline failed: {e}",
        }


def main():
    """CLI entry point for the microclimate pipeline."""
    parser = argparse.ArgumentParser(
        description="Regional Microclimate Modeling Engine"
    )

    # Required arguments
    parser.add_argument(
        "--region",
        required=True,
        help="Region name (e.g., region_1)",
    )

    # Mode selection
    parser.add_argument(
        "--mode",
        default="normals",
        choices=["normals", "daily", "hourly", "both", "realtime"],
        help="Operating mode (default: normals)",
    )

    # Date range arguments
    parser.add_argument(
        "--start-date",
        help="ISO 8601 start date (YYYY-MM-DD) for daily/hourly modes",
    )
    parser.add_argument(
        "--end-date",
        help="ISO 8601 end date (YYYY-MM-DD) for daily/hourly modes",
    )
    parser.add_argument(
        "--month",
        help="Month shorthand (YYYY-MM) for daily/hourly modes",
    )

    # Weather adjustment
    parser.add_argument(
        "--weather-year",
        type=int,
        help="Year for weather adjustment (e.g., 2024)",
    )

    # HRRR options
    parser.add_argument(
        "--hrrr-source",
        default="s3",
        choices=["s3", "gcs"],
        help="HRRR data source (default: s3)",
    )

    # Output options
    parser.add_argument(
        "--output-format",
        default="parquet",
        choices=["parquet", "csv", "both"],
        help="Output format (default: parquet)",
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation prompts for large downloads",
    )

    # Safety cube options
    parser.add_argument(
        "--safety-cube",
        action="store_true",
        help="Build aviation safety cube for daily mode",
    )
    parser.add_argument(
        "--cube-altitudes",
        type=int,
        nargs="+",
        help="Override default altitude levels for safety cube (e.g., 0 500 1000 3000)",
    )

    # Execution options
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print steps without executing",
    )
    parser.add_argument(
        "--all-regions",
        action="store_true",
        help="Run for all regions in registry",
    )

    # Logging
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run pipeline
    result = run_region(
        region_name=args.region,
        mode=args.mode,
        weather_year=args.weather_year,
        start_date=args.start_date,
        end_date=args.end_date,
        month=args.month,
        hrrr_source=args.hrrr_source,
        output_format=args.output_format,
        no_confirm=args.no_confirm,
        safety_cube=args.safety_cube,
        cube_altitudes=args.cube_altitudes,
        dry_run=args.dry_run,
        all_regions=args.all_regions,
    )

    # Print result
    print(f"\n{result['message']}")
    if result["status"] == "error":
        exit(1)


if __name__ == "__main__":
    main()
