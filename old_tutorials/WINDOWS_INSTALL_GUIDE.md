# Windows Installation Guide

If you encounter build errors when installing dependencies on Windows, follow this guide.

## ⚡ Quick Start (5 Minutes)

**Don't have Conda yet?** Start here:

1. **Download Miniconda:**
   - Go to: https://docs.conda.io/projects/miniconda/en/latest/
   - Download "Miniconda3 Windows 64-bit"
   - Run installer, **check "Add to PATH"**, restart computer

2. **Open Anaconda Prompt (Recommended):**
   - Press `Win + S` (search)
   - Type: `Anaconda Prompt`
   - Click "Anaconda Prompt (miniconda3)"
   
   **Alternative: Use PowerShell**
   - Press `Win + X` → "Windows PowerShell"

3. **Initialize Conda (First time only):**
   ```bash
   conda init powershell
   ```
   Then close and reopen PowerShell (skip if using Anaconda Prompt)

4. **Create Environment:**
   ```bash
   conda create -n microclimate python=3.10 -c conda-forge
   conda activate microclimate
   ```

5. **Install Packages:**
   ```bash
   conda install -c conda-forge geopandas rasterio shapely
   pip install -r requirements-minimal.txt
   ```

6. **Test It:**
   ```bash
   python -m src.pipeline data lidar --region region_1 --dry-run
   ```

✅ Done! You're ready to download data.

---

## Getting Conda (Detailed Instructions)

### What is Conda?

Conda is a package manager that makes installing geospatial packages on Windows much easier. It handles pre-built binaries so you don't need to compile anything.

### Download and Install Conda

**Step 1: Download Miniconda (Recommended - Smaller)**

1. Go to: https://docs.conda.io/projects/miniconda/en/latest/
2. Download **Miniconda3 Windows 64-bit** (or 32-bit if you have 32-bit Python)
3. Run the installer
4. During installation:
   - ✅ Check "Add Miniconda3 to my PATH"
   - ✅ Check "Register Miniconda3 as my default Python"
5. Click "Install"
6. Restart your computer

**Alternative: Download Anaconda (Larger, includes more packages)**

1. Go to: https://www.anaconda.com/download
2. Download **Anaconda3 Windows 64-bit**
3. Run the installer
4. Follow same steps as above

### Verify Conda Installation

Open PowerShell or Command Prompt and run:

```bash
conda --version
```

You should see something like: `conda 24.1.2`

If you get "command not found", restart your computer or add Conda to PATH manually.

### Add Conda to PATH (If Needed)

If conda command doesn't work:

1. Open Environment Variables:
   - Press `Win + X` → "System"
   - Click "Advanced system settings"
   - Click "Environment Variables"

2. Under "User variables", click "New"
   - Variable name: `PATH`
   - Variable value: `C:\Users\YOUR_USERNAME\miniconda3\Scripts`
   - Replace `YOUR_USERNAME` with your actual username

3. Click OK and restart PowerShell

## Common Issues and Solutions

### Issue: "CondaError: Run 'conda init' before 'conda activate'"

**Cause:** Conda needs to be initialized for PowerShell on first use.

**Solution:**

```bash
# Initialize conda for PowerShell
conda init powershell

# Close PowerShell completely
# Then reopen PowerShell

# Now try again
conda activate microclimate
```

**If that doesn't work:**

```bash
# Use the full path to activate
& 'C:\ProgramData\miniconda3\Scripts\activate.bat' microclimate
```

Or use Command Prompt instead of PowerShell:
```bash
# In Command Prompt (not PowerShell)
conda activate microclimate
```

### Issue: "ERROR: Failed to build 'shapely'"

**Cause:** Shapely requires compilation on Windows and needs build tools.

**Solution 1: Use Pre-built Wheels (Recommended)**

```bash
# Install pre-built wheels from conda-forge
conda install -c conda-forge shapely geopandas rasterio

# Then install remaining packages
pip install -r requirements.txt
```

**Solution 2: Install Build Tools**

1. Download and install Visual Studio Build Tools:
   - https://visualstudio.microsoft.com/downloads/
   - Select "Desktop development with C++"

2. Then install requirements:
   ```bash
   pip install -r requirements.txt
   ```

**Solution 3: Use OSGeo4W (Easiest for Windows)**

1. Download OSGeo4W installer:
   - https://trac.osgeo.org/osgeo4w/

2. Run installer and select:
   - GDAL
   - GEOS
   - PROJ
   - Python packages

3. Then install remaining packages:
   ```bash
   pip install -r requirements.txt
   ```

### Issue: "ERROR: Failed to build 'eccodes'"

**Cause:** eccodes requires GRIB library compilation.

**Solution 1: Skip eccodes (if not needed)**

```bash
# Create requirements-minimal.txt without eccodes
pip install -r requirements-minimal.txt
```

