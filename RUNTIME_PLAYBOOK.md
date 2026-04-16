# Microclimate Engine Runtime Playbook

Complete guide for installation, setup, data acquisition, and pipeline execution.

---

## Table of Contents

1. [Quick Start (5 minutes)](#quick-start-5-minutes)
2. [Installation](#installation)
3. [Troubleshooting](#troubleshooting)
4. [Data Acquisition](#data-acquisition)
5. [Pipeline Execution](#pipeline-execution)
6. [CLI Reference](#cli-reference)
7. [Migration Guide](#migration-guide)

---

## Quick Start (5 minutes)

### For Windows Users

**Step 1: Get Anaconda Prompt**
- Press `Win + S` (search)
- Type: `Anaconda Prompt`
- Click "Anaconda Prompt (miniconda3)"

**Step 2: Create Environment**
```bash
conda create -n microclimate python=3.10 -c conda-forge
conda activate microclimate
```

**Step 3: Install Packages**
```bash
conda install -c conda-forge geopandas rasterio shapely
pip install -r requirements-minimal.txt
```

**Step 4: Get API Key**
- Visit: https://opentopography.org
- Create account → Request API key
- Set: `$env:OPENTOPOGRAPHY_API_KEY="your_key"`

**Step 5: Download Data**
```bash
python -m src.pipeline data lidar --region region_1
python -m src.pipeline data nlcd --region region_1
```

**Step 6: Run Pipeline**
```bash
python -m src.pipeline run --region region_1 --mode normals
```

✅ Done!

### For Linux/Mac Users

```bash
# Create environment
conda create -n microclimate python=3.10 -c conda-forge
conda activate microclimate

# Install packages
pip install -r requirements.txt

# Get API key
export OPENTOPOGRAPHY_API_KEY="your_key"

# Download data
python -m src.pipeline data lidar --region region_1
python -m src.pipeline data nlcd --region region_1

# Run pipeline
python -m src.pipeline run --region region_1 --mode normals
```

---

## Installation

### Option 1: Conda (Recommended for Windows)

**Step 1: Download Conda**

- **Miniconda (Recommended - 150 MB):**
  - Go to: https://docs.conda.io/projects/miniconda/en/latest/
  - Download "Miniconda3 Windows 64-bit"

- **Anaconda (Full - 600 MB):**
  - Go to: https://www.anaconda.com/download
  - Download "Anaconda3 Windows 64-bit"

**Step 2: Install**

1. Run installer
2. **Check:** "Add Miniconda3 to my PATH"
3. **Check:** "Register Miniconda3 as my default Python"
4. Click "Install"
5. Restart computer

**Step 3: Verify**

Open Anaconda Prompt and run:
```bash
conda --version
```

**Step 4: Create Environment**

```bash
conda create -n microclimate python=3.10 -c conda-forge
conda activate microclimate
```

**Step 5: Install Geospatial Packages**

```bash
conda install -c conda-forge geopandas rasterio shapely
```

**Step 6: Install Remaining Packages**

```bash
pip install -r requirements-minimal.txt
```

### Option 2: Pip (Linux/Mac)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### Option 3: Docker

```bash
# Build image
docker build -t microclimate .

# Run container
docker run -it microclimate
```

### Minimal Installation

If you only need LiDAR and NLCD downloads:

```bash
pip install -r requirements-minimal.txt
```

---

## Troubleshooting

### Issue: "conda: The term 'conda' is not recognized"

**Cause:** Conda not in PATH

**Solution 1: Use Anaconda Prompt (Easiest)**
- Press `Win + S`
- Type: `Anaconda Prompt`
- Click "Anaconda Prompt (miniconda3)"

**Solution 2: Add to PATH**
1. Press `Win + X` → "System"
2. Click "Advanced system settings"
3. Click "Environment Variables"
4. Add: `C:\ProgramData\miniconda3\Scripts`
5. Restart PowerShell

**Solution 3: Reinstall Conda**
1. Uninstall from Control Panel
2. Download fresh installer
3. **Check "Add to PATH"** during installation
4. Restart computer

### Issue: "CondaError: Run 'conda init' before 'conda activate'"

**Cause:** Conda not initialized for PowerShell

**Solution:**
```bash
conda init powershell
```
Then close and reopen PowerShell completely.

(Skip if using Anaconda Prompt)

### Issue: "ERROR: Failed to build 'shapely'"

**Cause:** Build tools not installed

**Solution 1: Use Conda (Recommended)**
```bash
conda install -c conda-forge shapely geopandas rasterio
```

**Solution 2: Install Build Tools**
- Download Visual Studio Build Tools: https://visualstudio.microsoft.com/downloads/
- Select "Desktop development with C++"
- Then: `pip install -r requirements.txt`

**Solution 3: Use Minimal Requirements**
```bash
pip install -r requirements-minimal.txt
```

### Issue: "OPENTOPOGRAPHY_API_KEY environment variable not set"

**Cause:** API key not configured

**Solution:**

**Windows PowerShell:**
```bash
$env:OPENTOPOGRAPHY_API_KEY="your_api_key_here"
```

**Windows Command Prompt:**
```bash
set OPENTOPOGRAPHY_API_KEY=your_api_key_here
```

**Linux/Mac:**
```bash
export OPENTOPOGRAPHY_API_KEY="your_api_key_here"
```

**Permanent (Windows):**
1. Press `Win + X` → "System"
2. Click "Advanced system settings"
3. Click "Environment Variables"
4. Add new User variable:
   - Name: `OPENTOPOGRAPHY_API_KEY`
   - Value: `your_api_key_here`
5. Restart PowerShell

### Issue: "FileNotFoundError: LiDAR DEM file not found"

**Cause:** Data not downloaded yet

**Solution:**
```bash
python -m src.pipeline data lidar --region region_1
python -m src.pipeline data nlcd --region region_1
python -m src.pipeline data download-all --region region_1
```

---

## Data Acquisition

### Get API Key (Required for LiDAR)

1. Visit: https://opentopography.org
2. Create account (takes 2 minutes)
3. Go to "My Account" → Request API Key
4. Copy your API key
5. Set environment variable (see Troubleshooting section)

### Download Individual Data Sources

```bash
# LiDAR DEM (1m resolution)
python -m src.pipeline data lidar --region region_1

# NLCD Imperviousness (30m resolution)
python -m src.pipeline data nlcd --region region_1

# PRISM Temperature
python -m src.pipeline data prism

# Other sources
python -m src.pipeline data landsat --region region_1
python -m src.pipeline data mesowest
python -m src.pipeline data nrel-wind --region region_1
python -m src.pipeline data roads
python -m src.pipeline data boundaries
python -m src.pipeline data noaa-stations --region region_1
```

### Download All Data

```bash
python -m src.pipeline data download-all --region region_1
```

### Validate Downloaded Data

```bash
python -m src.pipeline data validate
```

### Data Download Options

```bash
# Force re-download
python -m src.pipeline data lidar --region region_1 --force-redownload

# Dry run (see what would happen)
python -m src.pipeline data lidar --region region_1 --dry-run

# Verbose output
python -m src.pipeline data lidar --region region_1 --verbose

# Custom output directory
python -m src.pipeline data lidar --region region_1 --output-dir /custom/path
```

### Data Sources

| Source | Command | Resolution | Coverage | Cost |
|--------|---------|-----------|----------|------|
| LiDAR DEM | `data lidar` | 1m | OR/WA | Free (API key) |
| NLCD Imperviousness | `data nlcd` | 30m | OR/WA | Free |
| PRISM Temperature | `data prism` | 800m | US | Free |
| Landsat 9 LST | `data landsat` | 100m | OR/WA | Free |
| MesoWest Wind | `data mesowest` | Station | US | Free (API key) |
| NREL Wind | `data nrel-wind` | 2km | OR/WA | Free |
| Road Networks | `data roads` | Vector | OR/WA | Free |
| Boundaries | `data boundaries` | Vector | US | Free |
| NOAA Stations | `data noaa-stations` | Station | US | Free |

---

## Pipeline Execution

### Normals Mode (30-year climate normals)

```bash
python -m src.pipeline run --region region_1 --mode normals
```

Output: `output/runs/region_1__normal__TIMESTAMP/`

### Daily Mode (specific date range)

```bash
python -m src.pipeline run --region region_1 --mode daily --start-date 2024-01-01 --end-date 2024-01-31
```

Output: `output/microclimate/daily_region_1_*.parquet`

### Hourly Mode (per-hour data)

```bash
python -m src.pipeline run --region region_1 --mode hourly --month 2024-01
```

Output: `output/microclimate/hourly_region_1_*.parquet`

### All Modes Together

```bash
python -m src.pipeline run --region region_1 --mode both --start-date 2024-01-01 --end-date 2024-01-31
```

### Batch Processing (All Regions)

```bash
python -m src.pipeline run --mode normals --all-regions
```

### Pipeline Options

```bash
# Weather adjustment
python -m src.pipeline run --region region_1 --mode normals --weather-year 2024

# Aviation safety cube
python -m src.pipeline run --region region_1 --mode daily --safety-cube

# Custom altitude levels
python -m src.pipeline run --region region_1 --mode daily --cube-altitudes 0 500 1000 3000

# Dry run (no execution)
python -m src.pipeline run --region region_1 --mode normals --dry-run

# Verbose logging
python -m src.pipeline run --region region_1 --mode normals --verbose

# Output format
python -m src.pipeline run --region region_1 --mode daily --output-format parquet
```

### Complete Workflow

```bash
# 1. Download all data
python -m src.pipeline data download-all --region region_1

# 2. Validate data
python -m src.pipeline data validate

# 3. Run normals mode
python -m src.pipeline run --region region_1 --mode normals

# 4. Run daily mode
python -m src.pipeline run --region region_1 --mode daily --month 2024-01

# 5. Run all modes
python -m src.pipeline run --region region_1 --mode both --start-date 2024-01-01 --end-date 2024-01-31
```

---

## CLI Reference

### Main Commands

```bash
# Show help
python -m src.pipeline --help

# Run pipeline
python -m src.pipeline run --help

# Data management
python -m src.pipeline data --help
```

### Run Command

```bash
python -m src.pipeline run [OPTIONS]

OPTIONS:
  --region REGION_NAME              Region name (required)
  --mode {normals,daily,hourly,both,realtime}
                                    Operating mode (default: normals)
  --start-date YYYY-MM-DD           Start date for daily/hourly
  --end-date YYYY-MM-DD             End date for daily/hourly
  --month YYYY-MM                   Month shorthand
  --weather-year YEAR               Year for weather adjustment
  --hrrr-source {s3,gcs}            HRRR data source (default: s3)
  --output-format {parquet,csv,both}
                                    Output format (default: parquet)
  --safety-cube                     Build aviation safety cube
  --cube-altitudes ALT1 ALT2 ...    Override altitude levels
  --all-regions                     Run for all regions
  --dry-run                         Print steps without executing
  --verbose                         Enable verbose logging
```

### Data Command

```bash
python -m src.pipeline data SUBCOMMAND [OPTIONS]

SUBCOMMANDS:
  download-all                      Download all data sources
  lidar                             Download LiDAR DEM
  prism                             Download PRISM temperature
  nlcd                              Download NLCD imperviousness
  landsat                           Download Landsat 9 LST
  mesowest                          Download MesoWest wind
  nrel-wind                         Download NREL wind resource
  roads                             Download road networks
  boundaries                        Download boundaries
  noaa-stations                     Download NOAA stations
  validate                          Validate all data

OPTIONS:
  --region REGION_NAME              Region name (default: region_1)
  --output-dir PATH                 Output directory (default: data)
  --force-redownload                Force re-download
  --dry-run                         Print steps without executing
  --verbose                         Enable verbose logging
```

---

## Migration Guide

### Old CLI → New CLI

The CLI has been refactored to use subcommands. Update your scripts:

| Old Command | New Command |
|-------------|-------------|
| `python -m src.pipeline --region region_1 --mode normals` | `python -m src.pipeline run --region region_1 --mode normals` |
| `python -m src.pipeline --region region_1 --mode daily --start-date 2024-01-01 --end-date 2024-01-31` | `python -m src.pipeline run --region region_1 --mode daily --start-date 2024-01-01 --end-date 2024-01-31` |
| `python -m src.pipeline --all-regions --mode normals` | `python -m src.pipeline run --mode normals --all-regions` |

### Key Changes

1. **Add `run` subcommand** before your existing options
2. **Data management** now uses `data` subcommand
3. **All options remain the same** - just add the subcommand

### Example Migration

**Old Script:**
```bash
#!/bin/bash
python -m src.pipeline --region region_1 --mode normals
python -m src.pipeline --region region_1 --mode daily --month 2024-01
```

**New Script:**
```bash
#!/bin/bash
python -m src.pipeline run --region region_1 --mode normals
python -m src.pipeline run --region region_1 --mode daily --month 2024-01
```

---

## Output Locations

### Normals Mode
```
output/runs/region_1__normal__TIMESTAMP/
├── terrain_attributes.csv
├── map_effective_hdd.html
├── map_terrain_position.html
├── map_uhi_effect.html
├── map_wind_infiltration.html
├── map_traffic_heat.html
├── qa_report.html
├── qa_report.md
└── run_manifest.json
```

### Daily Mode
```
output/microclimate/
└── daily_region_1_YYYY-MM-DD_YYYY-MM-DD.parquet
```

### Hourly Mode
```
output/microclimate/
└── hourly_region_1_YYYY-MM-DD_YYYY-MM-DD.parquet
```

### Data Files
```
data/
├── lidar/
│   └── dem_1m.tif
├── nlcd/
│   └── nlcd_2021_impervious.tif
├── prism/
│   └── *.tif
├── landsat/
│   └── *.tif
├── mesowest/
│   └── *.csv
├── nrel/
│   └── *.tif
├── roads/
│   └── *.shp
├── boundaries/
│   └── *.shp
└── noaa/
    └── *.csv
```

---

## Requirements Files

### Full Installation
```bash
pip install -r requirements.txt
```

### Minimal Installation (Windows)
```bash
pip install -r requirements-minimal.txt
```

### Data Acquisition Only
```bash
pip install -r requirements-data.txt
```

---

## Getting Help

### View Help Text
```bash
python -m src.pipeline --help
python -m src.pipeline run --help
python -m src.pipeline data --help
```

### Check Installation
```bash
python -c "import bmi_topography; print('✓ bmi-topography')"
python -c "import pygeohydro; print('✓ pygeohydro')"
python -c "import rasterio; print('✓ rasterio')"
```

### Common Issues

See **Troubleshooting** section above for:
- Conda not found
- Build errors
- API key issues
- Data not found

---

## References

- **OpenTopography:** https://opentopography.org
- **MRLC:** https://www.mrlc.gov
- **USGS 3DEP:** https://www.usgs.gov/3dep
- **Conda:** https://docs.conda.io/
- **PyGeoHydro:** https://pygeohydro.readthedocs.io/
- **bmi-topography:** https://bmi-topography.readthedocs.io/

---

## Summary

✅ **Installation:** Use Conda (Windows) or pip (Linux/Mac)
✅ **Data:** Download with `python -m src.pipeline data`
✅ **Pipeline:** Run with `python -m src.pipeline run`
✅ **Help:** Use `--help` flag for any command

**Quick Start:**
```bash
conda activate microclimate
export OPENTOPOGRAPHY_API_KEY="your_key"
python -m src.pipeline data download-all --region region_1
python -m src.pipeline run --region region_1 --mode normals
```

---

**Last Updated:** 2026-04-16
**Version:** 1.0
