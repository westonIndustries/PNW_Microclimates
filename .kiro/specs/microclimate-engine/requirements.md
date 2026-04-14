# Requirements — Regional Microclimate Modeling Engine

## Introduction

The **Regional Microclimate Modeling Engine** is a Python processing pipeline that converts geographic regions in Oregon and Washington into high-resolution microclimate maps at the sub-ZIP-code level. It integrates terrain data, surface imperviousness, atmospheric temperature normals, wind observations, and traffic-derived heat flux to produce granular `effective_hdd` values for microclimate cells within each ZIP code or Census block group. This cell-level granularity replaces the single airport-station HDD used in conventional forecasting, capturing sub-ZIP-code variation driven by terrain position, urban heat island effects, wind exposure, and anthropogenic heat load.

**Primary users**: Forecasting analysts and data engineers who maintain and run analysis pipelines. Secondary users: regulatory staff reviewing load forecasts who need to understand how weather normalization is applied at sub-regional scale. Tertiary users: infrastructure planners and weatherization program managers who need to identify neighborhoods with highest heating demand.

**Scope**: The pipeline covers the full Oregon and Washington extent as a single processing region (`region_1`). It produces a pre-computed lookup table (`terrain_attributes.csv`) with multiple rows per ZIP code (one per microclimate cell, plus one ZIP-code aggregate). Downstream models can join on individual cells for granular forecasting, or on ZIP-code aggregates for coarser analysis. The pipeline does not perform real-time raster sampling during model runs.

---

## Glossary

| Term | Definition |
|------|-----------|
| **microclimate_id** | Unique string identifier for a microclimate area, formatted as `{region_code}_{zip_code}_{base_station}_cell_{cell_id}` for cells (e.g., `R1_97201_KPDX_cell_001`) or `{region_code}_{zip_code}_{base_station}_aggregate` for ZIP-code aggregates (e.g., `R1_97201_KPDX_aggregate`). Primary key in `terrain_attributes.csv`. |
| **microclimate_cell** | A granular geographic subdivision within a ZIP code (e.g., 500m × 500m grid cell) that represents a distinct microclimate zone. Each cell has its own `effective_hdd` value calculated by the formula. Multiple cells per ZIP code enable sub-ZIP-code granularity in forecasting. |
| **cell_id** | Unique identifier for a microclimate cell within a ZIP code, formatted as `cell_001`, `cell_002`, etc. |
| **effective_hdd** | Adjusted annual heating degree days (base 65°F) for a microclimate cell or ZIP code aggregate, incorporating terrain, surface, wind, and traffic corrections on top of the PRISM/NOAA atmospheric base. |
| **TPI** | Topographic Position Index — the elevation at a point minus the mean elevation within a surrounding annulus (300–1,000 m radius). Negative TPI indicates a valley; positive TPI indicates a ridge. |
| **UHI** | Urban Heat Island — the phenomenon where dense impervious surfaces (asphalt, rooftops) absorb solar radiation and re-emit it as heat, raising effective air temperatures 2–5°F above the rural baseline. |
| **AADT** | Annual Average Daily Traffic — the total volume of vehicle traffic on a road segment divided by 365, used to compute anthropogenic heat flux from vehicle exhaust and friction. |
| **LiDAR** | Light Detection and Ranging — airborne laser scanning that produces a bare-earth digital elevation model (DEM) at 1 m resolution. Source: DOGAMI (Oregon) and WA DNR (Washington). |
| **PRISM** | Parameter-elevation Regressions on Independent Slopes Model — a gridded climate dataset from Oregon State University providing monthly temperature and precipitation normals at 800 m resolution. |
| **terrain_position** | Classification of each pixel as `windward`, `leeward`, `valley`, or `ridge` based on aspect relative to the prevailing SW wind (225°) and TPI. |
| **wind shadow** | A binary raster mask identifying areas where terrain blocks the prevailing wind, derived from TPI and aspect. Wind shadow areas have reduced infiltration loads but may trap urban heat. |
| **lapse rate** | The rate at which temperature decreases with elevation — approximately 3.5°F per 1,000 ft, equivalent to ~630 HDD per 1,000 ft above the base weather station. |
| **HRRR** | High-Resolution Rapid Refresh — a NOAA 3 km hourly atmospheric model covering CONUS, available from ~2014 to present. Provides temperature, wind, and other variables at multiple pressure levels. Archived on AWS S3 (`s3://noaa-hrrr-bdp-pds/`) and Google Cloud. |
| **GRIB2** | GRIdded Binary Edition 2 — the WMO standard binary format for gridded meteorological data. HRRR forecast files are distributed as GRIB2. Each file is ~50–100 MB per forecast hour. |
| **cfgrib** | A Python library that provides an xarray-compatible engine for reading GRIB2 files. Used via `xarray.open_dataset(path, engine="cfgrib")`. |
| **AGL** | Above Ground Level — altitude measured relative to the terrain surface rather than mean sea level. GA flight altitudes are typically expressed in feet AGL or MSL. |
| **pressure_level** | A constant-pressure surface in the atmosphere (e.g., 925 mb, 850 mb, 700 mb, 500 mb). HRRR provides wind and temperature fields at 22 pressure levels from 1000 mb to 500 mb. Standard altitude approximations: 925 mb ≈ 2,500 ft, 850 mb ≈ 5,000 ft, 700 mb ≈ 10,000 ft, 500 mb ≈ 18,000 ft. |
| **bias_correction** | An additive adjustment applied to HRRR daily fields so they inherit PRISM's terrain-aware station calibration: `hrrr_adjusted = hrrr_raw + (prism_normal − hrrr_climatology)`. |
| **GA** | General Aviation — non-commercial, non-military flying. GA aircraft typically operate below 18,000 ft MSL (Class G/E airspace). |
| **daily_mode** | A pipeline operating mode that uses HRRR as the atmospheric base (instead of PRISM normals) to produce daily `effective_hdd` and multi-altitude wind profiles per ZIP code. Contrast with **normals_mode** (existing PRISM-based annual output). |
| **normals_mode** | The existing pipeline operating mode that uses PRISM 30-year climate normals as the atmospheric base to produce annual `effective_hdd` per ZIP code. |

---

## Requirements

---

### Requirement 1: Spatial Boundary and Region Definition

**User Story**: As a forecasting analyst, I want the pipeline to process one geographic region at a time and clip all rasters to the OR/WA state boundary, so that memory usage is manageable and results are confined to the study area.

**Acceptance Criteria**:

