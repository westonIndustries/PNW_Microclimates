#!/usr/bin/env python
"""
Generate sample terrain_attributes.csv and create interactive maps.

This script creates sample microclimate cell data and generates the five
interactive Leaflet HTML maps for visualization.
"""

import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path
from shapely.geometry import box
from datetime import datetime, timezone

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.output.write_maps import write_maps
from src.output.write_terrain_attributes import write_terrain_attributes
from src import config


def generate_sample_cells_data():
    """Generate sample microclimate cell data for Portland area."""
    cells = []
    cell_id = 1
    
    # Create a 5x5 grid of cells in Portland area
    for i in range(5):
        for j in range(5):
            # Create 500m x 500m cells (approximate in degrees)
            lon = -122.7 + (i * 0.01)
            lat = 45.4 + (j * 0.01)
            
            # Determine cell type based on position
            if i < 2 and j < 2:
                cell_type = "urban"
                impervious = 60 + np.random.randint(-10, 10)
                hdd_offset = -100
            elif i < 3 and j < 3:
                cell_type = "suburban"
                impervious = 35 + np.random.randint(-10, 10)
                hdd_offset = -50
            else:
                cell_type = "rural"
                impervious = 10 + np.random.randint(-5, 5)
                hdd_offset = 50
            
            # Determine terrain position
            terrain_positions = ["windward", "leeward", "valley", "ridge"]
            terrain_position = terrain_positions[(i + j) % 4]
            
            # Compute HDD based on terrain and cell type
            base_hdd = 4700
            terrain_mult = {
                "windward": 1.08,
                "leeward": 0.98,
                "valley": 1.02,
                "ridge": 1.15,
            }[terrain_position]
            
            elevation = 200 + (i * 50) + (j * 30)
            elev_addition = (elevation - 30) / 1000 * 630  # KPDX is at 30 ft
            
            uhi_offset = 3.0 - (impervious / 100) * 2.5
            uhi_reduction = uhi_offset * 180
            
            road_heat = 25 - (cell_type == "rural") * 20
            traffic_reduction = road_heat / 5.5 * 9/5 * 180
            
            effective_hdd = (
                base_hdd * terrain_mult
                + elev_addition
                - uhi_reduction
                - traffic_reduction
            )
            
            cells.append({
                "zip_code": "97201",
                "cell_id": f"cell_{cell_id:03d}",
                "cell_type": cell_type,
                "cell_area_sqm": 250000.0,
                "base_station": "KPDX",
                "terrain_position": terrain_position,
                "mean_elevation_ft": float(elevation),
                "dominant_aspect_deg": 180 + (i * 20),
                "mean_wind_ms": 2.5 + (j * 0.3),
                "wind_infiltration_mult": 1.0 + (j * 0.05),
                "prism_annual_hdd": 4700.0,
                "lst_summer_c": 25.0 - (impervious / 100) * 3,
                "mean_impervious_pct": float(impervious),
                "surface_albedo": 0.20 - (impervious / 100) * 0.15,
                "uhi_offset_f": float(uhi_offset),
                "road_heat_flux_wm2": float(road_heat),
                "road_temp_offset_f": float(road_heat / 5.5 * 9/5),
                "hdd_terrain_mult": float(terrain_mult),
                "hdd_elev_addition": float(elev_addition),
                "hdd_uhi_reduction": float(uhi_reduction),
                "effective_hdd": float(effective_hdd),
            })
            cell_id += 1
    
    return pd.DataFrame(cells)


def generate_sample_cells_gdf(cells_df):
    """Convert cells DataFrame to GeoDataFrame with geometries."""
    geometries = []
    for idx, row in cells_df.iterrows():
        # Create 500m x 500m cells (approximate in degrees)
        lon = -122.7 + ((idx % 5) * 0.01)
        lat = 45.4 + ((idx // 5) * 0.01)
        geom = box(lon, lat, lon + 0.01, lat + 0.01)
        geometries.append(geom)
    
    cells_df = cells_df.copy()
    cells_df["geometry"] = geometries
    gdf = gpd.GeoDataFrame(cells_df, crs="EPSG:4326")
    return gdf


def main():
    """Generate sample data and create maps."""
    print("Generating sample microclimate cell data...")
    cells_df = generate_sample_cells_data()
    
    print(f"Generated {len(cells_df)} cells")
    print(f"Columns: {cells_df.columns.tolist()}")
    
    # Write terrain_attributes.csv
    output_dir = Path("output/microclimate")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\nWriting terrain_attributes.csv...")
    write_terrain_attributes(
        cells_df,
        region_code="R1",
        output_path=output_dir / "terrain_attributes.csv",
        pipeline_version=config.PIPELINE_VERSION,
        lidar_vintage=config.NLCD_VINTAGE,
        nlcd_vintage=config.NLCD_VINTAGE,
        prism_period=config.PRISM_PERIOD,
    )
    print(f"Wrote {output_dir / 'terrain_attributes.csv'}")
    
    # Generate GeoDataFrame and create maps
    print("\nGenerating GeoDataFrame...")
    cells_gdf = generate_sample_cells_gdf(cells_df)
    
    print("Creating interactive maps...")
    write_maps(cells_gdf, output_dir=output_dir)
    
    print("\nMaps generated successfully!")
    print(f"Output directory: {output_dir}")
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("map_*.html")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
