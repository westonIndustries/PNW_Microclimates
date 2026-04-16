# Quick Start Guide

## One-Minute Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Download all data
python -m src.pipeline data download-all --region region_1

# Run the pipeline
python -m src.pipeline run --region region_1 --mode normals
```

## Common Commands

### Data Management

```bash
# Download everything
python -m src.pipeline data download-all

# Download specific source
python -m src.pipeline data lidar
python -m src.pipeline data prism
python -m src.pipeline data nlcd

# Validate data
python -m src.pipeline data validate
```

### Run Pipeline

```bash
# Normals mode (30-year climate normals)
python -m src.pipeline run --region region_1 --mode normals

# Daily mode (specific date range)
python -m src.pipeline run --region region_1 --mode daily --start-date 2024-01-01 --end-date 2024-01-31

# Hourly mode (per-hour data)
python -m src.pipeline run --region region_1 --mode hourly --month 2024-01

# All modes together
python -m src.pipeline run --region region_1 --mode both --start-date 2024-01-01 --end-date 2024-01-31

# All regions
python -m src.pipeline run --mode normals --all-regions
```

### Debugging

```bash
# Verbose output
python -m src.pipeline run --region region_1 --mode normals --verbose

# Dry run (no execution)
python -m src.pipeline run --region region_1 --mode normals --dry-run

# Help
python -m src.pipeline --help
python -m src.pipeline run --help
python -m src.pipeline data --help
```

## Output Locations

- **Normals mode**: `output/runs/region_1__normal__TIMESTAMP/`
- **Daily mode**: `output/microclimate/daily_region_1_*.parquet`
- **Hourly mode**: `output/microclimate/hourly_region_1_*.parquet`
- **Data files**: `data/` directory

## Next Steps

1. Read `CLI_GUIDE.md` for detailed command reference
2. Read `data/DATA_SOURCES.md` for data source information
3. Check `.kiro/specs/microclimate-engine/design.md` for technical details
