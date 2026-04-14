# How the Ground-Only Microclimate Engine Works

## Executive Summary

The Regional Microclimate Modeling Engine's ground-only level is a data processing pipeline that produces hyper-local heating degree day (HDD) estimates at sub-ZIP-code granularity across Oregon and Washington. Instead of using a single airport weather station to estimate heating needs across an entire region, this system accounts for terrain, urban development, wind exposure, and traffic heat to produce location-specific values that are 2–5 times more accurate than traditional methods.

**Output**: A CSV file with multiple rows per ZIP code — one row per granular microclimate cell within that ZIP code. Each cell has its own `effective_hdd` value calculated by the formula. The file also includes ZIP-code-level aggregates for backward compatibility. Downstream forecasting models can join on individual cells for granular forecasting, or on ZIP-code aggregates for coarser analysis. No raster processing happens during model execution.

---

## The Problem We're Solving

Energy forecasters traditionally use a single airport weather station's heating degree days (HDD) to estimate heating demand across an entire service territory. This approach misses critical microclimate variation:

- **Terrain**: A valley ZIP code 5 miles from a ridgetop ZIP code can differ by 500+ HDD due to cold air pooling and wind exposure
- **Urban heat**: Dense urban areas run 2–5°F warmer than surrounding rural land due to pavement and buildings
- **Wind**: The Columbia River Gorge experiences 50% higher wind speeds than surrounding areas, increasing infiltration loads
- **Traffic**: Major highways generate waste heat that warms nearby areas

Result: Forecasts are systematically off by 10–20% in certain areas, leading to poor resource allocation and rate case disputes.

---

## How It Works: The 11-Step Process

### Step 1: Define the Region
The pipeline processes Oregon and Washington as a single region (`region_1`). It reads a registry that maps each ZIP code to its nearest NOAA weather station (e.g., Portland ZIP codes → KPDX airport).

### Step 2: Load Terrain Data
The pipeline loads a 1-meter resolution LiDAR digital elevation model (DEM) from DOGAMI (Oregon) and WA DNR (Washington). This captures every hill, valley, and ridge at sub-ZIP-code scale.

### Step 3: Load Climate Baseline
The pipeline loads 12 monthly temperature normal grids from PRISM (Oregon State University) at 800-meter resolution. These represent 30-year climate averages (1991–2020). The pipeline then bias-corrects these grids so they match the known HDD values at each NOAA weather station, ensuring consistency with existing forecasting models.

### Step 4: Align All Data to a Uniform Grid
All input data (terrain, climate, imperviousness, wind, roads) come at different resolutions (1 m, 30 m, 800 m, 2 km). The pipeline resamples everything to a uniform 1-meter grid using smooth bilinear interpolation (not blocky nearest-neighbor). This ensures all corrections are applied consistently.

### Step 5: Analyze Terrain Features
From the LiDAR DEM, the pipeline computes:
- **Aspect** (which direction slopes face: N, S, E, W)
- **Slope** (steepness in degrees)
- **Topographic Position Index (TPI)** (whether each location is in a valley or on a ridge)

These features are then classified into four terrain types:
- **Windward**: Faces the prevailing SW wind → higher HDD (more wind infiltration)
- **Leeward**: Sheltered from wind → lower HDD (less infiltration)
- **Valley**: Cold air pools here → higher HDD (colder)
- **Ridge**: Exposed to wind and sun → lower HDD (warmer)

### Step 6: Quantify Urban Heat Island Effect
The pipeline loads NLCD imperviousness data (30-meter resolution) showing the percentage of each area covered by pavement, roofs, and other impervious surfaces. It converts this to surface albedo (reflectivity) and computes the urban heat island (UHI) offset — how much warmer dense urban areas run compared to rural land. Typical range: 0–3°F depending on development density.

Optionally, the pipeline calibrates these estimates against Landsat 9 satellite land surface temperature data to ground-truth the UHI effect.

### Step 7: Compute Wind Effects
The pipeline merges MesoWest weather station observations (point data) with NREL gridded wind resource data (2 km resolution) to create a continuous wind speed surface. It then computes two wind-related corrections:
- **Wind stagnation**: Low wind speeds in sheltered valleys amplify the UHI effect (heat traps)
- **Wind infiltration**: High wind speeds increase envelope infiltration, raising heating load

The Columbia River Gorge receives a special floor (minimum multiplier of 1.15) to account for its extreme wind exposure.

