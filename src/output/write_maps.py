"""
Interactive Leaflet HTML maps for microclimate cell visualization.

Generates multiple choropleth maps showing:
- Cell-level effective HDD
- Terrain position classification
- UHI effect magnitude
- Wind infiltration multiplier
- Traffic heat flux

Each map includes layer controls, cell info popups, and zoom/pan capabilities.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box, mapping

logger = logging.getLogger(__name__)


def _get_color_scale(value: float, min_val: float, max_val: float, scheme: str = "viridis") -> str:
    """
    Map a normalized value to a hex color using a color scheme.
    
    Args:
        value: The value to map (will be normalized to [0, 1])
        min_val: Minimum value in the range
        max_val: Maximum value in the range
        scheme: Color scheme name ('viridis', 'plasma', 'inferno', 'magma', 'rdylbu', 'rdylgn')
    
    Returns:
        Hex color string (e.g., '#FF0000')
    """
    if max_val == min_val:
        normalized = 0.5
    else:
        normalized = (value - min_val) / (max_val - min_val)
    normalized = max(0, min(1, normalized))  # Clamp to [0, 1]
    
    # Color schemes as RGB tuples (0-1 scale)
    schemes = {
        "viridis": [
            (0.267, 0.004, 0.329),  # dark purple
            (0.282, 0.140, 0.458),
            (0.254, 0.265, 0.530),
            (0.206, 0.371, 0.553),
            (0.163, 0.471, 0.558),
            (0.127, 0.567, 0.550),
            (0.134, 0.658, 0.517),
            (0.266, 0.748, 0.440),
            (0.477, 0.821, 0.318),
            (0.741, 0.873, 0.149),
            (0.993, 0.906, 0.144),  # yellow
        ],
        "plasma": [
            (0.050, 0.030, 0.529),  # dark blue
            (0.275, 0.005, 0.592),
            (0.493, 0.014, 0.606),
            (0.649, 0.084, 0.580),
            (0.759, 0.176, 0.492),
            (0.827, 0.280, 0.370),
            (0.865, 0.387, 0.235),
            (0.878, 0.498, 0.101),
            (0.878, 0.610, 0.000),
            (0.941, 0.757, 0.131),
            (0.940, 0.975, 0.131),  # yellow
        ],
        "rdylbu": [
            (0.404, 0.000, 0.122),  # dark red
            (0.706, 0.016, 0.150),
            (0.837, 0.188, 0.153),
            (0.956, 0.427, 0.263),
            (0.992, 0.682, 0.380),
            (1.000, 0.910, 0.596),
            (0.816, 0.898, 0.773),
            (0.569, 0.816, 0.914),
            (0.267, 0.647, 0.910),
            (0.192, 0.502, 0.745),
            (0.192, 0.404, 0.659),  # dark blue
        ],
        "rdylgn": [
            (0.404, 0.000, 0.122),  # dark red
            (0.706, 0.016, 0.150),
            (0.837, 0.188, 0.153),
            (0.956, 0.427, 0.263),
            (0.992, 0.682, 0.380),
            (1.000, 0.910, 0.596),
            (0.816, 0.898, 0.773),
            (0.569, 0.898, 0.569),
            (0.267, 0.816, 0.267),
            (0.192, 0.659, 0.192),
            (0.000, 0.404, 0.000),  # dark green
        ],
    }
    
    color_list = schemes.get(scheme, schemes["viridis"])
    idx = int(normalized * (len(color_list) - 1))
    r, g, b = color_list[idx]
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def _get_categorical_color(category: str, category_type: str) -> str:
    """
    Map a categorical value to a hex color.
    
    Args:
        category: The category value (e.g., 'urban', 'windward')
        category_type: Type of category ('terrain_position', 'cell_type')
    
    Returns:
        Hex color string
    """
    colors = {
        "terrain_position": {
            "windward": "#1f77b4",  # blue
            "leeward": "#ff7f0e",   # orange
            "valley": "#2ca02c",    # green
            "ridge": "#d62728",     # red
        },
        "cell_type": {
            "urban": "#e41a1c",     # red
            "suburban": "#377eb8",  # blue
            "rural": "#4daf4a",     # green
            "valley": "#984ea3",    # purple
            "ridge": "#ff7f00",     # orange
            "gorge": "#a65628",     # brown
        },
    }
    return colors.get(category_type, {}).get(category, "#999999")


def _create_geojson_feature(
    geometry: Dict,
    properties: Dict,
    cell_id: str,
    color: str,
    popup_html: str,
) -> Dict:
    """Create a GeoJSON feature with styling and popup."""
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            **properties,
            "cell_id": cell_id,
            "color": color,
            "popup": popup_html,
        },
    }


def _build_popup_html(row: pd.Series) -> str:
    """Build HTML popup content for a cell."""
    html = f"""
    <div style="font-family: Arial, sans-serif; font-size: 12px; width: 250px;">
        <h4 style="margin: 0 0 8px 0; color: #333;">{row.get('cell_id', 'N/A')}</h4>
        <table style="width: 100%; border-collapse: collapse;">
            <tr style="background: #f5f5f5;">
                <td style="padding: 4px; border: 1px solid #ddd;"><b>Effective HDD</b></td>
                <td style="padding: 4px; border: 1px solid #ddd;">{row.get('effective_hdd', 'N/A'):.0f}</td>
            </tr>
            <tr>
                <td style="padding: 4px; border: 1px solid #ddd;"><b>Terrain</b></td>
                <td style="padding: 4px; border: 1px solid #ddd;">{row.get('terrain_position', 'N/A')}</td>
            </tr>
            <tr style="background: #f5f5f5;">
                <td style="padding: 4px; border: 1px solid #ddd;"><b>Elevation (ft)</b></td>
                <td style="padding: 4px; border: 1px solid #ddd;">{row.get('mean_elevation_ft', 'N/A'):.0f}</td>
            </tr>
            <tr>
                <td style="padding: 4px; border: 1px solid #ddd;"><b>Wind (m/s)</b></td>
                <td style="padding: 4px; border: 1px solid #ddd;">{row.get('mean_wind_ms', 'N/A'):.2f}</td>
            </tr>
            <tr style="background: #f5f5f5;">
                <td style="padding: 4px; border: 1px solid #ddd;"><b>Impervious (%)</b></td>
                <td style="padding: 4px; border: 1px solid #ddd;">{row.get('mean_impervious_pct', 'N/A'):.1f}</td>
            </tr>
            <tr>
                <td style="padding: 4px; border: 1px solid #ddd;"><b>UHI Offset (°F)</b></td>
                <td style="padding: 4px; border: 1px solid #ddd;">{row.get('uhi_offset_f', 'N/A'):.2f}</td>
            </tr>
            <tr style="background: #f5f5f5;">
                <td style="padding: 4px; border: 1px solid #ddd;"><b>Road Heat (W/m²)</b></td>
                <td style="padding: 4px; border: 1px solid #ddd;">{row.get('road_heat_flux_wm2', 'N/A'):.1f}</td>
            </tr>
            <tr>
                <td style="padding: 4px; border: 1px solid #ddd;"><b>Cell Area (m²)</b></td>
                <td style="padding: 4px; border: 1px solid #ddd;">{row.get('cell_area_sqm', 'N/A'):.0f}</td>
            </tr>
        </table>
    </div>
    """
    return html


def _create_html_map(
    title: str,
    geojson_data: Dict,
    layer_name: str,
    color_column: str,
    color_type: str,  # 'continuous' or 'categorical'
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    color_scheme: str = "viridis",
) -> str:
    """
    Create a complete Leaflet HTML map.
    
    Args:
        title: Map title
        geojson_data: GeoJSON FeatureCollection
        layer_name: Name of the data layer
        color_column: Column name used for coloring
        color_type: 'continuous' or 'categorical'
        min_val: Minimum value for continuous scale
        max_val: Maximum value for continuous scale
        color_scheme: Color scheme name for continuous data
    
    Returns:
        HTML string
    """
    # Compute bounds from GeoJSON
    bounds = [[90, 180], [-90, -180]]  # [min_lat, min_lon], [max_lat, max_lon]
    for feature in geojson_data.get("features", []):
        geom = feature.get("geometry", {})
        if geom.get("type") == "Polygon":
            coords = geom.get("coordinates", [[]])[0]
            for lon, lat in coords:
                bounds[0][0] = min(bounds[0][0], lat)
                bounds[0][1] = min(bounds[0][1], lon)
                bounds[1][0] = max(bounds[1][0], lat)
                bounds[1][1] = max(bounds[1][1], lon)
    
    center_lat = (bounds[0][0] + bounds[1][0]) / 2
    center_lon = (bounds[0][1] + bounds[1][1]) / 2
    
    # Build legend HTML
    if color_type == "continuous":
        legend_html = f"""
        <div style="background: white; padding: 10px; border-radius: 5px; box-shadow: 0 0 15px rgba(0,0,0,0.2);">
            <h4 style="margin: 0 0 10px 0;">{color_column}</h4>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 20px; background: {_get_color_scale(min_val, min_val, max_val, color_scheme)}; border: 1px solid #999;"></div>
                <span style="margin-left: 8px; font-size: 12px;">{min_val:.0f}</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 20px; background: {_get_color_scale((min_val + max_val) / 2, min_val, max_val, color_scheme)}; border: 1px solid #999;"></div>
                <span style="margin-left: 8px; font-size: 12px;">{(min_val + max_val) / 2:.0f}</span>
            </div>
            <div style="display: flex; align-items: center;">
                <div style="width: 20px; height: 20px; background: {_get_color_scale(max_val, min_val, max_val, color_scheme)}; border: 1px solid #999;"></div>
                <span style="margin-left: 8px; font-size: 12px;">{max_val:.0f}</span>
            </div>
        </div>
        """
    else:
        # Categorical legend
        categories = set()
        for feature in geojson_data.get("features", []):
            cat = feature.get("properties", {}).get(color_column)
            if cat:
                categories.add(cat)
        
        legend_items = ""
        for cat in sorted(categories):
            color = _get_categorical_color(cat, color_column)
            legend_items += f"""
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 20px; background: {color}; border: 1px solid #999;"></div>
                <span style="margin-left: 8px; font-size: 12px;">{cat}</span>
            </div>
            """
        
        legend_html = f"""
        <div style="background: white; padding: 10px; border-radius: 5px; box-shadow: 0 0 15px rgba(0,0,0,0.2);">
            <h4 style="margin: 0 0 10px 0;">{color_column}</h4>
            {legend_items}
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
        <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
        <style>
            body {{ margin: 0; padding: 0; }}
            #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
            .info {{ padding: 6px 8px; background: white; box-shadow: 0 0 15px rgba(0,0,0,0.2); border-radius: 5px; }}
            .legend {{ background: white; padding: 10px; border-radius: 5px; box-shadow: 0 0 15px rgba(0,0,0,0.2); }}
            .legend h4 {{ margin: 0 0 10px 0; }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            var map = L.map('map').setView([{center_lat}, {center_lon}], 9);
            
            L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '© OpenStreetMap contributors',
                maxZoom: 19,
                crossOrigin: true
            }}).addTo(map);
            
            var geojsonData = {json.dumps(geojson_data)};
            
            function getStyle(feature) {{
                return {{
                    fillColor: feature.properties.color,
                    weight: 1,
                    opacity: 0.8,
                    color: '#333',
                    dashArray: '3',
                    fillOpacity: 0.7
                }};
            }}
            
            function onEachFeature(feature, layer) {{
                var popup = L.popup().setContent(feature.properties.popup);
                layer.bindPopup(popup);
                layer.on('click', function() {{
                    layer.openPopup();
                }});
            }}
            
            L.geoJSON(geojsonData, {{
                style: getStyle,
                onEachFeature: onEachFeature
            }}).addTo(map);
            
            // Add legend
            var legend = L.control({{position: 'bottomright'}});
            legend.onAdd = function(map) {{
                var div = L.DomUtil.create('div', 'legend');
                div.innerHTML = `{legend_html}`;
                return div;
            }};
            legend.addTo(map);
            
            // Add title
            var title = L.control({{position: 'topleft'}});
            title.onAdd = function(map) {{
                var div = L.DomUtil.create('div', 'info');
                div.innerHTML = '<h3 style="margin: 0;">{title}</h3>';
                return div;
            }};
            title.addTo(map);
        </script>
    </body>
    </html>
    """
    return html


def write_maps(
    cells_gdf: gpd.GeoDataFrame,
    zip_boundaries_gdf: Optional[gpd.GeoDataFrame] = None,
    output_dir: Path = Path("output/microclimate"),
) -> None:
    """
    Generate interactive Leaflet HTML maps for microclimate cells.
    
    Args:
        cells_gdf: GeoDataFrame with cell geometries and attributes
        zip_boundaries_gdf: Optional GeoDataFrame with ZIP code boundaries
        output_dir: Directory to write map HTML files
    
    Raises:
        ValueError: If required columns are missing from cells_gdf
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Validate required columns
    required_cols = [
        "cell_id",
        "effective_hdd",
        "terrain_position",
        "uhi_offset_f",
        "wind_infiltration_mult",
        "road_heat_flux_wm2",
        "mean_elevation_ft",
        "mean_wind_ms",
        "mean_impervious_pct",
    ]
    missing_cols = [col for col in required_cols if col not in cells_gdf.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Ensure geometry column is valid
    if cells_gdf.geometry.isna().any():
        logger.warning("Removing rows with null geometries")
        cells_gdf = cells_gdf[cells_gdf.geometry.notna()].copy()
    
    # Convert to EPSG:4326 for Leaflet
    if cells_gdf.crs != "EPSG:4326":
        cells_gdf = cells_gdf.to_crs("EPSG:4326")
    
    # Define map configurations
    maps_config = [
        {
            "filename": "map_effective_hdd.html",
            "title": "Cell-Level Effective HDD",
            "color_column": "effective_hdd",
            "color_type": "continuous",
            "color_scheme": "viridis",
        },
        {
            "filename": "map_terrain_position.html",
            "title": "Terrain Position Classification",
            "color_column": "terrain_position",
            "color_type": "categorical",
        },
        {
            "filename": "map_uhi_effect.html",
            "title": "Urban Heat Island Effect (°F)",
            "color_column": "uhi_offset_f",
            "color_type": "continuous",
            "color_scheme": "rdylbu",
        },
        {
            "filename": "map_wind_infiltration.html",
            "title": "Wind Infiltration Multiplier",
            "color_column": "wind_infiltration_mult",
            "color_type": "continuous",
            "color_scheme": "plasma",
        },
        {
            "filename": "map_traffic_heat.html",
            "title": "Traffic Heat Flux (W/m²)",
            "color_column": "road_heat_flux_wm2",
            "color_type": "continuous",
            "color_scheme": "rdylgn",
        },
    ]
    
    # Generate each map
    for map_config in maps_config:
        logger.info(f"Generating {map_config['filename']}...")
        
        color_column = map_config["color_column"]
        color_type = map_config["color_type"]
        
        # Build GeoJSON features
        features = []
        for idx, row in cells_gdf.iterrows():
            if row.geometry.is_empty:
                continue
            
            # Determine color
            if color_type == "continuous":
                min_val = cells_gdf[color_column].min()
                max_val = cells_gdf[color_column].max()
                color = _get_color_scale(row[color_column], min_val, max_val, map_config.get("color_scheme", "viridis"))
            else:
                color = _get_categorical_color(row[color_column], color_column)
            
            # Build popup
            popup_html = _build_popup_html(row)
            
            # Create feature
            feature = _create_geojson_feature(
                geometry=mapping(row.geometry),
                properties={col: row[col] for col in cells_gdf.columns if col != "geometry"},
                cell_id=row.get("cell_id", "unknown"),
                color=color,
                popup_html=popup_html,
            )
            features.append(feature)
        
        geojson_data = {"type": "FeatureCollection", "features": features}
        
        # Create HTML map
        if color_type == "continuous":
            min_val = cells_gdf[color_column].min()
            max_val = cells_gdf[color_column].max()
            html = _create_html_map(
                title=map_config["title"],
                geojson_data=geojson_data,
                layer_name=color_column,
                color_column=color_column,
                color_type=color_type,
                min_val=min_val,
                max_val=max_val,
                color_scheme=map_config.get("color_scheme", "viridis"),
            )
        else:
            html = _create_html_map(
                title=map_config["title"],
                geojson_data=geojson_data,
                layer_name=color_column,
                color_column=color_column,
                color_type=color_type,
            )
        
        # Write HTML file
        output_path = output_dir / map_config["filename"]
        output_path.write_text(html)
        logger.info(f"Wrote {output_path}")
    
    logger.info(f"Map generation complete. Output directory: {output_dir}")
