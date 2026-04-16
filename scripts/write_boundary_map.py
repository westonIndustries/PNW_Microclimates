"""
Generate self-contained Leaflet HTML map of region boundary and ZIP codes.

Creates an interactive map showing the region_1 boundary and all ZIP code
boundaries with layer controls and popup information.

Usage:
    python scripts/write_boundary_map.py
    python scripts/write_boundary_map.py --output output/boundary_map.html
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import geopandas as gpd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Leaflet CSS and JS URLs
LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"
LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"


def load_boundary_data(boundary_dir: Path) -> tuple[dict, dict]:
    """Load region boundary and ZIP code data.

    Parameters
    ----------
    boundary_dir : Path
        Directory containing boundary GeoJSON files.

    Returns
    -------
    tuple[dict, dict]
        - Region boundary GeoJSON
        - ZIP codes GeoJSON
    """
    logger.info("Loading boundary data...")

    # Load region boundary
    region_path = boundary_dir / "region_1.geojson"
    if not region_path.exists():
        logger.warning(f"Region boundary not found: {region_path}")
        region_geojson = None
    else:
        with open(region_path) as f:
            region_geojson = json.load(f)
        logger.info(f"  Loaded region boundary from {region_path}")

    # Load ZIP codes
    zipcodes_path = boundary_dir / "zipcodes_orwa.geojson"
    if not zipcodes_path.exists():
        logger.warning(f"ZIP codes not found: {zipcodes_path}")
        zipcodes_geojson = None
    else:
        with open(zipcodes_path) as f:
            zipcodes_geojson = json.load(f)
        logger.info(f"  Loaded {len(zipcodes_geojson['features'])} ZIP codes from {zipcodes_path}")

    return region_geojson, zipcodes_geojson


def create_html_map(
    region_geojson: dict,
    zipcodes_geojson: dict,
    output_path: Path,
) -> None:
    """Create self-contained Leaflet HTML map.

    Parameters
    ----------
    region_geojson : dict
        Region boundary GeoJSON.
    zipcodes_geojson : dict
        ZIP codes GeoJSON.
    output_path : Path
        Output HTML file path.
    """
    logger.info(f"Creating HTML map...")

    # Compute center and zoom from region bounds
    if region_geojson and region_geojson["features"]:
        bbox = region_geojson["features"][0]["properties"]["bounding_box"]
        center_lat = (bbox["miny"] + bbox["maxy"]) / 2
        center_lon = (bbox["minx"] + bbox["maxx"]) / 2
        zoom = 7
    else:
        center_lat = 45.5
        center_lon = -120.5
        zoom = 7

    # Build HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Region 1 Boundary and ZIP Codes</title>
    <link rel="stylesheet" href="{LEAFLET_CSS}" />
    <script src="{LEAFLET_JS}"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
        }}
        #map {{
            position: absolute;
            top: 0;
            bottom: 0;
            width: 100%;
        }}
        .info {{
            padding: 6px 8px;
            font: 14px/16px Arial, Helvetica, sans-serif;
            background: white;
            background: rgba(255,255,255,0.8);
            box-shadow: 0 0 15px rgba(0,0,0,0.2);
            border-radius: 5px;
        }}
        .info h4 {{
            margin: 0 0 5px 0;
            color: #333;
        }}
        .legend {{
            line-height: 18px;
            color: #555;
        }}
        .legend i {{
            width: 18px;
            height: 18px;
            float: left;
            margin-right: 8px;
            opacity: 0.7;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        // Initialize map
        var map = L.map('map').setView([{center_lat}, {center_lon}], {zoom});

        // Add base layer
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors',
            maxZoom: 19
        }}).addTo(map);

        // Region boundary GeoJSON
        var regionGeoJSON = {json.dumps(region_geojson)};

        // ZIP codes GeoJSON
        var zipcodesGeoJSON = {json.dumps(zipcodes_geojson)};

        // Style functions
        function getZipCodeColor(source) {{
            switch(source) {{
                case 'rlis': return '#1f77b4';      // Blue
                case 'opendata': return '#ff7f0e';  // Orange
                case 'census': return '#2ca02c';    // Green
                default: return '#999';
            }}
        }}

        function getZipCodeStyle(feature) {{
            return {{
                fillColor: getZipCodeColor(feature.properties.source),
                weight: 1,
                opacity: 0.7,
                color: '#666',
                dashArray: '3',
                fillOpacity: 0.3
            }};
        }}

        function getRegionStyle(feature) {{
            return {{
                fillColor: 'none',
                weight: 3,
                opacity: 1,
                color: '#d62728',
                dashArray: '5,5',
                fillOpacity: 0
            }};
        }}

        // Popup functions
        function getZipCodePopup(feature) {{
            var props = feature.properties;
            return '<div class="info">' +
                '<h4>ZIP Code ' + props.zip_code + '</h4>' +
                '<p><b>State:</b> ' + props.state + '</p>' +
                '<p><b>Place:</b> ' + (props.po_name || 'N/A') + '</p>' +
                '<p><b>Source:</b> ' + props.source + '</p>' +
                '<p><b>Region:</b> ' + props.region_code + '</p>' +
                '</div>';
        }}

        function getRegionPopup(feature) {{
            var props = feature.properties;
            return '<div class="info">' +
                '<h4>' + props.region_name + '</h4>' +
                '<p><b>Code:</b> ' + props.region_code + '</p>' +
                '<p><b>States:</b> ' + props.states + '</p>' +
                '</div>';
        }}

        // Add ZIP code layer
        var zipcodesLayer = L.geoJSON(zipcodesGeoJSON, {{
            style: getZipCodeStyle,
            onEachFeature: function(feature, layer) {{
                layer.bindPopup(getZipCodePopup(feature));
            }}
        }});

        // Add region boundary layer
        var regionLayer = L.geoJSON(regionGeoJSON, {{
            style: getRegionStyle,
            onEachFeature: function(feature, layer) {{
                layer.bindPopup(getRegionPopup(feature));
            }}
        }});

        // Layer control
        var baseLayers = {{}};
        var overlayLayers = {{
            'Region Boundary': regionLayer,
            'ZIP Codes': zipcodesLayer
        }};

        L.control.layers(baseLayers, overlayLayers, {{
            position: 'topright',
            collapsed: false
        }}).addTo(map);

        // Add all layers to map
        regionLayer.addTo(map);
        zipcodesLayer.addTo(map);

        // Fit bounds to region
        if (regionGeoJSON.features.length > 0) {{
            var bounds = L.geoJSON(regionGeoJSON).getBounds();
            map.fitBounds(bounds);
        }}

        // Add legend
        var legend = L.control({{position: 'bottomleft'}});
        legend.onAdd = function(map) {{
            var div = L.DomUtil.create('div', 'info legend');
            div.innerHTML = '<h4>ZIP Code Sources</h4>' +
                '<i style="background: #1f77b4;"></i> RLIS (Oregon Metro)<br>' +
                '<i style="background: #ff7f0e;"></i> OpenDataSoft<br>' +
                '<i style="background: #2ca02c;"></i> Census TIGER/Line<br>' +
                '<i style="background: #d62728; border: 2px dashed;"></i> Region Boundary';
            return div;
        }};
        legend.addTo(map);
    </script>
</body>
</html>
"""

    # Write HTML file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    logger.info(f"  Wrote {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Leaflet HTML map of region boundary and ZIP codes"
    )
    parser.add_argument(
        "--boundary-dir",
        type=Path,
        default=Path("data/boundary"),
        help="Directory containing boundary GeoJSON files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/boundary_map.html"),
        help="Output HTML file path",
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Generating boundary map")
    logger.info("=" * 70)

    # Load boundary data
    region_geojson, zipcodes_geojson = load_boundary_data(args.boundary_dir)

    if region_geojson is None or zipcodes_geojson is None:
        logger.error("Missing required boundary data files")
        return

    # Create HTML map
    create_html_map(region_geojson, zipcodes_geojson, args.output)

    logger.info("=" * 70)
    logger.info("Boundary map generation complete!")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
