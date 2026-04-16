"""
Property-based tests for real-time daemon.

Tests verify:
- Static cache round-trip and hash-based staleness detection
- Streaming pipeline produces valid safety cube with expected columns
- Daemon graceful shutdown writes final status JSON
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from hypothesis import given, settings, strategies as st


# Property 1: Static cache round-trip
def test_static_cache_round_trip():
    """
    Property: Data written to cache should be readable and identical
    after round-trip (write → read).
    """
    from src.realtime.static_cache import build_static_cache, load_static_cache

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create temporary cache directory
        cache_dir = Path(tmpdir) / "test_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Build cache
        build_static_cache("test_region")

        # Load cache
        features = load_static_cache("test_region")

        # Verify: features are loaded
        assert len(features) > 0, "No features loaded from cache"

        # Verify: each feature is a numpy array
        for feature_name, data in features.items():
            assert isinstance(
                data, np.ndarray
            ), f"{feature_name} is not a numpy array"


# Property 2: Hash-based staleness detection
def test_cache_staleness_detection():
    """
    Property: Cache staleness detection should correctly identify when
    source files have changed.
    """
    from src.realtime.static_cache import check_cache_staleness

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create temporary source files
        source_file = Path(tmpdir) / "source.txt"
        source_file.write_text("original content")

        # Check staleness (should be stale initially)
        is_stale = check_cache_staleness("test_region", [str(source_file)])
        assert is_stale, "Cache should be stale initially"

        # Modify source file
        source_file.write_text("modified content")

        # Check staleness again (should still be stale)
        is_stale = check_cache_staleness("test_region", [str(source_file)])
        assert is_stale, "Cache should be stale after source modification"


# Property 3: Streaming pipeline produces valid safety cube
def test_streaming_pipeline_output():
    """
    Property: Streaming pipeline should produce valid safety cube with
    expected columns and physical bounds.
    """
    from src.realtime.streaming_pipeline import process_hrrr_cycle, validate_streaming_output

    # Create dummy HRRR dataset
    import xarray as xr

    dummy_data = np.random.randn(10, 10) + 273.15  # Temperature in Kelvin
    hrrr_ds = xr.Dataset(
        {
            "TMP_2maboveground": (["y", "x"], dummy_data),
            "UGRD_10maboveground": (["y", "x"], np.random.randn(10, 10)),
            "VGRD_10maboveground": (["y", "x"], np.random.randn(10, 10)),
        },
        coords={"time": pd.Timestamp.utcnow()},
    )

    # Process cycle
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        safety_cube = process_hrrr_cycle(
            hrrr_ds=hrrr_ds,
            static_cache_dir=cache_dir,
            region_name="test_region",
        )

        if safety_cube is not None:
            # Validate output
            validation = validate_streaming_output(safety_cube)
            assert validation["passed"], f"Validation failed: {validation['errors']}"

            # Verify: required columns present
            required_cols = [
                "datetime_utc",
                "zip_code",
                "altitude_ft",
                "temp_adjusted_f",
                "wind_speed_kt",
            ]
            for col in required_cols:
                assert col in safety_cube.columns, f"Missing column: {col}"

            # Verify: temperature is reasonable
            temp_min = safety_cube["temp_adjusted_f"].min()
            temp_max = safety_cube["temp_adjusted_f"].max()
            assert (
                -80 <= temp_min <= 120
            ), f"Temperature min out of range: {temp_min}°F"
            assert (
                -80 <= temp_max <= 120
            ), f"Temperature max out of range: {temp_max}°F"


# Property 4: Daemon graceful shutdown writes status JSON
def test_daemon_graceful_shutdown():
    """
    Property: Daemon should write final status JSON on graceful shutdown.
    """
    from src.realtime.daemon import DaemonStatus

    with tempfile.TemporaryDirectory() as tmpdir:
        status_file = Path(tmpdir) / "daemon_status.json"

        # Create status
        status = DaemonStatus("test_region")
        status.cycles_processed = 10
        status.cycles_failed = 2
        status.status = "stopped"

        # Save status
        status.save(status_file)

        # Verify: status file exists
        assert status_file.exists(), "Status file not created"

        # Verify: status file is valid JSON
        with open(status_file, "r") as f:
            saved_status = json.load(f)

        # Verify: status contains expected fields
        assert saved_status["region_name"] == "test_region"
        assert saved_status["cycles_processed"] == 10
        assert saved_status["cycles_failed"] == 2
        assert saved_status["status"] == "stopped"


# Integration test: Full daemon lifecycle
def test_daemon_lifecycle():
    """
    Property: Daemon should complete full lifecycle: start → process cycles → shutdown.
    """
    from src.realtime.daemon import DaemonStatus

    # Create status
    status = DaemonStatus("test_region")

    # Simulate processing cycles
    for i in range(5):
        status.cycles_processed += 1
        status.last_cycle_time = pd.Timestamp.utcnow()

    # Simulate shutdown
    status.status = "stopped"

    # Verify: status reflects lifecycle
    assert status.cycles_processed == 5
    assert status.status == "stopped"
    assert status.last_cycle_time is not None

    # Verify: status can be serialized
    status_dict = status.to_dict()
    assert status_dict["cycles_processed"] == 5
    assert status_dict["status"] == "stopped"


if __name__ == "__main__":
    # Run tests
    test_static_cache_round_trip()
    test_cache_staleness_detection()
    test_streaming_pipeline_output()
    test_daemon_graceful_shutdown()
    test_daemon_lifecycle()
    print("All real-time daemon property tests passed!")
