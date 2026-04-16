"""
Unit tests for the create_cells processor.

Tests cover:
- Basic cell creation with regular grid
- Cell ID assignment and formatting
- Polygon clipping and boundary handling
- Empty and edge case handling
- Optional characteristic classification
"""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import Affine
from shapely.geometry import Polygon, box

import geopandas as gpd
from src.processors.create_cells import create_microclimate_cells


class TestCreateMicroclimateBasic:
    """Test basic cell creation functionality."""

    def test_creates_cells_for_simple_square_polygon(self):
        """Test that cells are created for a simple square polygon."""
        # Create a 1000m × 1000m square polygon
        polygon = box(0, 0, 1000, 1000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        # Should create 4 cells (2×2 grid)
        assert len(result) == 4
        assert all(result["cell_id"].str.startswith("cell_"))

    def test_cell_id_formatting(self):
        """Test that cell IDs are formatted correctly (cell_001, cell_002, etc.)."""
        polygon = box(0, 0, 1000, 1000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        expected_ids = ["cell_001", "cell_002", "cell_003", "cell_004"]
        assert list(result["cell_id"]) == expected_ids

    def test_cell_area_computed(self):
        """Test that cell_area_sqm is computed correctly."""
        polygon = box(0, 0, 1000, 1000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        # Each cell should be 500m × 500m = 250,000 m²
        assert all(np.isclose(result["cell_area_sqm"], 250000, rtol=1e-6))

    def test_crs_preserved(self):
        """Test that CRS is preserved from input GeoDataFrame."""
        polygon = box(0, 0, 1000, 1000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]}, crs="EPSG:26910")

        result = create_microclimate_cells(gdf, cell_size_m=500)

        assert result.crs == "EPSG:26910"

    def test_accepts_geojson_dict(self):
        """Test that function accepts GeoJSON-like dict geometry."""
        polygon = box(0, 0, 1000, 1000)
        geojson_dict = polygon.__geo_interface__

        result = create_microclimate_cells(geojson_dict, cell_size_m=500)

        assert len(result) == 4
        assert result.crs is None


class TestCreateMicroclimatePolygonClipping:
    """Test polygon clipping and boundary handling."""

    def test_clips_cells_to_polygon_boundary(self):
        """Test that cells are clipped to polygon boundary."""
        # Create a polygon with a diagonal cut (to ensure partial cells)
        coords = [(0, 0), (1000, 0), (1000, 1000), (500, 1000), (0, 500), (0, 0)]
        polygon = Polygon(coords)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        # All cells should have area <= 250,000 m² (some will be smaller due to clipping)
        assert all(result["cell_area_sqm"] <= 250000)
        # At least some cells should be smaller than full size due to diagonal cut
        assert any(result["cell_area_sqm"] < 250000)

    def test_excludes_non_intersecting_cells(self):
        """Test that cells that don't intersect polygon are excluded."""
        # Create a small polygon in the middle of a larger grid
        polygon = box(250, 250, 750, 750)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        # Should create only 1 cell (the one that contains the polygon)
        assert len(result) == 1

    def test_handles_polygon_with_hole(self):
        """Test handling of polygon with interior hole."""
        # Create a polygon with a hole
        exterior = [(0, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 0)]
        interior = [(250, 250), (750, 250), (750, 750), (250, 750), (250, 250)]
        polygon = Polygon(exterior, [interior])
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        # Should create cells, but the one with the hole should have reduced area
        assert len(result) > 0
        # At least one cell should have area < 250,000 m² (the one with the hole)
        assert any(result["cell_area_sqm"] < 250000)


class TestCreateMicroclimateEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_geodataframe_raises_error(self):
        """Test that empty GeoDataFrame raises ValueError."""
        gdf = gpd.GeoDataFrame({"geometry": []})

        with pytest.raises(ValueError, match="empty"):
            create_microclimate_cells(gdf)

    def test_empty_polygon_raises_error(self):
        """Test that empty polygon raises ValueError."""
        polygon = Polygon()
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        with pytest.raises(ValueError, match="empty"):
            create_microclimate_cells(gdf)

    def test_invalid_input_type_raises_error(self):
        """Test that invalid input type raises TypeError."""
        with pytest.raises(TypeError):
            create_microclimate_cells("invalid")

    def test_very_small_polygon_creates_single_cell(self):
        """Test that very small polygon (smaller than cell size) creates a single cell."""
        # Create a 10m × 10m polygon (much smaller than 500m cell)
        polygon = box(0, 0, 10, 10)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        # Should create 1 cell (the polygon intersects with the grid cell)
        assert len(result) == 1
        # Cell area should be the polygon area (100 m²)
        assert np.isclose(result.iloc[0]["cell_area_sqm"], 100.0)

    def test_different_cell_sizes(self):
        """Test that different cell sizes produce correct number of cells."""
        polygon = box(0, 0, 2000, 2000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        # 500m cells: 4×4 = 16 cells
        result_500 = create_microclimate_cells(gdf, cell_size_m=500)
        assert len(result_500) == 16

        # 1000m cells: 2×2 = 4 cells
        result_1000 = create_microclimate_cells(gdf, cell_size_m=1000)
        assert len(result_1000) == 4

        # 250m cells: 8×8 = 64 cells
        result_250 = create_microclimate_cells(gdf, cell_size_m=250)
        assert len(result_250) == 64


class TestCreateMicroclimateCharacteristics:
    """Test optional characteristic classification."""

    def test_adds_cell_type_column_when_characteristics_provided(self):
        """Test that cell_type column is added when characteristics provided."""
        polygon = box(0, 0, 1000, 1000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        # Create a simple characteristics array (2×2 grid)
        characteristics = np.array([[1, 2], [3, 4]], dtype=np.float32)
        transform = Affine(500, 0, 0, 0, -500, 1000)

        result = create_microclimate_cells(
            gdf,
            cell_size_m=500,
            cell_characteristics=characteristics,
            cell_characteristics_transform=transform,
        )

        assert "cell_type" in result.columns
        assert len(result) == 4

    def test_characteristic_values_are_strings(self):
        """Test that characteristic values are stored as strings."""
        polygon = box(0, 0, 1000, 1000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        characteristics = np.array([[1, 2], [3, 4]], dtype=np.float32)
        transform = Affine(500, 0, 0, 0, -500, 1000)

        result = create_microclimate_cells(
            gdf,
            cell_size_m=500,
            cell_characteristics=characteristics,
            cell_characteristics_transform=transform,
        )

        # All non-null cell_type values should be strings
        non_null_types = result[result["cell_type"].notna()]["cell_type"]
        assert all(isinstance(v, str) for v in non_null_types)

    def test_handles_nan_in_characteristics(self):
        """Test that NaN values in characteristics are handled gracefully."""
        polygon = box(0, 0, 1000, 1000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        characteristics = np.array([[1, np.nan], [3, 4]], dtype=np.float32)
        transform = Affine(500, 0, 0, 0, -500, 1000)

        result = create_microclimate_cells(
            gdf,
            cell_size_m=500,
            cell_characteristics=characteristics,
            cell_characteristics_transform=transform,
        )

        # Should not raise error, some cells may have None for cell_type
        assert len(result) > 0


class TestCreateMicroclimateGeometry:
    """Test geometric properties of created cells."""

    def test_all_cells_are_polygons(self):
        """Test that all created cells are valid polygons."""
        polygon = box(0, 0, 1000, 1000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        assert all(geom.geom_type == "Polygon" for geom in result.geometry)

    def test_cells_do_not_overlap_significantly(self):
        """Test that cells don't overlap significantly (allowing for floating point errors)."""
        polygon = box(0, 0, 1000, 1000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        # Check pairwise overlaps
        for i in range(len(result)):
            for j in range(i + 1, len(result)):
                geom_i = result.iloc[i].geometry
                geom_j = result.iloc[j].geometry
                intersection = geom_i.intersection(geom_j)
                # Intersection should be negligible (line or point, not area)
                assert intersection.area < 1.0  # Allow tiny floating point errors

    def test_cells_cover_polygon_extent(self):
        """Test that cells collectively cover the polygon extent."""
        polygon = box(0, 0, 1000, 1000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        # Union of all cells should approximately equal the polygon
        from shapely.ops import unary_union
        union_geom = unary_union(result.geometry.values)
        # Coverage should be high (at least 95% of original polygon)
        coverage_ratio = union_geom.intersection(polygon).area / polygon.area
        assert coverage_ratio > 0.95


class TestCreateMicroclimateIntegration:
    """Integration tests with realistic scenarios."""

    def test_realistic_zip_code_polygon(self):
        """Test with a realistic ZIP code-like polygon."""
        # Create a roughly rectangular polygon (like a ZIP code boundary)
        polygon = box(500000, 5000000, 510000, 5010000)  # 10km × 10km in UTM
        gdf = gpd.GeoDataFrame({"geometry": [polygon]}, crs="EPSG:26910")

        result = create_microclimate_cells(gdf, cell_size_m=500)

        # 10km × 10km with 500m cells = 20×20 = 400 cells
        assert len(result) == 400
        assert result.crs == "EPSG:26910"
        # All cells should have area close to 250,000 m²
        assert all(np.isclose(result["cell_area_sqm"], 250000, rtol=0.01))

    def test_sequential_cell_ids(self):
        """Test that cell IDs are sequential and unique."""
        polygon = box(0, 0, 2000, 2000)
        gdf = gpd.GeoDataFrame({"geometry": [polygon]})

        result = create_microclimate_cells(gdf, cell_size_m=500)

        # Extract numeric part of cell IDs
        cell_numbers = [int(cid.split("_")[1]) for cid in result["cell_id"]]

        # Should be sequential from 1 to N
        assert cell_numbers == list(range(1, len(result) + 1))
        # Should be unique
        assert len(set(cell_numbers)) == len(cell_numbers)
