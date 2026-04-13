# Data Directory

Input data for the Regional Microclimate Modeling Engine. Each subdirectory maps to a config constant in `src/config.py`.

```
data/
├── lidar/              # LIDAR_DEM_RASTER       — 1m bare-earth DEM (GeoTIFF)
├── prism/              # PRISM_TEMP_DIR          — 12 monthly temperature normals (BIL/GeoTIFF)
├── landsat/            # LANDSAT_LST_RASTER      — Landsat 9 LST (GeoTIFF, optional)
├── wind/
│   ├── mesowest/       # MESOWEST_WIND_DIR       — per-station wind CSVs
│   └── nrel/           # NREL_WIND_RASTER        — 2km gridded wind resource (GeoTIFF)
├── nlcd/               # NLCD_IMPERVIOUS_RASTER  — NLCD 2021 imperviousness (GeoTIFF)
├── roads/              # ODOT_ROADS_SHP          — Oregon DOT AADT shapefile
│                       # WSDOT_ROADS_SHP         — Washington DOT AADT shapefile
├── boundary/           # BOUNDARY_SHP            — OR/WA combined state boundary (shapefile)
└── noaa_stations/      # (reference) NOAA station HDD normals and elevations
```

See each subdirectory's `README.md` for expected filenames, sources, and format details.

None of these files are committed to version control. Add them locally before running the pipeline.
