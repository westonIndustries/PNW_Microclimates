"""
Boundary clipping processor.

Loads the OR/WA state boundary shapefile, filters to the polygon(s) for the
current region, and uses ``rasterio.mask.mask`` to clip a raster array to the
boundary. Returns the clipped array and updated transform.
"""

from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.mask
from rasterio.crs import CRS
from rasterio.transform import Affine

from src.config import BOUNDARY_SHP

logger = logging.getLogger(__name__)


def clip_to_boundary(
    raster_array: np.ndarray,
    raster_transform: Affine,
    raster_crs: CRS,
    boundary_geom: dict | list,
) -> tuple[np.ndarray, Affine]:
    """Clip a raster array to a boundary geometry using rasterio.mask.mask.

    Parameters
    ----------
    raster_array : np.ndarray
        The raster array to clip (2D).
    raster_transform : Affine
        The affine transform of the raster.
    raster_crs : CRS
        The CRS of the raster.
    boundary_geom : dict | list
        A single GeoJSON-like geometry dict or a list of geometries to use as
        the clipping mask. Geometries must be in the same CRS as the raster.

    Returns
    -------
    tuple[np.ndarray, Affine]
        A tuple of (clipped_array, updated_transform). The clipped array has
        pixels outside the boundary set to NaN. The updated transform reflects
        the new origin after clipping.

    Notes
    -----
    - If ``boundary_geom`` is a single dict, it is wrapped in a list.
    - The function logs the clipped pixel dimensions and CRS.
    """
    # Ensure boundary_geom is a list
    if isinstance(boundary_geom, dict):
        boundary_geom = [boundary_geom]

    # Write raster to temporary file so rasterio.mask.mask can read it
    with NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Write the raster to a temporary GeoTIFF
        with rasterio.open(
            tmp_path,
            "w",
            driver="GTiff",
            height=raster_array.shape[0],
            width=raster_array.shape[1],
            count=1,
            dtype=raster_array.dtype,
            crs=raster_crs,
            transform=raster_transform,
            nodata=np.nan if raster_array.dtype == np.float64 else None,
        ) as dst:
            dst.write(raster_array, 1)

        # Open the temporary file and clip it
        with rasterio.open(tmp_path) as src:
            clipped_array, clipped_transform = rasterio.mask.mask(
                src,
                boundary_geom,
                crop=True,
            )

        # Extract the single band (rasterio.mask.mask returns (bands, rows, cols))
        clipped_array = clipped_array[0]

        # Log the clipped dimensions and CRS
        logger.info(
            f"Clipped raster to boundary: {clipped_array.shape[0]} rows × "
            f"{clipped_array.shape[1]} cols, CRS: {raster_crs}"
        )

        return clipped_array, clipped_transform

    finally:
        # Clean up temporary file
        Path(tmp_path).unlink(missing_ok=True)


def load_boundary_shapefile(boundary_shp_path: Path | None = None) -> gpd.GeoDataFrame:
    """Load the OR/WA state boundary shapefile.

    Parameters
    ----------
    boundary_shp_path : Path | None
        Path to the boundary shapefile. If None, uses ``BOUNDARY_SHP`` from config.

    Returns
    -------
    gpd.GeoDataFrame
        A GeoDataFrame with the boundary polygon(s).

    Raises
    ------
    FileNotFoundError
        If the shapefile does not exist at the configured path.
    """
    if boundary_shp_path is None:
        boundary_shp_path = BOUNDARY_SHP.resolve()

    if not boundary_shp_path.exists():
        raise FileNotFoundError(
            f"Boundary shapefile not found: {boundary_shp_path}"
        )

    gdf = gpd.read_file(boundary_shp_path)
    logger.info(f"Loaded boundary shapefile: {boundary_shp_path} ({len(gdf)} features)")

    return gdf


def get_region_boundary(
    region_name: str,
    boundary_gdf: gpd.GeoDataFrame | None = None,
) -> dict | list:
    """Extract the boundary geometry for a specific region.

    Parameters
    ----------
    region_name : str
        The region name (e.g., "region_1").
    boundary_gdf : gpd.GeoDataFrame | None
        The boundary GeoDataFrame. If None, loads from the configured path.

    Returns
    -------
    dict | list
        A GeoJSON-like geometry dict or list of geometries for the region.
        If the region has multiple polygons, returns a list; otherwise returns
        a single dict.

    Notes
    -----
    - Currently, the boundary shapefile is assumed to contain a single polygon
      for the entire OR/WA extent. This function returns that polygon's geometry.
    - In the future, if regions are subdivided, this function can filter by
      a ``region_name`` attribute on the shapefile features.
    """
    if boundary_gdf is None:
        boundary_gdf = load_boundary_shapefile()

    # For now, assume a single boundary polygon covering the entire region
    # In the future, filter by region_name attribute if available
    if len(boundary_gdf) == 0:
        raise ValueError("Boundary GeoDataFrame is empty")

    # Dissolve all geometries into a single geometry
    dissolved = boundary_gdf.dissolve()
    geom = dissolved.iloc[0].geometry

    # Convert to GeoJSON-like dict
    return geom.__geo_interface__
