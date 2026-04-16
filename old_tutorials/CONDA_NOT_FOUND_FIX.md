# Fix: "conda: The term 'conda' is not recognized"

## Quick Fix (2 minutes)

You're getting this error:
```
conda : The term 'conda' is not recognized as the name of a cmdlet, function, script file, or operable program.
```

This means Conda isn't in your PATH. Here are the solutions:

## Solution 1: Use Anaconda Prompt (Easiest)

**Don't use PowerShell. Use Anaconda Prompt instead:**

1. Press `Win + S` (search)
2. Type: `Anaconda Prompt`
3. Click "Anaconda Prompt (miniconda3)"
4. Now try:
   ```bash
   conda --version
   ```

✅ This should work!

Then continue with:
```bash
conda create -n microclimate python=3.10 -c conda-forge
conda activate microclimate
conda install -c conda-forge geopandas rasterio shapely
pip install -r requirements-minimal.txt
```

## Solution 2: Use Full Path in PowerShell

If you want to use PowerShell, use the full path:

```bash
& 'C:\ProgramData\miniconda3\Scripts\conda.exe' --version
```

To make it easier, create an alias:

```bash
Set-Alias -Name conda -Value 'C:\ProgramData\miniconda3\Scripts\conda.exe'
conda --version
```

## Solution 3: Add Conda to PATH Manually

If Conda wasn't added to PATH during installation:

### Step 1: Open Environment Variables

1. Press `Win + X`
2. Click "System"
3. Click "Advanced system settings"
4. Click "Environment Variables"

### Step 2: Add Conda to PATH

1. Under "User variables", click "New"
2. Variable name: `PATH`
3. Variable value: `C:\ProgramData\miniconda3\Scripts`
4. Click "OK"

### Step 3: Restart PowerShell

Close PowerShell completely and reopen it.

### Step 4: Test

```bash
conda --version
```

## Solution 4: Reinstall Conda

If none of the above work, reinstall Conda:

1. Uninstall Miniconda:
   - Go to Control Panel → Programs → Programs and Features
   - Find "Miniconda3"
   - Click "Uninstall"

2. Download fresh installer:
   - Go to: https://docs.conda.io/projects/miniconda/en/latest/
   - Download "Miniconda3 Windows 64-bit"

3. Run installer:
   - **Important:** Check "Add Miniconda3 to my PATH"
   - Check "Register Miniconda3 as my default Python"
   - Click "Install"

4. Restart computer

5. Open PowerShell and test:
   ```bash
   conda --version
   ```

## Recommended: Use Anaconda Prompt

The easiest solution is to **use Anaconda Prompt** instead of PowerShell:

1. Press `Win + S`
2. Type: `Anaconda Prompt`
3. Click "Anaconda Prompt (miniconda3)"
4. All conda commands will work

## Next Steps

Once conda works:

```bash
# Create environment
conda create -n microclimate python=3.10 -c conda-forge

# Activate it
conda activate microclimate

# Install packages
conda install -c conda-forge geopandas rasterio shapely
pip install -r requirements-minimal.txt

# Test
python -m src.pipeline data lidar --region region_1 --dry-run
```

## Reference

- Conda PATH issues: https://docs.conda.io/projects/conda/en/latest/user-guide/troubleshooting.html
- Anaconda Prompt: https://docs.anaconda.com/anaconda/user-guide/getting-started/
