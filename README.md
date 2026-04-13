# Regional Microclimate Modeling Engine — NW Natural Service Area

## Objective

This project is a Python processing pipeline that generates high-resolution microclimate maps for the NW Natural service territory. It integrates four data layers — terrain (1 m LiDAR DEM), surface character (NLCD imperviousness / asphalt), atmospheric conditions (PRISM temperature normals + MesoWest/NREL wind), and anthropogenic heat (ODOT/WSDOT traffic volumes) — to simulate temperature and wind variations at sub-district scale. The pipeline produces an `effective_hdd` value for every IRP district or Census block group, replacing the single airport-station HDD used in the base forecasting model. All corrections are pre-computed and written to `terrain_attributes.csv`, which the simulation pipeline joins at runtime without re-sampling any rasters.

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
python -m src.pipeline --region portland_metro

# Run all 8 regions sequentially
python -m src.pipeline --all-regions
```

Output is written to `output/microclimate/terrain_attributes.csv` plus an HTML/MD QA report.

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
└── src/
    ├── config.py                    # Constants, file paths, CRS, region registry
    ├── pipeline.py                  # Main orchestrator: run_region(region_name)
    ├── loaders/
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
    │   └── billing_comparison.py
    └── output/
        └── write_terrain_attributes.py
```

**Data inputs** (not included in this repo — see design doc for download sources):

```
Data/terrain/
├── lidar_dem_nwn.tif
├── prism_tmean/          # 12 monthly BIL files
├── landsat9_lst_nwn.tif
├── mesowest_wind/        # per-station CSVs
├── nrel_wind_nwn.tif
├── nlcd_impervious_nwn.tif
├── odot_roads_oregon.shp
├── wsdot_roads_washington.shp
└── odoe_utility_boundary.shp
```

---

## Parent Project

This pipeline is a sub-component of the **NW Natural End-Use Forecasting Model**. See the [parent project README](../README.md) and [MICROCLIMATE_CONVERSION.md](../MICROCLIMATE_CONVERSION.md) for the full geographic hierarchy, district-to-station mapping, and how `effective_hdd` feeds into the simulation pipeline.