1. The pipeline accepts a `region_name` parameter (e.g., `region_1`) that selects a predefined bounding box and ZIP code list from the region registry in `config.py`.
2. All input rasters are clipped to the OR/WA state boundary polygon before any computation. Pixels outside the boundary are masked and excluded from all outputs.
3. The region registry defines `region_1` (Oregon + Washington extent, bounding box: minx=-124.8, miny=41.9, maxx=-116.9, maxy=49.1 in EPSG:4326) with: region name, list of ZIP codes, primary base station(s), and bounding box coordinates.
4. Running the pipeline for a region that does not exist in the registry raises a descriptive `ValueError` identifying the unknown region name and listing valid options.
5. The clipped raster extents are logged at the start of each run, including pixel dimensions and CRS.

---

### Requirement 2: Terrain Data Ingestion

**User Story**: As a data engineer, I want the pipeline to load the 1 m LiDAR DEM from DOGAMI (Oregon) or WA DNR (Washington) and derive aspect, slope, and TPI, so that terrain-based corrections can be applied at full resolution.

**Acceptance Criteria**:

1. The loader reads a GeoTIFF at the path specified by `LIDAR_DEM_RASTER` in `config.py`, handles nodata values (replacing with `numpy.nan`), and returns a tuple of `(array, transform, crs)`.
2. Aspect is computed in degrees (0–360°, clockwise from north) using the LiDAR DEM gradient.
3. Slope is computed in degrees (0–90°) from the DEM gradient magnitude.
4. TPI is computed as the elevation at each pixel minus the mean elevation within an annulus of inner radius 300 m and outer radius 1,000 m. Pixels within 1,000 m of the raster edge are assigned `numpy.nan` for TPI.
5. If the DEM file does not exist at the configured path, the loader raises a `FileNotFoundError` with the full path in the message.

---

### Requirement 3: Atmospheric Base Construction

**User Story**: As a forecasting analyst, I want the pipeline to load PRISM 800 m monthly temperature normals, bias-correct them to NOAA station values, and produce an annual HDD grid, so that the atmospheric base reflects both spatial continuity and station-level accuracy.

**Acceptance Criteria**:

1. The loader reads 12 monthly PRISM mean temperature GeoTIFFs (BIL or GeoTIFF format) from `PRISM_TEMP_DIR` and computes an annual HDD grid by summing monthly HDD contributions (monthly mean temperature × days in month, base 65°F).
2. The PRISM grid is bias-corrected so that its value at each NOAA station location matches the NOAA 1991–2020 normal HDD for that station. The bias correction uses an additive offset per station, interpolated spatially across the grid.
3. The 11 reference station HDD values (KPDX: 4,850; KEUG: 4,650; KSLE: 4,900; KAST: 5,200; KDLS: 5,800; KOTH: 4,400; KONP: 4,600; KCVO: 4,750; KHIO: 4,900; KTTD: 5,100; KVUO: 4,950) are defined as constants in `config.py`.
4. If any of the 12 monthly PRISM files are missing, the loader raises a `FileNotFoundError` listing the missing months.
5. The output `prism_annual_hdd` grid is at 800 m resolution and covers the full clipped region extent.

---

### Requirement 4: Raster Downscaling

**User Story**: As a data engineer, I want all coarse-resolution rasters to be resampled to the 1 m LiDAR grid using bilinear interpolation, so that terrain-based corrections can be applied consistently at full resolution without blocky artifacts.

**Acceptance Criteria**:

1. All input rasters (PRISM 800 m, NLCD 30 m, NREL wind 2 km, Landsat 9 LST 30 m) are reprojected and resampled to match the LiDAR DEM's grid exactly: same CRS (EPSG:26910), same pixel size (1 m), same origin and extent.
2. Bilinear interpolation is used for all downscaling operations. Nearest-neighbor resampling is not used for any continuous-value raster.
3. The LiDAR DEM is the reference grid. All other rasters are snapped to it — no independent grid alignment is performed.
4. After downscaling, each raster array has the same shape as the LiDAR DEM array for the clipped region.
5. Downscaling is implemented using `rasterio.reproject` with `Resampling.bilinear`.

---

### Requirement 5: Terrain Position Classification

**User Story**: As a forecasting analyst, I want each pixel classified as windward, leeward, valley, or ridge, so that the correct HDD multiplier can be applied based on terrain exposure.

**Acceptance Criteria**:

1. **Windward**: aspect within ±90° of 225° (SW prevailing wind direction). HDD multiplier range: 1.05–1.10.
2. **Leeward**: aspect outside ±90° of 225°. HDD multiplier range: 0.95–1.02.
3. **Valley**: TPI < 0 (pixel is lower than its surrounding annulus). HDD multiplier range: 1.00–1.05.
4. **Ridge**: TPI > 0 and slope > 25°. HDD multiplier range: 1.10–1.20.
5. The prevailing wind direction (225°) is defined as a constant `PREVAILING_WIND_DEG` in `config.py` and is not hard-coded in the processor.
6. The output `terrain_position` column in `terrain_attributes.csv` contains one of the four string values: `windward`, `leeward`, `valley`, `ridge`.
7. Pixels that meet multiple criteria (e.g., windward and ridge) are classified as `ridge` — the most exposed category takes precedence.

---

### Requirement 6: Thermal Logic (Heat Gain)

**User Story**: As a forecasting analyst, I want the pipeline to compute surface albedo from NLCD imperviousness, apply a solar aspect multiplier, and derive a UHI temperature offset, so that urban heat island effects are captured at sub-district scale.

**Acceptance Criteria**:

1. Surface albedo is computed as: `surface_albedo = 0.20 − impervious_fraction × (0.20 − 0.05)`, where `impervious_fraction` is the NLCD imperviousness value divided by 100.
2. A solar aspect multiplier (range 0.8–1.2) is applied based on the LiDAR aspect raster: south-facing slopes (aspect 135°–225°) receive multiplier 1.2; north-facing slopes (aspect 315°–45°) receive multiplier 0.8; other aspects are interpolated linearly.
3. The UHI temperature offset is computed as: `uhi_offset_f = (0.20 − surface_albedo) × solar_irradiance_wm2 / 5.5 × 9/5`, where `solar_irradiance_wm2 = 200` W/m² is defined as a constant in `config.py`.
4. The UHI HDD reduction is: `uhi_hdd_reduction = uhi_offset_f × 180` (180 HDD per °F).
5. All intermediate values (`surface_albedo`, `uhi_offset_f`) are retained as columns in `terrain_attributes.csv`.

---

### Requirement 7: Landsat 9 Validation

**User Story**: As a data engineer, I want the pipeline to load Landsat 9 TIRS land surface temperature, compare urban and rural pixels, and calibrate the UHI offsets, so that the NLCD-derived estimates are grounded in observed surface temperatures.

