"""
Tests for MesoWest wind loader.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from src.loaders.load_mesowest_wind import load_mesowest_wind


@pytest.fixture
def mock_wind_dir(tmp_path):
    """Create a temporary wind directory."""
    wind_dir = tmp_path / "wind"
    wind_dir.mkdir()
    return wind_dir


def test_raises_file_not_found_when_directory_missing():
    """Test that FileNotFoundError is raised when wind directory doesn't exist."""
    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", Path("/nonexistent/path")):
        with pytest.raises(FileNotFoundError, match="MesoWest wind directory not found"):
            load_mesowest_wind()


def test_returns_empty_dict_when_no_csv_files(mock_wind_dir, caplog):
    """Test that empty dict is returned when no CSV files exist."""
    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        with caplog.at_level(logging.WARNING):
            result = load_mesowest_wind()

    assert result == {}
    assert "No valid MesoWest wind data loaded" in caplog.text


def test_loads_single_station_csv(mock_wind_dir):
    """Test loading a single station CSV file."""
    # Create a sample CSV for KPDX
    csv_path = mock_wind_dir / "KPDX.csv"
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "wind_speed_set_1": [2.5, 3.0, 2.8],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    assert "KPDX" in result
    assert "mean_wind_ms" in result["KPDX"]
    assert "p90_wind_ms" in result["KPDX"]
    assert result["KPDX"]["mean_wind_ms"] == pytest.approx(2.7666666, rel=1e-5)


def test_loads_multiple_stations(mock_wind_dir):
    """Test loading multiple station CSV files."""
    # Create CSVs for KPDX and KEUG
    for station_id, wind_values in [
        ("KPDX", [2.5, 3.0, 2.8]),
        ("KEUG", [1.5, 2.0, 1.8]),
    ]:
        csv_path = mock_wind_dir / f"{station_id}.csv"
        df = pd.DataFrame({
            "date_time": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "wind_speed_set_1": wind_values,
        })
        df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    assert len(result) == 2
    assert "KPDX" in result
    assert "KEUG" in result


def test_computes_mean_wind_speed(mock_wind_dir):
    """Test that mean wind speed is computed correctly."""
    csv_path = mock_wind_dir / "KPDX.csv"
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        "wind_speed_set_1": [1.0, 2.0, 3.0, 4.0],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    assert result["KPDX"]["mean_wind_ms"] == pytest.approx(2.5)


