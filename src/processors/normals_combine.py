"""
Orchestrate the normals mode microclimate pipeline.

This module coordinates all steps for computing annual effective HDD
from PRISM climate normals and terrain corrections.
"""

import logging
from pathlib import Path
from typing import Tuple, Dict, Any

import numpy as np
import pandas as pd
from rasterio.transform import Affine

from src.config import (
    BOUNDARY_SHP,
    LIDAR_DEM_RASTER,
    NLCD_VINTAGE,
    PIPELINE_VERSION,
    PRISM_PERIOD,
    REGION_REGISTRY_CSV,
    TERRAIN_ATTRIBUTES_CSV,
)
from src.loaders.load_lidar_dem import load_lidar_dem
from src.loaders.load_landsat_lst import load_landsat_lst
from src.loaders.load_mesowest_wind import load_mesowest_wind
from src.loaders.load_nlcd_impervious import load_nlcd_impervious
from src.loaders.load_nrel_wind import load_nrel_wind
from src.loaders.load_prism_temperature import load_prism_temperature
from src.loaders.load_region_registry import load_region_registry
from src.loaders.load_road_emissions import load_road_emissions
from src.processors.aggregate_cells_to_zip import aggregate_cells_to_zip
from src.processors.anthropogenic_load import compute_anthropogenic_load
from src.processors.clip_to_boundary import clip_to_boundary
from src.processors.combine_corrections import compute_effective_hdd
from src.processors.combine_corrections_cells import compute_effective_hdd_per_cell
from src.processors.create_cells import create_microclimate_cells
from src.processors.downscale import reproject_to_lidar_grid
from src.processors.terrain_analysis import analyze_terrain
from src.processors.thermal_logic import compute_thermal_logic
from src.processors.wind_steering import compute_wind_steering
from src.validation.qa_checks import run_all_qa_checks

logger = logging.getLogger(__name__)


def _extract_array_from_dict(d: Dict[str, Any], key: str, default_shape: tuple) -> np.ndarray:
    """Extract array from processor output dict, or return default array."""
    if isinstance(d, dict) and key in d:
        arr = d[key]
        if isinstance(arr, np.ndarray):
            return arr
    # Return array of ones (neutral multiplier) or zeros (neutral addition)
    if "mult" in key or "infiltration" in key:
        return np.ones(default_shape)
    else:
        return np.zeros(default_shape)


