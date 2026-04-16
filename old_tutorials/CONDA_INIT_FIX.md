# Fix: "CondaError: Run 'conda init' before 'conda activate'"

## Quick Fix (30 seconds)

You just installed Conda and got this error:

```
CondaError: Run 'conda init' before 'conda activate'
```

### Solution

**Step 1: Run conda init**

In PowerShell, type:

```bash
conda init powershell
```

You'll see output like:
```
modified      C:\Users\chad\AppData\Local\Temp\_MEI311282\shell\condabin\Conda.psm1
modified      C:\Users\chad\AppData\Local\Temp\_MEI311282\shell\condabin\conda-hook.ps1
...
==> For changes to take effect, close and re-open your current shell. <==
```

**Step 2: Close PowerShell**

Click the X button to close PowerShell completely.

**Step 3: Reopen PowerShell**

Press `Win + X` and select "Windows PowerShell" or "Terminal"

**Step 4: Try Again**

```bash
conda activate microclimate
```

✅ It should work now!

## What Happened?

When you installed Conda, it modified your PowerShell configuration. The `conda init` command finalizes this setup. You only need to do this once.

## If It Still Doesn't Work

### Option 1: Use Command Prompt Instead

Open Command Prompt (not PowerShell):
- Press `Win + R`
- Type `cmd`
- Press Enter

Then:
```bash
conda activate microclimate
```

### Option 2: Use Full Path

In PowerShell:
```bash
& 'C:\ProgramData\miniconda3\Scripts\activate.bat' microclimate
```

### Option 3: Restart Computer

Sometimes Windows needs a restart for environment changes to take effect:
1. Save your work
2. Restart your computer
3. Try again

## Next Steps

Once `conda activate microclimate` works:

```bash
conda install -c conda-forge geopandas rasterio shapely
pip install -r requirements-minimal.txt
python -m src.pipeline data lidar --region region_1 --dry-run
```

## Reference

- Conda init docs: https://docs.conda.io/projects/conda/en/latest/user-guide/getting-started.html