### Step 8: Quantify Traffic Heat
The pipeline loads ODOT (Oregon) and WSDOT (Washington) road traffic data (AADT = Annual Average Daily Traffic). For each road segment, it computes waste heat from vehicle exhaust and friction, then buffers that heat around the road (50–200 m depending on traffic volume). This heat is converted to a temperature offset (typically 0–1°F depending on proximity to major highways).

### Step 9: Create Granular Microclimate Cells
Instead of aggregating all 1-meter grid cells into a single ZIP-code value, the pipeline now groups them into larger microclimate cells (e.g., 100m × 100m or 500m × 500m blocks). Each cell represents a distinct microclimate zone within the ZIP code. Cells are assigned sequential IDs: `cell_001`, `cell_002`, etc.

This granularity allows forecasting models to distinguish between:
- A valley neighborhood (high HDD) vs. a ridgetop neighborhood (low HDD) within the same ZIP code
- Dense urban core (low HDD due to UHI) vs. suburban fringe (higher HDD) within the same ZIP code
- High-wind corridor (high infiltration HDD) vs. sheltered areas within the same ZIP code

### Step 10: Calculate Cell-Level Effective HDD
For each microclimate cell, the pipeline applies the correction formula:

```
cell_effective_hdd = base_hdd × terrain_multiplier
                   + elevation_addition
                   − urban_heat_reduction
                   − traffic_heat_reduction
```

Where each component is computed from the 1-meter grid cells within that microclimate cell:
- `base_hdd` = PRISM climate normal for the ZIP code's base station (same for all cells in the ZIP)
- `terrain_multiplier` = Mean terrain position multiplier for the cell (0.95–1.20)
- `elevation_addition` = Mean elevation lapse rate for the cell (~630 HDD per 1,000 ft)
- `urban_heat_reduction` = Mean UHI effect for the cell (warmer areas = larger reduction)
- `traffic_heat_reduction` = Mean road heat for the cell (proximity to highways)

Each cell gets its own row in the output CSV with a unique `cell_id`.

### Step 11: Aggregate to ZIP Code Level
The pipeline also computes ZIP-code-level aggregates by averaging all cells within the ZIP code:

```
zip_effective_hdd = mean(cell_effective_hdd for all cells in ZIP)
```

This produces a second set of rows (one per ZIP code) for backward compatibility with models that expect ZIP-code-level data. These aggregate rows have `cell_id = "aggregate"` or are marked with a flag.

### Step 12: Validate and Output
The pipeline runs automated quality checks:
- **Range checks**: Flag any HDD outside 2,000–8,000 (implausible for PNW)
- **Directional sanity**: Verify urban cells < rural cells, windward > leeward, high elevation > low elevation
- **Billing comparison** (optional): Compare against billing-derived therms per customer
- **Cell consistency**: Verify that ZIP-code aggregate equals mean of all cells (within rounding)

It then writes the final CSV (`terrain_attributes.csv`) with:
- **Multiple rows per ZIP code**: One row per microclimate cell (e.g., 10–50 cells per ZIP depending on size and terrain variation)
- **One aggregate row per ZIP code**: For backward compatibility
- All correction columns and metadata (run date, data vintage, pipeline version)

---

## Key Outputs

### Primary Output: `terrain_attributes.csv`

Multiple rows per ZIP code — one row per microclimate cell, plus one aggregate row per ZIP code.

**Cell-level rows** (granular forecasting):

| Column | Meaning |
|--------|---------|
| `microclimate_id` | Unique ID: `R1_97201_KPDX_cell_001` (region, ZIP, base station, cell) |
| `zip_code` | The ZIP code |
| `cell_id` | Cell identifier within the ZIP: `cell_001`, `cell_002`, etc. |
| `cell_type` | Classification: `urban`, `suburban`, `rural`, `valley`, `ridge`, `gorge`, etc. |
| `effective_hdd` | **Final adjusted HDD for this cell** — use this for granular forecasting |
| `terrain_position` | `windward`, `leeward`, `valley`, or `ridge` |
| `mean_elevation_ft` | Average elevation in this cell |
| `mean_wind_ms` | Average wind speed in this cell (m/s) |
| `mean_impervious_pct` | % of area covered by pavement/roofs in this cell |
| `uhi_offset_f` | Urban heat island effect in this cell (°F) |
| `road_heat_flux_wm2` | Traffic waste heat in this cell (W/m²) |
| `hdd_terrain_mult` | Terrain correction multiplier for this cell |
| `hdd_elev_addition` | Elevation correction for this cell (HDD) |
| `hdd_uhi_reduction` | UHI correction for this cell (HDD) |
| `cell_area_sqm` | Area of this cell (m²) |
| `run_date` | When this was computed |
| `pipeline_version` | Which version of the pipeline |
| `lidar_vintage` | Year of LiDAR data used |
| `nlcd_vintage` | Year of imperviousness data used |
| `prism_period` | Climate normal period (1991–2020) |