**Acceptance Criteria**:

1. The loader reads a Landsat 9 Collection 2 Level-2 LST GeoTIFF, applies the Collection 2 scale factor (0.00341802) and offset (149.0) to convert to Kelvin, then subtracts 273.15 to produce a Celsius array.
2. Urban pixels are defined as NLCD imperviousness ≥ 50%; rural pixels are defined as imperviousness ≤ 10%.
3. The mean LST difference between urban and rural pixels within each ZIP code is computed and compared against the NLCD-derived `uhi_offset_f`. If the observed difference exceeds the modeled offset by more than 1.5°C, a calibration warning is logged.
4. The calibrated `uhi_offset_f` is adjusted toward the Landsat-observed value using a weighted blend: 70% NLCD-derived, 30% Landsat-observed.
5. The mean summer LST for each ZIP code is written to the `lst_summer_c` column in `terrain_attributes.csv`.
6. If the Landsat LST file is not available, the pipeline logs a warning and proceeds without calibration, using the NLCD-derived UHI offset unchanged.

---

### Requirement 8: Wind Steering

**User Story**: As a forecasting analyst, I want the pipeline to compute a wind stagnation multiplier from TPI and wind speed, so that urban heat is amplified in sheltered valleys and reduced on exposed ridges.

**Acceptance Criteria**:

1. The wind speed surface is constructed by combining MesoWest station observations (point) with the NREL 2 km gridded wind resource, resampled to 1 m using bilinear interpolation.
2. The NREL wind raster (80 m hub height) is scaled to 10 m surface wind using a power law: `wind_10m = wind_80m × (10/80)^0.143`.
3. The wind stagnation multiplier is applied to the UHI offset:
   - Wind speed > 5 m/s and not in wind shadow: UHI offset × 0.7
   - Wind speed 3–5 m/s: UHI offset × 1.0
   - Wind speed < 3 m/s and in wind shadow: UHI offset × 1.3
4. The wind infiltration multiplier adds 1.5% to the effective HDD for each 1 m/s above 3 m/s (sheltered suburban baseline).
5. The Columbia River Gorge ZIP codes (served by stations KDLS and KTTD) receive a wind infiltration multiplier floor of 1.15, reflecting the high-wind corridor effect.
6. The output `mean_wind_ms` and `wind_infiltration_mult` columns are written to `terrain_attributes.csv`.

---

### Requirement 9: Anthropogenic Heat Load

**User Story**: As a forecasting analyst, I want the pipeline to load ODOT and WSDOT AADT shapefiles, compute road heat flux, and apply spatial buffers, so that vehicle traffic heat contributions are captured along major corridors.

**Acceptance Criteria**:

1. The loader reads ODOT (Oregon) and WSDOT (Washington) road shapefiles, filters to segments with AADT > 0, and computes heat flux per segment: `heat_flux_wm2 = (AADT / 86400) × 150,000 / road_area_m2`, where road area is segment length × lane width (default 3.7 m per lane).
2. A spatial buffer is applied around each road segment: 50 m for AADT < 10,000; 100 m for AADT 10,000–50,000; 200 m for AADT > 50,000.
3. The heat flux is distributed uniformly within the buffer zone. Overlapping buffers from multiple road segments are summed.
4. The road heat flux is converted to a temperature offset: `road_temp_offset_f = road_heat_flux_wm2 / 5.5 × 9/5`.
5. The output `road_heat_flux_wm2` and `road_temp_offset_f` columns are written to `terrain_attributes.csv`.
6. ZIP codes with no road segments in the AADT shapefiles receive `road_heat_flux_wm2 = 0.0` and `road_temp_offset_f = 0.0`.

---

### Requirement 10: Effective HDD Computation

**User Story**: As a forecasting analyst, I want the pipeline to combine all terrain, surface, wind, and traffic corrections into a single `effective_hdd` per ZIP code, so that downstream models have a single pre-computed value to join on.

**Acceptance Criteria**:

1. `effective_hdd` is computed as:
   ```
   effective_hdd = base_hdd
                 × terrain_multiplier
                 + elevation_hdd_addition
                 − uhi_hdd_reduction
                 − traffic_heat_hdd_reduction
   ```
   where `base_hdd` is the PRISM bias-corrected annual HDD for the ZIP code's base station.
2. `elevation_hdd_addition` is computed as: `(mean_elevation_ft − station_elevation_ft) / 1000 × 630`.
3. `traffic_heat_hdd_reduction` is computed as: `road_temp_offset_f × 180`.
4. All intermediate correction columns (`hdd_terrain_mult`, `hdd_elev_addition`, `hdd_uhi_reduction`) are retained in `terrain_attributes.csv`.
5. `effective_hdd` values outside the range 2,000–8,000 are flagged in the QA report as implausible for the PNW climate.

---

### Requirement 11: Granular Microclimate Cells

**User Story**: As a forecasting analyst, I want the pipeline to divide each ZIP code into granular microclimate cells (e.g., 500m × 500m grid cells), compute cell-level `effective_hdd` for each cell, and output multiple rows per ZIP code, so that downstream models can perform sub-ZIP-code granular forecasting and identify neighborhoods with highest heating demand.

**Acceptance Criteria**:

1. The pipeline creates a regular grid of microclimate cells within each ZIP code boundary. Cell size is configurable (default: 500m × 500m).
2. Each cell is assigned a unique `cell_id` within the ZIP code, formatted as `cell_001`, `cell_002`, etc.
3. Each cell is optionally classified by dominant characteristics (e.g., `urban`, `suburban`, `rural`, `valley`, `ridge`, `gorge`).
4. For each cell, the pipeline computes `effective_hdd` using the formula:
   ```
   cell_effective_hdd = base_hdd × terrain_multiplier
                      + elevation_hdd_addition
                      − uhi_hdd_reduction
                      − traffic_heat_hdd_reduction
   ```
   where each component is the **mean value for all 1-meter grid cells within that microclimate cell**.
5. Each cell gets its own row in `terrain_attributes.csv` with `microclimate_id = {region_code}_{zip_code}_{base_station}_cell_{cell_id}`.
6. All intermediate correction columns are retained per cell (elevation, wind speed, imperviousness, albedo, UHI offset, road heat flux, etc.).
7. Cell area (`cell_area_sqm`) is included in the output.
8. Cells with fewer than 10 valid 1-meter grid cells are flagged in QA as potentially unreliable.

---

### Requirement 12: ZIP-Code-Level Aggregates

