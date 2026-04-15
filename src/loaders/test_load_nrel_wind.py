"""Tests for src/loaders/load_nrel_wind.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.loaders.load_nrel_wind import load_nrel_wind


# ---------------------------------------------------------------------------
# FileNotFoundError tests
# ---------------------------------------------------------------------------


def test_raises_file_not_found_when_missing(tmp_path):
    """Raises FileNotFoundError with the full resolved path when file is absent."""
    fake_path = tmp_path / "nonexistent" / "wind.tif"
    with patch("src.loaders.load_nrel_wind.NREL_WIND_RASTER", fake_path):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_nrel_wind()
        assert "wind.tif" in str(exc_info.value)


def test_error_message_contains_full_path(tmp_path):
    """The error message includes the fully resolved path."""
    fake_path = tmp_path / "missing.tif"
    with patch("src.loaders.load_nrel_wind.NREL_WIND_RASTER", fake_path):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_nrel_wind()
        assert str(fake_path.resolve()) in str(exc_info.value)


# ---------------------------------------------------------------------------
# Helper function
# ---------------------------------------------------------------------------


def _make_mock_dataset(array_2d: np.ndarray, nodata, crs_epsg: int = 26910):
    """Create a mock rasterio dataset that returns the given array."""
    mock_ds = MagicMock()
    mock_ds.read.side_effect = lambda band: array_2d.copy()
    mock_ds.nodata = nodata
    mock_ds.transform = MagicMock(name="Affine")
    mock_ds.crs = MagicMock(name="CRS")
    mock_ds.crs.to_epsg.return_value = crs_epsg
    return mock_ds


# ---------------------------------------------------------------------------
# Nodata handling tests
# ---------------------------------------------------------------------------


def test_nodata_replaced_with_nan(tmp_path):
    """Nodata values in the raster are replaced with numpy.nan."""
    fake_path = tmp_path / "wind.tif"
    fake_path.touch()

    raw = np.array([[10.0, -9999.0], [12.0, -9999.0]])
    mock_ds = _make_mock_dataset(raw, nodata=-9999.0)

    with patch("src.loaders.load_nrel_wind.NREL_WIND_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, transform, crs = load_nrel_wind()

    assert np.isnan(array[0, 1])
    assert np.isnan(array[1, 1])
    assert not np.isnan(array[0, 0])
    assert not np.isnan(array[1, 0])


def test_no_nodata_value_leaves_array_unchanged(tmp_path):
    """When dataset.nodata is None, no values are replaced."""
    fake_path = tmp_path / "wind.tif"
    fake_path.touch()

    raw = np.array([[10.0, 12.0], [11.0, 13.0]])
    mock_ds = _make_mock_dataset(raw, nodata=None)

    with patch("src.loaders.load_nrel_wind.NREL_WIND_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, transform, crs = load_nrel_wind()

    assert not np.any(np.isnan(array))


# ---------------------------------------------------------------------------
# Power-law scaling tests
# ---------------------------------------------------------------------------


def test_power_law_scaling_applied(tmp_path):
    """Wind speed is scaled from 80m to 10m using power law: wind_10m = wind_80m × (10/80)^0.143."""
    fake_path = tmp_path / "wind.tif"
    fake_path.touch()

    # Use a simple 80 m/s wind speed for easy verification
    raw = np.array([[10.0, 10.0], [10.0, 10.0]])
    mock_ds = _make_mock_dataset(raw, nodata=None)

    with patch("src.loaders.load_nrel_wind.NREL_WIND_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, _, _ = load_nrel_wind()

    # Expected: 10 × (10/80)^0.143
    scaling_factor = (10.0 / 80.0) ** 0.143
    expected = 10.0 * scaling_factor

    np.testing.assert_array_almost_equal(array, expected)


def test_scaling_factor_is_less_than_one(tmp_path):
    """The scaling factor (10/80)^0.143 is less than 1, so 10m wind < 80m wind."""
    fake_path = tmp_path / "wind.tif"
    fake_path.touch()

    raw = np.array([[10.0]])
    mock_ds = _make_mock_dataset(raw, nodata=None)

    with patch("src.loaders.load_nrel_wind.NREL_WIND_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, _, _ = load_nrel_wind()

    # 10m wind should be less than 80m wind
    assert array[0, 0] < 10.0


def test_scaling_preserves_nan_values(tmp_path):
    """NaN values remain NaN after scaling."""
    fake_path = tmp_path / "wind.tif"
    fake_path.touch()

    raw = np.array([[10.0, -9999.0], [12.0, 11.0]])
    mock_ds = _make_mock_dataset(raw, nodata=-9999.0)

    with patch("src.loaders.load_nrel_wind.NREL_WIND_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, _, _ = load_nrel_wind()

    assert np.isnan(array[0, 1])
    assert not np.isnan(array[0, 0])
    assert not np.isnan(array[1, 0])
    assert not np.isnan(array[1, 1])


# ---------------------------------------------------------------------------
# Return type tests
# ---------------------------------------------------------------------------


def test_returns_float64_array(tmp_path):
    """The returned array is float64 regardless of the source dtype."""
    fake_path = tmp_path / "wind.tif"
    fake_path.touch()

    # Source is int16
    raw = np.array([[10, 12], [11, 13]], dtype=np.int16)
    mock_ds = _make_mock_dataset(raw, nodata=None)

    with patch("src.loaders.load_nrel_wind.NREL_WIND_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, _, _ = load_nrel_wind()

    assert array.dtype == np.float64


def test_returns_tuple_of_three(tmp_path):
    """load_nrel_wind returns a 3-tuple (array, transform, crs)."""
    fake_path = tmp_path / "wind.tif"
    fake_path.touch()

    raw = np.array([[10.0, 12.0], [11.0, 13.0]])
    mock_ds = _make_mock_dataset(raw, nodata=None)

    with patch("src.loaders.load_nrel_wind.NREL_WIND_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        result = load_nrel_wind()

    assert isinstance(result, tuple)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


def test_scaling_factor_constant():
    """The scaling factor (10/80)^0.143 is a constant value."""
    scaling_factor = (10.0 / 80.0) ** 0.143
    # Verify it's approximately 0.7428 (known value)
    assert 0.74 < scaling_factor < 0.75


def test_wind_speed_monotonicity(tmp_path):
    """Higher 80m wind speeds produce higher 10m wind speeds (monotonic)."""
    fake_path = tmp_path / "wind.tif"
    fake_path.touch()

    raw = np.array([[5.0, 10.0], [15.0, 20.0]])
    mock_ds = _make_mock_dataset(raw, nodata=None)

    with patch("src.loaders.load_nrel_wind.NREL_WIND_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, _, _ = load_nrel_wind()

    # Verify monotonicity: if 80m wind increases, 10m wind increases
    assert array[0, 0] < array[0, 1]
    assert array[0, 1] < array[1, 1]
    assert array[1, 0] < array[1, 1]
