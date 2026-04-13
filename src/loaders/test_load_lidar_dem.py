"""Tests for src/loaders/load_lidar_dem.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import numpy as np
import pytest

from src.loaders.load_lidar_dem import load_lidar_dem


# ---------------------------------------------------------------------------
# FileNotFoundError tests
# ---------------------------------------------------------------------------


def test_raises_file_not_found_when_missing(tmp_path):
    """Raises FileNotFoundError with the full resolved path when file is absent."""
    fake_path = tmp_path / "nonexistent" / "dem.tif"
    with patch("src.loaders.load_lidar_dem.LIDAR_DEM_RASTER", fake_path):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_lidar_dem()
        assert "dem.tif" in str(exc_info.value)


def test_error_message_contains_full_path(tmp_path):
    """The error message includes the fully resolved path."""
    fake_path = tmp_path / "missing.tif"
    with patch("src.loaders.load_lidar_dem.LIDAR_DEM_RASTER", fake_path):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_lidar_dem()
        # The resolved path should appear in the message
        assert str(fake_path.resolve()) in str(exc_info.value)


# ---------------------------------------------------------------------------
# Nodata handling tests
# ---------------------------------------------------------------------------


def _make_mock_dataset(array_2d: np.ndarray, nodata, crs_epsg: int = 26910):
    """Create a mock rasterio dataset that returns the given array."""
    mock_ds = MagicMock()
    mock_ds.read.return_value = array_2d[np.newaxis, :, :]  # rasterio returns (bands, rows, cols)
    mock_ds.read.side_effect = lambda band: array_2d.copy()
    mock_ds.nodata = nodata
    mock_ds.transform = MagicMock(name="Affine")
    mock_ds.crs = MagicMock(name="CRS")
    mock_ds.crs.to_epsg.return_value = crs_epsg
    return mock_ds


def test_nodata_replaced_with_nan(tmp_path):
    """Nodata values in the raster are replaced with numpy.nan."""
    fake_path = tmp_path / "dem.tif"
    fake_path.touch()

    raw = np.array([[100.0, -9999.0], [200.0, -9999.0]])
    mock_ds = _make_mock_dataset(raw, nodata=-9999.0)

    with patch("src.loaders.load_lidar_dem.LIDAR_DEM_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, transform, crs = load_lidar_dem()

    assert np.isnan(array[0, 1])
    assert np.isnan(array[1, 1])
    assert array[0, 0] == pytest.approx(100.0)
    assert array[1, 0] == pytest.approx(200.0)


def test_no_nodata_value_leaves_array_unchanged(tmp_path):
    """When dataset.nodata is None, no values are replaced."""
    fake_path = tmp_path / "dem.tif"
    fake_path.touch()

    raw = np.array([[100.0, 200.0], [300.0, 400.0]])
    mock_ds = _make_mock_dataset(raw, nodata=None)

    with patch("src.loaders.load_lidar_dem.LIDAR_DEM_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, transform, crs = load_lidar_dem()

    assert not np.any(np.isnan(array))
    np.testing.assert_array_equal(array, raw)


# ---------------------------------------------------------------------------
# Return type tests
# ---------------------------------------------------------------------------


def test_returns_float64_array(tmp_path):
    """The returned array is float64 regardless of the source dtype."""
    fake_path = tmp_path / "dem.tif"
    fake_path.touch()

    # Source is int16
    raw = np.array([[100, 200], [300, 400]], dtype=np.int16)
    mock_ds = _make_mock_dataset(raw, nodata=None)

    with patch("src.loaders.load_lidar_dem.LIDAR_DEM_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, transform, crs = load_lidar_dem()

    assert array.dtype == np.float64


def test_returns_tuple_of_three(tmp_path):
    """load_lidar_dem returns a 3-tuple (array, transform, crs)."""
    fake_path = tmp_path / "dem.tif"
    fake_path.touch()

    raw = np.array([[1.0, 2.0], [3.0, 4.0]])
    mock_ds = _make_mock_dataset(raw, nodata=None)

    with patch("src.loaders.load_lidar_dem.LIDAR_DEM_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        result = load_lidar_dem()

    assert isinstance(result, tuple)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Integer nodata test
# ---------------------------------------------------------------------------


def test_integer_nodata_replaced(tmp_path):
    """Integer nodata values (e.g., -32768) are correctly replaced with nan."""
    fake_path = tmp_path / "dem.tif"
    fake_path.touch()

    raw = np.array([[500.0, -32768.0], [-32768.0, 750.0]])
    mock_ds = _make_mock_dataset(raw, nodata=-32768)

    with patch("src.loaders.load_lidar_dem.LIDAR_DEM_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        array, _, _ = load_lidar_dem()

    assert np.isnan(array[0, 1])
    assert np.isnan(array[1, 0])
    assert array[0, 0] == pytest.approx(500.0)
    assert array[1, 1] == pytest.approx(750.0)