**User Story**: As a data engineer, I want the pipeline to compute ZIP-code-level aggregates by averaging all cells within each ZIP code, so that existing models can work unchanged while new models can opt into granular cell-level data.

**Acceptance Criteria**:

1. For each ZIP code, the pipeline computes aggregate values by averaging all cells:
   - `zip_effective_hdd = mean(cell_effective_hdd for all cells in ZIP)`
   - `zip_mean_elevation = mean(cell_mean_elevation for all cells)`
   - `zip_mean_wind = mean(cell_mean_wind for all cells)`
   - etc.
2. The pipeline computes variation statistics across cells:
   - `cell_hdd_min = min(cell_effective_hdd for all cells)`
   - `cell_hdd_max = max(cell_effective_hdd for all cells)`
   - `cell_hdd_std = std(cell_effective_hdd for all cells)`
   - `num_cells = count of cells in ZIP`
3. One aggregate row per ZIP code is written to `terrain_attributes.csv` with `microclimate_id = {region_code}_{zip_code}_{base_station}_aggregate` and `cell_id = "aggregate"`.
4. The aggregate row includes all mean correction columns plus variation statistics.
5. Verification check: ZIP-code aggregate `effective_hdd` must equal mean of all cells (within floating-point tolerance).

---

### Requirement 13: Interactive Cell-Based Maps

**User Story**: As a stakeholder, I want interactive Leaflet HTML maps that visualize microclimate cells at neighborhood scale (not just ZIP codes), so that I can explore microclimate variation and identify areas for infrastructure planning and weatherization programs.

**Acceptance Criteria**:

1. The pipeline generates multiple interactive Leaflet HTML maps showing:
   - **Cell-level effective HDD choropleth**: Each cell colored by its `effective_hdd` value using a color scale (e.g., blue for high HDD, red for low HDD)
   - **ZIP-code overlay**: Thin gray lines showing ZIP code boundaries for geographic reference
   - **Terrain position layer**: Cells colored by terrain type (windward, leeward, valley, ridge)
   - **UHI effect layer**: Cells colored by `uhi_offset_f` (urban heat island offset)
   - **Wind infiltration layer**: Cells colored by `wind_infiltration_mult`
   - **Traffic heat layer**: Cells colored by `road_heat_flux_wm2`
2. Each map includes a **layer control panel** allowing users to toggle between different correction layers and show/hide ZIP code and cell boundaries.
3. **Cell info popup**: Clicking any cell displays a popup with: `cell_id`, `cell_type`, `effective_hdd`, `terrain_position`, `mean_elevation_ft`, `mean_wind_ms`, `mean_impervious_pct`, `uhi_offset_f`, `road_heat_flux_wm2`, `cell_area_sqm`.
4. Maps support **zoom and pan** to explore specific neighborhoods at high detail.
5. Maps are self-contained HTML files with all GeoJSON data inlined (no external dependencies).
6. Maps are written to `output/microclimate/` with filenames: `map_effective_hdd.html`, `map_terrain_position.html`, `map_uhi_effect.html`, `map_wind_infiltration.html`, `map_traffic_heat.html`.

---

### Requirement 14: Output Schema

**User Story**: As a data engineer, I want the pipeline to write a `terrain_attributes.csv` with a well-defined schema including `microclimate_id`, `zip_code`, `cell_id`, and all correction columns, so that downstream models can join on a stable key without re-sampling rasters.

**Acceptance Criteria**:

1. The output file is written to the path specified by `TERRAIN_ATTRIBUTES_CSV` in `config.py`.
2. The `microclimate_id` is formatted as `{region_code}_{zip_code}_{base_station}` (e.g., `R1_97201_KPDX`). It is unique per row.
3. The CSV contains all columns defined in the output schema (see design doc), with correct data types: string for identifiers, float64 for numeric corrections, int for HDD values.
4. The `zip_code` column is the primary join key to external datasets. It must match the values in `ZIPCODE_STATION_MAP` exactly.
5. No raster files are read or sampled at downstream model runtime — all corrections are pre-computed and stored in the CSV.

---

### Requirement 15: Output Versioning

**User Story**: As a data engineer, I want every row in `terrain_attributes.csv` to carry metadata about when it was produced and which data vintages were used, so that stale rows can be identified after data updates.

**Acceptance Criteria**:

1. Every row contains a `run_date` column with an ISO 8601 timestamp (e.g., `2025-01-15T14:32:00`) set at pipeline execution time.
2. Every row contains a `pipeline_version` column with a semantic version string (e.g., `1.0.0`) defined as a constant in `config.py`.
3. Every row contains a `lidar_vintage` column with the year of the LiDAR DEM used (e.g., `2021`), defined per region in the region registry.
4. Every row contains an `nlcd_vintage` column with the NLCD release year (e.g., `2021`), defined as a constant in `config.py`.
5. Every row contains a `prism_period` column with the climate normal period string (e.g., `1991-2020`), defined as a constant in `config.py`.

---

### Requirement 16: QA and Validation

**User Story**: As a forecasting analyst, I want the pipeline to run automated range checks and directional sanity checks on the output, and produce an HTML/MD QA report, so that implausible values are caught before the CSV enters the simulation pipeline.

**Acceptance Criteria**:

1. Range checks flag any `effective_hdd` value outside 2,000–8,000 as a warning.
2. Directional sanity checks verify: (a) urban ZIP codes have lower `effective_hdd` than their rural neighbors; (b) windward ZIP codes have higher `effective_hdd` than leeward ZIP codes in the same region; (c) high-elevation ZIP codes have higher `effective_hdd` than low-elevation ZIP codes in the same region.
3. Billing comparison checks that `effective_hdd` for each ZIP code is within 15% of the billing-derived therms-per-customer ratio for that area. Divergences > 15% are flagged as warnings. This check is optional and requires billing data; if the billing reference CSV is not present, this check is skipped and a notice is logged.
4. The QA report is written to `output/microclimate/` as both `qa_report.html` and `qa_report.md`.
5. The pipeline exits with a non-zero return code if any hard failures are detected (e.g., `effective_hdd` < 0 or > 15,000).

---

### Requirement 17: Weather Adjustment

**User Story**: As a forecasting analyst, I want an optional weather adjustment step that scales `effective_hdd` by the ratio of actual to normal HDD for a specific historical year, so that calibration runs reflect observed weather rather than climate normals.

**Acceptance Criteria**:

