# NREL Wind Resource Raster

Place the NREL gridded wind resource GeoTIFF here.

**Expected file**: `nrel_wind_80m.tif`  
**Config constant**: `NREL_WIND_RASTER`  
**Source**: NREL Wind Prospector / AWS Truepower (https://windexchange.energy.gov)  
**Hub height**: 80 m (pipeline scales to 10 m surface wind via power law: `wind_10m = wind_80m × (10/80)^0.143`)  
**Resolution**: ~2 km  
