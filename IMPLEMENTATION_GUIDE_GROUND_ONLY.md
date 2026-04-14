# How to Implement the Ground-Only Level (Monthly Microclimate Generator)

This guide walks you through implementing the **ground-only level** of the Regional Microclimate Modeling Engine — the monthly microclimate generator that produces annual `effective_hdd` per ZIP code using PRISM climate normals as the atmospheric base.

The ground-only level is the foundation that all other modes (daily, hourly, real-time) build upon. It computes static terrain and surface corrections once, then reuses them.

---

## Overview: What You're Building

The pipeline takes five static data layers and combines them into a single `effective_hdd` value per ZIP code:

1. **Terrain** (LiDAR DEM) → aspect, slope, elevation, topographic position
2. **Surface** (NLCD imperviousness) → albedo, urban heat island effect
3. **Atmosphere** (PRISM temperature normals) → baseline heating degree days
4. **Wind** (MesoWest + NREL) → infiltration and stagnation effects
5. **Traffic** (ODOT/WSDOT AADT) → anthropogenic heat from vehicles

The output is a single CSV file (`terrain_attributes.csv`) with one row per ZIP code, containing the final `effective_hdd` and all intermediate correction columns. Downstream models join on this CSV at runtime — no raster sampling happens during model runs.

---

## Step-by-Step Implementation

### Step 1: Project Setup and Configuration

**Goal**: Define all constants, file paths, and reference data in one place.

**What to do**:

1. Create the package structure:
   ```
   src/
   ├── __init__.py
   ├── config.py
   ├── loaders/
   │   └── __init__.py
   ├── processors/
   │   └── __init__.py
   ├── validation/
   │   └── __init__.py
   └── output/
       └── __init__.py
   ```

2. In `src/config.py`, define:
   - **File paths**: `LIDAR_DEM_RASTER`, `PRISM_TEMP_DIR`, `NLCD_IMPERVIOUS_RASTER`, `LANDSAT_LST_RASTER`, `MESOWEST_WIND_DIR`, `NREL_WIND_RASTER`, `ODOT_ROADS_SHP`, `WSDOT_ROADS_SHP`, `BOUNDARY_SHP`, `TERRAIN_ATTRIBUTES_CSV`
   - **CRS**: `TARGET_CRS = "EPSG:26910"` (NAD83 / UTM Zone 10N)
   - **Physics constants**: `SOLAR_IRRADIANCE_WM2 = 200`, `LAPSE_RATE_HDD_PER_1000FT = 630`, `PREVAILING_WIND_DEG = 225`
   - **Station reference data**: `STATION_HDD_NORMALS` (dict of 11 NOAA stations with their 1991–2020 normal HDD), `STATION_ELEVATIONS_FT` (elevation of each station), `ZIPCODE_STATION_MAP` (which ZIP code maps to which base station)

3. Create `data/boundary/region_registry.csv` with columns: `region_code`, `region_name`, `zip_code`, `base_station`, `lidar_vintage`. For now, all OR/WA ZIP codes go to `region_1` with base station = nearest NOAA station.

**Why**: All downstream code reads from `config.py`. No magic numbers or hardcoded paths anywhere else.

---

### Step 2: Load Static Data Layers

**Goal**: Read the five input rasters and return them as numpy arrays with metadata.

**What to do**:

1. **`src/loaders/load_lidar_dem.py`**
   - Open the GeoTIFF at `LIDAR_DEM_RASTER` using `rasterio.open()`
   - Replace nodata values with `numpy.nan`
   - Return `(array, transform, crs)` tuple
   - Raise `FileNotFoundError` if file is missing

2. **`src/loaders/load_prism_temperature.py`**
   - Load all 12 monthly mean temperature files from `PRISM_TEMP_DIR`
   - For each month, compute HDD contribution: `monthly_hdd = max(0, monthly_mean_temp_f − 65) × days_in_month`
   - Sum all 12 months to get annual HDD grid
   - **Bias-correct** to NOAA stations:
     - For each of the 11 reference stations, compute the offset: `offset = station_normal_hdd − prism_grid_value_at_station`
     - Interpolate these 11 offsets across the full grid using `scipy.interpolate.griddata(points, values, grid, method='linear')`
     - Add the interpolated offset surface to the raw PRISM HDD grid
   - Return the bias-corrected annual HDD array

