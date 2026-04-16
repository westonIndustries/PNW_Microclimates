# Migration Guide: Old CLI → New CLI

## Overview

The microclimate engine CLI has been refactored to use a subcommand structure. This guide helps you migrate from the old syntax to the new syntax.

## Command Mapping

### Pipeline Execution

| Old Command | New Command |
|-------------|-------------|
| `python -m src.pipeline --region region_1 --mode normals` | `python -m src.pipeline run --region region_1 --mode normals` |
| `python -m src.pipeline --region region_1 --mode daily --start-date 2024-01-01 --end-date 2024-01-31` | `python -m src.pipeline run --region region_1 --mode daily --start-date 2024-01-01 --end-date 2024-01-31` |
| `python -m src.pipeline --region region_1 --mode hourly --month 2024-01` | `python -m src.pipeline run --region region_1 --mode hourly --month 2024-01` |
| `python -m src.pipeline --region region_1 --mode both --start-date 2024-01-01 --end-date 2024-01-31` | `python -m src.pipeline run --region region_1 --mode both --start-date 2024-01-01 --end-date 2024-01-31` |
| `python -m src.pipeline --all-regions --mode normals` | `python -m src.pipeline run --mode normals --all-regions` |

### Data Management (NEW)

These commands are new and were previously not available through the main CLI:

```bash
# Download all data
python -m src.pipeline data download-all --region region_1

# Download specific source
python -m src.pipeline data lidar --region region_1
python -m src.pipeline data prism
python -m src.pipeline data nlcd
python -m src.pipeline data landsat --region region_1
python -m src.pipeline data mesowest
python -m src.pipeline data nrel-wind --region region_1
python -m src.pipeline data roads
python -m src.pipeline data boundaries
python -m src.pipeline data noaa-stations --region region_1

# Validate downloaded data
python -m src.pipeline data validate
```

## Option Changes

All options remain the same, but they now come after the subcommand:

### Old Syntax
```bash
python -m src.pipeline --region region_1 --mode normals --verbose --dry-run
```

### New Syntax
```bash
python -m src.pipeline run --region region_1 --mode normals --verbose --dry-run
```

## Common Patterns

### Running Normals Mode

**Old:**
```bash
python -m src.pipeline --region region_1 --mode normals
```

**New:**
```bash
python -m src.pipeline run --region region_1 --mode normals
```

### Running Daily Mode

**Old:**
```bash
python -m src.pipeline --region region_1 --mode daily --start-date 2024-01-01 --end-date 2024-01-31
```

**New:**
```bash
python -m src.pipeline run --region region_1 --mode daily --start-date 2024-01-01 --end-date 2024-01-31
```

### Running All Regions

**Old:**
```bash
python -m src.pipeline --all-regions --mode normals
```

**New:**
```bash
python -m src.pipeline run --mode normals --all-regions
```

### Verbose Output

**Old:**
```bash
python -m src.pipeline --region region_1 --mode normals --verbose
```

**New:**
```bash
python -m src.pipeline run --region region_1 --mode normals --verbose
```

### Dry Run

**Old:**
```bash
python -m src.pipeline --region region_1 --mode normals --dry-run
```

**New:**
```bash
python -m src.pipeline run --region region_1 --mode normals --dry-run
```

## Scripts and Automation

If you have scripts that call the old CLI, update them as follows:

### Bash Script Example

**Old:**
```bash
#!/bin/bash
python -m src.pipeline --region region_1 --mode normals
python -m src.pipeline --region region_1 --mode daily --month 2024-01
```

**New:**
```bash
#!/bin/bash
python -m src.pipeline run --region region_1 --mode normals
python -m src.pipeline run --region region_1 --mode daily --month 2024-01
```

### Python Script Example

**Old:**
```python
import subprocess

result = subprocess.run([
    "python", "-m", "src.pipeline",
    "--region", "region_1",
    "--mode", "normals"
])
```

**New:**
```python
import subprocess

result = subprocess.run([
    "python", "-m", "src.pipeline",
    "run",
    "--region", "region_1",
    "--mode", "normals"
])
```

## CI/CD Updates

If you use CI/CD pipelines, update your configuration files:

### GitHub Actions Example

**Old:**
```yaml
- name: Run microclimate pipeline
  run: python -m src.pipeline --region region_1 --mode normals
```

**New:**
```yaml
- name: Run microclimate pipeline
  run: python -m src.pipeline run --region region_1 --mode normals
```

### GitLab CI Example

**Old:**
```yaml
run_pipeline:
  script:
    - python -m src.pipeline --region region_1 --mode normals
```

**New:**
```yaml
run_pipeline:
  script:
    - python -m src.pipeline run --region region_1 --mode normals
```

## Help and Documentation

Get help for the new CLI:

```bash
# Main help
python -m src.pipeline --help

# Run command help
python -m src.pipeline run --help

# Data command help
python -m src.pipeline data --help
```

## Troubleshooting

### "unrecognized arguments" Error

If you get an error like:
```
error: unrecognized arguments: --region
```

You're likely using the old syntax. Add the `run` subcommand:

```bash
# Wrong
python -m src.pipeline --region region_1 --mode normals

# Correct
python -m src.pipeline run --region region_1 --mode normals
```

### "invalid choice" Error

If you get an error like:
```
error: invalid choice: 'normals' (choose from 'run', 'data')
```

You're missing the subcommand. The mode should come after `run`:

```bash
# Wrong
python -m src.pipeline --mode normals

# Correct
python -m src.pipeline run --mode normals
```

## New Features

The refactored CLI also enables new features:

### Download Data Through CLI

```bash
# Download all data
python -m src.pipeline data download-all --region region_1

# Download specific source
python -m src.pipeline data lidar --region region_1
```

### Validate Data

```bash
# Validate all downloaded files
python -m src.pipeline data validate
```

### Batch Data Download

```bash
# Download for all regions
python -m src.pipeline data download-all --all-regions
```

## Summary

The key change is adding the `run` subcommand before your existing options:

```bash
# Add "run" here
python -m src.pipeline run --region region_1 --mode normals
                      ^^^
```

For data management, use the new `data` subcommand:

```bash
python -m src.pipeline data download-all --region region_1
                      ^^^^
```

See `CLI_GUIDE.md` for complete documentation.
