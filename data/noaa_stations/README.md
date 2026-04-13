# NOAA Station Normals

Place the NOAA 1991–2020 climate normals reference file here.

**Expected file**: `station_normals.csv`  
**Config constant**: Values are defined directly in `config.py` as `STATION_HDD_NORMALS` and `STATION_ELEVATIONS_FT`  
**Source**: NOAA Climate Data Online (https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals)  
**Required columns**: `station_id` (ICAO), `hdd_normal` (annual HDD base 65°F), `elevation_ft`  
**Used for**: Bias-correcting the PRISM temperature grid to observed station values  
