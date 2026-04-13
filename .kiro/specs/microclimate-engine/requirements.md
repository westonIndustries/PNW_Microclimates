# Requirements — Regional Microclimate Modeling Engine

## Introduction

The **Regional Microclimate Modeling Engine** is a Python processing pipeline that converts geographic regions in the regional utility service area into high-resolution microclimate maps. It integrates terrain data, surface imperviousness, atmospheric temperature normals, wind observations, and traffic-derived heat flux to produce an `effective_hdd` value for every planning district or Census block group. This value replaces the single airport-station HDD used in the base forecasting model, capturing sub-district variation driven by terrain position, urban heat island effects, wind exposure, and anthropogenic heat load.

**Primary users**: Forecasting analysts and data engineers who maintain and run the simulation pipeline. Secondary users: regulatory staff reviewing load forecasts who need to understand how weather normalization is applied at sub-district scale.

**Scope**: The pipeline covers the full Oregon and Washington service territory as a single processing region (`region_1`). It produces a pre-computed lookup table (`terrain_attributes.csv`) that the simulation pipeline joins at runtime. The pipeline does not perform real-time raster sampling during simulation runs.

---

## Glossary

| Term | Definition |
|------|-----------|
| **microclimate_id** | Unique string identifier for a microclimate area, formatted as `{region_code}_{district_code}_{base_station}` (e.g., `R1_DIST01_KPDX`). Primary key in `terrain_attributes.csv`. |
| **effective_hdd** | Adjusted annual heating degree days (base 65°F) for a district or block group, incorporating terrain, surface, wind, and traffic corrections on top of the PRISM/NOAA atmospheric base. |
| **TPI** | Topographic Position Index — the elevation at a point minus the mean elevation within a surrounding annulus (300–1,000 m radius). Negative TPI indicates a valley; positive TPI indicates a ridge. |
| **UHI** | Urban Heat Island — the phenomenon where dense impervious surfaces (asphalt, rooftops) absorb solar radiation and re-emit it as heat, raising effective air temperatures 2–5°F above the rural baseline. |
| **AADT** | Annual Average Daily Traffic — the total volume of vehicle traffic on a road segment divided by 365, used to compute anthropogenic heat flux from vehicle exhaust and friction. |
| **LiDAR** | Light Detection and Ranging — airborne laser scanning that produces a bare-earth digital elevation model (DEM) at 1 m resolution. Source: DOGAMI (Oregon) and WA DNR (Washington). |
| **PRISM** | Parameter-elevation Regressions on Independent Slopes Model — a gridded climate dataset from Oregon State University providing monthly temperature and precipitation normals at 800 m resolution. |
| **terrain_position** | Classification of each pixel as `windward`, `leeward`, `valley`, or `ridge` based on aspect relative to the prevailing SW wind (225°) and TPI. |
| **wind shadow** | A binary raster mask identifying areas where terrain blocks the prevailing wind, derived from TPI and aspect. Wind shadow areas have reduced infiltration loads but may trap urban heat. |
| **lapse rate** | The rate at which temperature decreases with elevation — approximately 3.5°F per 1,000 ft, equivalent to ~630 HDD per 1,000 ft above the base weather station. |

---

## Requirements

---

### Requirement 1: Spatial Boundary and Region Definition

**User Story**: As a forecasting analyst, I want the pipeline to process one geographic region at a time and clip all rasters to the state utility boundary, so that memory usage is manageable and results are confined to the actual service footprint.

**Acceptance Criteria**:

1. The pipeline accepts a `region_name` parameter (e.g., `region_1`) that selects a predefined bounding box and district list from the region registry in `config.py`.
2. All input rasters are clipped to the OR/WA state boundary polygon before any computation. Pixels outside the service territory boundary are masked and excluded from all outputs.
3. The region registry defines `region_1` (Oregon + Washington extent, bounding box: minx=-124.8, miny=41.9, maxx=-116.9, maxy=49.1 in EPSG:4326) with: region name, list of planning district codes, primary base station(s), and bounding box coordinates.
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
3. The mean LST difference between urban and rural pixels within each district is computed and compared against the NLCD-derived `uhi_offset_f`. If the observed difference exceeds the modeled offset by more than 1.5°C, a calibration warning is logged.
4. The calibrated `uhi_offset_f` is adjusted toward the Landsat-observed value using a weighted blend: 70% NLCD-derived, 30% Landsat-observed.
5. The mean summer LST for each district is written to the `lst_summer_c` column in `terrain_attributes.csv`.
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
5. The Columbia River Gorge districts receive a wind infiltration multiplier floor of 1.15, reflecting the high-wind corridor effect.
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
6. Districts with no road segments in the AADT shapefiles receive `road_heat_flux_wm2 = 0.0` and `road_temp_offset_f = 0.0`.

---

### Requirement 10: Effective HDD Computation

**User Story**: As a forecasting analyst, I want the pipeline to combine all terrain, surface, wind, and traffic corrections into a single `effective_hdd` per district, so that the simulation pipeline has a single pre-computed value to join on.

