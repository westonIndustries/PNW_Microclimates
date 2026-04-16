# HRRR Data Cache

This directory contains cached HRRR (High-Resolution Rapid Refresh) GRIB2 analysis files downloaded from AWS S3 or Google Cloud Storage.

## Cache Structure

```
data/hrrr/
├── manifest.csv                    # Download manifest tracking all cached files
├── YYYY/
│   ├── MM/
│   │   ├── DD/
│   │   │   ├── hrrr.tYYYYMMDDHHf00.grib2
│   │   │   ├── hrrr.tYYYYMMDDHHf00.grib2
│   │   │   └── ...
│   │   └── ...
│   └── ...
└── ...
```

Each GRIB2 file is approximately 50–100 MB and contains a single HRRR analysis (f00 forecast hour = analysis) for one hour.

## Manifest Schema

The `manifest.csv` file tracks all cached HRRR files with the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `datetime_utc` | string | ISO 8601 datetime (YYYY-MM-DDTHH:00:00) of the HRRR analysis |
| `status` | string | Download status: `cached`, `downloaded`, or `missing` |
| `file_size_bytes` | int | Size of the GRIB2 file in bytes (0 if missing) |
| `source_url` | string | Full S3 or GCS URL where the file was downloaded from |

Example:
```csv
datetime_utc,status,file_size_bytes,source_url
2024-01-15T00:00:00,cached,75000000,s3://noaa-hrrr-bdp-pds/hrrr.20240115/conus/hrrr.t20240115f00.grib2
2024-01-15T01:00:00,cached,76000000,s3://noaa-hrrr-bdp-pds/hrrr.20240115/conus/hrrr.t20240115f01.grib2
2024-01-15T02:00:00,missing,0,s3://noaa-hrrr-bdp-pds/hrrr.20240115/conus/hrrr.t20240115f02.grib2
```

## Storage Estimates

- **Per hour**: ~75 MB (GRIB2 file)
- **Per day**: ~1.8 GB (24 hours)
- **Per month**: ~54 GB (30 days)
- **Per year**: ~650 GB (365 days)

For a typical daily mode run covering 1 month across Oregon and Washington, expect:
- Download time: 2–4 hours (depending on network speed)
- Disk space: ~54 GB
- Processing time: 1–2 hours (bias correction, wind profile extraction, daily combine)

## Data Sources

### AWS S3 (Primary)

- **Bucket**: `s3://noaa-hrrr-bdp-pds/`
- **Access**: Anonymous (unsigned) access
- **Structure**: `hrrr.YYYYMMDD/conus/hrrr.tYYYYMMDDHHf00.grib2`
- **Availability**: 2014-07-30 to present
- **Region**: CONUS (Continental US)

Example S3 URL:
```
s3://noaa-hrrr-bdp-pds/hrrr.20240115/conus/hrrr.t20240115f00.grib2
```

### Google Cloud Storage (Alternative)

- **Bucket**: `gs://noaa-hrrr-bdp-pds/`
- **Access**: Anonymous access (requires `gcsfs` library)
- **Structure**: Same as S3
- **Availability**: Same as S3

Example GCS URL:
```
gs://noaa-hrrr-bdp-pds/hrrr.20240115/conus/hrrr.t20240115f00.grib2
```

## Manual Download Instructions

If you need to manually download HRRR files (e.g., for offline processing or troubleshooting):

### Using AWS CLI

```bash
# Install AWS CLI
pip install awscli

# Download a single file
aws s3 cp s3://noaa-hrrr-bdp-pds/hrrr.20240115/conus/hrrr.t20240115f00.grib2 \
  data/hrrr/2024/01/15/hrrr.t20240115f00.grib2 \
  --no-sign-request

# Download all files for a day
aws s3 sync s3://noaa-hrrr-bdp-pds/hrrr.20240115/conus/ \
  data/hrrr/2024/01/15/ \
  --no-sign-request \
  --exclude "*" \
  --include "hrrr.t20240115*f00.grib2"
```

### Using gsutil (Google Cloud)