3. **`src/loaders/load_nlcd_impervious.py`**
   - Open the NLCD imperviousness GeoTIFF
   - Replace sentinel values (127, 255) with `numpy.nan`
   - Clip valid values to 0–100 range
   - Return `(array, transform, crs)`

4. **`src/loaders/load_nrel_wind.py`**
   - Open the NREL wind resource GeoTIFF (80 m hub height)
   - Scale to 10 m surface wind using power law: `wind_10m = wind_80m × (10/80)^0.143`
   - Return `(array, transform, crs)`

5. **`src/loaders/load_landsat_lst.py`**
   - Open Landsat 9 Collection 2 Level-2 LST GeoTIFF
   - Apply scale factor 0.00341802 and offset 149.0 to convert to Kelvin
   - Subtract 273.15 to get Celsius
   - Return array (or `None` with a warning if file is missing)

6. **`src/loaders/load_road_emissions.py`**
   - Load ODOT and WSDOT road shapefiles
   - Filter to segments with AADT > 0
   - Compute heat flux per segment: `heat_flux_wm2 = (AADT / 86400) × 150000 / road_area_m2`
   - Return GeoDataFrame with `heat_flux_wm2` column

**Why**: Each loader is independent and testable. They all return consistent `(array, transform, crs)` tuples so downstream code can work with them uniformly.

---

### Step 3: Clip and Downscale All Rasters

**Goal**: Align all rasters to the LiDAR DEM grid (1 m, EPSG:26910) and clip to the OR/WA boundary.

**What to do**:

1. **`src/processors/clip_to_boundary.py`**
   - Load the OR/WA state boundary shapefile
   - Use `rasterio.mask.mask()` to clip a raster array to the boundary polygon
   - Return clipped array and updated transform
   - Log the clipped pixel dimensions

2. **`src/processors/downscale.py`**
   - Implement `reproject_to_lidar_grid(src_array, src_transform, src_crs, lidar_transform, lidar_crs, lidar_shape)`
   - Use `rasterio.warp.reproject()` with `Resampling.bilinear` to resample the source raster to match the LiDAR grid exactly
   - All coarse rasters (PRISM 800 m, NLCD 30 m, NREL 2 km, Landsat 30 m) pass through this function
   - Output arrays all have the same shape as the LiDAR DEM

**Why**: Bilinear interpolation preserves smooth gradients. All downstream processing works on a uniform 1 m grid.

---

### Step 4: Compute Terrain Corrections

**Goal**: Extract terrain features from the LiDAR DEM that affect microclimate.

**What to do**:

In **`src/processors/terrain_analysis.py`**, compute:

1. **Aspect** (degrees 0–360°, clockwise from north)
   - Use `numpy.gradient()` to compute DEM gradients in x and y directions
   - Compute aspect as `arctan2(dy, dx)` and convert to degrees

2. **Slope** (degrees 0–90°)
   - Compute from gradient magnitude: `slope = arctan(sqrt(dx² + dy²))`

3. **Topographic Position Index (TPI)**
   - For each pixel, compute the mean elevation within an annulus (inner radius 300 m, outer radius 1,000 m)
   - TPI = pixel elevation − annulus mean elevation
   - Negative TPI = valley, positive TPI = ridge
   - Pixels within 1,000 m of the raster edge get `numpy.nan`

4. **Terrain Position Classification**
   - **Windward**: aspect within ±90° of 225° (SW prevailing wind)
   - **Leeward**: aspect outside ±90° of 225°
   - **Valley**: TPI < 0
   - **Ridge**: TPI > 0 and slope > 25°
   - If multiple criteria match, use the most exposed category (ridge > windward > valley > leeward)

5. **Elevation Lapse Rate Addition**
   - For each ZIP code, compute mean elevation
   - Add HDD: `elev_addition = (mean_elev_ft − station_elev_ft) / 1000 × 630`