**Acceptance Criteria**:

1. `effective_hdd` is computed as:
   ```
   effective_hdd = base_hdd
                 × terrain_multiplier
                 + elevation_hdd_addition
                 − uhi_hdd_reduction
                 − traffic_heat_hdd_reduction
   ```
   where `base_hdd` is the PRISM bias-corrected annual HDD for the district's base station.
2. `elevation_hdd_addition` is computed as: `(mean_elevation_ft − station_elevation_ft) / 1000 × 630`.
3. `traffic_heat_hdd_reduction` is computed as: `road_temp_offset_f × 180`.
4. All intermediate correction columns (`hdd_terrain_mult`, `hdd_elev_addition`, `hdd_uhi_reduction`) are retained in `terrain_attributes.csv`.
5. `effective_hdd` values outside the range 2,000–8,000 are flagged in the QA report as implausible for the PNW climate.

---

### Requirement 11: Output Schema

**User Story**: As a data engineer, I want the pipeline to write a `terrain_attributes.csv` with a well-defined schema including `microclimate_id`, `district_code`, and all correction columns, so that the simulation pipeline can join on a stable key without re-sampling rasters.

**Acceptance Criteria**:

1. The output file is written to the path specified by `TERRAIN_ATTRIBUTES_CSV` in `config.py`.
2. The `microclimate_id` is formatted as `{region_code}_{district_code}_{base_station}` (e.g., `R1_DIST01_KPDX`). It is unique per row.
3. The CSV contains all columns defined in the output schema (see design doc), with correct data types: string for identifiers, float64 for numeric corrections, int for HDD values.
4. The `district_code` column is the primary join key back to the premise-equipment table. It must match the values in `DISTRICT_WEATHER_MAP` exactly.
5. No raster files are read or sampled at simulation runtime — all corrections are pre-computed and stored in the CSV.

---

### Requirement 12: Output Versioning

**User Story**: As a data engineer, I want every row in `terrain_attributes.csv` to carry metadata about when it was produced and which data vintages were used, so that stale rows can be identified after data updates.

**Acceptance Criteria**:

1. Every row contains a `run_date` column with an ISO 8601 timestamp (e.g., `2025-01-15T14:32:00`) set at pipeline execution time.
2. Every row contains a `pipeline_version` column with a semantic version string (e.g., `1.0.0`) defined as a constant in `config.py`.
3. Every row contains a `lidar_vintage` column with the year of the LiDAR DEM used (e.g., `2021`), defined per region in the region registry.
4. Every row contains an `nlcd_vintage` column with the NLCD release year (e.g., `2021`), defined as a constant in `config.py`.
5. Every row contains a `prism_period` column with the climate normal period string (e.g., `1991-2020`), defined as a constant in `config.py`.

---

### Requirement 13: QA and Validation

**User Story**: As a forecasting analyst, I want the pipeline to run automated range checks and directional sanity checks on the output, and produce an HTML/MD QA report, so that implausible values are caught before the CSV enters the simulation pipeline.

**Acceptance Criteria**:

1. Range checks flag any `effective_hdd` value outside 2,000–8,000 as a warning.
2. Directional sanity checks verify: (a) urban districts have lower `effective_hdd` than their rural neighbors; (b) windward districts have higher `effective_hdd` than leeward districts in the same region; (c) high-elevation districts have higher `effective_hdd` than low-elevation districts in the same region.
3. Billing comparison checks that `effective_hdd` for each district is within 15% of the billing-derived therms-per-customer ratio for that district. Divergences > 15% are flagged as warnings. This check is optional and requires utility-specific billing data; if the billing reference CSV is not present, this check is skipped and a notice is logged.
4. The QA report is written to `output/microclimate/` as both `qa_report.html` and `qa_report.md`.
5. The pipeline exits with a non-zero return code if any hard failures are detected (e.g., `effective_hdd` < 0 or > 15,000).

---

### Requirement 14: Weather Adjustment

**User Story**: As a forecasting analyst, I want an optional weather adjustment step that scales `effective_hdd` by the ratio of actual to normal HDD for a specific historical year, so that calibration runs reflect observed weather rather than climate normals.

**Acceptance Criteria**:

1. The weather adjustment is triggered by an optional `--weather-year` CLI argument (e.g., `--weather-year 2024`).
2. The adjustment factor is computed per station: `adjustment = actual_station_hdd / normal_station_hdd`, where actual HDD is derived from `WEATHER_CALDAY` and normal HDD is from `config.py`.
3. The adjusted value is: `effective_hdd_adjusted = effective_hdd × adjustment`.
4. The adjustment is applied after all terrain and surface corrections, so it scales the already-refined effective HDD.
5. When the weather adjustment is applied, the output column is named `effective_hdd_adjusted` and the unadjusted `effective_hdd` is retained as a separate column.
6. If `--weather-year` is not specified, no adjustment is applied and only `effective_hdd` is written.

---

### Requirement 15: Pipeline Re-run Cadence

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
