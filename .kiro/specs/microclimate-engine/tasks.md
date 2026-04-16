# Tasks — Regional Microclimate Modeling Engine

---

# Part A: Shared Foundation

All modes (monthly, daily, hourly, real-time) depend on these static data loaders, terrain processors, and surface physics layers. These are computed once and reused.

## Task 1: Project Setup and Configuration

- [x] 1.1 Create `src/` package structure with `__init__.py` files for `src`, `src/loaders`, `src/processors`, `src/validation`, and `src/output`
- [x] 1.2 Define all config constants in `src/config.py`: file paths (`LIDAR_DEM_RASTER`, `PRISM_TEMP_DIR`, `LANDSAT_LST_RASTER`, `MESOWEST_WIND_DIR`, `NREL_WIND_RASTER`, `NLCD_IMPERVIOUS_RASTER`, `ODOT_ROADS_SHP`, `WSDOT_ROADS_SHP`, `BOUNDARY_SHP`, `TERRAIN_ATTRIBUTES_CSV`, `REGION_REGISTRY_CSV`), CRS (`TARGET_CRS = "EPSG:26910"`), physics constants (`SOLAR_IRRADIANCE_WM2 = 200`, `LAPSE_RATE_HDD_PER_1000FT = 630`, `PREVAILING_WIND_DEG = 225`), station HDD normals (`STATION_HDD_NORMALS`), station elevations (`STATION_ELEVATIONS_FT`), and `ZIPCODE_STATION_MAP`; `REGION_REGISTRY_CSV` defaults to `data/boundary/region_registry.csv`
- [x] 1.3 Implement `src/loaders/load_region_registry.py` with two responsibilities: (a) **Generate** — if `REGION_REGISTRY_CSV` does not exist, generate it by reading `data/boundary/zipcodes_orwa.csv` (produced by task 6.3), assigning every OR and WA zip code to `region_code = "R1"` / `region_name = "region_1"`, computing `base_station` as the nearest NOAA station from `STATION_HDD_NORMALS` by haversine distance from each zip code's centroid, setting `lidar_vintage = 2021`, and writing the result to `REGION_REGISTRY_CSV`; (b) **Load** — read `REGION_REGISTRY_CSV` into a pandas DataFrame, group by `region_code` to build a dict of region definitions; each region entry contains: `region_name`, `base_stations` (unique list from the rows), `bounding_box` (computed as the min/max of all zip code centroids in that region, padded by 0.5°), `lidar_vintage`, and `zip_codes` (list of all zip codes assigned to that region); the pipeline reads this at startup and iterates over the unique regions — no region names are hardcoded anywhere in the code; if `zipcodes_orwa.csv` is also missing during generation, raise `FileNotFoundError` explaining that task 6.3 must be run first
- [x] 1.4 Write a config completeness property test (`src/validation/run_config_completeness.py`) that verifies: every ZIP code in `ZIPCODE_STATION_MAP` maps to a station in exactly one region, every base station in the region registry has an entry in `STATION_ELEVATIONS_FT` and `STATION_HDD_NORMALS`, and all required file path constants are defined

## Task 2: Static Data Loaders