```bash
# Install Google Cloud SDK
pip install google-cloud-storage

# Download a single file
gsutil cp gs://noaa-hrrr-bdp-pds/hrrr.20240115/conus/hrrr.t20240115f00.grib2 \
  data/hrrr/2024/01/15/hrrr.t20240115f00.grib2

# Download all files for a day
gsutil -m cp gs://noaa-hrrr-bdp-pds/hrrr.20240115/conus/hrrr.t20240115*f00.grib2 \
  data/hrrr/2024/01/15/
```

### Using Python

```python
from src.loaders.load_hrrr import HRRRLoader

loader = HRRRLoader()
loader.download_hrrr_range(
    start_date="2024-01-15",
    end_date="2024-01-31",
    source="s3",  # or "gcs"
    no_confirm=False
)
```

## GRIB2 File Contents

Each HRRR GRIB2 file contains the following variables (not exhaustive):

### Surface Variables (2 m AGL)
- **TMP:2 m above ground** — 2 m temperature (K)
- **UGRD:10 m above ground** — 10 m U-wind component (m/s)
- **VGRD:10 m above ground** — 10 m V-wind component (m/s)
- **PRES:surface** — Surface pressure (Pa)
- **RH:2 m above ground** — 2 m relative humidity (%)

### Pressure-Level Variables (1000–500 mb)
- **TMP:isobaricInhPa** — Temperature at pressure levels (K)
- **UGRD:isobaricInhPa** — U-wind at pressure levels (m/s)
- **VGRD:isobaricInhPa** — V-wind at pressure levels (m/s)
- **HGT:isobaricInhPa** — Geopotential height at pressure levels (m)

### Other Variables
- **APCP:surface** — Accumulated precipitation (kg/m²)
- **DSWRF:surface** — Downward shortwave radiation flux (W/m²)
- **DLWRF:surface** — Downward longwave radiation flux (W/m²)

## Reading GRIB2 Files

HRRR GRIB2 files can be read using the `cfgrib` engine in xarray:

```python
import xarray as xr

# Open a GRIB2 file
ds = xr.open_dataset("data/hrrr/2024/01/15/hrrr.t20240115f00.grib2", engine="cfgrib")

# List available variables
print(ds.data_vars)

# Extract 2m temperature
temp_2m = ds["TMP_2maboveground"]  # Shape: (y, x)

# Extract pressure-level wind
u_wind = ds["UGRD_isobaricInhPa"]  # Shape: (isobaricInhPa, y, x)
```

## Climatology Computation

For bias correction, the pipeline computes HRRR climatology (multi-year mean) for each month:

```python
from src.loaders.load_hrrr import HRRRLoader

loader = HRRRLoader()

# Compute climatology for January (requires ≥3 years of cached data)
jan_climatology = loader.get_hrrr_climatology(month=1, min_years=3)
```

The climatology is computed from all cached HRRR files for the target month across all available years. If fewer than 3 years are cached, a warning is logged and the available data is used.

## Troubleshooting

### Download Failures

If downloads fail with HTTP 404 errors:
1. Verify the date is within HRRR availability (2014-07-30 to present)
2. Check your internet connection
3. Try the alternative source (S3 vs. GCS)
4. Check the manifest CSV to see which hours are missing

### GRIB2 Reading Errors

If you get errors reading GRIB2 files:
1. Ensure `cfgrib` is installed: `pip install cfgrib`
2. Ensure `eccodes` system library is installed (required by cfgrib)
3. Try opening the file with `xarray.open_dataset(..., engine="cfgrib", backend_kwargs={"filter_by_keys": {"typeOfLevel": "surface"}})`

### Disk Space Issues

If you're running low on disk space:
1. Delete old cached files: `rm -rf data/hrrr/2020/` (for example)
2. Update the manifest: `python -c "from src.loaders.load_hrrr import HRRRLoader; HRRRLoader()._init_manifest()"`
3. Consider using a separate external drive for the cache

## References

- [NOAA HRRR Documentation](https://www.ncei.noaa.gov/products/high-resolution-rapid-refresh)
- [AWS HRRR Archive](https://registry.opendata.aws/noaa-hrrr-pds/)
- [Google Cloud HRRR Archive](https://console.cloud.google.com/storage/browser/noaa-hrrr-bdp-pds)
- [cfgrib Documentation](https://github.com/ecmwf/cfgrib)
