"""Tests for src/processors/clip_to_boundary.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import Affine
from shapely.geometry import Polygon

from src.processors.clip_to_boundary import (
    clip_to_boundary,
    get_region_boundary,
    load_boundary_shapefile,
)


# ---------------------------------------------------------------------------
# clip_to_boundary tests
# ---------------------------------------------------------------------------


def test_clip_to_boundary_returns_tuple():
    """clip_to_boundary returns a tuple of (array, transform)."""
    # Create a simple raster array
    raster_array = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    raster_transform = Affine.identity()
    raster_crs = CRS.from_epsg(26910)

    # Create a simple boundary geometry (a square covering the raster)
    boundary_geom = {
        "type": "Polygon",
        "coordinates": [[
            [0, 0],
            [2, 0],
            [2, 2],
            [0, 2],
            [0, 0],
        ]],
    }

    result = clip_to_boundary(raster_array, raster_transform, raster_crs, boundary_geom)

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], np.ndarray)
    assert hasattr(result[1], "a")  # Affine transform has 'a' attribute


def test_clip_to_boundary_wraps_single_dict_in_list():
    """If boundary_geom is a dict, it is wrapped in a list."""
    raster_array = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    raster_transform = Affine.identity()
    raster_crs = CRS.from_epsg(26910)

    boundary_geom = {
        "type": "Polygon",
        "coordinates": [[
            [0, 0],
            [2, 0],
            [2, 2],
            [0, 2],
            [0, 0],
        ]],
    }

    # Should not raise an error
    result = clip_to_boundary(raster_array, raster_transform, raster_crs, boundary_geom)
    assert isinstance(result, tuple)


def test_clip_to_boundary_accepts_list_of_geoms():
    """If boundary_geom is a list, it is used as-is."""
    raster_array = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    raster_transform = Affine.identity()
    raster_crs = CRS.from_epsg(26910)

    boundary_geom = [
        {
            "type": "Polygon",
            "coordinates": [[
                [0, 0],
                [2, 0],
                [2, 2],
                [0, 2],
                [0, 0],
            ]],
        }
    ]

    # Should not raise an error
    result = clip_to_boundary(raster_array, raster_transform, raster_crs, boundary_geom)
    assert isinstance(result, tuple)


def test_clip_to_boundary_logs_dimensions():
    """clip_to_boundary logs the clipped pixel dimensions."""
    raster_array = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    raster_transform = Affine.identity()
    raster_crs = CRS.from_epsg(26910)

    boundary_geom = {
        "type": "Polygon",
        "coordinates": [[
            [0, 0],
            [2, 0],
            [2, 2],
            [0, 2],
            [0, 0],
        ]],
    }

    with patch("src.processors.clip_to_boundary.logger") as mock_logger:
        clip_to_boundary(raster_array, raster_transform, raster_crs, boundary_geom)
        # Verify that logger.info was called
        assert mock_logger.info.called


# ---------------------------------------------------------------------------
# load_boundary_shapefile tests
# ---------------------------------------------------------------------------


def test_load_boundary_shapefile_raises_file_not_found(tmp_path):
    """Raises FileNotFoundError when shapefile does not exist."""
    fake_path = tmp_path / "nonexistent.shp"
    with pytest.raises(FileNotFoundError) as exc_info:
        load_boundary_shapefile(fake_path)
    assert "nonexistent.shp" in str(exc_info.value)


def test_load_boundary_shapefile_returns_geodataframe(tmp_path):
    """Returns a GeoDataFrame when shapefile exists."""
    # Create a simple shapefile
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    gdf = gpd.GeoDataFrame(
        {"geometry": [polygon]},
        crs="EPSG:26910",
    )
    shp_path = tmp_path / "boundary.shp"
    gdf.to_file(shp_path)

    result = load_boundary_shapefile(shp_path)

    assert isinstance(result, gpd.GeoDataFrame)
    assert len(result) > 0


def test_load_boundary_shapefile_uses_config_default(tmp_path):
    """Uses BOUNDARY_SHP from config when no path is provided."""
    # Create a simple shapefile
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    gdf = gpd.GeoDataFrame(
        {"geometry": [polygon]},
        crs="EPSG:26910",
    )
    shp_path = tmp_path / "boundary.shp"
    gdf.to_file(shp_path)

    with patch("src.processors.clip_to_boundary.BOUNDARY_SHP", shp_path):
        result = load_boundary_shapefile()
        assert isinstance(result, gpd.GeoDataFrame)


# ---------------------------------------------------------------------------
# get_region_boundary tests
# ---------------------------------------------------------------------------


def test_get_region_boundary_returns_geojson_dict():
    """get_region_boundary returns a GeoJSON-like dict."""
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    gdf = gpd.GeoDataFrame(
        {"geometry": [polygon]},
        crs="EPSG:26910",
    )

    result = get_region_boundary("region_1", gdf)

    assert isinstance(result, dict)
    assert "type" in result
    assert "coordinates" in result


def test_get_region_boundary_raises_on_empty_gdf():
    """Raises ValueError when GeoDataFrame is empty."""
    gdf = gpd.GeoDataFrame({"geometry": []}, crs="EPSG:26910")

    with pytest.raises(ValueError) as exc_info:
        get_region_boundary("region_1", gdf)
    assert "empty" in str(exc_info.value).lower()


def test_get_region_boundary_dissolves_multiple_polygons():
    """Dissolves multiple polygons into a single geometry."""
    polygon1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    polygon2 = Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])
    gdf = gpd.GeoDataFrame(
        {"geometry": [polygon1, polygon2]},
        crs="EPSG:26910",
    )

    result = get_region_boundary("region_1", gdf)

    assert isinstance(result, dict)
    assert "type" in result