1. The weather adjustment is triggered by an optional `--weather-year` CLI argument (e.g., `--weather-year 2024`).
2. The adjustment factor is computed per station: `adjustment = actual_station_hdd / normal_station_hdd`, where actual HDD is derived from `WEATHER_CALDAY` and normal HDD is from `config.py`.
3. The adjusted value is: `effective_hdd_adjusted = effective_hdd × adjustment`.
4. The adjustment is applied after all terrain and surface corrections, so it scales the already-refined effective HDD.
5. When the weather adjustment is applied, the output column is named `effective_hdd_adjusted` and the unadjusted `effective_hdd` is retained as a separate column.
6. If `--weather-year` is not specified, no adjustment is applied and only `effective_hdd` is written.

---

### Requirement 18: Pipeline Re-run Cadence

**User Story**: As a data engineer, I want documented triggers for when the terrain attributes pipeline must be re-run, so that the simulation pipeline is never using stale microclimate data without awareness.

**Acceptance Criteria**:

1. The pipeline documentation (README and design doc) lists the following re-run triggers:
   - New NLCD release (every 2–3 years): re-run Steps 6–11 for all regions
   - New LiDAR tiles available (DOGAMI updates): re-run Steps 4–11 for affected regions
   - Major wildfire changes land cover: re-run Steps 6–11 for affected districts
   - New weather station added to the network: re-run Steps 2–11 for affected districts
   - PRISM normal period updated: re-run Steps 3–11 for all regions
   - Annual model calibration cycle: re-run Step 10 (weather adjustment) only
2. The `run_date`, `lidar_vintage`, `nlcd_vintage`, and `prism_period` columns in `terrain_attributes.csv` (Requirement 12) provide the mechanism for identifying which rows are stale after any of these events.
3. A `--dry-run` CLI flag prints the list of steps that would be executed for a given region without writing any output files.

---

### Requirement 19: HRRR Data Ingestion

**User Story**: As a data engineer, I want the pipeline to download and cache HRRR 3 km GRIB2 analysis files from AWS S3 or Google Cloud for a specified date range, so that the daily mode has access to hourly atmospheric fields (temperature, wind, humidity) at high spatial resolution across CONUS.

#### Acceptance Criteria

1. WHEN a date range is specified via `--start-date` and `--end-date` CLI arguments (or a single month via `--month YYYY-MM`), THE HRRR_Loader SHALL download HRRR analysis files (f00 forecast hour = analysis) for every hour in that range from the AWS S3 archive at `s3://noaa-hrrr-bdp-pds/` using anonymous (unsigned) access. The `--month` shorthand expands to the first and last day of the specified month (e.g., `--month 2024-01` is equivalent to `--start-date 2024-01-01 --end-date 2024-01-31`).
2. WHEN a HRRR GRIB2 file for a requested hour already exists in the local cache directory (`data/hrrr/`), THE HRRR_Loader SHALL skip the download for that hour and use the cached file.
3. THE HRRR_Loader SHALL read each GRIB2 file using `xarray.open_dataset` with `engine="cfgrib"` and extract the following variables: 2 m temperature (`TMP:2 m above ground`), 10 m U-wind component (`UGRD:10 m above ground`), 10 m V-wind component (`VGRD:10 m above ground`), and pressure-level U/V wind components at all available levels from 1000 mb to 500 mb.
4. IF a HRRR file is unavailable on S3 for a requested hour (HTTP 404 or missing key), THEN THE HRRR_Loader SHALL log a warning identifying the missing hour and continue processing the remaining hours without raising an exception.
5. IF the `--hrrr-source` CLI argument is set to `gcs`, THEN THE HRRR_Loader SHALL download from the Google Cloud HRRR archive (`gs://high-resolution-rapid-refresh/`) instead of AWS S3.
6. THE HRRR_Loader SHALL write a download manifest CSV to `data/hrrr/manifest.csv` listing each requested hour, its download status (`downloaded`, `cached`, `missing`), file size in bytes, and the source URL.
7. WHEN all hours for a requested date have been downloaded, THE HRRR_Loader SHALL compute a daily mean 2 m temperature grid by averaging the 24 hourly analysis grids for that date and return the daily mean as an xarray DataArray with dimensions `(y, x)` in the HRRR native Lambert Conformal projection.
8. THE HRRR_Loader SHALL validate that the requested date range falls within the HRRR archive availability window: July 30, 2014 to present. IF a date before 2014-07-30 is requested, THEN THE HRRR_Loader SHALL raise a `ValueError` stating the earliest available HRRR date.
9. THE HRRR_Loader SHALL log the total data volume (number of hours, estimated download size at ~50–100 MB per file) before starting the download, and prompt for confirmation if the estimated total exceeds 10 GB (approximately 4–5 days of hourly data) unless `--no-confirm` is specified.

---

### Requirement 20: Multi-Altitude Wind Profiles

**User Story**: As a forecasting analyst supporting GA flight planning and drone operations, I want the pipeline to extract wind speed and direction at standard GA flight altitudes below 18,000 ft from HRRR pressure-level data, so that pilots and UAS operators can assess wind conditions at their planned cruise altitude for each ZIP code.

#### Acceptance Criteria

1. THE Wind_Profile_Extractor SHALL produce wind speed (knots) and wind direction (degrees true) at six standard altitude levels for each ZIP code: surface (10 m AGL), 3,000 ft AGL, 6,000 ft AGL, 9,000 ft AGL, 12,000 ft AGL, and 18,000 ft AGL.
2. WHEN the requested altitude falls between two HRRR pressure levels, THE Wind_Profile_Extractor SHALL interpolate wind U and V components linearly in log-pressure space between the bounding pressure levels, then compute speed and direction from the interpolated components.
3. THE Wind_Profile_Extractor SHALL convert HRRR pressure levels to approximate altitude AGL using the hypsometric equation with the HRRR 2 m temperature and surface pressure fields, rather than using fixed pressure-to-altitude lookup values.
4. WHEN HRRR data is available for multiple hours in a day, THE Wind_Profile_Extractor SHALL compute both the daily mean wind profile and the daily maximum wind speed at each altitude level per ZIP code.
5. THE Wind_Profile_Extractor SHALL assign wind profiles to ZIP codes by sampling the HRRR grid cell whose center is nearest to each ZIP code centroid.
6. IF a HRRR pressure-level field is missing or contains only fill values for a given hour, THEN THE Wind_Profile_Extractor SHALL exclude that hour from the daily aggregation and log a warning identifying the missing level and hour.
7. THE Wind_Profile_Extractor SHALL write the output wind profiles to columns in the daily output file using the naming convention `wind_speed_{alt}_kt` and `wind_dir_{alt}_deg` (e.g., `wind_speed_3000ft_kt`, `wind_dir_3000ft_deg`) for each of the six altitude levels, plus `wind_max_{alt}_kt` for the daily maximum at each level.