- [x] 2.1 `src/loaders/load_lidar_dem.py` — open the GeoTIFF at `LIDAR_DEM_RASTER`, replace nodata with `numpy.nan`, return `(array: np.ndarray, transform: Affine, crs: CRS)`; raise `FileNotFoundError` with full path if file is missing
- [x] 2.2 `src/loaders/load_prism_temperature.py` — load all 12 monthly mean temperature BIL/GeoTIFF files from `PRISM_TEMP_DIR`, compute monthly HDD contribution for each month (monthly mean temp × days in month, base 65°F), sum to annual HDD grid; then apply station bias correction: for each of the 11 NOAA reference stations in `STATION_HDD_NORMALS`, compute the additive offset between the PRISM grid value at the station location and the station's known normal HDD, then spatially interpolate those offsets across the full grid using `scipy.interpolate.griddata` (linear) and add the interpolated offset surface to the raw PRISM HDD grid; raise `FileNotFoundError` listing missing months if any of the 12 files are absent
- [x] 2.3 `src/loaders/load_landsat_lst.py` — load a Landsat 9 Collection 2 Level-2 LST GeoTIFF, apply scale factor 0.00341802 and offset 149.0 to convert to Kelvin, subtract 273.15 to return a Celsius array; return `None` with a logged warning if the file is not available
- [x] 2.4 `src/loaders/load_mesowest_wind.py` — load per-station wind CSV files from `MESOWEST_WIND_DIR`, aggregate to annual mean wind speed and 90th-percentile wind speed per station; return a `dict[str, dict]` keyed by station ID
- [x] 2.5 `src/loaders/load_nrel_wind.py` — load the NREL wind resource GeoTIFF at `NREL_WIND_RASTER` (80 m hub height), apply power-law scaling to 10 m surface wind: `wind_10m = wind_80m × (10/80)^0.143`; return `(array, transform, crs)`
- [x] 2.6 `src/loaders/load_nlcd_impervious.py` — load the NLCD imperviousness GeoTIFF at `NLCD_IMPERVIOUS_RASTER`, replace sentinel values (127, 255) with `numpy.nan`, clip valid values to 0–100; return `(array, transform, crs)`
- [x] 2.7 `src/loaders/load_road_emissions.py` — load ODOT and WSDOT road shapefiles, concatenate into a single GeoDataFrame, filter to rows with AADT > 0, compute `heat_flux_wm2` per segment using `(AADT / 86400) × 150000 / road_area_m2` where road area = segment length × 3.7 m; return the GeoDataFrame with `heat_flux_wm2` column added

## Task 3: Static Processors (Terrain, Thermal, Wind, Traffic)

- [x] 3.1 `src/processors/clip_to_boundary.py` — load the OR/WA state boundary shapefile, filter to the polygon(s) for the current region, use `rasterio.mask.mask` to clip a raster array to the boundary; return the clipped array and updated transform; log clipped pixel dimensions and CRS
- [x] 3.2 `src/processors/downscale.py` — implement `reproject_to_lidar_grid(src_array, src_transform, src_crs, lidar_transform, lidar_crs, lidar_shape)` using `rasterio.warp.reproject` with `Resampling.bilinear`; all coarse rasters (PRISM, NLCD, NREL wind, Landsat LST) are passed through this function to produce arrays with the same shape as the LiDAR DEM
- [x] 3.3 `src/processors/terrain_analysis.py` — compute: (a) aspect in degrees 0–360° from DEM gradient; (b) slope in degrees from gradient magnitude; (c) TPI as pixel elevation minus mean elevation in annulus 300–1,000 m; (d) wind shadow mask where TPI < 0 and aspect within ±90° of `PREVAILING_WIND_DEG + 180°`; (e) lapse rate HDD addition as `(elevation − station_elevation_ft) / 1000 × LAPSE_RATE_HDD_PER_1000FT`
- [x] 3.4 `src/processors/thermal_logic.py` — compute: (a) `surface_albedo = 0.20 − (impervious / 100) × 0.15`; (b) solar aspect multiplier (0.8 north, 1.2 south, linear interpolation); (c) `uhi_offset_f = (0.20 − surface_albedo) × SOLAR_IRRADIANCE_WM2 / 5.5 × 9/5`; (d) Landsat LST calibration (70/30 blend) if available
- [x] 3.5 `src/processors/wind_steering.py` — merge NREL 10 m wind grid with MesoWest station observations via spatial interpolation; compute stagnation multiplier (0.7×/1.0×/1.3× by wind speed and wind shadow); compute wind infiltration multiplier; apply Gorge floor of 1.15
- [x] 3.6 `src/processors/anthropogenic_load.py` — buffer road segments by AADT tier (50/100/200 m); rasterize buffered heat flux onto 1 m grid; compute `road_temp_offset_f = road_heat_flux_wm2 / 5.5 × 9/5`

## Task 4: Granular Microclimate Cells

