# Conda Quick Setup for Windows

## 5-Minute Installation

### Step 1: Download Conda (2 minutes)

**Option A: Miniconda (Recommended - 150 MB)**
- Go to: https://docs.conda.io/projects/miniconda/en/latest/
- Click "Miniconda3 Windows 64-bit"
- Save the installer

**Option B: Anaconda (Full - 600 MB)**
- Go to: https://www.anaconda.com/download
- Click "Download" for Windows 64-bit
- Save the installer

### Step 2: Install Conda (2 minutes)

1. Double-click the installer
2. Click "Next" through the wizard
3. **Important:** Check these boxes:
   - ✅ "Add Miniconda3 to my PATH"
   - ✅ "Register Miniconda3 as my default Python"
4. Click "Install"
5. **Restart your computer**

### Step 3: Open Anaconda Prompt (Recommended)

**Easiest way - use Anaconda Prompt:**

1. Press `Win + S` (search)
2. Type: `Anaconda Prompt`
3. Click "Anaconda Prompt (miniconda3)"

**Alternative: Use PowerShell**

1. Press `Win + X`
2. Select "Windows PowerShell" or "Terminal"

### Step 4: Verify Installation (30 seconds)

Type:
```bash
conda --version
```

You should see: `conda 24.1.2` (or similar)

If you get "conda: not recognized", see **CONDA_NOT_FOUND_FIX.md**

### Step 5: Create Environment (1 minute)

```bash
conda create -n microclimate python=3.10 -c conda-forge
```

When asked "Proceed ([y]/n)?", type `y` and press Enter

### Step 6: Activate Environment (10 seconds)

```bash
conda activate microclimate
```

You should see `(microclimate)` at the start of your command line

### Step 7: Install Packages (2 minutes)

```bash
conda install -c conda-forge geopandas rasterio shapely
```

When asked "Proceed ([y]/n)?", type `y` and press Enter

### Step 8: Install Remaining Packages (1 minute)

```bash
pip install -r requirements-minimal.txt
```

### Step 9: Test Installation (30 seconds)

```bash
python -c "import bmi_topography; print('✓ Ready!')"
```

## ✅ You're Done!

Now you can download data:

```bash
python -m src.pipeline data lidar --region region_1
python -m src.pipeline data nlcd --region region_1
```

## Troubleshooting

### "conda: not recognized"

**Solution:** See **CONDA_NOT_FOUND_FIX.md**

Or use Anaconda Prompt instead of PowerShell:
- Press `Win + S`
- Type: `Anaconda Prompt`
- Click "Anaconda Prompt (miniconda3)"

### "CondaError: Run 'conda init' before 'conda activate'"

**Solution (PowerShell only):**
```bash
conda init powershell
```

Then **close and reopen PowerShell completely**.

(Skip if using Anaconda Prompt)

### Installation is slow

**Normal!** First installation takes 5-10 minutes. Subsequent installs are faster.

### Out of disk space

**Solution:** Use Miniconda instead of Anaconda (smaller)

## Next Steps

1. Get API key for LiDAR:
   - Visit: https://opentopography.org
   - Create account
   - Request API key
   - Set: `$env:OPENTOPOGRAPHY_API_KEY="your_key"`

2. Download data:
   ```bash
   python -m src.pipeline data lidar --region region_1
   python -m src.pipeline data nlcd --region region_1
   ```

3. Run pipeline:
   ```bash
   python -m src.pipeline run --region region_1 --mode normals
   ```

## Reference

- Conda docs: https://docs.conda.io/
- Miniconda: https://docs.conda.io/projects/miniconda/en/latest/
- Anaconda: https://www.anaconda.com/download
