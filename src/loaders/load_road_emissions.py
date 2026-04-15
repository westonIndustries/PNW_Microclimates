"""
Road emissions loader.

Loads ODOT and WSDOT road shapefiles, concatenates them into a single
GeoDataFrame, filters to segments with AADT > 0, and computes heat flux
per segment based on traffic volume and road area.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import ODOT_ROADS_SHP, WSDOT_ROADS_SHP


# Road width in meters (default lane width)
ROAD_WIDTH_M = 3.7


def load_road_emissions() -> gpd.GeoDataFrame:
    """Load ODOT and WSDOT road shapefiles and compute heat flux per segment.

    Loads road shapefiles from Oregon DOT and Washington State DOT, concatenates
    them into a single GeoDataFrame, filters to segments with AADT > 0, and
    computes heat flux per segment using the formula:

        heat_flux_wm2 = (AADT / 86400) × 150000 / road_area_m2

    where road_area_m2 = segment_length_m × ROAD_WIDTH_M (3.7 m per lane).

    Returns
    -------
    gpd.GeoDataFrame
        A GeoDataFrame with columns:
        - **geometry**: LineString geometries of road segments
        - **AADT**: Annual Average Daily Traffic (vehicles per day)
        - **heat_flux_wm2**: Computed heat flux (W/m²) per segment
        - All other columns from the original shapefiles

    Raises
    ------
    FileNotFoundError
        If either ODOT or WSDOT shapefile does not exist.
    """
    odot_path = ODOT_ROADS_SHP.resolve()
    wsdot_path = WSDOT_ROADS_SHP.resolve()

    if not odot_path.exists():
        raise FileNotFoundError(f"ODOT roads shapefile not found: {odot_path}")

    if not wsdot_path.exists():
        raise FileNotFoundError(f"WSDOT roads shapefile not found: {wsdot_path}")

    # Load both shapefiles
    odot_gdf = gpd.read_file(odot_path)
    wsdot_gdf = gpd.read_file(wsdot_path)

    # Concatenate into a single GeoDataFrame
    roads_gdf = gpd.GeoDataFrame(
        pd.concat([odot_gdf, wsdot_gdf], ignore_index=True),
        crs=odot_gdf.crs
    )

    # Filter to segments with AADT > 0
    roads_gdf = roads_gdf[roads_gdf["AADT"] > 0].copy()

    # Compute segment length in meters
    # Ensure geometry is in a projected CRS for accurate length calculation
    if roads_gdf.crs is None or roads_gdf.crs.is_geographic:
        # If CRS is geographic, project to UTM Zone 10N (EPSG:26910)
        roads_gdf = roads_gdf.to_crs("EPSG:26910")

    roads_gdf["segment_length_m"] = roads_gdf.geometry.length

    # Compute road area in square meters
    roads_gdf["road_area_m2"] = roads_gdf["segment_length_m"] * ROAD_WIDTH_M

    # Compute heat flux: (AADT / 86400) × 150000 / road_area_m2
    roads_gdf["heat_flux_wm2"] = (
        (roads_gdf["AADT"] / 86400) * 150000 / roads_gdf["road_area_m2"]
    )

    # Drop intermediate columns
    roads_gdf = roads_gdf.drop(columns=["segment_length_m", "road_area_m2"])

    return roads_gdf