- [x] 4.1 Add cell-related constants to `src/config.py`: `CELL_SIZE_M = 500` (cell size in meters), `MIN_CELL_PIXELS = 10` (minimum 1m pixels per cell for reliability)
- [x] 4.2 Implement `src/processors/create_cells.py` — `create_microclimate_cells(zip_code_polygon, cell_size_m)` that: (a) creates a regular grid of cells within the ZIP code boundary; (b) assigns unique `cell_id` to each cell (`cell_001`, `cell_002`, etc.); (c) optionally classifies cells by dominant characteristics (urban, suburban, rural, valley, ridge, gorge); (d) returns a GeoDataFrame with cell geometries and IDs
- [x] 4.3 Implement `src/processors/combine_corrections_cells.py` — for each cell, compute `cell_effective_hdd` using the formula where each component is the **mean value for all 1-meter grid cells within that microclimate cell**; return a DataFrame with one row per cell per ZIP code

## Task 5: ZIP-Code Aggregates

- [x] 5.1 Implement `src/processors/aggregate_cells_to_zip.py` — for each ZIP code, compute: (a) `zip_effective_hdd = mean(cell_effective_hdd for all cells)`; (b) variation statistics: `cell_hdd_min`, `cell_hdd_max`, `cell_hdd_std`, `num_cells`; (c) return a DataFrame with one aggregate row per ZIP code with `cell_id = "aggregate"`
- [x] 5.2 Add verification check: ZIP-code aggregate `effective_hdd` must equal mean of all cells (within floating-point tolerance); flag mismatches in QA

## Task 6: Region Boundary and Reference Data Generation

- [x] 6.1 Write `scripts/generate_region1_boundary.py` — fetch OR/WA state boundary polygons from Census TIGER/Line, dissolve into `region_1` polygon, write `data/boundary/region_1.geojson` and `data/boundary/region_registry.csv`
- [x] 6.2 Accept optional `--source-dir` for pre-downloaded TIGER/Line shapefiles
- [x] 6.3 Build merged ZIP code boundary layer from RLIS > OpenDataSoft > Census ZCTA; write `data/boundary/zipcodes_orwa.geojson` and `zipcodes_orwa.csv`
- [x] 6.4 Update `data/boundary/README.md` to document all output files and schemas
- [x] 6.5 Write `scripts/write_boundary_map.py` — self-contained Leaflet HTML map of region boundary and ZIP codes

## Task 7: Surface Property Mask and Physics Engine (shared by daily/hourly/real-time)

- [x] 7.1 Add surface property constants to `src/config.py`: `NLCD_SURFACE_PROPERTIES` lookup table (z₀, albedo, emissivity per NLCD class), `NLCD_DISPLACEMENT_HEIGHT_M` lookup table (d per NLCD class), `ROUGHNESS_GRADIENT_THRESHOLD = 0.3`, `VON_KARMAN = 0.41`, `BL_DECAY_HEIGHT_FT = 500`, `UHI_BL_DECAY_HEIGHT_FT = 300`, `Z0_RURAL_REFERENCE = 0.03`, `SAFETY_CUBE_ALTITUDE_LEVELS_FT = [0, 500, 1000, 3000, 6000, 9000, 12000, 18000]`, `TKE_THRESHOLDS = {"smooth": 0.5, "light": 1.5, "moderate": 3.0}`
- [x] 7.2 Implement `src/processors/surface_property_mask.py` — `build_surface_mask(nlcd_array)` returns dict with `z0_m`, `displacement_height_m`, `albedo`, `emissivity`, `nlcd_class`, `roughness_gradient`, `roughness_transition_zone` arrays
- [x] 7.3 Implement `src/processors/surface_physics_engine.py` — (a) `apply_forest_displacement(wind_speed_ms, z_agl_m, z0, d, u_star)` — displaced log-law wind, zero below canopy; (b) `apply_uhi_boundary_layer(uhi_offset_f, z_agl_ft)` — exponential UHI decay, zero above 1,000 ft; (c) `compute_tke(u_star, z0_local)` — TKE from roughness contrast
- [x] 7.4 Implement `src/processors/boundary_layer_correction.py` — (a) `compute_wind_shear_correction` for roughness transition zones ≤ 1,000 ft; (b) `compute_thermal_subsidence` over water bodies ≤ 1,000 ft

