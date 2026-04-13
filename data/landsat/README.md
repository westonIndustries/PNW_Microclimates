# Landsat 9 Land Surface Temperature

Place the Landsat 9 Collection 2 Level-2 LST GeoTIFF here.

**Expected file**: `landsat9_lst.tif`  
**Config constant**: `LANDSAT_LST_RASTER`  
**Source**: USGS EarthExplorer or Microsoft Planetary Computer (via pystac-client)  
**Band**: ST_B10 (thermal infrared, 100 m resampled to 30 m)  
**Scale factor**: 0.00341802, offset: 149.0 → Kelvin; subtract 273.15 for Celsius  
**Note**: Optional — pipeline proceeds without calibration if file is absent.  