**Why**: Terrain drives cold air pooling, wind exposure, and elevation-based temperature variation.

---

### Step 5: Compute Surface Thermal Corrections

**Goal**: Quantify how surface properties (imperviousness, albedo) affect local temperature.

**What to do**:

In **`src/processors/thermal_logic.py`**, compute:

1. **Surface Albedo**
   - `surface_albedo = 0.20 − (impervious_fraction × 0.15)`
   - Where `impervious_fraction = NLCD_imperviousness / 100`
   - Albedo ranges from 0.05 (dark asphalt) to 0.20 (vegetation)

2. **Solar Aspect Multiplier**
   - South-facing slopes (aspect 135°–225°): multiplier = 1.2
   - North-facing slopes (aspect 315°–45°): multiplier = 0.8
   - Other aspects: interpolate linearly

3. **Urban Heat Island (UHI) Offset**
   - `uhi_offset_f = (0.20 − surface_albedo) × 200 / 5.5 × 9/5`
   - This converts the albedo difference to a temperature offset in °F
   - Typical range: 0–3°F depending on imperviousness

4. **Landsat 9 Calibration** (optional)
   - If Landsat LST is available:
     - Identify urban pixels (imperviousness ≥ 50%) and rural pixels (imperviousness ≤ 10%)
     - Compute mean LST difference between urban and rural within each ZIP code
     - If observed difference exceeds modeled UHI by > 1.5°C, blend: `calibrated_uhi = 0.7 × nlcd_derived + 0.3 × landsat_observed`

**Why**: Imperviousness drives urban heat island effects. Landsat provides ground truth for calibration.

---

### Step 6: Compute Wind Corrections

**Goal**: Quantify how wind speed and terrain exposure affect infiltration and heat removal.

**What to do**:

In **`src/processors/wind_steering.py`**, compute:

1. **Merge Wind Data**
   - Combine MesoWest station observations (point) with NREL gridded wind (2 km)
   - Use spatial interpolation to create a continuous 10 m wind speed surface

2. **Wind Stagnation Multiplier**
   - High wind (> 5 m/s) and not in wind shadow: UHI offset × 0.7 (wind removes heat)
   - Medium wind (3–5 m/s): UHI offset × 1.0 (baseline)
   - Low wind (< 3 m/s) and in wind shadow: UHI offset × 1.3 (heat traps)

3. **Wind Infiltration Multiplier**
   - Base multiplier = 1.0 at 3 m/s
   - Add 1.5% per m/s above 3 m/s: `infiltration_mult = 1.0 + 0.015 × (wind_speed − 3)`
   - This increases HDD because wind-driven infiltration increases heating load

4. **Gorge Floor**
   - Columbia River Gorge ZIP codes (KDLS, KTTD stations): minimum infiltration multiplier = 1.15

**Why**: Wind speed affects both heat removal (UHI) and envelope infiltration (heating load).

---

### Step 7: Compute Traffic Heat Corrections

**Goal**: Quantify anthropogenic heat from vehicle traffic.

**What to do**:

In **`src/processors/anthropogenic_load.py`**, compute:

1. **Buffer Road Segments by AADT**
   - AADT < 10,000: 50 m buffer
   - AADT 10,000–50,000: 100 m buffer
   - AADT > 50,000: 200 m buffer

2. **Rasterize Heat Flux**
   - Distribute the heat flux uniformly within each buffer zone
   - Rasterize onto the 1 m grid
   - Where buffers overlap, sum the heat flux

3. **Convert to Temperature Offset**
   - `road_temp_offset_f = road_heat_flux_wm2 / 5.5 × 9/5`
   - Typical range: 0–1°F depending on traffic density

**Why**: Major highways generate significant waste heat that warms nearby areas.

---

### Step 8: Create Granular Microclimate Cells

**Goal**: Divide each ZIP code into smaller microclimate cells (e.g., 100m × 100m or 500m × 500m blocks) to enable sub-ZIP-code granularity.

**What to do**:

In **`src/processors/create_cells.py`**, implement:

