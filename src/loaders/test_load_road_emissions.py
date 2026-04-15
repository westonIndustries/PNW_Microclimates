"""
Tests for road emissions loader.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString

from src.loaders.load_road_emissions import load_road_emissions, ROAD_WIDTH_M


@pytest.fixture
def mock_roads_dir(tmp_path):
    """Create a temporary roads directory with mock shapefiles."""
    roads_dir = tmp_path / "roads"
    roads_dir.mkdir()
    return roads_dir


def _create_mock_shapefile(path, geometries, attributes):
    """Helper to create a mock shapefile."""
    gdf = gpd.GeoDataFrame(
        attributes,
        geometry=geometries,
        crs="EPSG:26910"
    )
    gdf.to_file(path)
    return gdf


def test_raises_file_not_found_when_odot_missing(tmp_path):
    """Test that FileNotFoundError is raised when ODOT shapefile is missing."""
    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", Path("/nonexistent/odot.shp")):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", Path("/nonexistent/wsdot.shp")):
            with pytest.raises(FileNotFoundError, match="ODOT roads shapefile not found"):
                load_road_emissions()


def test_raises_file_not_found_when_wsdot_missing(tmp_path):
    """Test that FileNotFoundError is raised when WSDOT shapefile is missing."""
    odot_path = tmp_path / "odot.shp"
    # Create a minimal ODOT shapefile
    gdf = gpd.GeoDataFrame(
        {"AADT": [1000]},
        geometry=[LineString([(0, 0), (1, 1)])],
        crs="EPSG:26910"
    )
    gdf.to_file(odot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", Path("/nonexistent/wsdot.shp")):
            with pytest.raises(FileNotFoundError, match="WSDOT roads shapefile not found"):
                load_road_emissions()


def test_loads_single_segment_with_aadt(tmp_path):
    """Test loading a single road segment with AADT."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    # Create ODOT shapefile with one segment
    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [10000]},
        geometry=[LineString([(0, 0), (100, 0)])],  # 100 m long
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    # Create empty WSDOT shapefile
    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert len(result) == 1
    assert result.iloc[0]["AADT"] == 10000
    assert "heat_flux_wm2" in result.columns


def test_filters_out_zero_aadt(tmp_path):
    """Test that segments with AADT = 0 are filtered out."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    # Create ODOT shapefile with mixed AADT values
    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [10000, 0, 5000, 0]},
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(100, 0), (200, 0)]),
            LineString([(200, 0), (300, 0)]),
            LineString([(300, 0), (400, 0)]),
        ],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    # Create empty WSDOT shapefile
    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert len(result) == 2
    assert all(result["AADT"] > 0)


def test_computes_heat_flux_correctly(tmp_path):
    """Test that heat flux is computed correctly."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    # Create a segment: 100 m long, AADT = 86400 (1 vehicle per second)
    # heat_flux = (86400 / 86400) * 150000 / (100 * 3.7)
    #           = 1 * 150000 / 370
    #           = 405.405... W/m²
    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [86400]},
        geometry=[LineString([(0, 0), (100, 0)])],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    expected_heat_flux = (86400 / 86400) * 150000 / (100 * ROAD_WIDTH_M)
    assert result.iloc[0]["heat_flux_wm2"] == pytest.approx(expected_heat_flux)


def test_concatenates_odot_and_wsdot(tmp_path):
    """Test that ODOT and WSDOT shapefiles are concatenated."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    # Create ODOT shapefile with 2 segments
    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [10000, 5000]},
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(100, 0), (200, 0)]),
        ],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    # Create WSDOT shapefile with 1 segment
    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": [15000]},
        geometry=[LineString([(200, 0), (300, 0)])],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert len(result) == 3
    assert set(result["AADT"].values) == {10000, 5000, 15000}


def test_returns_geodataframe(tmp_path):
    """Test that result is a GeoDataFrame."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [10000]},
        geometry=[LineString([(0, 0), (100, 0)])],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert isinstance(result, gpd.GeoDataFrame)
    assert "geometry" in result.columns


