# Regional Microclimate Modeling Engine — Oregon & Washington

## Objective

A Python processing pipeline that generates high-resolution microclimate maps for Oregon and Washington at the ZIP code level. It integrates four data layers — terrain (1 m LiDAR DEM), surface character (NLCD imperviousness), atmospheric conditions (PRISM temperature normals + MesoWest/NREL wind), and anthropogenic heat (ODOT/WSDOT traffic volumes) — to compute temperature and wind variations at sub-ZIP-code scale. The pipeline produces an `effective_hdd` value for every ZIP code or Census block group, capturing terrain position, urban heat island effects, wind exposure, and traffic heat that a single weather station cannot represent. All corrections are pre-computed and written to `terrain_attributes.csv`, which downstream models can join at runtime without re-sampling any rasters.

---

## Spec Documents

| Document | Description |
|----------|-------------|
| [Requirements](`.kiro/specs/microclimate-engine/requirements.md`) | Functional requirements, user stories, and acceptance criteria |
| [Design](`.kiro/specs/microclimate-engine/design.md`) | Architecture, module structure, data flow, and output schema |
| [Tasks](`.kiro/specs/microclimate-engine/tasks.md`) | Implementation task list with sub-tasks |

---

## Getting Started

**Prerequisites**: Python 3.9+

```bash
# Install dependencies
pip install -r requirements.txt

# Run the pipeline for a single region
python -m src.pipeline --region region_1

# Run all regions sequentially
python -m src.pipeline --all-regions
```

Output is written to `output/microclimate/terrain_attributes.csv` plus an HTML/MD QA report and interactive Leaflet maps.

---

## Project Structure

```
Microclimates/
├── README.md
├── requirements.txt
├── .kiro/
│   └── specs/
│       └── microclimate-engine/
│           ├── requirements.md
│           ├── design.md
│           └── tasks.md
├── data/
│   ├── boundary/              # Region boundaries, ZIP code polygons, region registry
│   ├── lidar/                 # 1 m LiDAR DEM (DOGAMI / WA DNR)
│   ├── prism/                 # 12 monthly temperature normal GeoTIFFs
│   ├── landsat/               # Landsat 9 LST GeoTIFF
│   ├── wind/
│   │   ├── mesowest/          # Per-station wind CSVs
│   │   └── nrel/              # NREL wind resource GeoTIFF
│   ├── nlcd/                  # NLCD imperviousness GeoTIFF
│   ├── roads/                 # ODOT and WSDOT AADT shapefiles
│   └── noaa_stations/         # Station reference data
└── src/
    ├── config.py              # Constants, file paths, CRS, station reference data
    ├── pipeline.py            # Main orchestrator: run_region(region_name)
    ├── loaders/
    │   ├── load_region_registry.py
    │   ├── load_lidar_dem.py
    │   ├── load_prism_temperature.py
    │   ├── load_landsat_lst.py
    │   ├── load_mesowest_wind.py
    │   ├── load_nrel_wind.py
    │   ├── load_nlcd_impervious.py
    │   └── load_road_emissions.py
    ├── processors/
    │   ├── clip_to_boundary.py
    │   ├── downscale.py
    │   ├── terrain_analysis.py
    │   ├── thermal_logic.py
    │   ├── wind_steering.py
    │   ├── anthropogenic_load.py
    │   └── combine_corrections.py
    ├── validation/
    │   ├── qa_checks.py
    │   ├── billing_comparison.py
    │   └── run_config_completeness.py
    └── output/
        └── write_terrain_attributes.py
```

---

## How It Works

The pipeline supports two operating modes:

### Normals Mode (default)

1. **Boundary & region setup** — ZIP codes in OR/WA are grouped into processing regions. Each ZIP code is assigned to its nearest NOAA weather station.
2. **Terrain analysis** — LiDAR DEM drives aspect, slope, TPI, and windward/leeward classification.
3. **Atmospheric base** — PRISM 800 m temperature normals are bias-corrected to NOAA station observations and converted to annual HDD.
4. **Surface & thermal** — NLCD imperviousness drives albedo and urban heat island offsets, optionally calibrated against Landsat 9 LST.
5. **Wind** — MesoWest observations + NREL gridded wind produce stagnation and infiltration multipliers.
6. **Traffic heat** — ODOT/WSDOT AADT shapefiles produce buffered road heat flux.
7. **Combine** — All corrections merge into a single `effective_hdd` per ZIP code.
8. **QA** — Range checks, directional sanity, and optional billing comparison flag implausible values.

### Daily Mode (`--mode daily`)