**Solution 2: Use conda**

```bash
conda install -c conda-forge eccodes cfgrib
pip install -r requirements.txt
```

### Issue: "ERROR: Failed to build 'richdem'"

**Cause:** richdem requires compilation.

**Solution: Use conda**

```bash
conda install -c conda-forge richdem
pip install -r requirements.txt
```

## Recommended Installation Method for Windows

### Quick Start (5 minutes)

**Step 1: Open PowerShell**

Press `Win + X` and select "Windows PowerShell" or "Terminal"

**Step 2: Create Conda Environment**

```bash
conda create -n microclimate python=3.10 -c conda-forge
```

When asked "Proceed ([y]/n)?", type `y` and press Enter

**Step 3: Activate Environment**

```bash
conda activate microclimate
```

You should see `(microclimate)` at the start of your command line

**Step 4: Install Geospatial Packages**

```bash
conda install -c conda-forge geopandas rasterio shapely
```

When asked "Proceed ([y]/n)?", type `y` and press Enter

**Step 5: Install Remaining Packages**

```bash
pip install -r requirements-minimal.txt
```

**Step 6: Verify Installation**

```bash
python -c "import bmi_topography; print('✓ Ready to download LiDAR')"
```

### Option A: Using Conda (Easiest)

```bash
# 1. Create conda environment
conda create -n microclimate python=3.10

# 2. Activate environment
conda activate microclimate

# 3. Install geospatial packages from conda-forge
conda install -c conda-forge \
    gdal \
    geopandas \
    rasterio \
    shapely \
    richdem \
    eccodes \
    cfgrib

# 4. Install remaining packages
pip install -r requirements.txt
```

### Option B: Using pip with Pre-built Wheels

```bash
# 1. Create virtual environment
python -m venv venv

# 2. Activate environment
venv\Scripts\activate

# 3. Upgrade pip
python -m pip install --upgrade pip

# 4. Install pre-built wheels
pip install --only-binary :all: shapely geopandas rasterio

# 5. Install remaining packages
pip install -r requirements.txt
```

### Option C: Using OSGeo4W

1. Install OSGeo4W with GDAL, GEOS, PROJ
2. Use OSGeo4W Python environment
3. Install remaining packages: `pip install -r requirements.txt`

## Minimal Requirements

If you only need LiDAR and NLCD downloads, use this minimal setup:

```bash
# Create minimal requirements file
pip install \
    bmi-topography>=0.9.0 \
    pygeohydro>=0.16.0 \
    rasterio>=1.3 \
    geopandas>=0.14 \
    shapely>=2.0 \
    numpy>=1.24 \
    pandas>=2.0 \
    requests>=2.31
```

## Verification

After installation, verify everything works:

```bash
# Test imports
python -c "import rasterio; print('✓ rasterio')"
python -c "import geopandas; print('✓ geopandas')"
python -c "import shapely; print('✓ shapely')"
python -c "import bmi_topography; print('✓ bmi-topography')"
python -c "import pygeohydro; print('✓ pygeohydro')"

# Test CLI
python -m src.pipeline --help
```

## Troubleshooting Steps

1. **Update pip:**
   ```bash
   python -m pip install --upgrade pip setuptools wheel
   ```

2. **Clear pip cache:**
   ```bash
   pip cache purge
   ```

3. **Try installing one package at a time:**
   ```bash
   pip install rasterio
   pip install geopandas
   pip install shapely
   # etc.
   ```

4. **Check Python version:**
   ```bash
   python --version
   # Should be 3.8 or higher
   ```

5. **Use verbose output:**
   ```bash
   pip install -r requirements.txt -v
   ```

## Getting Help

If you still have issues:

1. Check the error message carefully
2. Search for the specific error online
3. Try the conda installation method
4. Check package documentation:
   - Rasterio: https://rasterio.readthedocs.io/
   - GeoPandas: https://geopandas.org/
   - Shapely: https://shapely.readthedocs.io/

## Alternative: Docker

If installation is too difficult, use Docker:

```bash
# Create Dockerfile
FROM continuumio/miniconda3

RUN conda install -c conda-forge \
    gdal geopandas rasterio shapely richdem eccodes cfgrib

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

CMD ["python", "-m", "src.pipeline", "--help"]
```

Then run:
```bash
docker build -t microclimate .
docker run -it microclimate
```

## Summary

**Recommended for Windows:**
1. Use Conda (easiest)
2. Or use OSGeo4W
3. Or use Docker

**Minimal installation:**
```bash
pip install bmi-topography pygeohydro rasterio geopandas shapely numpy pandas requests
```

**Full installation:**
```bash
conda install -c conda-forge gdal geopandas rasterio shapely richdem eccodes cfgrib
pip install -r requirements.txt
```