def test_heat_flux_column_exists(tmp_path):
    """Test that heat_flux_wm2 column is present in output."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [10000]},
        geometry=[LineString([(0, 0), (100, 0)])],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert "heat_flux_wm2" in result.columns


def test_heat_flux_positive_for_positive_aadt(tmp_path):
    """Test that heat flux is positive for positive AADT (property test)."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    # Create segments with various AADT values
    aadt_values = [1000, 5000, 10000, 50000, 100000]
    odot_gdf = gpd.GeoDataFrame(
        {"AADT": aadt_values},
        geometry=[LineString([(i * 100, 0), (i * 100 + 100, 0)]) for i in range(len(aadt_values))],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert all(result["heat_flux_wm2"] > 0)


def test_heat_flux_increases_with_aadt(tmp_path):
    """Test that heat flux increases with AADT (property test)."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    # Create two segments with same length but different AADT
    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [10000, 20000]},
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(100, 0), (200, 0)]),
        ],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    # Sort by AADT to ensure order
    result = result.sort_values("AADT").reset_index(drop=True)
    assert result.iloc[1]["heat_flux_wm2"] > result.iloc[0]["heat_flux_wm2"]


def test_heat_flux_decreases_with_length(tmp_path):
    """Test that heat flux decreases with segment length (property test)."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    # Create two segments with same AADT but different lengths
    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [10000, 10000]},
        geometry=[
            LineString([(0, 0), (100, 0)]),    # 100 m
            LineString([(100, 0), (300, 0)]),  # 200 m
        ],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    # Longer segment should have lower heat flux
    assert result.iloc[1]["heat_flux_wm2"] < result.iloc[0]["heat_flux_wm2"]


def test_preserves_aadt_column(tmp_path):
    """Test that AADT column is preserved in output."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [10000]},
        geometry=[LineString([(0, 0), (100, 0)])],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert "AADT" in result.columns
    assert result.iloc[0]["AADT"] == 10000


def test_preserves_geometry_column(tmp_path):
    """Test that geometry column is preserved in output."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    line = LineString([(0, 0), (100, 0)])
    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [10000]},
        geometry=[line],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert "geometry" in result.columns
    assert result.iloc[0].geometry.equals(line)


def test_handles_empty_both_shapefiles(tmp_path):
    """Test that empty result is returned when both shapefiles are empty."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    odot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert len(result) == 0
    assert isinstance(result, gpd.GeoDataFrame)


def test_handles_all_zero_aadt(tmp_path):
    """Test that empty result is returned when all AADT values are 0."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [0, 0, 0]},
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(100, 0), (200, 0)]),
            LineString([(200, 0), (300, 0)]),
        ],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert len(result) == 0


def test_heat_flux_formula_correctness(tmp_path):
    """Test that heat flux formula is correct: (AADT/86400) * 150000 / road_area_m2."""
    odot_path = tmp_path / "odot.shp"
    wsdot_path = tmp_path / "wsdot.shp"

    # Test with specific values
    aadt = 43200  # 0.5 vehicles per second
    length = 200  # 200 m
    expected_heat_flux = (aadt / 86400) * 150000 / (length * ROAD_WIDTH_M)

    odot_gdf = gpd.GeoDataFrame(
        {"AADT": [aadt]},
        geometry=[LineString([(0, 0), (length, 0)])],
        crs="EPSG:26910"
    )
    odot_gdf.to_file(odot_path)

    wsdot_gdf = gpd.GeoDataFrame(
        {"AADT": []},
        geometry=[],
        crs="EPSG:26910"
    )
    wsdot_gdf.to_file(wsdot_path)

    with mock.patch("src.loaders.load_road_emissions.ODOT_ROADS_SHP", odot_path):
        with mock.patch("src.loaders.load_road_emissions.WSDOT_ROADS_SHP", wsdot_path):
            result = load_road_emissions()

    assert result.iloc[0]["heat_flux_wm2"] == pytest.approx(expected_heat_flux)
