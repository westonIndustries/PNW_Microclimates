"""
Configuration constants for the Regional Microclimate Modeling Engine.

All file paths, CRS settings, physics constants, station reference data,
and pipeline metadata are defined here. No magic numbers or hardcoded paths
should appear in processor or loader modules — import from this module.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# File paths — all relative to project root, matching the data/ folder layout
# ---------------------------------------------------------------------------

LIDAR_DEM_RASTER = Path("data/lidar/dem_1m.tif")
PRISM_TEMP_DIR = Path("data/prism/")
LANDSAT_LST_RASTER = Path("data/landsat/landsat9_lst.tif")
MESOWEST_WIND_DIR = Path("data/wind/mesowest/")
NREL_WIND_RASTER = Path("data/wind/nrel/nrel_wind_80m.tif")
NLCD_IMPERVIOUS_RASTER = Path("data/nlcd/nlcd_impervious_2021.tif")
ODOT_ROADS_SHP = Path("data/roads/odot_roads.shp")
WSDOT_ROADS_SHP = Path("data/roads/wsdot_roads.shp")
BOUNDARY_SHP = Path("data/boundary/orwa_boundary.shp")
TERRAIN_ATTRIBUTES_CSV = Path("output/microclimate/terrain_attributes.csv")
REGION_REGISTRY_CSV = Path("data/boundary/region_registry.csv")
ZIPCODES_GEOJSON = Path("data/boundary/zipcodes_orwa.geojson")
ZIPCODES_CSV = Path("data/boundary/zipcodes_orwa.csv")

# ---------------------------------------------------------------------------
# Coordinate Reference System
# ---------------------------------------------------------------------------

TARGET_CRS = "EPSG:26910"  # NAD83 / UTM Zone 10N — covers OR and most of WA

# ---------------------------------------------------------------------------
# Physics constants
# ---------------------------------------------------------------------------

SOLAR_IRRADIANCE_WM2 = 200          # W/m² — representative annual mean for PNW
LAPSE_RATE_HDD_PER_1000FT = 630     # HDD increase per 1,000 ft elevation gain
PREVAILING_WIND_DEG = 225            # Degrees — dominant SW Pacific storm track
HDD_PER_DEGREE_F = 180              # Annual HDD per 1°F mean temperature shift

# ---------------------------------------------------------------------------
# Pipeline metadata
# ---------------------------------------------------------------------------

PIPELINE_VERSION = "1.0.0"
NLCD_VINTAGE = 2021
PRISM_PERIOD = "1991-2020"

# ---------------------------------------------------------------------------
# Station HDD normals — ICAO code → annual HDD base 65°F (1991-2020 NOAA)
# ---------------------------------------------------------------------------

STATION_HDD_NORMALS: dict[str, int] = {
    "KPDX": 4850,
    "KEUG": 4650,
    "KSLE": 4900,
    "KAST": 5200,
    "KDLS": 5800,
    "KOTH": 4400,
    "KONP": 4600,
    "KCVO": 4750,
    "KHIO": 4900,
    "KTTD": 5100,
    "KVUO": 4950,
}

# ---------------------------------------------------------------------------
# Station elevations — ICAO code → elevation in feet above sea level
# ---------------------------------------------------------------------------

STATION_ELEVATIONS_FT: dict[str, int] = {
    "KPDX": 30,
    "KEUG": 374,
    "KSLE": 214,
    "KAST": 10,
    "KDLS": 247,
    "KOTH": 17,
    "KONP": 50,
    "KCVO": 250,
    "KHIO": 208,
    "KTTD": 22,
    "KVUO": 20,
}

# ---------------------------------------------------------------------------
# Station coordinates — ICAO code → (lat, lon) for bias correction and
# nearest-station assignment
# ---------------------------------------------------------------------------

STATION_COORDS: dict[str, tuple[float, float]] = {
    "KPDX": (45.5898, -122.5951),
    "KEUG": (44.1246, -123.2190),
    "KSLE": (44.9095, -123.0032),
    "KAST": (46.1579, -123.8787),
    "KDLS": (45.6185, -121.1670),
    "KOTH": (43.4171, -124.2461),
    "KONP": (44.5804, -124.0579),
    "KCVO": (44.4971, -123.2896),
    "KHIO": (45.5404, -122.9498),
    "KTTD": (45.5494, -122.4013),
    "KVUO": (45.6205, -122.6565),
}

# ---------------------------------------------------------------------------
# District → weather station map
# Populated at runtime from the region registry CSV (see load_region_registry).
# ---------------------------------------------------------------------------

DISTRICT_WEATHER_MAP: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Gorge districts — Columbia River Gorge stations that receive a wind
# infiltration floor of 1.15 due to the high-wind corridor effect
# ---------------------------------------------------------------------------

GORGE_DISTRICTS: list[str] = ["KDLS", "KTTD"]