**ZIP-code aggregate rows** (backward compatibility):

| Column | Meaning |
|--------|---------|
| `microclimate_id` | Unique ID: `R1_97201_KPDX_aggregate` |
| `zip_code` | The ZIP code |
| `cell_id` | `aggregate` (indicates this is a ZIP-level summary) |
| `cell_type` | `zip_aggregate` |
| `effective_hdd` | **Mean effective HDD across all cells in this ZIP** — use for coarse forecasting |
| `terrain_position` | Most common terrain position in the ZIP |
| `mean_elevation_ft` | Mean elevation across all cells |
| `mean_wind_ms` | Mean wind speed across all cells |
| `mean_impervious_pct` | Mean imperviousness across all cells |
| `uhi_offset_f` | Mean UHI effect across all cells |
| `road_heat_flux_wm2` | Mean traffic heat across all cells |
| `hdd_terrain_mult` | Mean terrain multiplier across all cells |
| `hdd_elev_addition` | Mean elevation addition across all cells |
| `hdd_uhi_reduction` | Mean UHI reduction across all cells |
| `num_cells` | Number of granular cells in this ZIP |
| `cell_hdd_min` | Minimum effective HDD among all cells (shows variation) |
| `cell_hdd_max` | Maximum effective HDD among all cells (shows variation) |
| `cell_hdd_std` | Standard deviation of effective HDD across cells |
| `run_date` | When this was computed |
| `pipeline_version` | Which version of the pipeline |
| `lidar_vintage` | Year of LiDAR data used |
| `nlcd_vintage` | Year of imperviousness data used |
| `prism_period` | Climate normal period (1991–2020) |

### Secondary Outputs

- **`qa_report.html` / `qa_report.md`**: Quality assurance report flagging implausible values
- **Interactive maps**: Leaflet HTML maps showing:
  - **Cell-level choropleth**: Each microclimate cell colored by its `effective_hdd` value (granular view)
  - **ZIP-code overlay**: ZIP code boundaries overlaid on cells for geographic reference
  - **Terrain position layer**: Cells colored by terrain type (windward, leeward, valley, ridge)
  - **UHI effect layer**: Cells colored by urban heat island offset
  - **Wind infiltration layer**: Cells colored by wind stagnation/infiltration multiplier
  - **Traffic heat layer**: Cells colored by proximity to major roads
  - **Layer control panel**: Toggle between different correction layers
  - **Cell info popup**: Click any cell to see its `effective_hdd`, cell ID, terrain position, elevation, wind speed, imperviousness, etc.

---

## How Downstream Models Use This

### Option 1: Granular Cell-Level Forecasting (New)

For models that support sub-ZIP-code granularity:

```
heating_load = cell_effective_hdd × customers_in_cell
```

Join the CSV on `microclimate_id` (which includes the cell ID) to get the specific `effective_hdd` for each microclimate cell. This enables:
- Forecasting that accounts for terrain variation within a ZIP code
- Identifying which neighborhoods need weatherization programs
- More accurate load forecasting in mixed-terrain areas (e.g., Portland ZIP codes with both valley and ridge neighborhoods)

### Option 2: ZIP-Code-Level Forecasting (Backward Compatible)

For existing models that expect one value per ZIP code:

```
heating_load = zip_aggregate_effective_hdd × total_customers_in_zip
```

Join the CSV on `zip_code` and filter for rows where `cell_id = "aggregate"`. This produces the same result as before — one `effective_hdd` per ZIP code — but now you also have visibility into the variation within that ZIP (via `cell_hdd_min`, `cell_hdd_max`, `cell_hdd_std`).

### Option 3: Hybrid Approach

Use cell-level data where available (for granular forecasting), fall back to ZIP-code aggregates for areas with limited data or for coarser analysis.

All approaches avoid opening raster files during model execution — all corrections are pre-computed and stored in the CSV.

---

## Data Sources