1. **HRRR ingestion** — Download and cache HRRR 3 km GRIB2 analysis files (f00) from AWS S3 (`s3://noaa-hrrr-bdp-pds/`) or Google Cloud for a specified date range. Each file provides hourly temperature, wind, and pressure-level atmospheric fields across CONUS.
2. **Bias correction** — HRRR daily mean temperature is bias-corrected against PRISM climatology using `hrrr_adjusted = hrrr_raw + (prism_normal − hrrr_climatology)`, so that HRRR inherits PRISM's terrain-aware station calibration.
3. **Terrain corrections** — The same TPI, UHI, wind stagnation, and traffic heat corrections from normals mode are applied on top of the bias-corrected HRRR fields.
4. **Multi-altitude wind profiles** — Wind speed and direction are extracted at six GA flight altitudes (surface, 3,000 ft, 6,000 ft, 9,000 ft, 12,000 ft, 18,000 ft AGL) from HRRR pressure-level data, with log-pressure interpolation for intermediate altitudes.
5. **Daily output** — Daily `effective_hdd` + multi-altitude wind profiles per ZIP code, written to a time-series Parquet or CSV file.

---

## Data Inputs

Data files are not included in this repo. See the design doc for download sources and formats.

| Layer | Resolution | Source |
|-------|-----------|--------|
| LiDAR DEM | 1 m | DOGAMI (OR), WA DNR (WA) |
| PRISM temperature | 800 m | Oregon State University |
| HRRR atmospheric fields | 3 km | NOAA via AWS S3 (`s3://noaa-hrrr-bdp-pds/`) or Google Cloud |
| NLCD imperviousness | 30 m | USGS |
| Landsat 9 LST | 30 m | USGS via Planetary Computer |
| MesoWest wind | point | MesoWest / Synoptic |
| NREL wind resource | 2 km | NREL Wind Toolkit |
| Road traffic (AADT) | vector | ODOT (OR), WSDOT (WA) |
| State boundaries | vector | US Census TIGER/Line |
| ZIP code boundaries | vector | Census ZCTA / OpenDataSoft / RLIS |

---

## What This Data Is Useful For

The `effective_hdd` output captures real microclimate variation that a single airport weather station misses. A few ways this data gets used:

- **Energy demand forecasting** — Replace flat HDD assumptions with terrain-aware values. A valley ZIP code and a ridgetop ZIP code 5 miles apart can differ by 500+ HDD, which translates directly to heating load differences.
- **Rate case weather normalization** — Regulators want to know whether a utility's sales were high because of cold weather or because of growth. ZIP-code-level HDD lets you normalize at a much finer grain than one station per service territory.
- **Building energy modeling** — Feed `effective_hdd` into DOE-2, EnergyPlus, or simplified degree-day models to get location-specific heating estimates without running a full weather file for every site.
- **Urban heat island research** — The UHI offset and Landsat LST calibration columns quantify how much warmer dense urban areas run compared to surrounding rural land, useful for public health and urban planning studies.
- **Infrastructure planning** — Identify which ZIP codes face the highest wind infiltration loads (Gorge corridor) or the strongest cold-air pooling (Willamette Valley floor) to prioritize weatherization programs or distribution system upgrades.
- **Climate adaptation analysis** — Compare `effective_hdd` across vintages as land cover changes (new development, wildfire, reforestation) to track how microclimate shifts over time.
- **Insurance and risk modeling** — Freeze risk, pipe burst probability, and snow load estimates all benefit from knowing whether a location sits in a sheltered valley or on an exposed ridge.
- **Aviation weather and flight planning** — Terrain position, wind stagnation, and cold-air pooling data help identify fog-prone valleys and turbulence corridors. Pilots and dispatchers operating out of smaller PNW airfields (Aurora, Troutdale, The Dalles) can use the wind and TPI layers to anticipate conditions that METAR stations don't capture between reporting intervals. In daily mode, multi-altitude wind profiles from HRRR pressure-level data give GA pilots wind speed and direction at six standard cruise altitudes (surface through 18,000 ft AGL) per ZIP code, enabling altitude-optimized route planning and turbulence avoidance without relying solely on winds-aloft forecasts from distant upper-air stations.
- **Drone / UAS operations** — Low-altitude wind variability matters for delivery drones and survey flights. The merged MesoWest + NREL wind surface at 10 m height gives a much better picture of surface-level gusts and sheltering than the 80 m hub-height data alone, especially in the Gorge corridor and Cascade foothills. Daily mode adds HRRR-derived wind profiles at 3,000 ft and 6,000 ft AGL, which are the primary operating altitudes for beyond-visual-line-of-sight (BVLOS) UAS missions.
- **Airport microclimate characterization** — Quantify how much an airport's official ASOS/AWOS readings diverge from conditions just a few miles away due to terrain and land cover. Useful for calibrating TAF accuracy and understanding why pilot reports (PIREPs) of icing or turbulence don't always match the nearest station.
- **Daily energy demand tracking** — Daily mode produces time-series `effective_hdd` per ZIP code, enabling day-by-day load tracking and short-range demand forecasting that captures terrain-driven microclimate variation. This is more granular than using a single station's daily HDD for an entire service territory.
- **Historical weather reconstruction** — With HRRR data available from ~2014 to present, daily mode can reconstruct terrain-corrected daily HDD for any historical period, useful for after-the-fact billing analysis, rate case exhibits, and weather normalization studies that need daily granularity.