1. **Define cell size**: Choose a cell size (e.g., 500m × 500m) that balances granularity with data stability
2. **Grid the ZIP code**: Create a regular grid of cells within each ZIP code boundary
3. **Assign cell IDs**: Label each cell as `cell_001`, `cell_002`, etc. within the ZIP code
4. **Classify cells**: Optionally classify cells by dominant characteristics (e.g., `urban`, `suburban`, `rural`, `valley`, `ridge`)

**Why**: Cells enable forecasting models to distinguish between different microclimate zones within a single ZIP code (e.g., valley vs. ridge neighborhoods).

---

## Step 9: Combine All Corrections into Cell-Level Effective HDD

**Goal**: For each microclimate cell, merge all terrain, surface, wind, and traffic corrections into a cell-specific `effective_hdd` value.

**What to do**:

In **`src/processors/combine_corrections.py`**, for each cell, compute:

```
cell_effective_hdd = base_hdd × terrain_multiplier
                   + elevation_hdd_addition
                   − uhi_hdd_reduction
                   − traffic_heat_hdd_reduction
```

Where each component is the **mean value for all 1-meter grid cells within that microclimate cell**:
- `base_hdd` = PRISM bias-corrected annual HDD for the ZIP code's base station (same for all cells in the ZIP)
- `terrain_multiplier` = Mean terrain position multiplier for the cell (0.95–1.20)
- `elevation_hdd_addition` = Mean elevation lapse rate for the cell (~630 HDD per 1,000 ft)
- `uhi_hdd_reduction` = Mean UHI effect for the cell (warmer areas = larger reduction)
- `traffic_heat_hdd_reduction` = Mean road heat for the cell (proximity to highways)

Each cell gets its own row in the output CSV with a unique `cell_id`.

**Why**: This cell-level formula captures microclimate variation within ZIP codes, enabling granular forecasting.

---

### Step 10: Aggregate Cells to ZIP Code Level

**Goal**: Compute ZIP-code-level aggregates by averaging all cells within each ZIP code, for backward compatibility with existing models.

**What to do**:

In **`src/output/write_terrain_attributes.py`**, for each ZIP code:

1. **Compute mean values** across all cells:
   - `zip_effective_hdd = mean(cell_effective_hdd for all cells in ZIP)`
   - `zip_mean_elevation = mean(cell_mean_elevation for all cells)`
   - `zip_mean_wind = mean(cell_mean_wind for all cells)`
   - etc.

2. **Compute variation statistics**:
   - `cell_hdd_min = min(cell_effective_hdd for all cells)`
   - `cell_hdd_max = max(cell_effective_hdd for all cells)`
   - `cell_hdd_std = std(cell_effective_hdd for all cells)`
   - `num_cells = count of cells in ZIP`

3. **Write aggregate row** with `cell_id = "aggregate"` or a flag indicating it's a ZIP-level summary

**Why**: Aggregates allow existing models to work unchanged while new models can opt into granular cell-level data. The variation statistics show how much microclimate diversity exists within each ZIP code.

---

## Step 11: Validate and Output

**Goal**: Catch implausible values and write the final CSV with both cell-level and ZIP-level rows.

**What to do**:

In **`src/validation/qa_checks.py`**:

1. **Range Checks**
   - Flag any cell `effective_hdd` < 2,000 or > 8,000 as a warning
   - Flag any cell `effective_hdd` < 0 or > 15,000 as a hard failure

2. **Directional Sanity Checks**
   - Urban cells should have lower `effective_hdd` than rural cells in the same ZIP
   - Windward cells should have higher `effective_hdd` than leeward cells
   - High-elevation cells should have higher `effective_hdd` than low-elevation cells

3. **Cell Consistency Checks**
   - Verify that ZIP-code aggregate `effective_hdd` equals mean of all cells (within rounding)
   - Flag any cells with extreme outlier values

4. **Billing Comparison** (optional)
   - Compare cell-level `effective_hdd` against billing-derived therms per customer
   - Flag divergences > 15% as warnings