---

### Requirement 21: Daily Microclimate Mode

**User Story**: As a forecasting analyst, I want a daily operating mode that uses HRRR as the atmospheric base (bias-corrected against PRISM climatology) and applies the same terrain corrections as the normals mode, so that I can produce daily `effective_hdd` and multi-altitude wind profiles per ZIP code for historical analysis and short-range forecasting.

#### Acceptance Criteria

1. WHEN the `--mode daily` CLI argument is specified along with a date range (`--start-date` and `--end-date`, or `--month YYYY-MM`), THE Pipeline SHALL operate in daily mode, using HRRR daily mean temperature as the atmospheric base instead of PRISM annual normals.
2. THE Pipeline SHALL bias-correct the HRRR daily temperature field against PRISM climatology using the additive formula: `hrrr_adjusted = hrrr_raw + (prism_normal − hrrr_climatology)`, where `prism_normal` is the PRISM 30-year monthly mean for the corresponding month (period: 1991–2020) and `hrrr_climatology` is the HRRR multi-year mean for the same month (computed from all available HRRR years in the cache, minimum 3 years required). The PRISM normals cover the 1991–2020 climate period; the HRRR archive covers July 30, 2014 to present. Daily mode is therefore limited to dates within the HRRR archive window.
3. WHEN the HRRR cache contains fewer than 3 years of data for the target month, THE Pipeline SHALL log a warning and fall back to using the PRISM normal directly as the bias correction reference (i.e., `hrrr_adjusted = hrrr_raw + (prism_normal − hrrr_raw_monthly_mean)` using only the available cached data).
4. THE Pipeline SHALL apply the same terrain corrections in daily mode as in normals mode: TPI-based terrain position multiplier, elevation lapse rate addition, UHI reduction, wind stagnation adjustment, and traffic heat reduction. The correction formulas and constants are identical between modes.
5. THE Pipeline SHALL compute daily `effective_hdd` for each ZIP code as: `daily_effective_hdd = max(0, 65 − hrrr_adjusted_temp_f) × terrain_multiplier + daily_elev_addition − daily_uhi_reduction − daily_traffic_reduction`, where `hrrr_adjusted_temp_f` is the bias-corrected HRRR daily mean temperature in °F for that ZIP code.
6. THE Pipeline SHALL write daily mode output to a time-series file at `output/microclimate/daily_{region_name}_{start_date}_{end_date}.parquet` (default) or `.csv` if `--output-format csv` is specified. Each row represents one ZIP code on one date, with columns: `date`, `zip_code`, `microclimate_id`, `hrrr_raw_temp_f`, `hrrr_adjusted_temp_f`, `daily_effective_hdd`, `bias_correction_f`, plus the six altitude-level wind columns from Requirement 17.
7. WHEN the `--mode normals` CLI argument is specified (or no `--mode` argument is given), THE Pipeline SHALL operate in the existing normals mode using PRISM as the atmospheric base, producing annual `effective_hdd` per ZIP code. The normals mode behavior is unchanged from Requirements 1–15.
8. IF `--mode daily` is specified without a date range (`--start-date`/`--end-date` or `--month`), THEN THE Pipeline SHALL raise a `ValueError` stating that daily mode requires a date range or month.
9. THE Pipeline SHALL support running both modes sequentially in a single invocation via `--mode both`, which first runs normals mode to produce `terrain_attributes.csv`, then runs daily mode for the specified date range (or month), reusing the terrain corrections already computed in the normals pass.
10. THE Pipeline SHALL document the supported date ranges in the CLI help text and README: HRRR daily mode supports dates from 2014-07-30 to present; PRISM normals mode uses the 1991–2020 climate normal period and does not require a date range.

---

### Requirement 22: Altitude-Level Microclimate Profiles

**User Story**: As a GA pilot or aviation weather analyst, I want the pipeline to produce bias-corrected temperature and HDD at each altitude level where wind data is available (surface, 3,000, 6,000, 9,000, 12,000, and 18,000 ft AGL), so that I can assess the full atmospheric profile — not just wind — at my planned cruise altitude for each ZIP code.

#### Acceptance Criteria

1. THE Pipeline SHALL extract HRRR temperature at each of the six altitude levels (surface, 3,000, 6,000, 9,000, 12,000, 18,000 ft AGL) by interpolating HRRR pressure-level temperature fields using the same log-pressure interpolation method used for wind in Requirement 17.
2. THE Pipeline SHALL bias-correct the altitude-level temperatures against PRISM climatology using the same additive formula as the surface bias correction (Requirement 18 AC2), applied independently at each altitude level: `temp_alt_adjusted = temp_alt_raw + bias_correction_f`, where `bias_correction_f` is the surface-level PRISM bias correction for that ZIP code (altitude-specific PRISM data does not exist, so the surface bias is propagated upward).
3. THE Pipeline SHALL compute altitude-level HDD for each altitude as: `hdd_{alt} = max(0, 65 − temp_{alt}_adjusted_f)` per ZIP code per date. No surface-specific terrain corrections (UHI, traffic heat, imperviousness) are applied at altitude — only the bias-corrected HRRR temperature drives the HDD computation above the surface.
4. THE Pipeline SHALL write the altitude-level temperature and HDD columns to the daily output file alongside the existing surface and wind columns, using the naming convention: `temp_{alt}_f` (e.g., `temp_3000ft_f`), `temp_{alt}_adjusted_f`, and `hdd_{alt}` (e.g., `hdd_3000ft`) for each of the six altitude levels.
5. THE altitude-level microclimate profiles SHALL only be produced in daily mode (`--mode daily` or `--mode both`). Normals mode output is unchanged.
6. IF HRRR pressure-level temperature data is missing for a given hour and altitude, THE Pipeline SHALL exclude that hour from the daily mean at that altitude and log a warning, consistent with the wind profile handling in Requirement 17 AC6.

---

### Requirement 23: Surface Property Mask and Boundary Layer Modification

**User Story**: As a GA pilot or drone operator, I want the pipeline to account for surface roughness transitions (forest edges, water bodies, urban areas) when computing wind and temperature in the boundary layer (0–1,000 ft AGL), so that the low-altitude microclimate profiles reflect localized wind shear over forest edges and thermal subsidence over water bodies rather than treating the surface as uniform.

#### Acceptance Criteria

