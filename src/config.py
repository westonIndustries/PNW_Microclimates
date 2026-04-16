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
LAPSE_RATE_CDD_PER_1000FT = 630     # CDD increase per 1,000 ft elevation gain (same magnitude as HDD)
PREVAILING_WIND_DEG = 225            # Degrees — dominant SW Pacific storm track
HDD_PER_DEGREE_F = 180              # Annual HDD per 1°F mean temperature shift
CDD_PER_DEGREE_F = 180              # Annual CDD per 1°F mean temperature shift (same as HDD)

# ---------------------------------------------------------------------------
# Microclimate cell constants
# ---------------------------------------------------------------------------

CELL_SIZE_M = 500                   # Cell size in meters (500m × 500m grid cells)
MIN_CELL_PIXELS = 10                # Minimum 1m pixels per cell for reliability

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
# ZIP code → weather station map
# Populated at runtime from the region registry CSV (see load_region_registry).
# Each ZIP code is assigned to its nearest NOAA station by haversine distance.
# ---------------------------------------------------------------------------

ZIPCODE_STATION_MAP: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Gorge stations — Columbia River Gorge stations that receive a wind
# infiltration floor of 1.15 due to the high-wind corridor effect
# ---------------------------------------------------------------------------

GORGE_STATIONS: list[str] = ["KDLS", "KTTD"]

# ---------------------------------------------------------------------------
# Surface property constants for boundary layer physics
# ---------------------------------------------------------------------------

# NLCD surface properties lookup table — per NLCD 2021 land cover class
# Maps NLCD class code to (z0_m, albedo, emissivity)
# z0_m: roughness length in meters
# albedo: surface albedo (0.0–1.0)
# emissivity: thermal emissivity (0.0–1.0)
NLCD_SURFACE_PROPERTIES: dict[int, dict[str, float]] = {
    11: {"z0_m": 0.0002, "albedo": 0.08, "emissivity": 0.98},      # Open water
    12: {"z0_m": 0.0005, "albedo": 0.10, "emissivity": 0.98},      # Perennial ice/snow
    21: {"z0_m": 0.05, "albedo": 0.20, "emissivity": 0.95},        # Developed, open space
    22: {"z0_m": 0.50, "albedo": 0.15, "emissivity": 0.92},        # Developed, low intensity
    23: {"z0_m": 0.80, "albedo": 0.12, "emissivity": 0.90},        # Developed, medium intensity
    24: {"z0_m": 1.20, "albedo": 0.10, "emissivity": 0.88},        # Developed, high intensity
    31: {"z0_m": 0.01, "albedo": 0.25, "emissivity": 0.94},        # Barren land
    41: {"z0_m": 1.50, "albedo": 0.12, "emissivity": 0.98},        # Deciduous forest
    42: {"z0_m": 1.80, "albedo": 0.10, "emissivity": 0.98},        # Evergreen forest
    43: {"z0_m": 1.60, "albedo": 0.11, "emissivity": 0.98},        # Mixed forest
    51: {"z0_m": 0.30, "albedo": 0.20, "emissivity": 0.96},        # Dwarf scrub
    52: {"z0_m": 0.20, "albedo": 0.22, "emissivity": 0.96},        # Shrub/scrub
    71: {"z0_m": 0.10, "albedo": 0.25, "emissivity": 0.97},        # Grassland/herbaceous
    72: {"z0_m": 0.08, "albedo": 0.24, "emissivity": 0.97},        # Sedge/herbaceous
    73: {"z0_m": 0.12, "albedo": 0.26, "emissivity": 0.97},        # Lichens and mosses
    74: {"z0_m": 0.05, "albedo": 0.23, "emissivity": 0.97},        # Pasture/hay
    81: {"z0_m": 0.15, "albedo": 0.24, "emissivity": 0.97},        # Cultivated crops
    82: {"z0_m": 0.08, "albedo": 0.25, "emissivity": 0.97},        # Pasture/hay (alt)
    90: {"z0_m": 0.40, "albedo": 0.18, "emissivity": 0.97},        # Woody wetlands
    95: {"z0_m": 0.30, "albedo": 0.20, "emissivity": 0.97},        # Emergent herbaceous wetlands
}

