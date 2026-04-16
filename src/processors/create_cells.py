"""
Microclimate cell creation processor.

Divides a ZIP code polygon into a regular grid of square cells (default 500m × 500m).
Each cell is assigned a unique cell_id and optionally classified by dominant characteristics.
Returns a GeoDataFrame with cell geometries and metadata.
"""

from __future__ import annotations

import logging
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box
from shapely.ops import unary_union

from src.config import CELL_SIZE_M

logger = logging.getLogger(__name__)


def create_microclimate_cells(
    zip_code_polygon: gpd.GeoDataFrame | dict,
    cell_size_m: int = CELL_SIZE_M,
    cell_characteristics: Optional[np.ndarray] = None,
    cell_characteristics_transform: Optional[object] = None,
) -> gpd.GeoDataFrame:
    """Create a regular grid of microclimate cells within a ZIP code boundary.

    Parameters
    ----------
    zip_code_polygon : gpd.GeoDataFrame | dict
        A GeoDataFrame with a single row containing the ZIP code polygon geometry,
        or a GeoJSON-like geometry dict. If a GeoDataFrame, the CRS is preserved.
    cell_size_m : int, optional
        Cell size in meters (default: 500m from config.CELL_SIZE_M).
    cell_characteristics : np.ndarray, optional
        A 2D raster array of cell characteristics (e.g., dominant NLCD class, terrain type).
        If provided, the dominant characteristic is computed for each cell.
    cell_characteristics_transform : object, optional
        The affine transform of the cell_characteristics raster (rasterio.transform.Affine).
        Required if cell_characteristics is provided.

    Returns
    -------
    gpd.GeoDataFrame
        A GeoDataFrame with columns:
        - geometry: cell polygon (square)
        - cell_id: unique identifier (cell_001, cell_002, etc.)
        - cell_type: optional, dominant characteristic if cell_characteristics provided
        - cell_area_sqm: area of the cell in square meters

    Notes
    -----
    - Cells are created as a regular grid covering the bounding box of the polygon.
    - Only cells that intersect the polygon boundary are included in the output.
    - Cell IDs are assigned sequentially in row-major order (top-left to bottom-right).
    - If cell_characteristics is provided, the dominant value within each cell is
      computed and stored in the cell_type column.
    """
    # Extract geometry and CRS
    if isinstance(zip_code_polygon, gpd.GeoDataFrame):
        if len(zip_code_polygon) == 0:
            raise ValueError("GeoDataFrame is empty")
        geom = zip_code_polygon.iloc[0].geometry
        crs = zip_code_polygon.crs
    elif isinstance(zip_code_polygon, dict):
        # Assume it's a GeoJSON-like dict
        from shapely.geometry import shape
        geom = shape(zip_code_polygon)
        crs = None
    else:
        raise TypeError(
            f"zip_code_polygon must be GeoDataFrame or dict, got {type(zip_code_polygon)}"
        )

    if geom.is_empty:
        raise ValueError("Polygon geometry is empty")

    # Get bounding box in the polygon's coordinate system
    minx, miny, maxx, maxy = geom.bounds

    # Create a regular grid of cells
    cells = []
    cell_id_counter = 1

    # Iterate over grid cells in row-major order (top-left to bottom-right)
    y = maxy
    while y > miny:
        x = minx
        while x < maxx:
            # Create cell as a square box
            cell_geom = box(x, y - cell_size_m, x + cell_size_m, y)

            # Check if cell intersects the polygon
            if cell_geom.intersects(geom):
                # Clip cell to polygon boundary
                clipped_geom = cell_geom.intersection(geom)

                # Skip if intersection is empty or degenerate
                if not clipped_geom.is_empty and clipped_geom.area > 0:
                    cell_id = f"cell_{cell_id_counter:03d}"
                    cell_area_sqm = clipped_geom.area

                    cells.append({
                        "geometry": clipped_geom,
                        "cell_id": cell_id,
                        "cell_area_sqm": cell_area_sqm,
                    })
                    cell_id_counter += 1

            x += cell_size_m
        y -= cell_size_m

    if len(cells) == 0:
        logger.warning(
            f"No cells created for polygon with bounds {geom.bounds}. "
            f"Cell size: {cell_size_m}m"
        )
        # Return empty GeoDataFrame with correct schema
        return gpd.GeoDataFrame(
            {
                "geometry": [],
                "cell_id": [],
                "cell_area_sqm": [],
            },
            crs=crs,
        )

    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame(cells, crs=crs)

    # Optionally compute dominant characteristic for each cell
    if cell_characteristics is not None and cell_characteristics_transform is not None:
        gdf["cell_type"] = gdf.geometry.apply(
            lambda geom: _get_dominant_characteristic(
                geom,
                cell_characteristics,
                cell_characteristics_transform,
            )
        )

    logger.info(
        f"Created {len(gdf)} microclimate cells with size {cell_size_m}m × {cell_size_m}m"
    )

    return gdf


def _get_dominant_characteristic(
    cell_geom: object,
    characteristics_array: np.ndarray,
    characteristics_transform: object,
) -> Optional[str]:
    """Compute the dominant characteristic value within a cell geometry.

    Parameters
    ----------
    cell_geom : shapely.geometry.Polygon
        The cell geometry.
    characteristics_array : np.ndarray
        A 2D raster array of characteristic values.
    characteristics_transform : rasterio.transform.Affine
        The affine transform of the raster.

    Returns
    -------
    str | None
        The dominant characteristic value (as a string), or None if no valid values
        are found within the cell.

    Notes
    -----
    - This function samples the raster at the cell's centroid and returns the value
      at that location. For a more robust approach, consider computing the mode of
      all pixels within the cell, but that is more computationally expensive.
    """
    try:
        # Get cell centroid
        centroid = cell_geom.centroid

        # Convert centroid coordinates to raster indices
        # Using the inverse of the affine transform
        from rasterio.transform import Affine
        inv_transform = ~characteristics_transform
        col, row = inv_transform * (centroid.x, centroid.y)

        # Convert to integer indices
        row, col = int(row), int(col)

        # Check bounds
        if 0 <= row < characteristics_array.shape[0] and 0 <= col < characteristics_array.shape[1]:
            value = characteristics_array[row, col]

            # Check for NaN or nodata
            if np.isnan(value) if isinstance(value, (float, np.floating)) else False:
                return None

            return str(int(value))

        return None

    except Exception as e:
        logger.debug(f"Error computing dominant characteristic: {e}")
        return None