1. THE Pipeline SHALL construct a surface property mask from NLCD 2021 land cover classifications, mapping each NLCD class to three physical parameters using a lookup table defined in `config.py`:
   - **Roughness length (z₀)** in meters: Water = 0.001, Urban/Developed = 1.0, Forest (Deciduous/Evergreen/Mixed) = 1.2, Shrub/Scrub = 0.15, Grassland/Pasture = 0.03, Cropland = 0.05, Barren = 0.005, Wetlands = 0.10. All other NLCD classes default to 0.05.
   - **Albedo**: Water = 0.06, Urban = 0.15, Forest = 0.12, Shrub = 0.20, Grassland = 0.25, Cropland = 0.22, Barren = 0.30, Wetlands = 0.14.
   - **Emissivity**: Water = 0.98, Urban = 0.92, Forest = 0.97, Shrub = 0.95, Grassland = 0.96, Cropland = 0.95, Barren = 0.90, Wetlands = 0.97.
2. THE Pipeline SHALL compute a roughness length gradient (Δz₀) at each pixel by taking the spatial gradient magnitude of the z₀ field. Pixels where Δz₀ exceeds a configurable threshold (`ROUGHNESS_GRADIENT_THRESHOLD`, default 0.3 m per pixel) are flagged as **roughness transition zones** (e.g., forest edges, urban-rural boundaries).
3. THE Pipeline SHALL compute a **wind shear correction** in roughness transition zones for altitudes ≤ 1,000 ft AGL using the log-law wind profile: `u(z) = (u_star / κ) × ln(z / z₀)`, where `κ = 0.41` (von Kármán constant) and `u_star` is the friction velocity derived from the HRRR 10 m wind and the local z₀. The wind shear correction is the difference between the log-law profile computed with the upwind z₀ and the local z₀, applied as an additive adjustment to the HRRR boundary-layer wind at altitudes ≤ 1,000 ft AGL.
4. THE Pipeline SHALL compute a **thermal subsidence correction** over water bodies: where NLCD class is Open Water (11), the boundary-layer temperature at altitudes ≤ 1,000 ft AGL is reduced by a water cooling offset computed as `water_cooling_f = (T_land − T_water) × exp(−z_agl / H_bl)`, where `T_land` is the HRRR 2 m temperature over the nearest non-water pixel, `T_water` is the HRRR 2 m temperature over the water pixel, `z_agl` is the altitude in feet, and `H_bl = 500 ft` is the boundary layer decay height (configurable as `BL_DECAY_HEIGHT_FT` in `config.py`). This captures the thermal sink effect where cool air over rivers and lakes suppresses convective mixing in the lowest 500–1,000 ft.
5. THE Pipeline SHALL write the surface property mask values (`z0_m`, `albedo`, `emissivity`, `roughness_transition_zone` boolean, `nlcd_class`) as additional columns in the daily output for each ZIP code, aggregated as the area-weighted mean (z₀, albedo, emissivity) or fraction (roughness_transition_zone) within each ZIP code polygon.
6. THE boundary layer modifications (wind shear correction and thermal subsidence) SHALL only be applied to altitudes ≤ 1,000 ft AGL. Altitudes above 1,000 ft (3,000 ft, 6,000 ft, etc.) are unaffected and use the standard HRRR pressure-level interpolation from Requirement 17.
7. THE surface property mask SHALL be computed once per pipeline run (it depends on NLCD, which is static) and reused across all daily time steps.

---

### Requirement 24: Surface Physics Engine and Aviation Safety Cube

**User Story**: As a GA pilot or aviation safety analyst, I want the pipeline to produce a 3D "Aviation Safety Cube" — a per-ZIP-code, per-altitude, per-day data structure that integrates NLCD-derived surface physics (roughness, displacement height, albedo, TKE) with HRRR-downscaled atmospheric fields — so that I can assess wind shear, turbulence, thermal hazards, and icing risk at any altitude from the surface through 18,000 ft AGL.

#### Acceptance Criteria

1. THE Surface Physics Engine SHALL generate spatially-explicit maps of three physical parameters from NLCD 2021 land cover, computed once per pipeline run and reused across all daily time steps:
   - **Roughness length (z₀)** — as defined in Requirement 20 AC1.
   - **Zero-plane displacement height (d)** — the effective height at which the wind profile origin is shifted upward by dense surface elements. Lookup: Water (11): d = 0 m; Shrub (52): d = 0.5 m; Grassland/Pasture (71, 81): d = 0.1 m; Cropland (82): d = 0.3 m; Deciduous Forest (41): d = 15 m; Evergreen Forest (42): d = 18 m; Mixed Forest (43): d = 16 m; Developed Low (22): d = 5 m; Developed Med (23): d = 8 m; Developed High (24): d = 12 m; Developed Open (21): d = 2 m; Barren (31): d = 0 m; Wetlands (90, 95): d = 1 m. Default: d = 0.5 m.
   - **Albedo** — as defined in Requirement 20 AC1.
2. THE Surface Physics Engine SHALL apply land-cover-specific atmospheric modifiers to the HRRR boundary layer (0–1,000 ft AGL) before constructing the Aviation Safety Cube:
   - **Water (NLCD 11)**: Apply a thermal sink (Requirement 20 AC4) AND reduce surface friction by using the water z₀ (0.001 m) in the displaced log-law wind profile, producing lower wind shear and smoother flow over water bodies.
   - **Forests (NLCD 41–43)**: Compute the displaced wind profile using `u(z) = (u_star / κ) × ln((z − d) / z₀)` where `d` is the displacement height for the forest class. For altitudes below `d + z₀` (i.e., within the canopy), wind speed is set to zero. The displacement height shifts the effective wind profile origin upward, producing a wind speed deficit in the lowest 50–100 ft above the canopy that is critical for low-level GA operations near forested terrain.
   - **Developed (NLCD 22–24)**: Apply the UHI temperature offset from Requirement 6 to the boundary-layer temperature profile (0–1,000 ft AGL) with exponential decay: `uhi_bl(z) = uhi_offset_f × exp(−z_agl / H_uhi)` where `H_uhi = 300 ft` (configurable as `UHI_BL_DECAY_HEIGHT_FT`). Additionally, compute a Turbulent Kinetic Energy (TKE) enhancement: `tke_urban = 0.5 × u_star² × (1 + 2 × (z0_urban / z0_rural))` where `z0_rural = 0.03 m` is the reference rural roughness. TKE is reported in m²/s² and indicates mechanical turbulence intensity.