5. **Write QA Report**
   - Generate `qa_report.html` and `qa_report.md` with:
     - Summary statistics (min, max, mean, std of cell `effective_hdd`)
     - List of flagged cells and reasons
     - Choropleth map colored by QA status

In **`src/output/write_terrain_attributes.py`**:

1. **Write cell-level rows**: One row per microclimate cell with:
   - `microclimate_id` = `{region_code}_{zip_code}_{base_station}_cell_{cell_id}`
   - `cell_id`, `cell_type`, `effective_hdd`, all correction columns
   - `cell_area_sqm` (area of the cell)

2. **Write ZIP-level aggregate rows**: One row per ZIP code with:
   - `microclimate_id` = `{region_code}_{zip_code}_{base_station}_aggregate`
   - `cell_id` = `"aggregate"`, `cell_type` = `"zip_aggregate"`
   - `effective_hdd` = mean across all cells
   - `num_cells`, `cell_hdd_min`, `cell_hdd_max`, `cell_hdd_std`

3. **Add versioning metadata**:
   - `run_date` = ISO 8601 timestamp
   - `pipeline_version` = semantic version
   - `lidar_vintage`, `nlcd_vintage`, `prism_period`

**Why**: QA catches data quality issues before they propagate downstream. Cell-level and ZIP-level rows serve different use cases.

---

## Step 12: Create Interactive Cell-Based Maps

**Goal**: Produce Leaflet HTML maps that visualize cells and their corrections at granular scale.

**What to do**:

In **`src/output/write_maps.py`**, create multiple interactive maps:

1. **Cell-level effective HDD choropleth**
   - Color each cell by its `effective_hdd` value
   - Use a color scale (e.g., blue for high HDD, red for low HDD)
   - Overlay ZIP code boundaries as thin gray lines for geographic reference
   - Click any cell to show popup with: `cell_id`, `effective_hdd`, `terrain_position`, `mean_elevation_ft`, `mean_wind_ms`, `mean_impervious_pct`, `uhi_offset_f`, `road_heat_flux_wm2`

2. **Terrain position layer**
   - Color cells by terrain type: windward (orange), leeward (blue), valley (green), ridge (red)
   - Show how terrain drives HDD variation within ZIP codes

3. **UHI effect layer**
   - Color cells by `uhi_offset_f` (urban heat island offset)
   - Show which neighborhoods are warmest due to development

4. **Wind infiltration layer**
   - Color cells by `wind_infiltration_mult`
   - Show which areas have highest infiltration loads

5. **Traffic heat layer**
   - Color cells by `road_heat_flux_wm2`
   - Show which areas are affected by major roads

6. **Layer control panel**
   - Allow users to toggle between different correction layers
   - Show/hide ZIP code boundaries
   - Show/hide cell boundaries

7. **Zoom and pan**
   - Allow users to zoom into specific neighborhoods
   - Show cell-level detail at high zoom levels

**Why**: Cell-level maps enable stakeholders to visualize microclimate variation at neighborhood scale, not just ZIP-code scale. This supports infrastructure planning, weatherization programs, and regulatory discussions.

---

## Step 13: Optional Weather Adjustment

**Goal**: Scale `effective_hdd` by actual-to-normal weather ratio for a specific historical year.

**What to do**:

In **`src/processors/weather_adjustment.py`**:

1. If `--weather-year` CLI argument is provided:
   - Compute actual HDD for that year from observed weather data
   - Compute adjustment factor per station: `adjustment = actual_hdd / normal_hdd`
   - Apply to all cells: `cell_effective_hdd_adjusted = cell_effective_hdd × adjustment`

2. Write both `effective_hdd` (unadjusted) and `effective_hdd_adjusted` (adjusted) columns

**Why**: Allows calibration runs to reflect observed weather rather than climate normals.

---

## Data Flow Diagram