---

# Part B: Monthly Microclimate Generator (`--mode normals`)

Uses PRISM 30-year climate normals as the atmospheric base. Produces annual `effective_hdd` per ZIP code.

## Task 8: Monthly — Combine Corrections and Output

- [x] 8.1 `src/processors/combine_corrections.py` — `compute_effective_hdd(base_hdd, terrain_mult, elev_addition, uhi_reduction, traffic_reduction)` returning `base_hdd × terrain_mult + elev_addition − uhi_reduction − traffic_reduction`
- [x] 8.2 `src/processors/weather_adjustment.py` — optional `--weather-year` adjustment: `effective_hdd_adjusted = effective_hdd × (actual_station_hdd / normal_station_hdd)` (applies to all cells)
- [x] 8.3 `src/output/write_terrain_attributes.py` — write `terrain_attributes.csv` with: (a) **cell-level rows** (one per cell per ZIP code) with `microclimate_id = {region}_{zip}_{station}_cell_{cell_id}`, `cell_id`, `cell_type`, `effective_hdd`, all correction columns, `cell_area_sqm`; (b) **ZIP-code aggregate rows** (one per ZIP code) with `microclimate_id = {region}_{zip}_{station}_aggregate`, `cell_id = "aggregate"`, `effective_hdd = mean across cells`, `num_cells`, `cell_hdd_min`, `cell_hdd_max`, `cell_hdd_std`, all mean correction columns
- [x] 8.4 Add versioning columns to all rows: `run_date`, `pipeline_version`, `lidar_vintage`, `nlcd_vintage`, `prism_period`

## Task 9: Monthly — Validation and QA

- [x] 9.1 `src/validation/qa_checks.py` — range checks (2,000–8,000 HDD per cell), directional sanity (urban cells < rural cells, windward > leeward, high elevation > low elevation), cell consistency (ZIP aggregate = mean of cells), hard failure flags
- [x] 9.2 `src/validation/billing_comparison.py` — compare cell-level and ZIP-level `effective_hdd` against billing-derived therms; flag > 15% divergence
- [x] 9.3 Write QA report as `qa_report.html` and `qa_report.md` with cell-level and ZIP-level statistics
- [x] 9.4 Flag cells with < 10 valid 1-meter grid pixels as potentially unreliable

## Task 10: Monthly — Maps and Visualization

- [x] 10.1 Implement `src/output/write_maps.py` — create multiple interactive Leaflet HTML maps showing **cells** (not just ZIP codes):
  - **Cell-level effective HDD choropleth**: Each cell colored by `effective_hdd` value with ZIP code overlay
  - **Terrain position layer**: Cells colored by terrain type (windward, leeward, valley, ridge)
  - **UHI effect layer**: Cells colored by `uhi_offset_f`
  - **Wind infiltration layer**: Cells colored by `wind_infiltration_mult`
  - **Traffic heat layer**: Cells colored by `road_heat_flux_wm2`
  - **Layer control panel**: Toggle between layers and show/hide boundaries
  - **Cell info popup**: Click any cell to see `cell_id`, `effective_hdd`, terrain, elevation, wind, imperviousness, etc.
  - **Zoom and pan**: Explore neighborhoods at high detail
- [x] 10.2 Write maps to `output/microclimate/`: `map_effective_hdd.html`, `map_terrain_position.html`, `map_uhi_effect.html`, `map_wind_infiltration.html`, `map_traffic_heat.html`
- [x] 10.3 Property test: all cell `effective_hdd` values in output CSV within 2,000–8,000
- [x] 10.4 Property test: directional sanity — urban cells < rural cells, windward > leeward
- [x] 10.5 Property test: ZIP-code aggregate equals mean of all cells (within floating-point tolerance)

