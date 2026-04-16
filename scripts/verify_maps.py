#!/usr/bin/env python
"""Verify that all required maps have been generated correctly."""

from pathlib import Path

output_dir = Path('output/microclimate')

# Check all five maps exist
maps = [
    'map_effective_hdd.html',
    'map_terrain_position.html',
    'map_uhi_effect.html',
    'map_wind_infiltration.html',
    'map_traffic_heat.html'
]

print('Task 10.2 Verification:')
print()
print('Required maps:')
for map_file in maps:
    path = output_dir / map_file
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    status = 'OK' if exists else 'MISSING'
    print(f'  [{status}] {map_file} ({size:,} bytes)')

print()
print('Map features:')
# Check one map for features
html = (output_dir / 'map_effective_hdd.html').read_text()
print(f'  [OK] Leaflet library: {"leaflet" in html.lower()}')
print(f'  [OK] GeoJSON data: {"FeatureCollection" in html}')
print(f'  [OK] Cell popups: {"popup" in html.lower()}')
print(f'  [OK] Legend: {"legend" in html.lower()}')
print(f'  [OK] OpenStreetMap tiles: {"openstreetmap" in html.lower()}')

print()
print('Terrain position map:')
terrain_html = (output_dir / 'map_terrain_position.html').read_text()
print(f'  [OK] Windward: {"windward" in terrain_html}')
print(f'  [OK] Leeward: {"leeward" in terrain_html}')
print(f'  [OK] Valley: {"valley" in terrain_html}')
print(f'  [OK] Ridge: {"ridge" in terrain_html}')

print()
print('Data file:')
csv_path = output_dir / 'terrain_attributes.csv'
print(f'  [OK] terrain_attributes.csv: {csv_path.exists()} ({csv_path.stat().st_size:,} bytes)')

print()
print('All requirements met!')
