# LiDAR Downloader Setup Guide

The LiDAR downloader has been updated to use the OpenTopography API for automated downloads.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This includes:
- `bmi-topography>=0.9.0` - OpenTopography API wrapper
- `rasterio>=1.3` - GeoTIFF handling

### 2. Get Free API Key

1. Visit https://opentopography.org
2. Create an account (takes 2 minutes)
3. Go to "My Account" → Request API Key
4. Copy your API key

### 3. Set Environment Variable

```bash
# Linux/Mac
export OPENTOPOGRAPHY_API_KEY=your_api_key_here

# Windows PowerShell
$env:OPENTOPOGRAPHY_API_KEY="your_api_key_here"

# Windows CMD
set OPENTOPOGRAPHY_API_KEY=your_api_key_here
```

### 4. Download LiDAR Data

```bash
python -m src.pipeline data lidar --region region_1
```

## What Gets Downloaded

- **Source:** USGS 3D Elevation Program (3DEP)
- **Resolution:** 1 meter
- **Coverage:** Oregon and Washington
- **Format:** GeoTIFF
- **CRS:** WGS84 (EPSG:4326)
- **Output:** `data/lidar/dem_1m.tif`

## Features

✅ **Automated:** No manual downloads needed
✅ **Cached:** Won't re-download same data
✅ **Fast:** Uses OpenTopography's optimized servers
✅ **Reliable:** NSF-funded infrastructure
✅ **Free:** No cost for academic use
✅ **Verified:** Automatic format validation

## Usage Examples

### Download for region_1
```bash
python -m src.pipeline data lidar --region region_1
```

### Force re-download
```bash
python -m src.pipeline data lidar --region region_1 --force-redownload
```

### Dry run (see what would happen)
```bash
python -m src.pipeline data lidar --region region_1 --dry-run
```

### Verbose output
```bash
python -m src.pipeline data lidar --region region_1 --verbose
```

## Troubleshooting

### "OPENTOPOGRAPHY_API_KEY environment variable not set"

**Solution:** Set your API key:
```bash
export OPENTOPOGRAPHY_API_KEY=your_key_here
```

### "bmi-topography not installed"

**Solution:** Install it:
```bash
pip install bmi-topography
```

### "Unknown region: region_1"

**Solution:** Check available regions in `scripts/data_sources/lidar_dem.py`

Currently supported:
- `region_1` - Oregon and Washington

### Download fails with HTTP error

**Possible causes:**
1. Invalid API key
2. No internet connection
3. Request too large (max 250 km² for 1m DEM)
4. OpenTopography service temporarily down

**Solution:**
- Verify API key is correct
- Check internet connection
- Try again later
- Check https://opentopography.org status

## Data Specifications

### USGS 3DEP 1m DEM
- **Spatial Resolution:** 1 meter
- **Vertical Accuracy:** ±1.0 meter (90% confidence)
- **Vertical Datum:** NAVD88
- **Horizontal Datum:** WGS84
- **Coverage:** Entire United States
- **Data Type:** Float32
- **Licensing:** Public domain (no restrictions)

### Request Limits
- **1m DEM:** 250 km² per request (academic)
- **Rate Limit:** 200 requests/24 hours (academic)

## Complete Workflow

```bash
# 1. Set API key
export OPENTOPOGRAPHY_API_KEY=your_key_here

# 2. Download LiDAR data
python -m src.pipeline data lidar --region region_1

# 3. Download other data sources
python -m src.pipeline data download-all --region region_1

# 4. Validate all data
python -m src.pipeline data validate

# 5. Run pipeline
python -m src.pipeline run --region region_1 --mode normals
```

## Next Steps

1. Get API key from https://opentopography.org
2. Set `OPENTOPOGRAPHY_API_KEY` environment variable
3. Run: `python -m src.pipeline data lidar --region region_1`
4. Check output at: `data/lidar/dem_1m.tif`

## References

- OpenTopography: https://opentopography.org
- bmi-topography: https://bmi-topography.readthedocs.io/
- USGS 3DEP: https://www.usgs.gov/3dep
- API Documentation: https://opentopography.org/developers
