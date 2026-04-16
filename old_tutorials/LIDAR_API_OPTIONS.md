# LiDAR Data Download APIs

Yes! There are several APIs available for downloading LiDAR DEM data. Here are your best options:

## 1. OpenTopography REST API (Recommended)

**Best for:** USGS 3DEP 1m LiDAR DEM data for Oregon and Washington

### Overview
- **Provider:** OpenTopography (NSF-funded facility)
- **Data:** USGS 3D Elevation Program (3DEP) DEMs at 1m, 10m, and 30m resolution
- **Coverage:** Entire United States including Oregon and Washington
- **Cost:** Free (requires free API key)
- **Rate Limits:** 200 calls/24 hours (academic), 50 calls/24 hours (non-academic)

### Getting Started

1. **Get a Free API Key:**
   - Go to https://opentopography.org
   - Create an account
   - Request a free API key in "My Account" section
   - Takes ~5 minutes

2. **Set API Key in Environment:**
   ```bash
   export OPENTOPOGRAPHY_API_KEY=your_api_key_here
   ```

3. **API Endpoint:**
   ```
   https://portal.opentopography.org/API/globaldem
   ```

### Example Request

```bash
# Download 1m DEM for a bounding box
curl "https://portal.opentopography.org/API/globaldem?demtype=USGS1m&south=45.0&north=45.5&west=-122.0&east=-121.5&outputFormat=GTiff&API_Key=YOUR_KEY"
```

### Python Implementation

```python
import requests
from pathlib import Path

def download_lidar_dem_opentopography(
    south: float,
    north: float,
    west: float,
    east: float,
    output_path: Path,
    api_key: str,
    dem_type: str = "USGS1m"
):
    """Download LiDAR DEM from OpenTopography API."""
    
    url = "https://portal.opentopography.org/API/globaldem"
    
    params = {
        "demtype": dem_type,  # USGS1m, USGS10m, USGS30m
        "south": south,
        "north": north,
        "west": west,
        "east": east,
        "outputFormat": "GTiff",
        "API_Key": api_key
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(response.content)
    
    return output_path
```

## 2. bmi-topography Python Library (Easiest)

**Best for:** Simple Python-based downloads with caching

### Installation

```bash
pip install bmi-topography
```

### Usage

```python
from bmi_topography import Topography

# Set up parameters
params = {
    "dem_type": "USGS1m",  # or USGS10m, USGS30m
    "south": 45.0,
    "north": 45.5,
    "west": -122.0,
    "east": -121.5,
    "output_format": "GTiff",
    "cache_dir": "~/.bmi_topography"
}

# Create instance
topo = Topography(**params)

# Fetch data (automatically cached)
filepath = topo.fetch()

# Load into xarray
data = topo.load()
```