## Task 11: Monthly — Future Enhancements (Optional)

- [x] 11.1* Monthly effective HDD profiles (12 columns: `effective_hdd_jan` … `effective_hdd_dec`)
- [x] 11.2* Precipitation/moisture correction from PRISM precipitation normals
- [x] 11.3* Cold air drainage quantification from LiDAR flow accumulation
- [x] 11.4* Effective CDD output (UHI increases cooling load)
- [x] 11.5* Error propagation and uncertainty bounds (`effective_hdd_low`, `effective_hdd_high`)
- [x] 11.6* UTM zone boundary handling (Zone 11N districts)

---

# Part C: Daily Microclimate Generator (`--mode daily`)

Uses HRRR 3 km data bias-corrected against PRISM. Produces daily `effective_hdd` + multi-altitude wind/temp/HDD profiles per ZIP code.

## Task 12: Daily — HRRR Integration and Bias Correction

- [x] 12.1 Add HRRR-related constants to `src/config.py`: `HRRR_CACHE_DIR`, `HRRR_S3_BUCKET`, `HRRR_GCS_BUCKET`, `HRRR_EARLIEST_DATE`, `HRRR_DOWNLOAD_CONFIRM_THRESHOLD_GB`, `GA_ALTITUDE_LEVELS_FT`, `HRRR_PRESSURE_LEVELS_MB`, `HRRR_MIN_CLIM_YEARS`, `DAILY_OUTPUT_DIR`
- [x] 12.2 `src/loaders/load_hrrr.py` — download/cache HRRR GRIB2 from S3/GCS, extract 2 m temp + 10 m wind + pressure-level wind, compute daily mean, write manifest CSV; support `--month YYYY-MM` shorthand; validate dates ≥ 2014-07-30; prompt if > 10 GB
- [x] 12.3 `src/processors/bias_correct_hrrr.py` — `bias_correct(hrrr_daily_temp, prism_monthly_normal, hrrr_climatology)` → `hrrr_adjusted = hrrr_raw + (prism_normal − hrrr_climatology)`; fallback when < 3 years cached
- [x] 12.4 `src/processors/wind_profile_extractor.py` — extract wind speed/direction at 6 GA altitudes via log-pressure interpolation from HRRR pressure levels; also extract temperature at each altitude; assign to ZIP codes by nearest grid cell
- [x] 12.5 `src/processors/daily_combine.py` — `compute_daily_effective_hdd` per ZIP × date; orchestrate daily pipeline: load HRRR → bias correct → wind profiles → combine → write
- [x] 12.6 `src/output/write_daily_output.py` — write daily Parquet/CSV with `daily_effective_hdd`, wind profiles, altitude temp/HDD
- [x] 12.7 Create `data/hrrr/README.md` — cache structure, manifest schema, storage estimates, manual download instructions
- [x] 12.8 Property test: HRRR bias correction round-trip and identity
- [x] 12.9 Property test: wind profile altitude interpolation bounds and physical reasonableness
- [x] 12.10 Property test: daily effective_hdd non-negativity and temperature monotonicity

## Task 13: Daily — Altitude-Level Microclimate Profiles

- [ ] 13.1 `src/processors/altitude_microclimate.py` — bias-correct altitude temperatures, compute `hdd_{alt} = max(0, 65 − temp_{alt}_adjusted_f)` with no surface corrections above ground
- [ ] 13.2 Integrate altitude profiles into daily combine pipeline
- [ ] 13.3 Add altitude columns to daily output schema (18 columns: temp raw/adjusted + HDD at 6 levels)
- [ ] 13.4 Apply boundary layer corrections (wind shear, thermal subsidence) at ≤ 1,000 ft AGL
- [ ] 13.5 Add surface property columns to daily output (`z0_m`, `albedo`, `emissivity`, `roughness_transition_pct`, `nlcd_dominant_class`, `wind_shear_correction_sfc_kt`, `water_cooling_sfc_f`)
- [ ] 13.6 Property test: altitude temperature decreases with height (5°F inversion tolerance)
- [ ] 13.7 Property test: altitude HDD increases with height
- [ ] 13.8 Property test: no surface corrections at altitude
- [ ] 13.9 Property test: wind shear correction zero outside transition zones
- [ ] 13.10 Property test: thermal subsidence zero over non-water pixels
- [ ] 13.11 Property test: boundary layer corrections only apply ≤ 1,000 ft