```
LiDAR DEM (1 m)
    ↓
Clip to boundary
    ↓
Terrain analysis (aspect, slope, TPI)
    ↓
    ├─→ Terrain position classification
    │
    ├─→ Elevation lapse rate
    │
    └─→ Wind shadow mask

PRISM Temp (800 m) ──→ Downscale (bilinear) ──→ Bias-correct to NOAA stations
    ↓
Annual HDD grid

NLCD Imperviousness (30 m) ──→ Downscale ──→ Surface albedo ──→ UHI offset
    ↓
Landsat LST (optional) ──→ Calibrate UHI

MesoWest + NREL Wind ──→ Downscale ──→ Wind stagnation multiplier
    ↓
Wind infiltration multiplier

ODOT/WSDOT AADT ──→ Buffer by AADT ──→ Rasterize heat flux ──→ Road temp offset
    ↓
    ├─ Terrain multiplier
    ├─ Elevation addition
    ├─ UHI reduction
    └─ Traffic reduction
        ↓
    Create microclimate cells (e.g., 500m × 500m grid)
        ↓
    For each cell, compute effective_hdd using formula
        ↓
    Cell-level rows (one per cell per ZIP code)
        ↓
    Aggregate cells to ZIP code level
        ↓
    ZIP-code aggregate rows (one per ZIP code)
        ↓
    Combine cell + aggregate rows
        ↓
    Write terrain_attributes.csv
        ↓
    QA checks
        ↓
    qa_report.html / qa_report.md
```

---

## Key Implementation Details

### Bilinear Interpolation for Downscaling

All coarse rasters must be resampled to the 1 m LiDAR grid using **bilinear interpolation**, not nearest-neighbor. This preserves smooth gradients and avoids blocky artifacts.

```python
from rasterio.warp import reproject, Resampling

reproject(
    src_array,
    dst_array,
    src_transform=src_transform,
    dst_transform=lidar_transform,
    src_crs=src_crs,
    dst_crs=lidar_crs,
    resampling=Resampling.bilinear
)
```

### PRISM Bias Correction

PRISM provides spatial continuity; NOAA stations provide calibration accuracy. Combine them:

```python
# Compute offset at each station location
offsets = []
for station_id, station_hdd in STATION_HDD_NORMALS.items():
    lat, lon = STATION_COORDS[station_id]
    prism_value_at_station = prism_grid[row, col]  # sample PRISM at station location
    offset = station_hdd - prism_value_at_station
    offsets.append((lat, lon, offset))

# Interpolate offsets across the full grid
from scipy.interpolate import griddata
offset_surface = griddata(
    points=[(lat, lon) for lat, lon, _ in offsets],
    values=[offset for _, _, offset in offsets],
    xi=(grid_lats, grid_lons),
    method='linear'
)

# Apply offset
prism_bias_corrected = prism_grid + offset_surface
```

### TPI Computation

Topographic Position Index captures valley/ridge classification:

```python
from scipy.ndimage import uniform_filter

# Compute mean elevation in annulus (300–1000 m radius)
# Use two circular kernels: outer (1000 m) and inner (300 m)
outer_radius_pixels = 1000 / pixel_size_m
inner_radius_pixels = 300 / pixel_size_m

# Create circular kernels
outer_kernel = create_circular_kernel(outer_radius_pixels)
inner_kernel = create_circular_kernel(inner_radius_pixels)

# Compute annulus mean
outer_mean = uniform_filter(dem, footprint=outer_kernel)
inner_mean = uniform_filter(dem, footprint=inner_kernel)
annulus_mean = (outer_mean * outer_area - inner_mean * inner_area) / (outer_area - inner_area)

# TPI = elevation - annulus mean
tpi = dem - annulus_mean
```

### Terrain Position Classification

Classify each pixel based on aspect and TPI:

```python
def classify_terrain_position(aspect_deg, tpi, slope_deg, prevailing_wind_deg=225):
    # Windward: aspect within ±90° of prevailing wind
    windward_min = (prevailing_wind_deg - 90) % 360
    windward_max = (prevailing_wind_deg + 90) % 360
    is_windward = (aspect_deg >= windward_min) or (aspect_deg <= windward_max)
    
    # Ridge: TPI > 0 and slope > 25°
    is_ridge = (tpi > 0) and (slope_deg > 25)
    
    # Valley: TPI < 0
    is_valley = tpi < 0
    
    # Leeward: not windward
    is_leeward = not is_windward
    
    # Precedence: ridge > windward > valley > leeward
    if is_ridge:
        return 'ridge'
    elif is_windward:
        return 'windward'
    elif is_valley:
        return 'valley'
    else:
        return 'leeward'
```