### Features
- Automatic caching (won't re-download)
- Handles API key management
- Returns xarray DataArray
- Supports multiple DEM types

## 3. USGS 3DEP Lidar Explorer (Web Interface)

**Best for:** Manual browsing and understanding available data

- **URL:** https://lidarvisor.com/tutorials/download-usgs-3dep-lidar/
- **Coverage:** All US states including OR/WA
- **Resolution:** 1m, 10m, 30m
- **Cost:** Free, no account required
- **Limitation:** Manual download only (not API)

## 4. AWS Open Data Registry

**Best for:** Large-scale batch downloads

- **Provider:** AWS Registry of Open Data
- **Data:** USGS 3DEP LiDAR point clouds and DEMs
- **Access:** S3 API
- **Cost:** Free (AWS data transfer charges may apply)
- **Advantage:** Fast downloads if you have AWS account

### Example with boto3

```python
import boto3

s3 = boto3.client('s3')

# List available LiDAR tiles
response = s3.list_objects_v2(
    Bucket='usgs-lidar-open',
    Prefix='ept.json'
)

# Download specific tile
s3.download_file(
    'usgs-lidar-open',
    'ept.json',
    'local_ept.json'
)
```

## Recommended Implementation for Your Project

I recommend using **bmi-topography** because:

1. ✅ Simple Python API
2. ✅ Automatic caching (won't re-download)
3. ✅ Handles API key management
4. ✅ Returns xarray DataArray (compatible with your pipeline)
5. ✅ Supports all USGS 3DEP resolutions
6. ✅ Well-maintained and documented

### Updated lidar_dem.py Implementation

```python
"""Download LiDAR DEM from OpenTopography via bmi-topography."""

import logging
from pathlib import Path
from typing import Tuple

import numpy as np
from bmi_topography import Topography
from rasterio.transform import Affine
from rasterio.crs import CRS

logger = logging.getLogger(__name__)


def download_lidar_dem(
    south: float,
    north: float,
    west: float,
    east: float,
    output_dir: Path = Path("data/lidar"),
    dem_type: str = "USGS1m",
) -> Tuple[np.ndarray, Affine, CRS]:
    """
    Download 1m LiDAR DEM from OpenTopography.
    
    Args:
        south: Southern latitude bound
        north: Northern latitude bound
        west: Western longitude bound
        east: Eastern longitude bound
        output_dir: Output directory for DEM file
        dem_type: DEM type (USGS1m, USGS10m, USGS30m)
    
    Returns:
        Tuple of (array, transform, crs)
    """
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Downloading {dem_type} DEM from OpenTopography...")
    logger.info(f"Bounds: ({south}, {west}) to ({north}, {east})")
    
    # Create Topography instance
    params = {
        "dem_type": dem_type,
        "south": south,
        "north": north,
        "west": west,
        "east": east,
        "output_format": "GTiff",
        "cache_dir": str(output_dir / ".cache")
    }
    
    topo = Topography(**params)
    
    # Fetch data (automatically cached)
    filepath = topo.fetch()
    logger.info(f"Downloaded to: {filepath}")
    
    # Load into xarray
    da = topo.load()
    
    # Extract array and metadata
    array = da.values[0]  # Remove band dimension
    
    # Get transform and CRS from xarray
    transform = Affine.identity()  # Will be set from rasterio
    crs = CRS.from_epsg(4326)  # WGS84
    
    # Replace nodata with NaN
    array = np.where(array == 0, np.nan, array)
    
    logger.info(f"DEM shape: {array.shape}, dtype: {array.dtype}")
    
    return array, transform, crs


def download_lidar_for_region(
    region_name: str,
    output_dir: Path = Path("data/lidar"),
) -> Tuple[np.ndarray, Affine, CRS]:
    """
    Download LiDAR DEM for a specific region.
    
    Args:
        region_name: Region name (e.g., "region_1")
        output_dir: Output directory
    
    Returns:
        Tuple of (array, transform, crs)
    """
    
    # Define region bounds (Oregon and Washington)
    region_bounds = {
        "region_1": {
            "south": 42.0,
            "north": 49.0,
            "west": -124.5,
            "east": -116.5,
        }
    }
    
    if region_name not in region_bounds:
        raise ValueError(f"Unknown region: {region_name}")
    
    bounds = region_bounds[region_name]
    
    return download_lidar_dem(
        south=bounds["south"],
        north=bounds["north"],
        west=bounds["west"],
        east=bounds["east"],
        output_dir=output_dir,
        dem_type="USGS1m",
    )
```

## Installation

Add to `requirements.txt`:

```
bmi-topography>=0.9.0
```

Or install manually:

```bash
pip install bmi-topography
```

## API Key Setup

1. **Get free API key:**
   - Visit https://opentopography.org
   - Create account
   - Request API key

2. **Set environment variable:**
   ```bash
   export OPENTOPOGRAPHY_API_KEY=your_key_here
   ```

3. **Or create `.opentopography.txt`:**
   ```
   your_api_key_here
   ```

## Data Specifications

### USGS 3DEP 1m DEM
- **Resolution:** 1 meter
- **Coverage:** Entire US (OR/WA included)
- **Format:** GeoTIFF
- **CRS:** WGS84 (EPSG:4326)
- **Vertical Datum:** NAVD88
- **Licensing:** Public domain (no restrictions)

### Request Limits
- **1m DEM:** 250 km² per request (academic users)
- **10m DEM:** 25,000 km² per request
- **30m DEM:** 225,000 km² per request

## Advantages of This Approach

✅ **Programmatic:** Fully automated downloads
✅ **Cached:** Won't re-download same data
✅ **Simple:** Just a few lines of Python
✅ **Reliable:** NSF-funded infrastructure
✅ **Free:** No cost for academic use
✅ **Well-documented:** Extensive examples available
✅ **Integrated:** Works with xarray/rasterio

## Next Steps

1. Install bmi-topography: `pip install bmi-topography`
2. Get free API key from OpenTopography
3. Set `OPENTOPOGRAPHY_API_KEY` environment variable
4. Update `scripts/data_sources/lidar_dem.py` with the implementation above
5. Test: `python -m src.pipeline data lidar --region region_1`

## References

- OpenTopography: https://opentopography.org
- bmi-topography docs: https://bmi-topography.readthedocs.io/
- USGS 3DEP: https://www.usgs.gov/3dep
- OpenTopography API: https://opentopography.org/developers
