"""
Anthropogenic heat load processor.

Buffers road segments by AADT tier, rasterizes buffered heat flux onto the
1 m LiDAR grid, and computes temperature offset from heat flux.
"""

from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import rasterio.features
from rasterio.crs import CRS
from rasterio.transform import Affine

logger = logging.getLogger(__name__)


def compute_anthropogenic_load(
    roads_gdf: gpd.GeoDataFrame,
    lidar_transform: Affine,
    lidar_crs: CRS,
    lidar_shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Compute road heat flux and temperature offset on the 1 m LiDAR grid.

    Buffers each road segment by AADT tier (50 m for AADT < 10,000; 100 m for
    10,000–50,000; 200 m for > 50,000), rasterizes buffered geometries with
    heat flux values onto the 1 m grid, and converts heat flux to temperature
    offset using the formula: road_temp_offset_f = road_heat_flux_wm2 / 5.5 × 9/5

    Parameters
    ----------
    roads_gdf : gpd.GeoDataFrame
        A GeoDataFrame with road segments. Must have columns:
        - **geometry**: LineString geometries of road segments
        - **AADT**: Annual Average Daily Traffic (vehicles per day)
        - **heat_flux_wm2**: Heat flux (W/m²) per segment
    lidar_transform : Affine
        The affine transform of the target LiDAR DEM grid.
    lidar_crs : CRS
        The CRS of the target LiDAR DEM grid.
    lidar_shape : tuple[int, int]
        The shape (rows, cols) of the target LiDAR DEM grid.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        A tuple of (road_heat_flux_wm2, road_temp_offset_f), both with shape
        matching lidar_shape. Pixels with no road influence are set to 0.0.

    Notes
    -----
    - If roads_gdf is empty or has no valid segments, returns arrays of zeros.
    - Overlapping buffers from multiple road segments are summed.
    - NaN values are replaced with 0.0 in the output.
    """
    # Initialize output arrays
    heat_flux_array = np.zeros(lidar_shape, dtype=np.float64)

    # Handle empty GeoDataFrame
    if roads_gdf.empty:
        logger.warning("No road segments provided; returning zero heat flux array")
        temp_offset_array = np.zeros(lidar_shape, dtype=np.float64)
        return heat_flux_array, temp_offset_array

    # Ensure roads_gdf is in the same CRS as the LiDAR grid
    if roads_gdf.crs != lidar_crs:
        roads_gdf = roads_gdf.to_crs(lidar_crs)

    # Create a copy to avoid modifying the original
    roads_gdf = roads_gdf.copy()

    # Compute buffer distance based on AADT tier
    def get_buffer_distance(aadt):
        """Return buffer distance in meters based on AADT tier."""
        if aadt < 10000:
            return 50
        elif aadt <= 50000:
            return 100
        else:
            return 200

    roads_gdf["buffer_distance"] = roads_gdf["AADT"].apply(get_buffer_distance)

    # Create buffered geometries
    roads_gdf["buffered_geometry"] = roads_gdf.apply(
        lambda row: row.geometry.buffer(row["buffer_distance"]),
        axis=1,
    )

    # Create a list of (geometry, heat_flux) tuples for rasterization
    # rasterio.features.rasterize expects an iterable of (geometry, value) tuples
    shapes = [
        (geom, flux)
        for geom, flux in zip(roads_gdf["buffered_geometry"], roads_gdf["heat_flux_wm2"])
    ]

    # Rasterize buffered geometries with heat flux values
    # merge_alg=rasterio.enums.MergeAlg.add sums overlapping values
    if shapes:
        rasterized = rasterio.features.rasterize(
            shapes,
            out_shape=lidar_shape,
            transform=lidar_transform,
            fill=0.0,
            merge_alg=rasterio.enums.MergeAlg.add,
            dtype=np.float64,
        )
        heat_flux_array = rasterized

    # Replace NaN with 0.0
    heat_flux_array = np.nan_to_num(heat_flux_array, nan=0.0)

    # Compute temperature offset: road_temp_offset_f = road_heat_flux_wm2 / 5.5 × 9/5
    temp_offset_array = (heat_flux_array / 5.5) * (9 / 5)

    logger.info(
        f"Computed anthropogenic load: max heat flux = {heat_flux_array.max():.2f} W/m², "
        f"max temp offset = {temp_offset_array.max():.2f} °F"
    )

    return heat_flux_array, temp_offset_array
