# Quick Fix for Installation Issues

## If you're getting "ERROR: Failed to build 'shapely'" on Windows

### Quick Fix (30 seconds)

**Option 1: Use Conda (Recommended)**

```bash
# Install conda if you don't have it
# Download from: https://www.anaconda.com/download

# Then run:
conda create -n microclimate python=3.10
conda activate microclimate
conda install -c conda-forge geopandas rasterio shapely
pip install -r requirements-minimal.txt
```

**Option 2: Use Minimal Requirements**

```bash
pip install -r requirements-minimal.txt
```

This installs only what's needed for LiDAR and NLCD downloads.

**Option 3: Skip problematic packages**

```bash
# Install without eccodes and richdem
pip install \
    bmi-topography \
    pygeohydro \
    rasterio \
    geopandas \
    shapely \
    numpy \
    pandas \
    requests
```

## What to do next

### 1. Test if it works

```bash
python -m src.pipeline data lidar --region region_1 --dry-run
python -m src.pipeline data nlcd --region region_1 --dry-run
```

### 2. If it still fails

Try the full conda installation:

```bash
# Create new environment
conda create -n microclimate python=3.10 -c conda-forge

# Activate it
conda activate microclimate

# Install all packages
conda install -c conda-forge \
    gdal \
    geopandas \
    rasterio \
    shapely \
    richdem \
    eccodes \
    cfgrib \
    xarray \
    pandas \
    numpy \
    scipy

# Install remaining packages
pip install -r requirements.txt
```

### 3. Verify installation

```bash
python -c "import bmi_topography; print('✓ bmi-topography works')"
python -c "import pygeohydro; print('✓ pygeohydro works')"
python -c "import rasterio; print('✓ rasterio works')"
```

## Files Available

- **requirements.txt** - Full requirements (may have build issues on Windows)
- **requirements-minimal.txt** - Minimal requirements (recommended for Windows)
- **requirements-data.txt** - Data acquisition dependencies reference
- **WINDOWS_INSTALL_GUIDE.md** - Detailed Windows installation guide

## Recommended Path

1. Try: `pip install -r requirements-minimal.txt`
2. If that fails, use: `conda` (see WINDOWS_INSTALL_GUIDE.md)
3. If conda fails, use: Docker (see WINDOWS_INSTALL_GUIDE.md)

## Need Help?

See **WINDOWS_INSTALL_GUIDE.md** for detailed troubleshooting.
