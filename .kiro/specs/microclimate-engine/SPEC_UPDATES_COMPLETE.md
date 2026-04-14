# Spec Updates Complete

## Summary

All three spec documents have been successfully updated to reflect the cell-based microclimate architecture:

### 1. **requirements.md** ✅
- Updated introduction to describe sub-ZIP-code granularity with microclimate cells
- Added glossary terms: `microclimate_cell`, `cell_id`
- Added 3 new requirements (11, 12, 13) for:
  - Granular Microclimate Cells (Requirement 11)
  - ZIP-Code-Level Aggregates (Requirement 12)
  - Interactive Cell-Based Maps (Requirement 13)
- All subsequent requirements renumbered (+3, now 26 total)
- Includes detailed acceptance criteria for cell-level and ZIP-level outputs

### 2. **design.md** ✅
- Updated module structure to include new processors:
  - `create_cells.py` — divide ZIP codes into 500m × 500m cells
  - `combine_corrections_cells.py` — compute cell-level effective_hdd
  - `aggregate_cells_to_zip.py` — aggregate cells to ZIP level
  - `write_maps.py` — generate interactive Leaflet maps showing cells
- Updated normals mode pipeline (now 14 steps instead of 11):
  - Step 9: create_cells
  - Step 10: combine_corrections_cells
  - Step 11: aggregate_cells_to_zip
  - Step 12: weather adjustment
  - Step 13: write_terrain_attributes
  - Step 14: write_maps
- Updated output schema to include:
  - `cell_id` — unique cell identifier within ZIP code
  - `cell_type` — cell classification (urban, suburban, rural, valley, ridge, gorge)
  - `cell_area_sqm` — area of the microclimate cell
  - `num_cells`, `cell_hdd_min`, `cell_hdd_max`, `cell_hdd_std` — variation statistics
  - Updated `microclimate_id` format to include cell identifiers

### 3. **tasks.md** ✅
- **Renumbered all tasks sequentially (1-17)** — eliminated gaps like 3.5, 3.6, F1, etc.
- Task structure now:
  - Task 1: Project Setup and Configuration
  - Task 2: Static Data Loaders
  - Task 3: Static Processors (Terrain, Thermal, Wind, Traffic)
  - Task 4: Granular Microclimate Cells
  - Task 5: ZIP-Code Aggregates
  - Task 6: Region Boundary and Reference Data Generation
  - Task 7: Surface Property Mask and Physics Engine
  - Task 8: Monthly — Combine Corrections and Output
  - Task 9: Monthly — Validation and QA
  - Task 10: Monthly — Maps and Visualization
  - Task 11: Monthly — Future Enhancements (Optional)
  - Task 12: Daily — HRRR Integration and Bias Correction
  - Task 13: Daily — Altitude-Level Microclimate Profiles
  - Task 14: Daily — Aviation Safety Cube
  - Task 15: Hourly — Per-Hour Processing Pipeline
  - Task 16: Real-Time — Data Daemon (Optional)
  - Task 17: Pipeline Orchestrator and CLI

## Key Architecture Changes

### Cell-Based Output Structure
- **Cell-level rows**: One row per cell per ZIP code with `microclimate_id = {region}_{zip}_{station}_cell_{cell_id}`
- **ZIP-code aggregate rows**: One row per ZIP code with `microclimate_id = {region}_{zip}_{station}_aggregate`
- Each cell gets its own `effective_hdd` calculated from the mean of 1-meter grid cells within that cell
- ZIP-code aggregates include variation statistics: min, max, std of cell values

### Cell-Based Maps
- Interactive Leaflet HTML maps showing cells at neighborhood scale (not just ZIP codes)
- Multiple visualization layers:
  - Cell-level effective HDD choropleth
  - Terrain position layer
  - UHI effect layer
  - Wind infiltration layer
  - Traffic heat layer
- Layer control panel to toggle between views
- Cell info popup with detailed attributes
- Zoom and pan functionality

### Pipeline Steps
- Normals mode now includes cell creation and aggregation steps
- All terrain corrections applied at cell level, then aggregated to ZIP level
- Maps generated showing cell-level variation within each ZIP code

## Files Updated
- `.kiro/specs/microclimate-engine/requirements.md`
- `.kiro/specs/microclimate-engine/design.md`
- `.kiro/specs/microclimate-engine/tasks.md`

## Next Steps
The spec is now complete and ready for implementation. Users can:
1. Review the updated requirements, design, and tasks
2. Begin implementing tasks sequentially (Tasks 1-17)
3. Use the cell-based architecture to support granular forecasting at neighborhood scale
