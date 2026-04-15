"""
Tests for NLCD imperviousness loader.

Tests cover:
- File not found error handling
- Sentinel value replacement (127, 255 → nan)
- Valid value clipping to 0–100
- Return type and shape validation
- Edge cases (all nan, all valid, mixed values)
- Property-based tests for value ranges and sentinel handling
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine

from src.loaders.load_nlcd_impervious import load_nlcd_impervious


def _make_mock_dataset(
    array: np.ndarray,
    transform: Affine | None = None,
    crs: CRS | None = None,
) -> rasterio.DatasetReader:
    """Create a mock rasterio dataset for testing."""
    if transform is None:
        transform = Affine.identity()
    if crs is None:
        crs = CRS.from_epsg(26910)

    class MockDataset:
        def __init__(self, data, trans, c):
            self.data = data
            self.transform = trans
            self.crs = c

        def read(self, band):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return MockDataset(array, transform, crs)


def _patch_and_load(array, transform=None, crs=None):
    """Helper to patch file existence and rasterio.open, then call load_nlcd_impervious."""
    mock_ds = _make_mock_dataset(array, transform, crs)
    
    with patch("rasterio.open", return_value=mock_ds):
        with patch("pathlib.Path.exists", return_value=True):
            return load_nlcd_impervious()


# ============================================================================
# Error Handling Tests
# ============================================================================


def test_raises_file_not_found_when_file_missing():
    """Test that FileNotFoundError is raised when NLCD file does not exist."""
    with patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(FileNotFoundError, match="NLCD imperviousness file not found"):
            load_nlcd_impervious()


# ============================================================================
# Sentinel Value Replacement Tests
# ============================================================================


def test_replaces_sentinel_127_with_nan():
    """Test that sentinel value 127 is replaced with nan."""
    array = np.array([[50, 127, 75], [100, 127, 25]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    assert np.isnan(result[0, 1])
    assert np.isnan(result[1, 1])
    assert result[0, 0] == 50
    assert result[0, 2] == 75


def test_replaces_sentinel_255_with_nan():
    """Test that sentinel value 255 is replaced with nan."""
    array = np.array([[50, 255, 75], [100, 255, 25]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    assert np.isnan(result[0, 1])
    assert np.isnan(result[1, 1])
    assert result[0, 0] == 50
    assert result[0, 2] == 75


def test_replaces_both_sentinels_with_nan():
    """Test that both sentinel values (127 and 255) are replaced with nan."""
    array = np.array([[50, 127, 75], [100, 255, 25]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    assert np.isnan(result[0, 1])
    assert np.isnan(result[1, 1])
    assert result[0, 0] == 50
    assert result[0, 2] == 75
    assert result[1, 0] == 100
    assert result[1, 2] == 25


def test_preserves_valid_values_near_sentinels():
    """Test that valid values near sentinel values are preserved."""
    array = np.array([[126, 127, 128], [254, 255, 0]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    assert result[0, 0] == 100  # 126 clipped to 100
    assert np.isnan(result[0, 1])  # 127 is sentinel
    assert result[0, 2] == 100  # 128 clipped to 100
    assert result[1, 0] == 100  # 254 clipped to 100
    assert np.isnan(result[1, 1])  # 255 is sentinel
    assert result[1, 2] == 0  # 0 is valid


# ============================================================================
# Value Clipping Tests
# ============================================================================


def test_clips_values_above_100_to_100():
    """Test that values above 100 are clipped to 100."""
    array = np.array([[101, 150, 200], [255, 127, 100]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    assert result[0, 0] == 100  # 101 clipped to 100
    assert result[0, 1] == 100  # 150 clipped to 100
    assert result[0, 2] == 100  # 200 clipped to 100
    assert np.isnan(result[1, 0])  # 255 is sentinel
    assert np.isnan(result[1, 1])  # 127 is sentinel
    assert result[1, 2] == 100  # 100 is valid


def test_clips_values_below_0_to_0():
    """Test that negative values are clipped to 0."""
    # Note: uint8 cannot represent negative values, so we use float array
    array = np.array([[-5, 0, 50], [100, 127, 255]], dtype=np.float32)
    result, _, _ = _patch_and_load(array)

    assert result[0, 0] == 0  # -5 clipped to 0
    assert result[0, 1] == 0  # 0 is valid
    assert result[0, 2] == 50  # 50 is valid
    assert result[1, 0] == 100  # 100 is valid
    assert np.isnan(result[1, 1])  # 127 is sentinel
    assert np.isnan(result[1, 2])  # 255 is sentinel


def test_preserves_valid_range_0_to_100():
    """Test that valid values in 0–100 range are preserved."""
    array = np.array([[0, 25, 50], [75, 100, 50]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    assert result[0, 0] == 0
    assert result[0, 1] == 25
    assert result[0, 2] == 50
    assert result[1, 0] == 75
    assert result[1, 1] == 100
    assert result[1, 2] == 50


# ============================================================================
# Return Type and Shape Tests
# ============================================================================


def test_returns_tuple_of_three():
    """Test that the function returns a tuple of three elements."""
    array = np.array([[50, 75, 100]], dtype=np.uint8)
    result = _patch_and_load(array)

    assert isinstance(result, tuple)
    assert len(result) == 3


def test_returns_float64_array():
    """Test that the returned array is float64."""
    array = np.array([[50, 75, 100]], dtype=np.uint8)
    result_array, _, _ = _patch_and_load(array)

    assert result_array.dtype == np.float64


def test_returns_affine_transform():
    """Test that the returned transform is an Affine object."""
    array = np.array([[50, 75, 100]], dtype=np.uint8)
    transform = Affine(30.0, 0.0, 500000.0, 0.0, -30.0, 5000000.0)
    _, returned_transform, _ = _patch_and_load(array, transform=transform)

    assert returned_transform == transform


def test_returns_crs():
    """Test that the returned CRS is correct."""
    array = np.array([[50, 75, 100]], dtype=np.uint8)
    crs = CRS.from_epsg(26910)
    _, _, returned_crs = _patch_and_load(array, crs=crs)

    assert returned_crs == crs


def test_output_shape_matches_input():
    """Test that output array shape matches input shape."""
    array = np.array([[50, 75, 100], [25, 50, 75], [0, 100, 50]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    assert result.shape == array.shape


# ============================================================================
# Edge Case Tests
# ============================================================================


def test_handles_all_nan_array():
    """Test that an array of all sentinel values becomes all nan."""
    array = np.array([[127, 255, 127], [255, 127, 255]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    assert np.all(np.isnan(result))


def test_handles_all_valid_array():
    """Test that an array of all valid values is preserved."""
    array = np.array([[0, 50, 100], [25, 75, 50]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    expected = np.array([[0, 50, 100], [25, 75, 50]], dtype=np.float64)
    np.testing.assert_array_equal(result, expected)


def test_handles_single_pixel():
    """Test that a single-pixel array is handled correctly."""
    array = np.array([[50]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    assert result.shape == (1, 1)
    assert result[0, 0] == 50


def test_handles_large_array():
    """Test that a large array is handled correctly."""
    array = np.random.randint(0, 101, size=(1000, 1000), dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    assert result.shape == (1000, 1000)
    assert np.all((result >= 0) & (result <= 100) | np.isnan(result))


# ============================================================================
# Property-Based Tests
# ============================================================================


def test_output_values_in_valid_range_or_nan_property():
    """**Validates: Requirements 2.6**
    
    Property: All output values are either in [0, 100] or nan.
    """
    # Generate random array with mix of valid and sentinel values
    array = np.random.choice([0, 25, 50, 75, 100, 127, 255], size=(100, 100)).astype(np.uint8)
    result, _, _ = _patch_and_load(array)

    # Check that all values are either in [0, 100] or nan
    valid_mask = ~np.isnan(result)
    assert np.all((result[valid_mask] >= 0) & (result[valid_mask] <= 100))


def test_sentinel_values_always_become_nan_property():
    """**Validates: Requirements 2.6**
    
    Property: Sentinel values (127, 255) are always replaced with nan.
    """
    # Create array with known sentinel positions
    array = np.array([[50, 127, 75], [100, 255, 25], [127, 255, 50]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    # Check that positions with sentinel values are now nan
    assert np.isnan(result[0, 1])  # 127
    assert np.isnan(result[1, 1])  # 255
    assert np.isnan(result[2, 0])  # 127
    assert np.isnan(result[2, 1])  # 255


def test_valid_values_preserved_property():
    """**Validates: Requirements 2.6**
    
    Property: Valid values in [0, 100] are preserved unchanged.
    """
    # Create array with only valid values
    array = np.array([[0, 25, 50], [75, 100, 10], [99, 1, 50]], dtype=np.uint8)
    result, _, _ = _patch_and_load(array)

    expected = array.astype(np.float64)
    np.testing.assert_array_equal(result, expected)


def test_out_of_range_values_clipped_property():
    """**Validates: Requirements 2.6**
    
    Property: Values outside [0, 100] (excluding sentinels) are clipped to [0, 100].
    """
    # Create array with out-of-range values
    array = np.array([[-10, 0, 50], [100, 110, 200]], dtype=np.float32)
    result, _, _ = _patch_and_load(array)

    # Check that out-of-range values are clipped
    assert result[0, 0] == 0  # -10 clipped to 0
    assert result[0, 1] == 0  # 0 is valid
    assert result[0, 2] == 50  # 50 is valid
    assert result[1, 0] == 100  # 100 is valid
    assert result[1, 1] == 100  # 110 clipped to 100
    assert result[1, 2] == 100  # 200 clipped to 100