## Task 14: Daily — Aviation Safety Cube

- [ ] 14.1 `src/processors/aviation_safety_cube.py` — `build_safety_cube` assembling ZIP × date × 8 altitudes with temp, wind, TKE, wind shear, HDD, density altitude, turbulence flag
- [ ] 14.2 `src/output/write_safety_cube.py` — write cube to date-partitioned Parquet with snappy compression
- [ ] 14.3 Integrate safety cube into daily combine pipeline
- [ ] 14.4 Update CLI with `--safety-cube` flag and `--cube-altitudes` override
- [ ] 14.5 Update daily output schema in `design.md` for safety cube columns
- [ ] 14.6 Property test: forest displacement sets wind to zero below canopy
- [ ] 14.7 Property test: UHI boundary layer decay (5.0°F at surface → ~1.84°F at 500 ft → 0 at 1,500 ft)
- [ ] 14.8 Property test: TKE scales with roughness (urban > rural)
- [ ] 14.9 Property test: wind shear constant for linear wind profile
- [ ] 14.10 Property test: density altitude equals pressure altitude at ISA standard
- [ ] 14.11 Property test: turbulence flag thresholds (smooth/light/moderate/severe)

---

# Part D: Hourly Microclimate Generator (`--mode hourly`)

Uses individual HRRR hourly analyses (no daily averaging). Produces per-hour safety cubes and microclimate profiles.

## Task 15: Hourly — Per-Hour Processing Pipeline

- [ ] 15.1 Update `src/loaders/load_hrrr.py` — add `return_hourly=True` option that returns a list of per-hour xarray Datasets instead of computing the daily mean; each Dataset contains one hour's 2 m temp, 10 m wind, surface pressure, and pressure-level fields
- [ ] 15.2 Implement `src/processors/hourly_combine.py` — `process_single_hour(hour_ds: xr.Dataset, surface_mask: dict, terrain_corrections: pd.DataFrame, bias_correction: pd.Series, uhi_offsets: pd.Series) -> pd.DataFrame` that: (a) bias-corrects the single-hour HRRR temperature against PRISM normals; (b) extracts multi-altitude wind and temperature profiles at 8 safety cube altitudes; (c) applies surface physics (forest displacement, UHI BL decay, water subsidence, TKE); (d) computes hourly HDD contribution at each altitude: `hourly_hdd = max(0, 65 − temp_adjusted_f) / 24`; (e) returns a DataFrame with columns: `datetime_utc`, `zip_code`, `altitude_ft`, `temp_adjusted_f`, `wind_speed_kt`, `wind_dir_deg`, `tke_m2s2`, `wind_shear_kt_per_100ft`, `hourly_hdd`, `density_altitude_ft`, `turbulence_flag`
- [ ] 15.3 Implement `src/processors/hourly_orchestrator.py` — `run_hourly_pipeline(region_name, start_date, end_date, hrrr_source, terrain_corrections_df)` that: (a) loads HRRR with `return_hourly=True`; (b) iterates over each hour, calling `process_single_hour`; (c) concatenates results into a single DataFrame; (d) writes output via `write_hourly_output`
- [ ] 15.4 `src/output/write_hourly_output.py` — write hourly results to `output/microclimate/hourly_{region}_{start}_{end}.parquet` partitioned by date; each row is ZIP × hour × altitude; use snappy compression
- [ ] 15.5 Update CLI in `src/pipeline.py` — add `hourly` to `--mode` choices; `--mode hourly` requires `--start-date`/`--end-date` or `--month`; hourly mode skips daily averaging and produces per-hour safety cubes
- [ ] 15.6 Update `src/pipeline.py` `run_region` — add hourly mode branch that calls `run_hourly_pipeline`; `--mode both` now runs normals → daily → hourly if date range is specified
- [ ] 15.7 Property test: verify hourly HDD sums to daily — for a synthetic 24-hour period, assert that `sum(hourly_hdd)` across all 24 hours equals the daily `effective_hdd` within floating-point tolerance
- [ ] 15.8 Property test: verify each hour produces exactly 8 altitude levels × N ZIP codes rows
- [ ] 15.9 Property test: verify `datetime_utc` column contains valid ISO 8601 timestamps with hour precision and all 24 hours are present for a complete day

