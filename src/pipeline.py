"""
Regional Microclimate Modeling Engine — Main Pipeline Orchestrator

Orchestrates the full pipeline: normals mode, daily mode, hourly mode, and
real-time mode. Provides CLI entry point with support for all operating modes.
"""

import argparse
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd

from src.config import TERRAIN_ATTRIBUTES_CSV, DAILY_OUTPUT_DIR
from src.processors.daily_combine import run_daily_pipeline
from src.output.write_daily_output import write_daily_output
from src.output.write_safety_cube import write_safety_cube

logger = logging.getLogger(__name__)


def publish_run_folder(
    region_name: str,
    mode: str,
    output_files: List[str],
    weather_year: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    step_times: Optional[Dict[str, float]] = None,
) -> Path:
    """
    Assemble a self-contained output folder with all pipeline artifacts.

    Creates a folder with naming convention:
    `output/runs/{region}__{weather_year or "normal"}__{YYYYMMDDTHHMM}/`

    Copies all output files (GeoJSONs, maps, CSVs, Parquets, QA reports) and
    creates a run_manifest.json with metadata.

    Parameters
    ----------
    region_name : str
        Region name (e.g., "region_1")
    mode : str
        Operating mode (normals, daily, hourly, both, realtime)
    output_files : list
        List of output file paths to include
    weather_year : int, optional
        Year for weather adjustment (None for normals)
    start_date : str, optional
        ISO 8601 start date for daily/hourly modes
    end_date : str, optional
        ISO 8601 end date for daily/hourly modes
    step_times : dict, optional
        Timing information for each pipeline step

    Returns
    -------
    Path
        Path to the published run folder
    """
    # Create runs directory
    runs_dir = Path("output/runs")
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Generate folder name
    weather_label = weather_year if weather_year else "normal"
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M")
    run_folder_name = f"{region_name}__{weather_label}__{timestamp}"
    run_folder = runs_dir / run_folder_name

    # Create run folder and subdirectories
    run_folder.mkdir(parents=True, exist_ok=True)
    geojson_dir = run_folder / "geojson"
    geojson_dir.mkdir(exist_ok=True)

    logger.info(f"Publishing run folder to {run_folder}")

    # Copy output files
    copied_files = []
    for output_file in output_files:
        output_path = Path(output_file)
        if not output_path.exists():
            logger.warning(f"Output file not found: {output_file}")
            continue

        # Determine destination based on file type
        if output_path.suffix == ".geojson":
            dest = geojson_dir / output_path.name
        elif output_path.name.endswith(".html"):
            dest = run_folder / output_path.name
        elif output_path.suffix in [".csv", ".parquet"]:
            dest = run_folder / output_path.name
        elif output_path.name in ["qa_report.html", "qa_report.md", "pipeline.log"]:
            dest = run_folder / output_path.name
        else:
            dest = run_folder / output_path.name

        try:
            shutil.copy2(output_path, dest)
            copied_files.append(dest.name)
            logger.debug(f"Copied {output_path} to {dest}")
        except Exception as e:
            logger.warning(f"Failed to copy {output_path}: {e}")

    # Copy terrain_attributes.csv if it exists
    if Path(TERRAIN_ATTRIBUTES_CSV).exists():
        try:
            shutil.copy2(TERRAIN_ATTRIBUTES_CSV, run_folder / "terrain_attributes.csv")
            copied_files.append("terrain_attributes.csv")
        except Exception as e:
            logger.warning(f"Failed to copy terrain_attributes.csv: {e}")

    # Copy QA reports if they exist
    qa_report_html = Path("output/microclimate/qa_report.html")
    qa_report_md = Path("output/microclimate/qa_report.md")
    if qa_report_html.exists():
        try:
            shutil.copy2(qa_report_html, run_folder / "qa_report.html")
            copied_files.append("qa_report.html")
        except Exception as e:
            logger.warning(f"Failed to copy qa_report.html: {e}")
    if qa_report_md.exists():
        try:
            shutil.copy2(qa_report_md, run_folder / "qa_report.md")
            copied_files.append("qa_report.md")
        except Exception as e:
            logger.warning(f"Failed to copy qa_report.md: {e}")

    # Create run_manifest.json
    manifest: Dict[str, Any] = {
        "region_name": region_name,
        "mode": mode,
        "weather_year": weather_year,
        "start_date": start_date,
        "end_date": end_date,
        "run_date": datetime.utcnow().isoformat(),
        "pipeline_version": "1.0.0",
        "lidar_vintage": 2021,
        "nlcd_vintage": 2021,
        "prism_period": "1991-2020",
        "files": sorted(copied_files),
    }

    # Add timing information if available
    if step_times:
        manifest["timing"] = step_times

    manifest_path = run_folder / "run_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info(f"Created run_manifest.json with {len(copied_files)} files")

    logger.info(f"Run folder published to {run_folder}")
    return run_folder


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
        - 'timing': dict with timing information
    """
    import time
    
    start_time = time.time()
    step_times = {}

    logger.info(f"Starting pipeline for region={region_name}, mode={mode}")

    # Create output directory for logs
    output_dir = Path("output/microclimate") / region_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Set up file logging
    log_file = output_dir / f"pipeline_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    logging.getLogger().addHandler(file_handler)

    logger.info(f"Logging to {log_file}")

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
            normals_start = time.time()
            # TODO: Implement normals mode pipeline
            normals_time = time.time() - normals_start
            step_times["normals"] = normals_time
            logger.info(f"Normals mode completed in {normals_time:.2f} seconds")

        # Daily mode
        if mode in ["daily", "both"]:
            logger.info(f"Running daily mode for {start_date} to {end_date}")
            daily_start = time.time()

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

            daily_time = time.time() - daily_start
            step_times["daily"] = daily_time
            logger.info(f"Daily mode completed in {daily_time:.2f} seconds")

        # Hourly mode (runs after daily if mode="both")
        if mode in ["hourly", "both"] and start_date and end_date:
            logger.info(f"Running hourly mode for {start_date} to {end_date}")
            hourly_start = time.time()

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

            # Import hourly pipeline
            from src.processors.hourly_orchestrator import run_hourly_pipeline
            from src.output.write_hourly_output import write_hourly_output

            # Run hourly pipeline
            hourly_data = run_hourly_pipeline(
                region_name=region_name,
                start_date=start_date,
                end_date=end_date,
                terrain_corrections_df=terrain_df,
                zip_code_centroids=zip_centroids,
                hrrr_source=hrrr_source,
            )

            # Write hourly output
            hourly_output_path = write_hourly_output(
                hourly_data,
                region_name=region_name,
                start_date=start_date,
                end_date=end_date,
            )
            output_files.append(str(hourly_output_path))
            logger.info(f"Hourly output written to {hourly_output_path}")

            hourly_time = time.time() - hourly_start
            step_times["hourly"] = hourly_time
            logger.info(f"Hourly mode completed in {hourly_time:.2f} seconds")

        # Real-time mode
        if mode in ["realtime"]:
            logger.info("Starting real-time daemon mode")
            realtime_start = time.time()
            from src.realtime.daemon import run_daemon

            run_daemon(
                region_name=region_name,
                poll_interval_sec=300,
                lookback_hours=2,
                foreground=True,
            )
            realtime_time = time.time() - realtime_start
            step_times["realtime"] = realtime_time
            logger.info(f"Real-time daemon completed in {realtime_time:.2f} seconds")

        # Calculate total timing
        total_time = time.time() - start_time
        step_times["total"] = total_time
        logger.info(f"Pipeline completed in {total_time:.2f} seconds")

        # Publish run folder
        try:
            run_folder = publish_run_folder(
                region_name=region_name,
                mode=mode,
                output_files=output_files,
                weather_year=weather_year,
                start_date=start_date,
                end_date=end_date,
                step_times=step_times,
            )
            logger.info(f"Run artifacts published to {run_folder}")
        except Exception as e:
            logger.warning(f"Failed to publish run folder: {e}")
            run_folder = None

        return {
            "status": "success",
            "region": region_name,
            "mode": mode,
            "output_files": output_files,
            "run_folder": str(run_folder) if run_folder else None,
            "timing": step_times,
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

    # Handle --all-regions flag
    if args.all_regions:
        logger.info("Running pipeline for all regions in registry")
        # Load region registry
        try:
            region_registry = pd.read_csv("data/boundary/region_registry.csv")
            regions = region_registry["region_code"].unique()
            logger.info(f"Found {len(regions)} regions: {regions}")

            for region in regions:
                logger.info(f"\n{'='*60}")
                logger.info(f"Processing region: {region}")
                logger.info(f"{'='*60}\n")

                result = run_region(
                    region_name=region,
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
                    all_regions=False,
                )

                if result["status"] == "error":
                    logger.error(f"Region {region} failed: {result['message']}")
                else:
                    logger.info(f"Region {region} completed successfully")

        except Exception as e:
            logger.error(f"Failed to process all regions: {e}", exc_info=True)
            exit(1)
    else:
        # Run pipeline for single region
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
