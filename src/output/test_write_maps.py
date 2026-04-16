"""
Tests for write_maps module.

Tests verify that interactive Leaflet HTML maps are generated correctly
with cell-level data, proper coloring, popups, and layer controls.
"""

import pytest
import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path
from shapely.geometry import box
import tempfile
import json

from src.output.write_maps import write_maps


class TestWriteMaps:
    """Test write_maps functionality."""

    @pytest.fixture
    def sample_cells_gdf(self):
        """Create a sample GeoDataFrame with cell geometries."""
        # Create a simple grid of cells in Portland area
        cells = []
        cell_id = 1
        for i in range(3):
            for j in range(3):
                # Create 500m x 500m cells (approximate in degrees)
                lon = -122.6 + (i * 0.005)
                lat = 45.5 + (j * 0.005)
                geom = box(lon, lat, lon + 0.005, lat + 0.005)
                
                cells.append({
                    "cell_id": f"cell_{cell_id:03d}",
                    "zip_code": "97201",
                    "cell_type": "urban" if cell_id <= 3 else "suburban" if cell_id <= 6 else "rural",
                    "cell_area_sqm": 250000.0,
                    "base_station": "KPDX",
                    "effective_hdd": 4500.0 + (cell_id * 50),
                    "terrain_position": ["windward", "leeward", "valley", "ridge", "windward", "leeward", "valley", "ridge", "windward"][cell_id - 1],
                    "mean_elevation_ft": 300.0 + (cell_id * 20),
                    "mean_wind_ms": 3.0 + (cell_id * 0.2),
                    "wind_infiltration_mult": 1.0 + (cell_id * 0.02),
                    "mean_impervious_pct": 50.0 - (cell_id * 5),
                    "uhi_offset_f": 2.5 - (cell_id * 0.2),
                    "road_heat_flux_wm2": 20.0 - (cell_id * 2),
                    "geometry": geom,
                })
                cell_id += 1
        
        gdf = gpd.GeoDataFrame(cells, crs="EPSG:4326")
        return gdf

    def test_write_maps_creates_files(self, sample_cells_gdf):
        """Test that write_maps creates all required map files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_maps(sample_cells_gdf, output_dir=output_dir)
            
            # Check that all map files were created
            expected_files = [
                "map_effective_hdd.html",
                "map_terrain_position.html",
                "map_uhi_effect.html",
                "map_wind_infiltration.html",
                "map_traffic_heat.html",
            ]
            
            for filename in expected_files:
                filepath = output_dir / filename
                assert filepath.exists(), f"Map file {filename} was not created"
                assert filepath.stat().st_size > 0, f"Map file {filename} is empty"

    def test_write_maps_html_contains_leaflet(self, sample_cells_gdf):
        """Test that generated HTML contains Leaflet library references."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_maps(sample_cells_gdf, output_dir=output_dir)
            
            html_file = output_dir / "map_effective_hdd.html"
            html_content = html_file.read_text()
            
            # Check for Leaflet library
            assert "leaflet" in html_content.lower()
            assert "openstreetmap" in html_content.lower()

    def test_write_maps_html_contains_geojson(self, sample_cells_gdf):
        """Test that generated HTML contains GeoJSON data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_maps(sample_cells_gdf, output_dir=output_dir)
            
            html_file = output_dir / "map_effective_hdd.html"
            html_content = html_file.read_text()
            
            # Check for GeoJSON data
            assert "FeatureCollection" in html_content
            assert "Feature" in html_content
            assert "geometry" in html_content

    def test_write_maps_html_contains_popups(self, sample_cells_gdf):
        """Test that generated HTML contains popup content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_maps(sample_cells_gdf, output_dir=output_dir)
            
            html_file = output_dir / "map_effective_hdd.html"
            html_content = html_file.read_text()
            
            # Check for popup content
            assert "popup" in html_content.lower()
            assert "cell_id" in html_content
            assert "effective_hdd" in html_content

    def test_write_maps_html_contains_legend(self, sample_cells_gdf):
        """Test that generated HTML contains legend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_maps(sample_cells_gdf, output_dir=output_dir)
            
            html_file = output_dir / "map_effective_hdd.html"
            html_content = html_file.read_text()
            
            # Check for legend
            assert "legend" in html_content.lower()

    def test_write_maps_terrain_position_categorical(self, sample_cells_gdf):
        """Test that terrain position map uses categorical colors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_maps(sample_cells_gdf, output_dir=output_dir)
            
            html_file = output_dir / "map_terrain_position.html"
            html_content = html_file.read_text()
            
            # Check for terrain position categories
            assert "windward" in html_content
            assert "leeward" in html_content
            assert "valley" in html_content
            assert "ridge" in html_content

    def test_write_maps_with_missing_columns_raises_error(self):
        """Test that write_maps raises error if required columns are missing."""
        # Create GeoDataFrame without required columns
        gdf = gpd.GeoDataFrame({
            "cell_id": ["cell_001"],
            "geometry": [box(-122.6, 45.5, -122.595, 45.505)],
        }, crs="EPSG:4326")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            with pytest.raises(ValueError, match="Missing required columns"):
                write_maps(gdf, output_dir=output_dir)

    def test_write_maps_with_null_geometries(self, sample_cells_gdf):
        """Test that write_maps handles null geometries gracefully."""
        # Add a row with null geometry
        null_row = sample_cells_gdf.iloc[0].copy()
        null_row.geometry = None
        sample_cells_gdf = pd.concat([sample_cells_gdf, gpd.GeoDataFrame([null_row], crs="EPSG:4326")], ignore_index=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            # Should not raise an error
            write_maps(sample_cells_gdf, output_dir=output_dir)
            
            # Check that files were created
            assert (output_dir / "map_effective_hdd.html").exists()

    def test_write_maps_creates_output_directory(self):
        """Test that write_maps creates output directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "nonexistent" / "path"
            
            # Create sample data
            cells = []
            for i in range(3):
                geom = box(-122.6 + (i * 0.005), 45.5, -122.595 + (i * 0.005), 45.505)
                cells.append({
                    "cell_id": f"cell_{i:03d}",
                    "zip_code": "97201",
                    "cell_type": "urban",
                    "cell_area_sqm": 250000.0,
                    "base_station": "KPDX",
                    "effective_hdd": 4500.0,
                    "terrain_position": "windward",
                    "mean_elevation_ft": 300.0,
                    "mean_wind_ms": 3.0,
                    "wind_infiltration_mult": 1.0,
                    "mean_impervious_pct": 50.0,
                    "uhi_offset_f": 2.5,
                    "road_heat_flux_wm2": 20.0,
                    "geometry": geom,
                })
            
            gdf = gpd.GeoDataFrame(cells, crs="EPSG:4326")
            write_maps(gdf, output_dir=output_dir)
            
            # Check that directory was created
            assert output_dir.exists()
            assert (output_dir / "map_effective_hdd.html").exists()

    def test_write_maps_converts_crs_to_4326(self):
        """Test that write_maps converts CRS to EPSG:4326."""
        # Create GeoDataFrame in UTM
        cells = []
        for i in range(3):
            # UTM Zone 10N coordinates (approximate)
            x = 500000 + (i * 5000)
            y = 5000000
            geom = box(x, y, x + 5000, y + 5000)
            cells.append({
                "cell_id": f"cell_{i:03d}",
                "zip_code": "97201",
                "cell_type": "urban",
                "cell_area_sqm": 250000.0,
                "base_station": "KPDX",
                "effective_hdd": 4500.0,
                "terrain_position": "windward",
                "mean_elevation_ft": 300.0,
                "mean_wind_ms": 3.0,
                "wind_infiltration_mult": 1.0,
                "mean_impervious_pct": 50.0,
                "uhi_offset_f": 2.5,
                "road_heat_flux_wm2": 20.0,
                "geometry": geom,
            })
        
        gdf = gpd.GeoDataFrame(cells, crs="EPSG:26910")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_maps(gdf, output_dir=output_dir)
            
            # Check that files were created
            assert (output_dir / "map_effective_hdd.html").exists()

    def test_write_maps_all_five_maps_generated(self, sample_cells_gdf):
        """Test that all five required maps are generated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_maps(sample_cells_gdf, output_dir=output_dir)
            
            # Verify all five maps exist
            maps = [
                "map_effective_hdd.html",
                "map_terrain_position.html",
                "map_uhi_effect.html",
                "map_wind_infiltration.html",
                "map_traffic_heat.html",
            ]
            
            for map_file in maps:
                filepath = output_dir / map_file
                assert filepath.exists(), f"{map_file} not found"
                
                # Verify file is not empty
                content = filepath.read_text()
                assert len(content) > 1000, f"{map_file} is too small"
                
                # Verify it's valid HTML (strip whitespace first)
                assert "<!DOCTYPE html>" in content, f"{map_file} is not valid HTML"
