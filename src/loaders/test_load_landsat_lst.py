"""Tests for src/loaders/load_landsat_lst.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.loaders.load_landsat_lst import (
    load_landsat_lst,
    LST_SCALE_FACTOR,
    LST_OFFSET,
    KELVIN_TO_CELSIUS,
)


# ---------------------------------------------------------------------------
# File not found tests
# ---------------------------------------------------------------------------


def test_returns_none_when_file_missing(tmp_path, caplog):
    """Returns None with a logged warning when the file is not available."""
    fake_path = tmp_path / "nonexistent" / "lst.tif"
    with patch("src.loaders.load_landsat_lst.LANDSAT_LST_RASTER", fake_path):
        result = load_landsat_lst()

    assert result is None
    assert "not found" in caplog.text.lower()
    assert "proceeding without" in caplog.text.lower()


def test_warning_logged_with_full_path(tmp_path, caplog):
    """The warning message includes the full resolved path."""
    fake_path = tmp_path / "missing.tif"
    with patch("src.loaders.load_landsat_lst.LANDSAT_LST_RASTER", fake_path):
        result = load_landsat_lst()

    assert result is None
    assert str(fake_path.resolve()) in caplog.text


# ---------------------------------------------------------------------------
# Scale factor and offset conversion tests
# ---------------------------------------------------------------------------


def _make_mock_dataset(array_2d: np.ndarray, crs_epsg: int = 26910):
    """Create a mock rasterio dataset that returns the given array."""
    mock_ds = MagicMock()
    mock_ds.read.return_value = array_2d[np.newaxis, :, :]  # rasterio returns (bands, rows, cols)
    mock_ds.read.side_effect = lambda band: array_2d.copy()
    mock_ds.transform = MagicMock(name="Affine")
    mock_ds.crs = MagicMock(name="CRS")
    mock_ds.crs.to_epsg.return_value = crs_epsg
    return mock_ds


def test_applies_scale_factor_and_offset(tmp_path):
    """Scale factor and offset are correctly applied to convert to Kelvin."""
    fake_path = tmp_path / "lst.tif"
    fake_path.touch()

    # Digital numbers from Landsat
    lst_dn = np.array([[10000.0, 20000.0], [30000.0, 40000.0]])
    mock_ds = _make_mock_dataset(lst_dn)

    with patch("src.loaders.load_landsat_lst.LANDSAT_LST_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        result = load_landsat_lst()

    assert result is not None
    array, _, _ = result

    # Expected: (DN * scale_factor + offset) - 273.15
    expected = (lst_dn * LST_SCALE_FACTOR + LST_OFFSET) - KELVIN_TO_CELSIUS
    np.testing.assert_array_almost_equal(array, expected)


def test_converts_to_celsius(tmp_path):
    """Output is in Celsius (Kelvin - 273.15)."""
    fake_path = tmp_path / "lst.tif"
    fake_path.touch()

    # DN that should convert to approximately 300 K (26.85°C)
    # 300 K = (DN * 0.00341802 + 149.0)
    # DN = (300 - 149) / 0.00341802 ≈ 44,100
    lst_dn = np.array([[44100.0]])
    mock_ds = _make_mock_dataset(lst_dn)

    with patch("src.loaders.load_landsat_lst.LANDSAT_LST_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        result = load_landsat_lst()

    assert result is not None
    array, _, _ = result

    # Should be approximately 26.58°C (more precise calculation)
    assert array[0, 0] == pytest.approx(26.58, abs=0.1)


def test_zero_dn_produces_negative_celsius(tmp_path):
    """DN of 0 produces negative Celsius (cold)."""
    fake_path = tmp_path / "lst.tif"
    fake_path.touch()

    lst_dn = np.array([[0.0]])
    mock_ds = _make_mock_dataset(lst_dn)

    with patch("src.loaders.load_landsat_lst.LANDSAT_LST_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        result = load_landsat_lst()

    assert result is not None
    array, _, _ = result

    # DN=0 → K = 0 * 0.00341802 + 149.0 = 149.0 K
    # 149.0 K - 273.15 = -124.15°C
    assert array[0, 0] == pytest.approx(149.0 - KELVIN_TO_CELSIUS)


# ---------------------------------------------------------------------------
# Return type tests
# ---------------------------------------------------------------------------


def test_returns_float64_array(tmp_path):
    """The returned array is float64."""
    fake_path = tmp_path / "lst.tif"
    fake_path.touch()

    lst_dn = np.array([[10000, 20000], [30000, 40000]], dtype=np.int32)
    mock_ds = _make_mock_dataset(lst_dn)

    with patch("src.loaders.load_landsat_lst.LANDSAT_LST_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        result = load_landsat_lst()

    assert result is not None
    array, _, _ = result
    assert array.dtype == np.float64


def test_returns_tuple_of_three_when_available(tmp_path):
    """load_landsat_lst returns a 3-tuple (array, transform, crs) when file exists."""
    fake_path = tmp_path / "lst.tif"
    fake_path.touch()

    lst_dn = np.array([[10000.0, 20000.0], [30000.0, 40000.0]])
    mock_ds = _make_mock_dataset(lst_dn)

    with patch("src.loaders.load_landsat_lst.LANDSAT_LST_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        result = load_landsat_lst()

    assert result is not None
    assert isinstance(result, tuple)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dn_value", [0, 1000, 10000, 50000, 65535])
def test_monotonic_increase_with_dn(tmp_path, dn_value):
    """Celsius temperature increases monotonically with DN value.
    
    **Validates: Requirements 7.1**
    """
    fake_path = tmp_path / "lst.tif"
    fake_path.touch()

    lst_dn = np.array([[float(dn_value)]])
    mock_ds = _make_mock_dataset(lst_dn)

    with patch("src.loaders.load_landsat_lst.LANDSAT_LST_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        result = load_landsat_lst()

    assert result is not None
    array, _, _ = result

    # For any DN value, the output should be:
    # (DN * scale_factor + offset) - 273.15
    expected = (dn_value * LST_SCALE_FACTOR + LST_OFFSET) - KELVIN_TO_CELSIUS
    assert array[0, 0] == pytest.approx(expected)


def test_scale_factor_offset_constants_correct(tmp_path):
    """Scale factor and offset match Landsat 9 Collection 2 specification.
    
    **Validates: Requirements 7.1**
    """
    # These are the official Landsat 9 Collection 2 Level-2 values
    assert LST_SCALE_FACTOR == pytest.approx(0.00341802)
    assert LST_OFFSET == pytest.approx(149.0)
    assert KELVIN_TO_CELSIUS == pytest.approx(273.15)


def test_realistic_temperature_range(tmp_path):
    """Output temperatures are in realistic range for Earth surface.
    
    **Validates: Requirements 7.1**
    """
    fake_path = tmp_path / "lst.tif"
    fake_path.touch()

    # Create a range of DN values that should produce realistic surface temps
    # Realistic surface temps: -50°C to +80°C
    # -50°C = 223.15 K → DN = (223.15 - 149) / 0.00341802 ≈ 21,700
    # +80°C = 353.15 K → DN = (353.15 - 149) / 0.00341802 ≈ 59,700
    lst_dn = np.array([[21700.0, 40000.0, 59700.0]])
    mock_ds = _make_mock_dataset(lst_dn)

    with patch("src.loaders.load_landsat_lst.LANDSAT_LST_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        result = load_landsat_lst()

    assert result is not None
    array, _, _ = result

    # Check that all values are in realistic range
    assert np.all(array >= -60)  # Allow some margin below -50°C
    assert np.all(array <= 90)   # Allow some margin above +80°C


def test_preserves_spatial_structure(tmp_path):
    """Array shape and spatial structure are preserved through conversion.
    
    **Validates: Requirements 7.1**
    """
    fake_path = tmp_path / "lst.tif"
    fake_path.touch()

    # Create a 2D array with distinct values
    lst_dn = np.array([
        [10000.0, 20000.0, 30000.0],
        [40000.0, 50000.0, 60000.0],
        [15000.0, 25000.0, 35000.0],
    ])
    mock_ds = _make_mock_dataset(lst_dn)

    with patch("src.loaders.load_landsat_lst.LANDSAT_LST_RASTER", fake_path), \
         patch("rasterio.open", return_value=MagicMock(__enter__=lambda s: mock_ds, __exit__=MagicMock(return_value=False))):
        result = load_landsat_lst()

    assert result is not None
    array, _, _ = result

    # Shape should be preserved
    assert array.shape == lst_dn.shape
    
    # Relative ordering should be preserved (monotonicity)
    assert array[0, 0] < array[0, 1] < array[0, 2]
    assert array[1, 0] < array[1, 1] < array[1, 2]