# NLCD displacement height lookup table — per NLCD 2021 land cover class
# Maps NLCD class code to displacement height d in meters
# d: height above ground where wind profile effectively begins (for forests/urban)
NLCD_DISPLACEMENT_HEIGHT_M: dict[int, float] = {
    11: 0.0,        # Open water
    12: 0.0,        # Perennial ice/snow
    21: 0.0,        # Developed, open space
    22: 2.0,        # Developed, low intensity
    23: 4.0,        # Developed, medium intensity
    24: 6.0,        # Developed, high intensity
    31: 0.0,        # Barren land
    41: 15.0,       # Deciduous forest
    42: 18.0,       # Evergreen forest
    43: 16.0,       # Mixed forest
    51: 0.5,        # Dwarf scrub
    52: 1.0,        # Shrub/scrub
    71: 0.0,        # Grassland/herbaceous
    72: 0.0,        # Sedge/herbaceous
    73: 0.0,        # Lichens and mosses
    74: 0.0,        # Pasture/hay
    81: 0.5,        # Cultivated crops
    82: 0.0,        # Pasture/hay (alt)
    90: 2.0,        # Woody wetlands
    95: 1.0,        # Emergent herbaceous wetlands
}

# Boundary layer physics constants
ROUGHNESS_GRADIENT_THRESHOLD = 0.3   # Threshold for roughness transition zone detection
VON_KARMAN = 0.41                    # Von Kármán constant for log-law wind profile
BL_DECAY_HEIGHT_FT = 500             # Boundary layer decay height for general effects (ft AGL)
UHI_BL_DECAY_HEIGHT_FT = 300         # UHI boundary layer decay height (ft AGL)
Z0_RURAL_REFERENCE = 0.03            # Reference roughness length for rural areas (m)

# Safety cube altitude levels for aviation and GA operations
SAFETY_CUBE_ALTITUDE_LEVELS_FT = [0, 500, 1000, 3000, 6000, 9000, 12000, 18000]

# Turbulence kinetic energy thresholds for aviation safety classification
TKE_THRESHOLDS: dict[str, float] = {
    "smooth": 0.5,      # TKE < 0.5 m²/s² — smooth conditions
    "light": 1.5,       # 0.5 ≤ TKE < 1.5 m²/s² — light turbulence
    "moderate": 3.0,    # 1.5 ≤ TKE < 3.0 m²/s² — moderate turbulence
    # TKE ≥ 3.0 m²/s² — severe turbulence
}


# ---------------------------------------------------------------------------
# HRRR (High-Resolution Rapid Refresh) data ingestion and caching
# ---------------------------------------------------------------------------

# Local cache directory for downloaded HRRR GRIB2 files
HRRR_CACHE_DIR = Path("data/hrrr/")

# AWS S3 bucket for HRRR data (public, anonymous access)
HRRR_S3_BUCKET = "s3://noaa-hrrr-bdp-pds/"

# Google Cloud Storage bucket for HRRR data (alternative source)
HRRR_GCS_BUCKET = "gs://noaa-hrrr-bdp-pds/"

# Earliest available HRRR analysis date (f00 forecast hour = analysis)
# HRRR became available on 2014-07-30
HRRR_EARLIEST_DATE = "2014-07-30"

# Download confirmation threshold — prompt user if estimated download exceeds this size (GB)
HRRR_DOWNLOAD_CONFIRM_THRESHOLD_GB = 10

# Minimum number of years of HRRR climatology required for bias correction
# If fewer years are cached, fallback to raw HRRR monthly mean
HRRR_MIN_CLIM_YEARS = 3

# Output directory for daily mode results
DAILY_OUTPUT_DIR = Path("output/microclimate/daily/")

# ---------------------------------------------------------------------------
# General Aviation (GA) altitude levels for multi-level microclimate profiles
# ---------------------------------------------------------------------------

# GA altitude levels in feet AGL for safety cube and wind profile extraction
# Includes surface (0 ft), boundary layer (500, 1000 ft), and upper levels
GA_ALTITUDE_LEVELS_FT = [0, 500, 1000, 3000, 6000, 9000, 12000, 18000]

# ---------------------------------------------------------------------------
# HRRR pressure levels for wind and temperature extraction
# ---------------------------------------------------------------------------

# HRRR pressure levels (mb) available in the analysis files
# Used for log-pressure interpolation to GA altitude levels
HRRR_PRESSURE_LEVELS_MB = [1000, 975, 950, 925, 900, 875, 850, 825, 800, 775, 750, 700, 650, 600, 550, 500]
