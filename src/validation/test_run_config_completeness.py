"""Tests for src/validation/run_config_completeness.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.validation.run_config_completeness import (
    CheckResult,
    check_zipcode_region_uniqueness,
    check_file_path_constants,
    check_station_coverage,
    run_all_checks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry(
    stations_by_region: dict[str, list[str]] | None = None,
) -> dict[str, dict]:
    """Build a minimal registry dict for testing."""
    if stations_by_region is None:
        stations_by_region = {"R1": ["KPDX", "KEUG"]}
    return {
        code: {"base_stations": stations, "zip_codes": []}
        for code, stations in stations_by_region.items()
    }


# ---------------------------------------------------------------------------
# Check 1 — ZIP code–region uniqueness
# ---------------------------------------------------------------------------


class TestZipcodeRegionUniqueness:
    def test_empty_map_passes(self):
        """An empty ZIPCODE_STATION_MAP (pre-runtime) is valid."""
        result = check_zipcode_region_uniqueness(registry=None)
        assert result.passed

    def test_all_zipcodes_in_one_region(self):
        """ZIP codes mapping to stations in exactly one region pass."""
        registry = _make_registry({"R1": ["KPDX", "KEUG"]})
        with patch(
            "src.validation.run_config_completeness.ZIPCODE_STATION_MAP",
            {"97201": "KPDX", "97401": "KEUG"},
        ):
            result = check_zipcode_region_uniqueness(registry)
        assert result.passed
        assert len(result.errors) == 0

    def test_zipcode_station_not_in_registry(self):
        """A ZIP code mapping to an unknown station is flagged."""
        registry = _make_registry({"R1": ["KPDX"]})
        with patch(
            "src.validation.run_config_completeness.ZIPCODE_STATION_MAP",
            {"97201": "KXYZ"},
        ):
            result = check_zipcode_region_uniqueness(registry)
        assert not result.passed
        assert any("KXYZ" in e for e in result.errors)

    def test_station_in_multiple_regions(self):
        """A station appearing in two regions is flagged for its ZIP code."""
        registry = _make_registry({"R1": ["KPDX"], "R2": ["KPDX"]})
        with patch(
            "src.validation.run_config_completeness.ZIPCODE_STATION_MAP",
            {"97201": "KPDX"},
        ):
            result = check_zipcode_region_uniqueness(registry)
        assert not result.passed
        assert any("multiple regions" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Check 2 — station coverage
# ---------------------------------------------------------------------------


class TestStationCoverage:
    def test_all_stations_present(self):
        """Stations in both dicts pass."""
        registry = _make_registry({"R1": ["KPDX"]})
        result = check_station_coverage(registry)
        assert result.passed

    def test_station_missing_from_elevations(self):
        """A station missing from STATION_ELEVATIONS_FT is flagged."""
        registry = _make_registry({"R1": ["KPDX", "KFOO"]})
        result = check_station_coverage(registry)
        assert not result.passed
        assert any("KFOO" in e and "ELEVATIONS" in e for e in result.errors)

    def test_station_missing_from_hdd(self):
        """A station missing from STATION_HDD_NORMALS is flagged."""
        registry = _make_registry({"R1": ["KBAR"]})
        result = check_station_coverage(registry)
        assert not result.passed
        assert any("KBAR" in e and "HDD" in e for e in result.errors)

    def test_no_registry_falls_back_to_config_keys(self):
        """Without a registry, checks the union of config dict keys."""
        result = check_station_coverage(registry=None)
        assert result.passed
        assert "11 stations" in result.details


# ---------------------------------------------------------------------------
# Check 3 — file path constants
# ---------------------------------------------------------------------------


class TestFilePathConstants:
    def test_all_paths_defined(self):
        """All required path constants are defined in the current config."""
        result = check_file_path_constants()
        assert result.passed
        assert "11 path constants" in result.details

    def test_none_path_flagged(self):
        """A None path constant is flagged."""
        with patch(
            "src.validation.run_config_completeness._REQUIRED_PATH_CONSTANTS",
            {"LIDAR_DEM_RASTER": None},
        ):
            result = check_file_path_constants()
        assert not result.passed
        assert any("None" in e for e in result.errors)

    def test_non_path_type_flagged(self):
        """A string (not Path) constant is flagged."""
        with patch(
            "src.validation.run_config_completeness._REQUIRED_PATH_CONSTANTS",
            {"LIDAR_DEM_RASTER": "/some/path"},
        ):
            result = check_file_path_constants()
        assert not result.passed
        assert any("str" in e for e in result.errors)

    def test_empty_path_flagged(self):
        """An empty Path is flagged."""
        with patch(
            "src.validation.run_config_completeness._REQUIRED_PATH_CONSTANTS",
            {"LIDAR_DEM_RASTER": Path("")},
        ):
            result = check_file_path_constants()
        assert not result.passed
        assert any("empty" in e for e in result.errors)


# ---------------------------------------------------------------------------
# run_all_checks
# ---------------------------------------------------------------------------


class TestRunAllChecks:
    def test_returns_three_results(self):
        results = run_all_checks()
        assert len(results) == 3
        assert all(isinstance(r, CheckResult) for r in results)

    def test_all_pass_with_current_config(self):
        results = run_all_checks()
        assert all(r.passed for r in results)
