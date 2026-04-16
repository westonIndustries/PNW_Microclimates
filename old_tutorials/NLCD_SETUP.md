# NLCD Imperviousness Downloader Setup Guide

The NLCD imperviousness downloader has been updated to use PyGeoHydro for automated downloads from MRLC GeoServer.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This includes:
- `pygeohydro>=0.16.0` - MRLC GeoServer access
- `rasterio>=1.3` - GeoTIFF handling
- `shapely>=2.0` - Geometry handling

### 2. Download NLCD Data

```bash
python -m src.pipeline data nlcd --region region_1
```

## What Gets Downloaded

- **Source:** MRLC (Multi-Resolution Land Characteristics) GeoServer
- **Dataset:** NLCD 2021 Imperviousness
- **Resolution:** 30 meters
- **Coverage:** Oregon and Washington
- **Format:** GeoTIFF
- **CRS:** WGS84 (EPSG:4326)
- **Output:** `data/nlcd/nlcd_2021_impervious.tif`
- **Cost:** Free (no API key required)

## Features

✅ **Automated:** No manual downloads needed
✅ **Cached:** Won't re-download same data
✅ **Fast:** Uses MRLC GeoServer
✅ **Reliable:** USGS infrastructure
✅ **Free:** No cost, no authentication required
✅ **Verified:** Automatic format validation

## Usage Examples

### Download for region_1
```bash
python -m src.pipeline data nlcd --region region_1
```

### Force re-download
```bash
python -m src.pipeline data nlcd --region region_1 --force-redownload
```

### Dry run (see what would happen)
```bash
python -m src.pipeline data nlcd --region region_1 --dry-run
```

### Verbose output
```bash
python -m src.pipeline data nlcd --region region_1 --verbose
```

## Troubleshooting

### "pygeohydro not installed"

**Solution:** Install it:
```bash
pip install pygeohydro
```

### "Unknown region: region_1"

**Solution:** Check available regions in `scripts/data_sources/nlcd_impervious.py`

Currently supported:
- `region_1` - Oregon and Washington

### Download fails with connection error

**Possible causes:**
1. No internet connection
2. MRLC GeoServer temporarily unavailable
3. Request too large (try smaller region)

**Solution:**
- Check internet connection
- Try again later
- Check https://www.mrlc.gov status
- Download manually if needed

### Memory error during download

**Cause:** Request is too large for available memory

**Solution:**
- Divide region into smaller areas
- Increase available memory
- Use lower resolution (if available)

## Data Specifications

### NLCD 2021 Imperviousness
- **Spatial Resolution:** 30 meters
- **Data Type:** Percent imperviousness (0-100)
- **Vertical Datum:** N/A (raster data)
- **Horizontal Datum:** WGS84
- **Coverage:** Entire United States
- **Licensing:** Public domain (no restrictions)
- **Update Frequency:** Every 2-3 years

### Data Interpretation
- **0:** No impervious surface
- **1-100:** Percent of pixel covered by impervious surface
- **NoData:** Areas outside coverage or water bodies

## Complete Workflow

```bash
# 1. Download NLCD imperviousness
python -m src.pipeline data nlcd --region region_1

# 2. Download other data sources
python -m src.pipeline data download-all --region region_1

# 3. Validate all data
python -m src.pipeline data validate

# 4. Run pipeline
python -m src.pipeline run --region region_1 --mode normals
```

## PyGeoHydro Features

PyGeoHydro provides:
- Access to NLCD imperviousness, land cover, and canopy data
- Automatic domain decomposition for large requests
- Resampling on server side
- Support for multiple years
- Statistics computation

## Next Steps

1. Install dependencies: `pip install -r requirements.txt`
2. Run: `python -m src.pipeline data nlcd --region region_1`
3. Check output at: `data/nlcd/nlcd_2021_impervious.tif`

## References

- MRLC: https://www.mrlc.gov
- PyGeoHydro: https://pygeohydro.readthedocs.io/
- NLCD 2021: https://www.usgs.gov/programs/VHP/NLCD_2021_Release
- NLCD Imperviousness: https://www.mrlc.gov/data/type/urban-imperviousness