### UHI Offset Calculation

Convert surface albedo to temperature offset:

```python
def compute_uhi_offset_f(impervious_fraction, solar_irradiance_wm2=200):
    # Albedo ranges from 0.05 (dark) to 0.20 (vegetation)
    surface_albedo = 0.20 - (impervious_fraction * 0.15)
    
    # Temperature offset from albedo difference
    # Formula: ΔT = (Δalbedo) × (solar_irradiance) / (sensible_heat_flux_coefficient)
    # Sensible heat flux coefficient ≈ 5.5 W/m²/K
    uhi_offset_k = (0.20 - surface_albedo) * solar_irradiance_wm2 / 5.5
    
    # Convert K to °F (multiply by 9/5)
    uhi_offset_f = uhi_offset_k * 9 / 5
    
    return uhi_offset_f
```

### Effective HDD Formula

Combine all corrections:

```python
def compute_effective_hdd(
    base_hdd,
    terrain_multiplier,
    elevation_hdd_addition,
    uhi_offset_f,
    road_temp_offset_f
):
    # UHI and traffic heat reduce HDD (warmer = less heating needed)
    uhi_hdd_reduction = uhi_offset_f * 180  # 180 HDD per °F
    traffic_hdd_reduction = road_temp_offset_f * 180
    
    effective_hdd = (
        base_hdd * terrain_multiplier
        + elevation_hdd_addition
        - uhi_hdd_reduction
        - traffic_hdd_reduction
    )
    
    return max(0, effective_hdd)  # HDD cannot be negative
```

---

## Testing Strategy

For each module, write property-based tests:

1. **Terrain Analysis**
   - TPI values are symmetric around zero (valleys and ridges)
   - Aspect values are in range 0–360°
   - Slope values are in range 0–90°

2. **Thermal Logic**
   - Albedo is in range 0.05–0.20
   - UHI offset is non-negative
   - UHI offset increases with imperviousness

3. **Wind Steering**
   - Wind infiltration multiplier ≥ 1.0
   - Stagnation multiplier is in range 0.7–1.3

4. **Combine Corrections**
   - Effective HDD is in range 2,000–8,000 for PNW
   - Urban ZIP codes have lower effective HDD than rural neighbors
   - Windward ZIP codes have higher effective HDD than leeward

---

## Running the Pipeline

Once all modules are implemented:

```bash
# Run for region_1 (all OR/WA)
python -m src.pipeline --region region_1 --mode normals

# Output: output/microclimate/terrain_attributes.csv
#         output/microclimate/qa_report.html
#         output/microclimate/qa_report.md
```

The CSV is ready to join with downstream models on `microclimate_id` or `zip_code`.

---

## Summary

The ground-only level is a 13-step pipeline that:

1. Loads five static data layers (LiDAR, PRISM, NLCD, wind, roads)
2. Clips and downscales all rasters to a uniform 1 m grid
3. Computes terrain corrections (aspect, slope, TPI, elevation)
4. Computes surface corrections (albedo, UHI, Landsat calibration)
5. Computes wind corrections (stagnation, infiltration)
6. Computes traffic corrections (road heat flux)
7. Creates granular microclimate cells (e.g., 500m × 500m grid)
8. Combines all corrections into cell-level effective HDD per cell
9. Aggregates cells to ZIP code level
10. Writes terrain_attributes.csv with both cell-level and ZIP-level rows
11. Runs QA checks and generates reports
12. Creates interactive Leaflet maps showing cells colored by effective HDD and corrections
13. Optionally adjusts for actual weather

The output is a pre-computed lookup table with multiple rows per ZIP code (one per cell, plus one aggregate), plus interactive maps that visualize cell-level microclimate variation. Downstream models can join on individual cells for granular forecasting, or on ZIP-code aggregates for coarser analysis. No raster sampling happens during model runs — all corrections are pre-computed and stored in the CSV.
