# Pipeline Output

Pipeline writes here at runtime. Files are not committed to version control.

## Top-level

- `terrain_attributes.csv` — pre-computed microclimate lookup table (config: `TERRAIN_ATTRIBUTES_CSV`)
- `qa_report.html` — QA validation report
- `qa_report.md` — QA validation report (markdown)
- `pipeline.log` — step-by-step execution log

## runs/

Each pipeline execution produces a self-contained, web-deployable folder here. The folder name encodes the run parameters so re-runs never overwrite each other.

**Folder naming**: `output/runs/{region}__{weather_year or "normal"}__{YYYYMMDDTHHMM}/`

Examples:
```
output/runs/region_1__normal__20250415T1432/
output/runs/region_1__2024__20250416T0900/
```

### Folder contents

```
region_1__normal__20250415T1432/
├── map_effective_hdd.html   ← final combined Leaflet map (open this)
├── map_qa_flags.html        ← QA status map
├── map_boundary.html        ← boundary + ZIP code verification map
├── terrain_attributes.csv   ← pre-computed microclimate lookup table
├── qa_report.html           ← QA validation report
├── qa_report.md             ← QA validation report (markdown)
├── pipeline.log             ← step-by-step execution log
├── run_manifest.json        ← run parameters, versions, file list
└── geojson/
    ├── lidar_dem.geojson
    ├── prism_annual_hdd.geojson
    ├── landsat_lst.geojson
    ├── mesowest_wind_stations.geojson
    ├── nrel_wind_surface.geojson
    ├── nlcd_impervious.geojson
    ├── road_heat_flux.geojson
    ├── proc_clipped_boundary.geojson
    ├── proc_downscaled.geojson
    ├── proc_terrain_analysis.geojson
    ├── proc_thermal_logic.geojson
    ├── proc_wind_steering.geojson
    ├── proc_road_buffers.geojson
    ├── proc_anthropogenic_load.geojson
    ├── proc_effective_hdd_grid.geojson
    ├── output_microclimate_polygons.geojson
    ├── output_hdd_range_check.geojson
    └── output_directional_sanity.geojson
```

The HTML files inline all GeoJSON data as JavaScript variables — no web server needed. The entire folder can be:
- Opened locally by double-clicking `map_effective_hdd.html`
- Copied to a web server and served as static files
- Zipped and shared as a complete run artifact

`run_manifest.json` schema:
```json
{
  "region_name": "region_1",
  "weather_year": null,
  "run_date": "2025-04-15T14:32:00",
  "pipeline_version": "1.0.0",
  "lidar_vintage": 2021,
  "nlcd_vintage": 2021,
  "prism_period": "1991-2020",
  "files": ["map_effective_hdd.html", "terrain_attributes.csv", ...]
}
```

## geojson/ (working directory)

One GeoJSON file per loader and processor stage, plus final output files. All polygon layers use district boundaries as the geometry unit. Points and lines are used only where no polygon exists (weather stations, road segments).

Every polygon feature carries a structured popup with three sections: **Stage** (which task produced it), **Inputs** (source data and parameters used), **Outputs** (computed values for that district).

### Loader outputs (Task 2) — district Polygons unless noted

| File | Geometry | Popup highlights |
|------|----------|-----------------|
| `lidar_dem.geojson` | Polygons | `mean_elevation_ft`, `min/max_elevation_ft`, `mean_slope_deg` |
| `prism_annual_hdd.geojson` | Polygons | `prism_annual_hdd`, 12 monthly HDD contributions |
| `landsat_lst.geojson` | Polygons | `lst_summer_c`, `lst_urban_c`, `lst_rural_c`, `lst_urban_rural_diff_c` |
| `mesowest_wind_stations.geojson` | **Points** (no polygon) | `station_id`, `mean_wind_ms`, `p90_wind_ms`, `elevation_ft` |
| `nrel_wind_surface.geojson` | Polygons | `mean_wind_80m_ms`, `mean_wind_10m_ms` |
| `nlcd_impervious.geojson` | Polygons | `mean_impervious_pct`, `pct_urban`, `pct_rural` |
| `road_heat_flux.geojson` | **LineStrings** (no polygon) | `AADT`, `heat_flux_wm2`, `road_temp_offset_f`, `source` |

### Processor outputs (Task 3) — district Polygons unless noted

| File | Geometry | Popup highlights |
|------|----------|-----------------|
| `proc_clipped_boundary.geojson` | **Polygon** (region boundary) | `crs`, `pixel_width_m`, `pixel_height_m`, `masked_pixel_count` |
| `proc_downscaled.geojson` | Polygons | `prism_hdd_downscaled`, `nlcd_impervious_downscaled`, `nrel_wind_10m_downscaled` |
| `proc_terrain_analysis.geojson` | Polygons | `terrain_position`, `dominant_aspect_deg`, `mean_tpi`, `wind_shadow_pct`, `lapse_hdd_addition` |
| `proc_thermal_logic.geojson` | Polygons | `surface_albedo`, `uhi_offset_f`, `uhi_hdd_reduction`, `calibration_applied` |
| `proc_wind_steering.geojson` | Polygons | `wind_stagnation_mult`, `wind_infiltration_mult`, `gorge_floor_applied` |
| `proc_road_buffers.geojson` | **Polygons** (buffer zones) | `AADT`, `buffer_m`, `heat_flux_wm2` |
| `proc_anthropogenic_load.geojson` | Polygons | `mean_road_heat_flux_wm2`, `road_temp_offset_f`, `road_segment_count` |
| `proc_effective_hdd_grid.geojson` | Polygons | Full formula breakdown: `base_hdd × terrain_mult + elev_addition − uhi_reduction − traffic_reduction = effective_hdd` |

### Output GeoJSON files (Task 4) — district Polygons

| File | Popup highlights |
|------|-----------------|
| `output_microclimate_polygons.geojson` | All inputs + all corrections + `effective_hdd` + versioning metadata — **primary layer** |
| `output_hdd_range_check.geojson` | `effective_hdd`, `range_status`, `in_range`; colored green/yellow/red |
| `output_directional_sanity.geojson` | `urban_rural_class`, `directional_check`, `sanity_note` |

All GeoJSON files use EPSG:4326.

## maps/ (deprecated)

HTML maps are now written directly into the run folder under `output/runs/`. See the `runs/` section above.
