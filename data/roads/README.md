# Road Network Shapefiles (AADT)

Place the Oregon and Washington road shapefiles here.

**Expected files**:
- `odot_roads.shp` (+ `.dbf`, `.shx`, `.prj`) — Oregon DOT  
- `wsdot_roads.shp` (+ `.dbf`, `.shx`, `.prj`) — Washington State DOT  

**Config constants**: `ODOT_ROADS_SHP`, `WSDOT_ROADS_SHP`  
**Source**: ODOT (https://www.oregon.gov/odot/data) and WSDOT (https://www.wsdot.wa.gov/data)  
**Required attribute**: `AADT` (Annual Average Daily Traffic); segments with AADT = 0 are filtered out  
**Used for**: Computing anthropogenic heat flux along road corridors  
