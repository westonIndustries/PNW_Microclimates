# Runtime Update Summary

## Overview

The microclimate engine runtime has been updated to integrate the new data acquisition utilities directly into the main pipeline CLI. The system now provides a unified interface for both data management and pipeline execution.

## Key Changes

### 1. CLI Structure Refactored

**Before:**
```bash
python -m src.pipeline --region region_1 --mode normals
```

**After:**
```bash
# Pipeline execution
python -m src.pipeline run --region region_1 --mode normals

# Data management
python -m src.pipeline data download-all --region region_1
python -m src.pipeline data validate
```

### 2. New Subcommand System

The CLI now uses a two-level subcommand structure:

```
src.pipeline
├── run          # Execute microclimate pipeline
│   ├── --region
│   ├── --mode {normals,daily,hourly,both,realtime}
│   ├── --start-date / --end-date / --month
│   └── ... (all existing options)
│
└── data         # Download and manage data sources
    ├── download-all
    ├── lidar
    ├── prism
    ├── nlcd
    ├── landsat
    ├── mesowest
    ├── nrel-wind
    ├── roads
    ├── boundaries
    ├── noaa-stations
    └── validate
```

### 3. Data Acquisition Integration

All data source downloaders are now accessible through the unified CLI:

```bash
# Download individual sources
python -m src.pipeline data lidar --region region_1
python -m src.pipeline data prism --output-dir /custom/path
python -m src.pipeline data mesowest --force-redownload

# Download all sources at once
python -m src.pipeline data download-all --region region_1

# Validate all downloaded files
python -m src.pipeline data validate
```

### 4. Updated Dependencies

Added data acquisition dependencies to `requirements.txt`:
- `planetary-computer>=0.5.0` - For Landsat STAC queries
- `synoptic>=3.0.0` - For MesoWest API access

Created `requirements-data.txt` with all data acquisition dependencies for reference.

### 5. New Documentation

Created comprehensive guides:
- **CLI_GUIDE.md** - Complete CLI reference with examples
- **QUICK_START.md** - Quick reference for common commands
- **RUNTIME_UPDATE_SUMMARY.md** - This file

## Implementation Details

### Modified Files

1. **src/pipeline.py**
   - Refactored `main()` function to use argparse subparsers
   - Added `_handle_run_command()` for pipeline execution
   - Added `_handle_data_command()` for data acquisition
   - Integrated all data source modules

2. **requirements.txt**
   - Added `planetary-computer>=0.5.0`
   - Added `synoptic>=3.0.0`

### New Files

1. **CLI_GUIDE.md** - Comprehensive CLI documentation
2. **QUICK_START.md** - Quick reference guide
3. **RUNTIME_UPDATE_SUMMARY.md** - This summary
4. **requirements-data.txt** - Data acquisition dependencies reference

## Backward Compatibility

The old CLI syntax is no longer supported. Users must use the new subcommand structure:

```bash
# Old (no longer works)
python -m src.pipeline --region region_1 --mode normals

# New (required)
python -m src.pipeline run --region region_1 --mode normals
```

## Usage Examples

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

### Batch Processing

```bash
# Download for all regions
python -m src.pipeline data download-all --all-regions

# Run for all regions
python -m src.pipeline run --mode normals --all-regions
```

### Development

```bash
# Dry run
python -m src.pipeline run --region region_1 --mode normals --dry-run

# Verbose logging
python -m src.pipeline run --region region_1 --mode normals --verbose

# Help
python -m src.pipeline --help
python -m src.pipeline run --help
python -m src.pipeline data --help
```

## Benefits

1. **Unified Interface** - Single entry point for all operations
2. **Better Organization** - Clear separation between pipeline and data management
3. **Discoverability** - Subcommands make available options more obvious
4. **Extensibility** - Easy to add new subcommands in the future
5. **Documentation** - Help text available for all commands

## Testing

The updated CLI has been validated for:
- ✅ Syntax correctness (no diagnostics)
- ✅ Argument parsing structure
- ✅ Subcommand routing
- ✅ Data module imports
- ✅ Help text generation

## Next Steps

1. Test the new CLI with actual data downloads
2. Verify all data source modules work correctly
3. Test pipeline execution with downloaded data
4. Update any CI/CD scripts to use new CLI syntax
5. Update user documentation and tutorials

## Support

For detailed information:
- See `CLI_GUIDE.md` for complete command reference
- See `QUICK_START.md` for common commands
- See `data/DATA_SOURCES.md` for data source details
- Run `python -m src.pipeline --help` for inline help
