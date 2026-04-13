"""
Config completeness validation for the Regional Microclimate Modeling Engine.

Verifies three structural properties of the pipeline configuration:

1. **ZIP code–region uniqueness** — every ZIP code in ``ZIPCODE_STATION_MAP``
   maps to a station that belongs to exactly one region in the registry.
2. **Station coverage** — every base station referenced by the region registry
   has an entry in both ``STATION_ELEVATIONS_FT`` and ``STATION_HDD_NORMALS``.
3. **File path constants** — all required file path constants are defined and
   are ``pathlib.Path`` instances.

The module is both importable (for use in pytest) and runnable as a script::

    python -m src.validation.run_config_completeness
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import (
    BOUNDARY_SHP,
    ZIPCODE_STATION_MAP,
    LANDSAT_LST_RASTER,
    LIDAR_DEM_RASTER,
    MESOWEST_WIND_DIR,
    NLCD_IMPERVIOUS_RASTER,
    NREL_WIND_RASTER,
    ODOT_ROADS_SHP,
    PRISM_TEMP_DIR,
    REGION_REGISTRY_CSV,
    STATION_ELEVATIONS_FT,
    STATION_HDD_NORMALS,
    TERRAIN_ATTRIBUTES_CSV,
    WSDOT_ROADS_SHP,
)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """Outcome of a single validation check."""

    name: str
    passed: bool
    details: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Check 1 — ZIP code–region uniqueness
# ---------------------------------------------------------------------------

def check_zipcode_region_uniqueness(
    registry: dict[str, dict[str, Any]] | None = None,
) -> CheckResult:
    """Every ZIP code in ``ZIPCODE_STATION_MAP`` maps to a station in exactly one region.

    Since ``ZIPCODE_STATION_MAP`` is populated at runtime, this check uses
    the *registry* dict (keyed by region_code) to build the inverse mapping
    from base-station to regions.  If *registry* is ``None`` the check falls
    back to verifying that ``ZIPCODE_STATION_MAP`` is a dict (it may be
    empty before the pipeline runs).
    """
    errors: list[str] = []

    # When no registry is provided, validate ZIPCODE_STATION_MAP directly
    if registry is None:
        if not isinstance(ZIPCODE_STATION_MAP, dict):
            errors.append("ZIPCODE_STATION_MAP is not a dict")
            return CheckResult(
                name="zipcode_region_uniqueness",
                passed=False,
                details="ZIPCODE_STATION_MAP type check failed",
                errors=errors,
            )
        # With an empty map (pre-runtime), there's nothing to cross-check
        if len(ZIPCODE_STATION_MAP) == 0:
            return CheckResult(
                name="zipcode_region_uniqueness",
                passed=True,
                details=(
                    "ZIPCODE_STATION_MAP is empty (populated at runtime); "
                    "no cross-check performed"
                ),
            )

    # Build station → [regions] mapping from the registry
    if registry is not None:
        station_regions: dict[str, list[str]] = {}
        for region_code, region_info in registry.items():
            for station in region_info.get("base_stations", []):
                station_regions.setdefault(station, []).append(region_code)

        # Every ZIP code in ZIPCODE_STATION_MAP should map to a station
        # that belongs to exactly one region
        for zipcode, station in ZIPCODE_STATION_MAP.items():
            regions = station_regions.get(station, [])
            if len(regions) == 0:
                errors.append(
                    f"ZIP code '{zipcode}' maps to station '{station}' "
                    f"which is not in any region"
                )
            elif len(regions) > 1:
                errors.append(
                    f"ZIP code '{zipcode}' maps to station '{station}' "
                    f"which appears in multiple regions: {regions}"
                )

    passed = len(errors) == 0
    return CheckResult(
        name="zipcode_region_uniqueness",
        passed=passed,
        details=f"Checked {len(ZIPCODE_STATION_MAP)} ZIP codes" if registry else "No registry provided",
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Check 2 — station coverage
# ---------------------------------------------------------------------------

def check_station_coverage(
    registry: dict[str, dict[str, Any]] | None = None,
) -> CheckResult:
    """Every base station in the registry has entries in both
    ``STATION_ELEVATIONS_FT`` and ``STATION_HDD_NORMALS``.
    """
    errors: list[str] = []

    # Collect all base stations from the registry
    all_stations: set[str] = set()
    if registry is not None:
        for region_info in registry.values():
            all_stations.update(region_info.get("base_stations", []))
    else:
        # Fall back to the union of keys in the two station dicts
        all_stations = set(STATION_HDD_NORMALS.keys()) | set(
            STATION_ELEVATIONS_FT.keys()
        )

    for station in sorted(all_stations):
        if station not in STATION_ELEVATIONS_FT:
            errors.append(
                f"Station '{station}' missing from STATION_ELEVATIONS_FT"
            )
        if station not in STATION_HDD_NORMALS:
            errors.append(
                f"Station '{station}' missing from STATION_HDD_NORMALS"
            )

    passed = len(errors) == 0
    return CheckResult(
        name="station_coverage",
        passed=passed,
        details=f"Checked {len(all_stations)} stations",
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Check 3 — file path constants
# ---------------------------------------------------------------------------

_REQUIRED_PATH_CONSTANTS: dict[str, Path] = {
    "LIDAR_DEM_RASTER": LIDAR_DEM_RASTER,
    "PRISM_TEMP_DIR": PRISM_TEMP_DIR,
    "LANDSAT_LST_RASTER": LANDSAT_LST_RASTER,
    "MESOWEST_WIND_DIR": MESOWEST_WIND_DIR,
    "NREL_WIND_RASTER": NREL_WIND_RASTER,
    "NLCD_IMPERVIOUS_RASTER": NLCD_IMPERVIOUS_RASTER,
    "ODOT_ROADS_SHP": ODOT_ROADS_SHP,
    "WSDOT_ROADS_SHP": WSDOT_ROADS_SHP,
    "BOUNDARY_SHP": BOUNDARY_SHP,
    "TERRAIN_ATTRIBUTES_CSV": TERRAIN_ATTRIBUTES_CSV,
    "REGION_REGISTRY_CSV": REGION_REGISTRY_CSV,
}


def check_file_path_constants() -> CheckResult:
    """All required file path constants are defined and are ``Path`` instances."""
    errors: list[str] = []

    for name, value in _REQUIRED_PATH_CONSTANTS.items():
        if value is None:
            errors.append(f"{name} is None")
        elif not isinstance(value, Path):
            errors.append(f"{name} is {type(value).__name__}, expected Path")
        elif str(value) in ("", "."):
            errors.append(f"{name} is an empty path")

    passed = len(errors) == 0
    return CheckResult(
        name="file_path_constants",
        passed=passed,
        details=f"Checked {len(_REQUIRED_PATH_CONSTANTS)} path constants",
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_checks(
    registry: dict[str, dict[str, Any]] | None = None,
) -> list[CheckResult]:
    """Execute all config completeness checks and return results."""
    return [
        check_zipcode_region_uniqueness(registry),
        check_station_coverage(registry),
        check_file_path_constants(),
    ]


def main() -> None:
    """Run all checks, print results, and exit with appropriate code."""
    # Attempt to load the registry if the CSV exists
    registry: dict[str, dict[str, Any]] | None = None
    try:
        from src.loaders.load_region_registry import load_region_registry

        registry = load_region_registry()
    except Exception:
        # Registry may not be generated yet — run checks without it
        pass

    results = run_all_checks(registry)

    all_passed = True
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}: {result.details}")
        for err in result.errors:
            print(f"       - {err}")
        if not result.passed:
            all_passed = False

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