3. THE Pipeline SHALL construct the **Aviation Safety Cube** as a per-ZIP-code, per-altitude, per-date data structure with the following fields at each of the seven altitude levels (surface, 500 ft, 1,000 ft, 3,000 ft, 6,000 ft, 9,000 ft, 12,000 ft, 18,000 ft AGL):
   - `temp_adjusted_f` — bias-corrected temperature (°F), with UHI boundary-layer decay applied for developed areas at ≤ 1,000 ft
   - `wind_speed_kt` — wind speed (knots), with displaced log-law correction for forests and roughness transitions at ≤ 1,000 ft
   - `wind_dir_deg` — wind direction (degrees true)
   - `tke_m2s2` — turbulent kinetic energy (m²/s²); elevated over developed areas, near-zero over water, moderate over forests
   - `wind_shear_kt_per_100ft` — vertical wind shear between this level and the level below (knots per 100 ft); flags mechanical shear from roughness transitions and thermal shear from inversions
   - `hdd` — heating degree days at this altitude (same formula as Requirement 19)
   - `density_altitude_ft` — pressure altitude corrected for non-standard temperature, computed as `pressure_alt + 120 × (temp_c − isa_temp_c)` where ISA temp decreases at 2°C per 1,000 ft from 15°C at sea level
4. THE Aviation Safety Cube SHALL add two altitude levels not in the original wind profile (500 ft and 1,000 ft AGL) to provide finer resolution in the boundary layer where surface physics effects are strongest. These are interpolated from HRRR surface and pressure-level data using the same log-pressure method, then modified by the surface physics corrections.
5. THE Aviation Safety Cube output SHALL be written to `output/microclimate/safety_cube_{region}_{start}_{end}.parquet` with one row per ZIP code × date × altitude level (8 altitude levels × N ZIP codes × N days). The Parquet file uses snappy compression and is partitioned by date for efficient time-range queries.
6. THE Pipeline SHALL compute a **surface-level turbulence flag** for each ZIP code and date: `turbulence_flag` = `"smooth"` if TKE < 0.5 m²/s², `"light"` if 0.5–1.5, `"moderate"` if 1.5–3.0, `"severe"` if > 3.0. This flag is included at every altitude level in the cube.
7. THE Aviation Safety Cube SHALL only be produced in daily mode (`--mode daily` or `--mode both`). Normals mode output is unchanged.

---

### Requirement 25: Real-Time Data Daemon (Optional)

**User Story**: As an aviation weather operations team, I want a persistent daemon process that automatically polls for new hourly HRRR analysis cycles, downscales them against pre-cached static terrain and surface features, and produces an updated Aviation Safety Cube within minutes of each HRRR release, so that pilots and dispatchers have near-real-time microclimate data without manual pipeline invocations.

#### Acceptance Criteria

1. THE Daemon SHALL use the `herbie` Python library to poll for the latest available HRRR analysis cycle (`product="prs"`, `fxx=0`) at a configurable interval (default: every 5 minutes). When a new cycle is detected (i.e., a cycle newer than the last processed cycle), the daemon downloads and processes it automatically.
2. THE Daemon SHALL maintain a pre-computed static cache of all non-temporal features: NLCD-derived roughness length, displacement height, albedo, emissivity, and roughness transition mask; LiDAR-derived slope, aspect, TPI, terrain position, and wind shadow mask; road heat flux raster; and UHI offset raster. The static cache is built once via a `--build-cache` CLI command and reused across all real-time cycles. The cache includes a manifest with file hashes so that stale caches are detected when source data changes.
3. THE Daemon SHALL process each incoming HRRR cycle through a streaming pipeline that: (a) bias-corrects the HRRR temperature against PRISM normals; (b) downscales the 3 km HRRR fields to the 1 m LiDAR grid using bilinear interpolation; (c) applies all cached surface physics modifiers (forest displacement, UHI boundary-layer decay, water thermal subsidence, TKE); (d) extracts multi-altitude wind and temperature profiles; (e) assembles and writes an Aviation Safety Cube for that hour. The entire processing chain must complete within 120 seconds per cycle to keep pace with hourly HRRR releases.
4. THE Daemon SHALL run the HRRR poller in a separate `multiprocessing.Process` to maintain system responsiveness. The main process consumes downloaded datasets from a queue and runs the streaming pipeline. This separation ensures that network I/O (polling and downloading) does not block the compute-intensive downscaling and physics calculations.
5. THE Daemon SHALL handle graceful shutdown on SIGINT/SIGTERM by draining the processing queue, completing any in-progress cycle, writing a final status file, and exiting with code 0.
6. THE Daemon SHALL write a `daemon_status.json` file to the real-time output directory, updated after each processed cycle, containing: `last_cycle_processed` (ISO 8601), `last_poll_time`, `cycles_processed_today`, `errors_today`, and `uptime_seconds`.
7. THE Daemon SHALL rotate output folders older than 48 hours to an archive subdirectory to prevent unbounded disk growth. The retention period is configurable.
8. ON startup, THE Daemon SHALL optionally process the last N hours of HRRR data (configurable via `--lookback`, default 2 hours) to backfill any cycles missed while the daemon was not running, before entering the polling loop.

---

### Requirement 26: Hourly Microclimate Mode

**User Story**: As a GA pilot or UAS operator planning a flight within the next few hours, I want per-hour microclimate profiles (not daily averages) so that I can see how conditions change through the day — morning inversions, afternoon convective turbulence, evening wind shifts — at each altitude level for my departure and destination ZIP codes.

#### Acceptance Criteria

1. WHEN the `--mode hourly` CLI argument is specified along with a date range, THE Pipeline SHALL process each HRRR analysis hour individually (no daily averaging) and produce one Aviation Safety Cube per hour.
2. THE hourly output SHALL contain one row per ZIP code × hour × altitude level, with columns: `datetime_utc` (ISO 8601 with hour precision), `zip_code`, `altitude_ft`, `temp_adjusted_f`, `wind_speed_kt`, `wind_dir_deg`, `tke_m2s2`, `wind_shear_kt_per_100ft`, `hourly_hdd`, `density_altitude_ft`, `turbulence_flag`.
3. THE `hourly_hdd` value SHALL be computed as `max(0, 65 − temp_adjusted_f) / 24` so that summing all 24 hours for a day produces the daily `effective_hdd` (within floating-point tolerance).
4. THE hourly output SHALL be written to `output/microclimate/hourly_{region}_{start}_{end}.parquet` partitioned by date, using snappy compression.
5. THE same surface physics corrections (forest displacement, UHI boundary-layer decay, water thermal subsidence, TKE) SHALL be applied per-hour, using the actual hourly HRRR fields rather than daily averages.
6. WHEN `--mode both` is specified with a date range, THE Pipeline SHALL run normals mode first, then daily mode, then hourly mode, reusing the terrain corrections computed in the normals pass.
7. IF `--mode hourly` is specified without a date range, THE Pipeline SHALL raise a `ValueError` stating that hourly mode requires a date range or month.