def test_computes_90th_percentile_wind_speed(mock_wind_dir):
    """Test that 90th-percentile wind speed is computed correctly."""
    csv_path = mock_wind_dir / "KPDX.csv"
    # Create 100 wind speed values: 1, 2, 3, ..., 100
    wind_speeds = list(range(1, 101))
    df = pd.DataFrame({
        "date_time": [f"2024-01-{i:02d}" for i in range(1, 101)],
        "wind_speed_set_1": wind_speeds,
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    # 90th percentile of 1-100 should be approximately 90.9
    assert result["KPDX"]["p90_wind_ms"] == pytest.approx(90.9, rel=0.01)


def test_handles_nan_values(mock_wind_dir):
    """Test that NaN values are skipped."""
    csv_path = mock_wind_dir / "KPDX.csv"
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        "wind_speed_set_1": [1.0, np.nan, 3.0, 4.0],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    # Mean of [1.0, 3.0, 4.0] = 2.666...
    assert result["KPDX"]["mean_wind_ms"] == pytest.approx(2.6666666, rel=1e-5)


def test_handles_missing_wind_speed_column(mock_wind_dir, caplog):
    """Test that CSV with missing wind_speed_set_1 column is skipped."""
    csv_path = mock_wind_dir / "KPDX.csv"
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02"],
        "other_column": [1.0, 2.0],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        with caplog.at_level(logging.WARNING):
            result = load_mesowest_wind()

    assert "KPDX" not in result
    assert "missing 'wind_speed_set_1' column" in caplog.text


def test_handles_invalid_csv_file(mock_wind_dir, caplog):
    """Test that CSV file with missing wind_speed_set_1 column is skipped."""
    csv_path = mock_wind_dir / "KPDX.csv"
    # Create a CSV with valid format but missing the required column
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02"],
        "other_data": [1.0, 2.0],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        with caplog.at_level(logging.WARNING):
            result = load_mesowest_wind()

    assert "KPDX" not in result
    assert "missing 'wind_speed_set_1' column" in caplog.text


def test_handles_all_nan_values(mock_wind_dir, caplog):
    """Test that station with all NaN values is skipped."""
    csv_path = mock_wind_dir / "KPDX.csv"
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "wind_speed_set_1": [np.nan, np.nan, np.nan],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        with caplog.at_level(logging.WARNING):
            result = load_mesowest_wind()

    assert "KPDX" not in result
    assert "No valid wind speed observations" in caplog.text


def test_handles_string_wind_speeds(mock_wind_dir):
    """Test that string wind speeds are converted to numeric."""
    csv_path = mock_wind_dir / "KPDX.csv"
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "wind_speed_set_1": ["2.5", "3.0", "2.8"],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    assert "KPDX" in result
    assert result["KPDX"]["mean_wind_ms"] == pytest.approx(2.7666666, rel=1e-5)


def test_handles_mixed_valid_invalid_values(mock_wind_dir):
    """Test that mixed valid and invalid values are handled correctly."""
    csv_path = mock_wind_dir / "KPDX.csv"
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        "wind_speed_set_1": [1.0, "invalid", 3.0, np.nan],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    # Mean of [1.0, 3.0] = 2.0
    assert result["KPDX"]["mean_wind_ms"] == pytest.approx(2.0)


def test_returns_dict_with_correct_keys(mock_wind_dir):
    """Test that returned dict has correct structure."""
    csv_path = mock_wind_dir / "KPDX.csv"
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02"],
        "wind_speed_set_1": [2.5, 3.0],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    assert isinstance(result, dict)
    assert "KPDX" in result
    assert isinstance(result["KPDX"], dict)
    assert set(result["KPDX"].keys()) == {"mean_wind_ms", "p90_wind_ms"}


def test_wind_speeds_are_floats(mock_wind_dir):
    """Test that returned wind speeds are floats."""
    csv_path = mock_wind_dir / "KPDX.csv"
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02"],
        "wind_speed_set_1": [2.5, 3.0],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    assert isinstance(result["KPDX"]["mean_wind_ms"], float)
    assert isinstance(result["KPDX"]["p90_wind_ms"], float)


def test_p90_greater_than_or_equal_to_mean(mock_wind_dir):
    """Test that 90th percentile is >= mean (property test)."""
    csv_path = mock_wind_dir / "KPDX.csv"
    # Create 100 random wind speeds
    np.random.seed(42)
    wind_speeds = np.random.uniform(0.5, 10.0, 100).tolist()
    df = pd.DataFrame({
        "date_time": [f"2024-01-{i:02d}" for i in range(1, 101)],
        "wind_speed_set_1": wind_speeds,
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    assert result["KPDX"]["p90_wind_ms"] >= result["KPDX"]["mean_wind_ms"]


def test_wind_speeds_non_negative(mock_wind_dir):
    """Test that wind speeds are non-negative (property test)."""
    csv_path = mock_wind_dir / "KPDX.csv"
    df = pd.DataFrame({
        "date_time": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "wind_speed_set_1": [0.0, 2.5, 5.0],
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    assert result["KPDX"]["mean_wind_ms"] >= 0.0
    assert result["KPDX"]["p90_wind_ms"] >= 0.0


def test_large_dataset_performance(mock_wind_dir):
    """Test that loader handles large datasets efficiently."""
    csv_path = mock_wind_dir / "KPDX.csv"
    # Create 10,000 wind speed observations
    wind_speeds = np.random.uniform(0.5, 10.0, 10000).tolist()
    df = pd.DataFrame({
        "date_time": pd.date_range("2024-01-01", periods=10000, freq="h"),
        "wind_speed_set_1": wind_speeds,
    })
    df.to_csv(csv_path, index=False)

    with mock.patch("src.loaders.load_mesowest_wind.MESOWEST_WIND_DIR", mock_wind_dir):
        result = load_mesowest_wind()

    assert "KPDX" in result
    assert result["KPDX"]["mean_wind_ms"] > 0
    assert result["KPDX"]["p90_wind_ms"] > 0