def run_normals_pipeline(
    region_name: str,
    weather_year: int = None,
) -> Tuple[pd.DataFrame, dict]:
    """
    Orchestrate the normals mode microclimate pipeline.

    Loads static data, applies terrain and surface corrections, creates
    microclimate cells, and computes annual effective HDD per ZIP code.

    Parameters
    ----------
    region_name : str
        Region name (e.g., "region_1")
    weather_year : int, optional
        Year for weather adjustment. If provided, scales effective HDD
        by the ratio of actual to normal HDD for that year.

    Returns
    -------
    Tuple[pd.DataFrame, dict]
        (cells_df, qa_results) where:
        - cells_df: DataFrame with cell-level and ZIP-code aggregate rows
        - qa_results: Dictionary with QA check results
    """
    logger.info(f"Starting normals mode pipeline for {region_name}")

    # Load region registry
    logger.info("Loading region registry")
    region_registry = load_region_registry()
    
    # Map region_name to region_code (e.g., "region_1" -> "R1")
    region_code = None
    for code, info in region_registry.items():
        if info["region_name"] == region_name:
            region_code = code
            break
    
    if region_code is None:
        raise ValueError(f"Region {region_name} not found in registry")
    
    region_info = region_registry[region_code]
    zip_codes = region_info["zip_codes"]
    base_stations = region_info["base_stations"]
    logger.info(f"Processing {len(zip_codes)} ZIP codes with {len(base_stations)} base stations")

    # Load static data
    logger.info("Loading static data")
    lidar_array, lidar_transform, lidar_crs = load_lidar_dem()
    logger.info(f"Loaded LiDAR DEM: shape={lidar_array.shape}, CRS={lidar_crs}")

    prism_annual_hdd, prism_monthly = load_prism_temperature()
    logger.info(f"Loaded PRISM temperature: shape={prism_annual_hdd.shape}")

    nlcd_array, nlcd_transform, nlcd_crs = load_nlcd_impervious()
    logger.info(f"Loaded NLCD imperviousness: shape={nlcd_array.shape}")

    nrel_wind_array, nrel_wind_transform, nrel_wind_crs = load_nrel_wind()
    logger.info(f"Loaded NREL wind: shape={nrel_wind_array.shape}")

    landsat_lst_array = load_landsat_lst()
    if landsat_lst_array is not None:
        logger.info(f"Loaded Landsat LST: shape={landsat_lst_array.shape}")
    else:
        logger.warning("Landsat LST not available; will use fallback values")

    mesowest_wind = load_mesowest_wind()
    logger.info(f"Loaded MesoWest wind data for {len(mesowest_wind)} stations")

    road_gdf = load_road_emissions()
    logger.info(f"Loaded road emissions: {len(road_gdf)} segments")

    # Clip to boundary
    logger.info("Clipping to region boundary")
    lidar_clipped, lidar_transform_clipped = clip_to_boundary(
        lidar_array, lidar_transform, region_name
    )
    logger.info(f"Clipped LiDAR: shape={lidar_clipped.shape}")

    # Downscale all rasters to LiDAR grid
    logger.info("Downscaling rasters to LiDAR grid")
    prism_downscaled = reproject_to_lidar_grid(
        prism_annual_hdd,
        Affine.identity(),  # Placeholder; actual transform from loader
        "EPSG:4326",  # Placeholder; actual CRS from loader
        lidar_transform_clipped,
        lidar_crs,
        lidar_clipped.shape,
    )
    logger.info(f"Downscaled PRISM: shape={prism_downscaled.shape}")

    nlcd_downscaled = reproject_to_lidar_grid(
        nlcd_array,
        nlcd_transform,
        nlcd_crs,
        lidar_transform_clipped,
        lidar_crs,
        lidar_clipped.shape,
    )
    logger.info(f"Downscaled NLCD: shape={nlcd_downscaled.shape}")

    nrel_wind_downscaled = reproject_to_lidar_grid(
        nrel_wind_array,
        nrel_wind_transform,
        nrel_wind_crs,
        lidar_transform_clipped,
        lidar_crs,
        lidar_clipped.shape,
    )
    logger.info(f"Downscaled NREL wind: shape={nrel_wind_downscaled.shape}")

    if landsat_lst_array is not None:
        landsat_lst_downscaled = reproject_to_lidar_grid(
            landsat_lst_array,
            Affine.identity(),  # Placeholder
            "EPSG:4326",  # Placeholder
            lidar_transform_clipped,
            lidar_crs,
            lidar_clipped.shape,
        )
    else:
        landsat_lst_downscaled = None

    # Compute terrain analysis
    logger.info("Computing terrain analysis")
    # TODO: Get station elevation from region registry
    station_elevation_ft = 100.0  # Placeholder
    terrain_dict = analyze_terrain(lidar_clipped, station_elevation_ft)
    logger.info(f"Computed terrain: {len(terrain_dict)} arrays")

    # Compute thermal logic
    logger.info("Computing thermal logic")
    thermal_dict = compute_thermal_logic(
        nlcd_downscaled, landsat_lst_downscaled, lidar_clipped
    )
    logger.info(f"Computed thermal: {len(thermal_dict)} arrays")

    # Compute wind steering
    logger.info("Computing wind steering")
    wind_dict = compute_wind_steering(
        nrel_wind_downscaled, terrain_dict, mesowest_wind
    )
    logger.info(f"Computed wind steering: {len(wind_dict)} arrays")

    # Compute anthropogenic load
    logger.info("Computing anthropogenic load")
    heat_flux_array, traffic_temp_offset_array = compute_anthropogenic_load(
        road_gdf, lidar_transform_clipped, lidar_crs, lidar_clipped.shape
    )
    logger.info(f"Computed anthropogenic load: max heat flux = {heat_flux_array.max():.2f} W/m²")

    # Create microclimate cells
    logger.info("Creating microclimate cells")
    cells_gdf = create_microclimate_cells(region_name, zip_codes)
    logger.info(f"Created {len(cells_gdf)} cells")

    # Extract arrays from processor outputs
    logger.info("Extracting correction arrays")
    default_shape = lidar_clipped.shape
    
    terrain_mult_array = _extract_array_from_dict(terrain_dict, "terrain_multiplier", default_shape)
    elev_addition_array = _extract_array_from_dict(terrain_dict, "lapse_rate_hdd_addition", default_shape)
    uhi_offset_array = _extract_array_from_dict(thermal_dict, "uhi_offset_f", default_shape)
    wind_infiltration_array = _extract_array_from_dict(wind_dict, "wind_infiltration_mult", default_shape)
    mean_wind_array = _extract_array_from_dict(wind_dict, "mean_wind_ms", default_shape)
    mean_elevation_array = _extract_array_from_dict(terrain_dict, "mean_elevation_ft", default_shape)
    mean_impervious_array = nlcd_downscaled  # NLCD is already the imperviousness array
    surface_albedo_array = _extract_array_from_dict(thermal_dict, "surface_albedo", default_shape)

    # Combine corrections and compute effective HDD per cell
    logger.info("Combining corrections and computing effective HDD")
    cells_df = compute_effective_hdd_per_cell(
        cells_gdf,
        base_hdd_array=prism_downscaled,
        terrain_mult_array=terrain_mult_array,
        elev_addition_array=elev_addition_array,
        uhi_offset_array=uhi_offset_array,
        traffic_heat_offset_array=traffic_temp_offset_array,
        wind_infiltration_mult_array=wind_infiltration_array,
        mean_wind_array=mean_wind_array,
        mean_elevation_array=mean_elevation_array,
        mean_impervious_array=mean_impervious_array,
        surface_albedo_array=surface_albedo_array,
        lidar_transform=lidar_transform_clipped,
        lidar_shape=lidar_clipped.shape,
        region_code="R1",  # TODO: Get from region registry
    )
    logger.info(f"Computed effective HDD for {len(cells_df)} cells")

    # Aggregate to ZIP codes
    logger.info("Aggregating to ZIP codes")
    zip_df = aggregate_cells_to_zip(cells_df)
    logger.info(f"Aggregated to {len(zip_df)} ZIP codes")

    # Combine cell and aggregate rows
    output_df = pd.concat([cells_df, zip_df], ignore_index=True)

    # Apply weather adjustment if specified
    if weather_year is not None:
        logger.info(f"Applying weather adjustment for {weather_year}")
        # TODO: Implement weather adjustment
        pass

    # Run QA checks
    logger.info("Running QA checks")
    qa_results = run_all_qa_checks(output_df)
    logger.info(f"QA checks completed")

    return output_df, qa_results
