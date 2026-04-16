# Data Sources for Microclimate Pipeline

This document describes all input data files required by the microclimate pipeline, their sources, and how to obtain them.

## Quick Start

To download and validate all data:

```bash
python scripts/download_data.py download-all --region region_1
```

To validate existing data:

```bash
python scripts/download_data.py validate
```

## Data Files

### 1. LiDAR DEM (1m resolution)

**File**: `data/lidar/dem_1m.tif`  
**Format**: GeoTIFF  
**CRS**: EPSG:26910 (NAD83 / UTM Zone 10N)  
**Resolution**: 1 meter  
**Coverage**: Oregon and Washington  
**Vintage**: 2021

**Sources**:
- **Oregon**: [DOGAMI LiDAR](https://www.oregongeology.org/lidar)
- **Washington**: [WA DNR LiDAR](https://www.dnrwa.wa.gov/lidar)

**Download**:
```bash
python scripts/download_data.py lidar --output-dir data/lidar
```

### 2. PRISM Temperature Normals (800m resolution)

**Files**: `data/prism/PRISM_tmean_30yr_normal_800mM{01-12}_01_bil.bil` (12 monthly files)  
**Format**: BIL (Band Interleaved by Line) or GeoTIFF  
**CRS**: EPSG:4326 (WGS84)  
**Resolution**: 800 meters  
**Period**: 1991-2020  
**Coverage**: Continental US

**Source**: [PRISM Climate Group](https://www.prism.oregonstate.edu/)

**Download**:
```bash
python scripts/download_data.py prism --output-dir data/prism
```

### 3. NLCD Imperviousness (30m resolution)

**File**: `data/nlcd/nlcd_2021_impervious_l48_20230405.tif`  
**Format**: GeoTIFF  
**CRS**: EPSG:5070 (NAD83 / Conus Albers Equal Area Conic)  
**Resolution**: 30 meters  
**Year**: 2021  
**Coverage**: Continental US

**Source**: [USGS NLCD 2021 Release](https://www.usgs.gov/programs/VHP/NLCD_2021_Release)

**Download**:
```bash
python scripts/download_data.py nlcd --output-dir data/nlcd
```

### 4. Landsat 9 LST (30m resolution)

**File**: `data/landsat/LC09_L2SP_*_LST_ST.TIF`  
**Format**: GeoTIFF  
**CRS**: EPSG:32610 (UTM Zone 10N) or EPSG:32611 (UTM Zone 11N)  
**Resolution**: 30 meters  
**Collection**: Landsat 9 Collection 2 Level-2  
**Coverage**: Oregon and Washington

**Source**: [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/)

**Requirements**: `pip install pystac-client`

**Download**:
```bash
python scripts/download_data.py landsat --region region_1 --output-dir data/landsat
```

### 5. MesoWest Wind Observations

**File**: `data/mesowest/station_wind_*.csv`  
**Format**: CSV  
**Coverage**: Oregon and Washington stations  
**Period**: Annual aggregates (mean, p90)

**Source**: [SynopticLabs / MesoWest](https://synopticlabs.org/)

**Requirements**: 
- SynopticLabs API key (free registration)
- Set environment variable: `SYNOPTIC_API_KEY=<your_key>`

**Download**:
```bash
export SYNOPTIC_API_KEY=<your_key>
python scripts/download_data.py mesowest --output-dir data/mesowest
```

### 6. NREL Wind Resource (2km resolution)

**File**: `data/nrel_wind/nrel_wind_80m.tif`  
**Format**: GeoTIFF  
**CRS**: EPSG:4326 (WGS84)  
**Resolution**: 2 kilometers  
**Hub Height**: 80 meters  
**Coverage**: Continental US

**Source**: [NREL Wind Resource Data](https://data.nrel.gov/submissions/4)

**Download**:
```bash
python scripts/download_data.py nrel-wind --output-dir data/nrel_wind
```

### 7. Road Network Shapefiles (AADT)

**Files**: 
- `data/roads/ODOT_roads.shp` (Oregon)
- `data/roads/WSDOT_roads.shp` (Washington)

**Format**: Shapefile  
**CRS**: EPSG:26910 (NAD83 / UTM Zone 10N)  
**Required Columns**: `AADT` (Annual Average Daily Traffic)

**Sources**:
- **Oregon**: [ODOT](https://www.oregon.gov/odot/)
- **Washington**: [WSDOT](https://www.wsdot.wa.gov/)

**Download**:
```bash
python scripts/download_data.py roads --output-dir data/roads
```

### 8. Boundary Shapefiles

**Files**:
- `data/boundary/region_1.geojson` (State boundary)
- `data/boundary/zipcodes_orwa.geojson` (ZIP code boundaries)

**Format**: GeoJSON or Shapefile  
**CRS**: EPSG:4326 (WGS84)  
**Coverage**: Oregon and Washington

**Source**: [Census TIGER/Line](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html)

**Download**:
```bash
python scripts/download_data.py boundaries --output-dir data/boundary
```

### 9. NOAA Station Metadata

**File**: `data/noaa/station_metadata.csv`  
**Format**: CSV  
**Required Columns**: `ICAO`, `latitude`, `longitude`, `elevation_ft`, `hdd_normal`  
**Period**: 1991-2020 normals

**Source**: [NOAA Climate Normals](https://www.ncei.noaa.gov/products/land-based-station-data-climate-normals/)

**Download**:
```bash
python scripts/download_data.py noaa-stations --output-dir data/noaa
```

## Directory Structure

After downloading all data, your `data/` directory should look like:

```
data/
├── lidar/
│   └── dem_1m.tif
├── prism/
│   ├── PRISM_tmean_30yr_normal_800mM01_01_bil.bil
│   ├── PRISM_tmean_30yr_normal_800mM02_01_bil.bil
│   └── ... (12 monthly files)
├── nlcd/
│   └── nlcd_2021_impervious_l48_20230405.tif
├── landsat/
│   └── LC09_L2SP_*_LST_ST.TIF
├── mesowest/
│   └── station_wind_*.csv
├── nrel_wind/
│   └── nrel_wind_80m.tif
├── roads/
│   ├── ODOT_roads.shp
│   └── WSDOT_roads.shp
├── boundary/
│   ├── region_1.geojson
│   └── zipcodes_orwa.geojson
└── noaa/
    └── station_metadata.csv
```

## Validation

To check that all required files are present and valid:

```bash
python scripts/download_data.py validate --output-dir data
```

## Licensing and Attribution

- **LiDAR**: Check DOGAMI/WA DNR terms
- **PRISM**: [PRISM License](https://www.prism.oregonstate.edu/terms/)
- **NLCD**: Public domain (USGS)
- **Landsat**: Public domain (USGS)
- **MesoWest**: Check SynopticLabs terms
- **NREL**: Public domain (NREL)
- **Census**: Public domain (US Census Bureau)
- **NOAA**: Public domain (NOAA)

## Troubleshooting

### Missing LiDAR DEM
The LiDAR DEM is the largest file (~50-100 GB uncompressed). Download from DOGAMI or WA DNR directly.

### PRISM Download Issues
PRISM files are large. Download from their website directly if the script fails.

### API Keys
Some data sources require API keys:
- **SynopticLabs**: Free registration at https://synopticlabs.org/
- **Microsoft Planetary Computer**: Free access at https://planetarycomputer.microsoft.com/

### CRS Mismatches
If downloaded files have different CRS, the pipeline will reproject them automatically during downscaling.

## Manual Download Instructions

If automated download scripts fail, download files manually:

1. Visit the source URL for each data type
2. Select the appropriate region (Oregon/Washington)
3. Download the file
4. Place in the corresponding `data/` subdirectory
5. Run validation: `python scripts/download_data.py validate`
