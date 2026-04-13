"""Tests for src/loaders/load_region_registry.py."""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.loaders.load_region_registry import (
    _haversine_km,
    _nearest_station,
    _csv_has_data,
    generate_region_registry,
    load_region_registry,
)


# ---------------------------------------------------------------------------
# Haversine tests
# ---------------------------------------------------------------------------


def test_haversine_same_point():
    """Distance from a point to itself is zero."""
    assert _haversine_km(45.0, -122.0, 45.0, -122.0) == pytest.approx(0.0)


def test_haversine_known_distance():
    """Portland (KPDX) to Eugene (KEUG) is roughly 160-180 km."""
    d = _haversine_km(45.5898, -122.5951, 44.1246, -123.2190)
    assert 150 < d < 200


# ---------------------------------------------------------------------------
# Nearest station tests
# ---------------------------------------------------------------------------


def test_nearest_station_portland():
    """A point near Portland airport should map to KPDX."""
    station = _nearest_station(45.59, -122.60)
    assert station == "KPDX"


def test_nearest_station_eugene():
    """A point near Eugene airport should map to KEUG."""
    station = _nearest_station(44.12, -123.22)
    assert station == "KEUG"


# ---------------------------------------------------------------------------
# CSV helper tests
# ---------------------------------------------------------------------------


def test_csv_has_data_missing_file(tmp_path):
    assert _csv_has_data(tmp_path / "nope.csv") is False


def test_csv_has_data_header_only(tmp_path):
    p = tmp_path / "header.csv"
    p.write_text("a,b,c\n")
    assert _csv_has_data(p) is False


def test_csv_has_data_with_rows(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b,c\n1,2,3\n")
    assert _csv_has_data(p) is True


# ---------------------------------------------------------------------------
# Generate tests
# ---------------------------------------------------------------------------


def _write_zipcodes(path: Path) -> None:
    """Write a small zipcodes CSV for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "zip_code": ["97201", "97202", "98001"],
            "state": ["OR", "OR", "WA"],
            "po_name": ["Portland", "Portland", "Auburn"],
            "region_code": ["R1", "R1", "R1"],
            "centroid_lon": [-122.69, -122.63, -122.26],
            "centroid_lat": [45.52, 45.48, 47.30],
        }
    )
    df.to_csv(path, index=False)


def test_generate_raises_when_zipcodes_missing(tmp_path):
    """generate_region_registry raises FileNotFoundError when zipcodes CSV is absent."""
    fake_zip = tmp_path / "zipcodes.csv"
    fake_reg = tmp_path / "registry.csv"
    with patch("src.loaders.load_region_registry.ZIPCODES_CSV", fake_zip), \
         patch("src.loaders.load_region_registry.REGION_REGISTRY_CSV", fake_reg):
        with pytest.raises(FileNotFoundError, match="task 7.3"):
            generate_region_registry()


def test_generate_raises_when_zipcodes_header_only(tmp_path):
    """generate_region_registry raises FileNotFoundError when zipcodes CSV has only headers."""
    fake_zip = tmp_path / "zipcodes.csv"
    fake_zip.write_text("zip_code,state,po_name,region_code,centroid_lon,centroid_lat\n")
    fake_reg = tmp_path / "registry.csv"
    with patch("src.loaders.load_region_registry.ZIPCODES_CSV", fake_zip), \
         patch("src.loaders.load_region_registry.REGION_REGISTRY_CSV", fake_reg):
        with pytest.raises(FileNotFoundError, match="task 7.3"):
            generate_region_registry()


def test_generate_creates_registry(tmp_path):
    """generate_region_registry writes a valid CSV with expected columns."""
    fake_zip = tmp_path / "zipcodes.csv"
    _write_zipcodes(fake_zip)
    fake_reg = tmp_path / "registry.csv"

    with patch("src.loaders.load_region_registry.ZIPCODES_CSV", fake_zip), \
         patch("src.loaders.load_region_registry.REGION_REGISTRY_CSV", fake_reg):
        df = generate_region_registry()

    assert fake_reg.exists()
    assert list(df.columns) == [
        "zip_code", "state", "region_code", "region_name", "base_station", "lidar_vintage",
    ]
    assert len(df) == 3
    assert set(df["region_code"]) == {"R1"}
    assert set(df["region_name"]) == {"region_1"}
    assert all(df["lidar_vintage"] == 2021)
    # Every base_station should be a valid NOAA station code
    from src.config import STATION_HDD_NORMALS
    assert all(s in STATION_HDD_NORMALS for s in df["base_station"])


# ---------------------------------------------------------------------------
# Load tests
# ---------------------------------------------------------------------------


def test_load_region_registry_structure(tmp_path):
    """load_region_registry returns a dict with expected keys and types."""
    fake_zip = tmp_path / "zipcodes.csv"
    _write_zipcodes(fake_zip)
    fake_reg = tmp_path / "registry.csv"

    with patch("src.loaders.load_region_registry.ZIPCODES_CSV", fake_zip), \
         patch("src.loaders.load_region_registry.REGION_REGISTRY_CSV", fake_reg):
        regions = load_region_registry()

    assert "R1" in regions
    r1 = regions["R1"]
    assert r1["region_name"] == "region_1"
    assert isinstance(r1["base_stations"], list)
    assert len(r1["base_stations"]) > 0
    assert isinstance(r1["bounding_box"], dict)
    assert set(r1["bounding_box"].keys()) == {"minx", "miny", "maxx", "maxy"}
    assert r1["lidar_vintage"] == 2021
    assert set(r1["zip_codes"]) == {"97201", "97202", "98001"}


def test_load_bounding_box_padding(tmp_path):
    """Bounding box should be padded by 0.5° from centroid extremes."""
    fake_zip = tmp_path / "zipcodes.csv"
    _write_zipcodes(fake_zip)
    fake_reg = tmp_path / "registry.csv"

    with patch("src.loaders.load_region_registry.ZIPCODES_CSV", fake_zip), \
         patch("src.loaders.load_region_registry.REGION_REGISTRY_CSV", fake_reg):
        regions = load_region_registry()

    bbox = regions["R1"]["bounding_box"]
    # centroid_lon range: -122.69 to -122.26 → minx = -123.19, maxx = -121.76
    assert bbox["minx"] == pytest.approx(-122.69 - 0.5)
    assert bbox["maxx"] == pytest.approx(-122.26 + 0.5)
    # centroid_lat range: 45.48 to 47.30 → miny = 44.98, maxy = 47.80
    assert bbox["miny"] == pytest.approx(45.48 - 0.5)
    assert bbox["maxy"] == pytest.approx(47.30 + 0.5)


def test_load_triggers_generate_when_empty(tmp_path):
    """load_region_registry auto-generates when registry CSV is header-only."""
    fake_zip = tmp_path / "zipcodes.csv"
    _write_zipcodes(fake_zip)
    fake_reg = tmp_path / "registry.csv"
    # Write header-only CSV
    fake_reg.write_text("zip_code,state,region_code,region_name,base_station,lidar_vintage\n")

    with patch("src.loaders.load_region_registry.ZIPCODES_CSV", fake_zip), \
         patch("src.loaders.load_region_registry.REGION_REGISTRY_CSV", fake_reg):
        regions = load_region_registry()

    assert "R1" in regions
    assert len(regions["R1"]["zip_codes"]) == 3
