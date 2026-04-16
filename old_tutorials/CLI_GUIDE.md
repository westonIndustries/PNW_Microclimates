# Microclimate Engine CLI Guide

The updated runtime now integrates data acquisition utilities directly into the main pipeline CLI. The new structure uses subcommands for better organization.

## Installation

Install all dependencies including data acquisition tools:

```bash
pip install -r requirements.txt
```

## Usage

### Run Microclimate Pipeline

Run the microclimate modeling pipeline for a specific region:

```bash
# Run normals mode (default)
python -m src.pipeline run --region region_1 --mode normals

# Run daily mode for a date range
python -m src.pipeline run --region region_1 --mode daily --start-date 2024-01-01 --end-date 2024-01-31

# Run hourly mode for a specific month
python -m src.pipeline run --region region_1 --mode hourly --month 2024-01

# Run all modes in sequence
python -m src.pipeline run --region region_1 --mode both --start-date 2024-01-01 --end-date 2024-01-31

# Run for all regions in registry
python -m src.pipeline run --mode normals --all-regions

# Enable verbose logging
python -m src.pipeline run --region region_1 --mode normals --verbose
```

### Download Data

Download input data from public sources:

```bash
# Download all data sources
python -m src.pipeline data download-all --region region_1

# Download specific data source
python -m src.pipeline data lidar --region region_1
python -m src.pipeline data prism
python -m src.pipeline data nlcd
python -m src.pipeline data landsat --region region_1
python -m src.pipeline data mesowest
python -m src.pipeline data nrel-wind --region region_1
python -m src.pipeline data roads
python -m src.pipeline data boundaries
python -m src.pipeline data noaa-stations --region region_1

# Validate all downloaded data
python -m src.pipeline data validate

# Force re-download even if files exist
python -m src.pipeline data download-all --force-redownload

# Specify custom output directory
python -m src.pipeline data download-all --output-dir /path/to/data
```

## Run Command Options

```
--region REGION_NAME          Region name (e.g., region_1) [required]
--mode {normals,daily,hourly,both,realtime}
                              Operating mode (default: normals)
--start-date YYYY-MM-DD       Start date for daily/hourly modes
--end-date YYYY-MM-DD         End date for daily/hourly modes
--month YYYY-MM               Month shorthand for daily/hourly modes
--weather-year YEAR           Year for weather adjustment
--hrrr-source {s3,gcs}        HRRR data source (default: s3)
--output-format {parquet,csv,both}
                              Output format (default: parquet)
--safety-cube                 Build aviation safety cube for daily mode
--cube-altitudes ALT1 ALT2... Override default altitude levels
--dry-run                     Print steps without executing
--all-regions                 Run for all regions in registry
--verbose                     Enable verbose logging
```

## Data Command Options

```
--region REGION_NAME          Region name (default: region_1)
--output-dir PATH             Base output directory (default: data)
--force-redownload            Force re-download even if files exist
--dry-run                     Print steps without executing
--verbose                     Enable verbose logging
```

## Data Sources

The data acquisition system supports the following sources:

| Source | Command | Notes |
|--------|---------|-------|
| LiDAR DEM | `lidar` | 1m resolution from DOGAMI/WA DNR |
| PRISM Temperature | `prism` | 30-year climate normals (800m) |
| NLCD Imperviousness | `nlcd` | 2021 imperviousness (30m) |
| Landsat 9 LST | `landsat` | Collection 2 Level-2 LST scenes |
| MesoWest Wind | `mesowest` | Station wind observations (requires API key) |
| NREL Wind | `nrel-wind` | Wind resource map (80m hub height) |
| Road Networks | `roads` | ODOT/WSDOT shapefiles with AADT |
| Boundaries | `boundaries` | Census TIGER/Line shapefiles |
| NOAA Stations | `noaa-stations` | Station metadata and HDD normals |

Most sources provide manual download instructions due to licensing/authentication requirements. See `data/DATA_SOURCES.md` for detailed information.

## Examples

### Complete Workflow

```bash
# 1. Download all required data
python -m src.pipeline data download-all --region region_1

# 2. Validate downloaded data
python -m src.pipeline data validate

# 3. Run normals mode
python -m src.pipeline run --region region_1 --mode normals

# 4. Run daily mode for a month
python -m src.pipeline run --region region_1 --mode daily --month 2024-01

# 5. Run all modes for a date range
python -m src.pipeline run --region region_1 --mode both --start-date 2024-01-01 --end-date 2024-01-31
```

### Batch Processing

```bash
# Run normals mode for all regions
python -m src.pipeline run --mode normals --all-regions --verbose

# Download data for all regions
python -m src.pipeline data download-all --all-regions
```

### Development

```bash
# Dry run to see what would happen
python -m src.pipeline run --region region_1 --mode normals --dry-run

# Verbose output for debugging
python -m src.pipeline run --region region_1 --mode normals --verbose
```

## Output

### Normals Mode Output

- `output/runs/region_1__normal__TIMESTAMP/`
  - `terrain_attributes.csv` - Cell-level and ZIP-level HDD data
  - `map_effective_hdd.html` - Interactive HDD choropleth map
  - `map_terrain_position.html` - Terrain type map
  - `map_uhi_effect.html` - Urban heat island effect map
  - `map_wind_infiltration.html` - Wind infiltration map
  - `map_traffic_heat.html` - Traffic heat map
  - `qa_report.html` - QA report with statistics
  - `qa_report.md` - QA report in markdown
  - `run_manifest.json` - Run metadata

### Daily Mode Output

- `output/microclimate/daily_region_1_YYYY-MM-DD_YYYY-MM-DD.parquet`
  - Daily effective HDD per ZIP code
  - Multi-altitude wind/temperature profiles
  - Safety cube data (if `--safety-cube` flag used)

### Hourly Mode Output

- `output/microclimate/hourly_region_1_YYYY-MM-DD_YYYY-MM-DD.parquet`
  - Per-hour safety cubes
  - Multi-altitude microclimate profiles
  - 8 altitude levels per hour

## Troubleshooting

### Missing Data Files

If the pipeline fails with "FileNotFoundError", run the data acquisition:

```bash
python -m src.pipeline data download-all --region region_1
```

### Large Downloads

For large data downloads (>10GB), the system will prompt for confirmation. Skip with:

```bash
python -m src.pipeline data download-all --no-confirm
```

### API Keys

Some data sources (e.g., MesoWest) require API keys. Set environment variables:

```bash
export SYNOPTIC_API_TOKEN=your_token_here
python -m src.pipeline data mesowest
```

## Help

Get help for any command:

```bash
python -m src.pipeline --help
python -m src.pipeline run --help
python -m src.pipeline data --help
```