---

# Part E: Real-Time Microclimate Generator (`--mode realtime`, Optional)

Persistent daemon that polls for new HRRR cycles and produces safety cubes within minutes of each release.

## Task 16: Real-Time — Data Daemon (Optional)

- [ ] 16.1* Add `herbie` to `requirements.txt` and `src/config.py`: `DAEMON_POLL_INTERVAL_SEC = 300`, `DAEMON_HRRR_PRODUCT = "prs"`, `DAEMON_LOOKBACK_HOURS = 2`, `STATIC_CACHE_DIR = Path("data/cache/static/")`, `REALTIME_OUTPUT_DIR = Path("output/realtime/")`
- [ ] 16.2* Implement `src/realtime/static_cache.py` — `build_static_cache(region_name)` pre-computes and serializes all static features (NLCD surface mask, LiDAR terrain, road heat flux, UHI offsets) to `.npz` files with a `cache_manifest.json` for hash-based staleness detection
- [ ] 16.3* Implement `src/realtime/hrrr_poller.py` — `HRRRPoller` class using `herbie.Herbie` to poll for latest HRRR `prs` analysis cycle; exponential backoff on errors; emits xarray Dataset to callback
- [ ] 16.4* Implement `src/realtime/streaming_pipeline.py` — `process_hrrr_cycle(hrrr_ds, static_cache_dir, region_name)` that bias-corrects, downscales 3 km → 1 m, applies cached surface physics, builds single-hour safety cube; must complete within 120 seconds
- [ ] 16.5* Implement `src/realtime/daemon.py` — `run_daemon(region_name)` with `multiprocessing.Process` for poller, queue-based consumption, graceful SIGINT/SIGTERM shutdown, `daemon_status.json`, 48-hour output rotation
- [ ] 16.6* CLI entry point: `python -m src.realtime.daemon --region region_1` with `--build-cache`, `--poll-interval`, `--lookback`, `--foreground` flags
- [ ] 16.7* Property test: static cache round-trip and hash-based staleness detection
- [ ] 16.8* Property test: streaming pipeline produces valid safety cube with expected columns and physical bounds
- [ ] 16.9* Property test: daemon graceful shutdown writes final status JSON

---

# Part F: Pipeline Orchestrator (ties all modes together)

## Task 17: Pipeline Orchestrator and CLI

- [ ] 17.1 `src/pipeline.py` — implement `run_region(region_name, mode, weather_year, start_date, end_date)` that dispatches to the correct mode: `normals` → Part B, `daily` → Part C, `hourly` → Part D, `both` → normals then daily then hourly (reusing terrain corrections), `realtime` → Part E daemon
- [ ] 17.2 CLI entry point: `python -m src.pipeline --region region_1 --mode normals|daily|hourly|both|realtime` with all existing flags (`--weather-year`, `--start-date`, `--end-date`, `--month`, `--hrrr-source`, `--output-format`, `--no-confirm`, `--safety-cube`, `--cube-altitudes`, `--dry-run`, `--all-regions`)
- [ ] 17.3 Support `--all-regions` flag for batch processing across all regions in the registry
- [ ] 17.4 Log progress and timing per step; write logs to stdout and run output folder
- [ ] 17.5 Implement `publish_run_folder` — assemble self-contained output folder with all GeoJSONs, maps, CSVs, Parquets, QA reports, and `run_manifest.json`