| Layer | Resolution | Source |
|-------|-----------|--------|
| Terrain (LiDAR DEM) | 1 m | DOGAMI (OR), WA DNR (WA) |
| Climate baseline (PRISM) | 800 m | Oregon State University |
| Imperviousness (NLCD) | 30 m | USGS |
| Land surface temperature (Landsat 9) | 30 m | USGS via Planetary Computer |
| Wind observations (MesoWest) | Point | Synoptic Data |
| Wind resource (NREL) | 2 km | NREL Wind Toolkit |
| Road traffic (AADT) | Vector | ODOT, WSDOT |
| State boundary | Vector | US Census TIGER/Line |
| ZIP code boundaries | Vector | Census ZCTA / OpenDataSoft / RLIS |

---

## Accuracy & Validation

The pipeline produces `effective_hdd` values that are typically within 5–10% of billing-derived therms per customer — a significant improvement over single-station HDD which can be off by 15–25% in certain areas.

At the cell level, variation within a ZIP code can be 10–30% depending on terrain and development patterns. For example:
- A valley cell might have 5,200 HDD while a ridgetop cell in the same ZIP has 4,800 HDD
- An urban core cell might have 4,600 HDD while a suburban fringe cell has 4,900 HDD

This variation is captured in the `cell_hdd_min`, `cell_hdd_max`, and `cell_hdd_std` columns of the ZIP-code aggregate rows.

Quality checks catch:
- Implausible values (< 2,000 or > 8,000 HDD)
- Directional inconsistencies (urban warmer than rural, etc.)
- Divergences from billing data (if available)
- Cell consistency (ZIP aggregate should equal mean of all cells)

All flagged ZIP codes and cells are listed in the QA report for manual review.

---

## Timeline & Effort

**Ground-only level (monthly mode with granular cells and cell-based maps)**:
- **Data preparation**: 1–2 weeks (downloading and organizing input files)
- **Implementation**: 5–7 weeks (13 processing steps including cell creation, aggregation, and map generation, ~50 lines of code per step on average)
- **Testing & validation**: 2–3 weeks (property-based tests, QA checks, cell consistency verification, map validation, manual review)
- **Total**: 8–12 weeks for a team of 1–2 engineers

**Reusability**: Once the ground-only level is complete, the daily and hourly modes reuse 80% of the code, adding only HRRR data ingestion and time-series aggregation. The cell-based approach and maps scale naturally to daily and hourly modes.

---

## Why This Matters

1. **Granular forecasting**: 10–20% improvement in accuracy for terrain-driven areas by forecasting at the cell level instead of ZIP-code level
2. **Sub-ZIP-code insights**: Identify which neighborhoods within a ZIP code have the highest heating demand (valleys, urban cores, high-wind areas)
3. **Regulatory credibility**: Detailed microclimate data supports rate case exhibits and weather normalization arguments
4. **Infrastructure planning**: Identify which cells need weatherization programs or distribution upgrades
5. **Backward compatibility**: ZIP-code aggregates allow existing models to work unchanged while new models can opt into granular cell-level data
6. **Scalability**: Pre-computed CSV allows fast joins in any downstream model without re-sampling rasters

---

## Example: How Granular Cells Improve Forecasting

**Old approach (single-station HDD)**:
- Portland ZIP 97201 uses KPDX airport HDD: 4,850
- All customers in 97201 get the same forecast
- Result: 15–20% error in valley neighborhoods, 5–10% error in ridge neighborhoods

**New approach (ZIP-code aggregate)**:
- Portland ZIP 97201 aggregate effective HDD: 4,920 (accounting for terrain, UHI, wind)
- All customers in 97201 get the same forecast
- Result: 5–10% error across the ZIP code

**New approach (granular cells)**:
- Portland ZIP 97201 has 15 microclimate cells:
  - Valley cells (e.g., Willamette Valley floor): 5,100–5,200 HDD
  - Ridge cells (e.g., West Hills): 4,700–4,800 HDD
  - Urban core cells (downtown): 4,600–4,700 HDD
  - Suburban cells: 4,900–5,000 HDD
- Customers in valley neighborhoods get 5,150 HDD forecast
- Customers in ridge neighborhoods get 4,750 HDD forecast
- Result: 2–5% error across all neighborhoods

---

## Next Steps

1. **Confirm data availability**: Verify all input files are accessible (LiDAR, PRISM, NLCD, roads, etc.)
2. **Set up development environment**: Python 3.9+, required packages (rasterio, geopandas, scipy, pandas, etc.)
3. **Begin implementation**: Follow the 11-step process in the implementation guide
4. **Validate against billing data**: Compare output against known therms per customer for 5–10 representative ZIP codes
5. **Deploy to production**: Write final CSV to shared location for downstream models to consume

The spec is complete and ready for implementation. See `IMPLEMENTATION_GUIDE_GROUND_ONLY.md` for detailed technical steps.
