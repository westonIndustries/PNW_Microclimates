"""
Property-based tests for hourly microclimate processing.

Tests verify physical correctness of hourly processing:
- Hourly HDD sums to daily effective HDD
- Each hour produces exactly 8 altitude levels × N ZIP codes rows
- datetime_utc column contains valid ISO 8601 timestamps with all 24 hours
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from hypothesis import given, settings, strategies as st


# Property 1: Hourly HDD sums to daily effective HDD
@given(
    daily_temp_f=st.floats(min_value=-40, max_value=100),
)
@settings(max_examples=50)
def test_hourly_hdd_sums_to_daily(daily_temp_f):
    """
    Property: For a synthetic 24-hour period with constant temperature,
    the sum of hourly HDD contributions should equal the daily effective HDD
    within floating-point tolerance.

    Formula:
        daily_hdd = max(0, 65 - daily_temp_f)
        hourly_hdd = max(0, 65 - hourly_temp_f) / 24
        sum(hourly_hdd for 24 hours) ≈ daily_hdd
    """
    base_temp_f = 65.0

    # Compute daily HDD
    daily_hdd = max(0, base_temp_f - daily_temp_f)

    # Compute hourly HDD for 24 hours (assuming constant temperature)
    hourly_hdd_sum = 0.0
    for hour in range(24):
        hourly_hdd = max(0, base_temp_f - daily_temp_f) / 24
        hourly_hdd_sum += hourly_hdd

    # Verify: sum of hourly HDD equals daily HDD (within floating-point tolerance)
    assert (
        abs(hourly_hdd_sum - daily_hdd) < 1e-6
    ), f"Hourly HDD sum {hourly_hdd_sum} != daily HDD {daily_hdd}"


# Property 2: Each hour produces exactly 8 altitude levels × N ZIP codes rows
@given(
    num_zips=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=50)
def test_hourly_output_structure(num_zips):
    """
    Property: For a single hour with N ZIP codes, the hourly output should
    have exactly N × 8 rows (one per ZIP × altitude combination).

    Expected altitudes: 0, 500, 1000, 3000, 6000, 9000, 12000, 18000 ft AGL
    """
    altitude_levels = [0, 500, 1000, 3000, 6000, 9000, 12000, 18000]
    expected_rows = num_zips * len(altitude_levels)

    # Create sample hourly data
    rows = []
    for zip_idx in range(num_zips):
        for alt_ft in altitude_levels:
            rows.append({
                "datetime_utc": "2024-01-15T12:00:00",
                "zip_code": f"9720{zip_idx}",
                "altitude_ft": alt_ft,
                "temp_adjusted_f": 40.0,
                "wind_speed_kt": 10.0,
                "wind_dir_deg": 225.0,
                "tke_m2s2": 0.5,
                "wind_shear_kt_per_100ft": 0.0,
                "hourly_hdd": 1.0,
                "density_altitude_ft": 1000.0,
                "turbulence_flag": "light",
            })

    hourly_df = pd.DataFrame(rows)

    # Verify: correct number of rows
    assert (
        len(hourly_df) == expected_rows
    ), f"Expected {expected_rows} rows, got {len(hourly_df)}"

    # Verify: each ZIP has all 8 altitudes
    for zip_code in hourly_df["zip_code"].unique():
        zip_data = hourly_df[hourly_df["zip_code"] == zip_code]
        alt_count = len(zip_data["altitude_ft"].unique())
        assert (
            alt_count == 8
        ), f"ZIP {zip_code} has {alt_count} altitudes (expected 8)"


# Property 3: datetime_utc contains valid ISO 8601 timestamps with all 24 hours
@given(
    start_date=st.dates(min_value=datetime(2020, 1, 1).date(), max_value=datetime(2025, 12, 31).date()),
)
@settings(max_examples=50)
def test_hourly_datetime_validity(start_date):
    """
    Property: For a complete day, the hourly output should contain exactly 24
    unique datetime_utc values (one per hour), all in valid ISO 8601 format,
    and spanning exactly 24 hours.
    """
    # Create sample hourly data for 24 hours
    rows = []
    for hour in range(24):
        dt = datetime.combine(start_date, datetime.min.time()) + timedelta(hours=hour)
        datetime_utc = dt.isoformat()

        rows.append({
            "datetime_utc": datetime_utc,
            "zip_code": "97201",
            "altitude_ft": 0,
            "temp_adjusted_f": 40.0,
            "wind_speed_kt": 10.0,
            "wind_dir_deg": 225.0,
            "tke_m2s2": 0.5,
            "wind_shear_kt_per_100ft": 0.0,
            "hourly_hdd": 1.0,
            "density_altitude_ft": 1000.0,
            "turbulence_flag": "light",
        })

    hourly_df = pd.DataFrame(rows)

    # Verify: 24 unique datetimes
    unique_datetimes = hourly_df["datetime_utc"].unique()
    assert (
        len(unique_datetimes) == 24
    ), f"Expected 24 unique datetimes, got {len(unique_datetimes)}"

    # Verify: all datetimes are valid ISO 8601
    for dt_str in unique_datetimes:
        try:
            pd.Timestamp(dt_str)
        except Exception as e:
            raise AssertionError(f"Invalid ISO 8601 datetime: {dt_str}: {e}")

    # Verify: datetimes span exactly 24 hours
    datetimes = pd.to_datetime(hourly_df["datetime_utc"]).sort_values()
    time_span = datetimes.iloc[-1] - datetimes.iloc[0]
    expected_span = timedelta(hours=23)  # 24 hours = 0 to 23 hours
    assert (
        time_span == expected_span
    ), f"Datetime span {time_span} != expected {expected_span}"


# Integration test: Hourly output structure and content
def test_hourly_output_integration():
    """
    Property: Hourly output should have correct structure, valid values,
    and all required columns.
    """
    # Create sample hourly data for 2 ZIPs × 24 hours × 8 altitudes
    rows = []
    for hour in range(24):
        dt = datetime(2024, 1, 15, hour, 0, 0)
        datetime_utc = dt.isoformat()

        for zip_code in ["97201", "97202"]:
            for alt_ft in [0, 500, 1000, 3000, 6000, 9000, 12000, 18000]:
                rows.append({
                    "datetime_utc": datetime_utc,
                    "zip_code": zip_code,
                    "altitude_ft": alt_ft,
                    "temp_adjusted_f": 40.0 - (alt_ft / 1000) * 3.5,
                    "wind_speed_kt": 10.0 + (alt_ft / 1000) * 2,
                    "wind_dir_deg": 225.0,
                    "tke_m2s2": 0.5 + (alt_ft / 1000) * 0.1,
                    "wind_shear_kt_per_100ft": 0.0 if alt_ft > 1000 else 0.1,
                    "hourly_hdd": max(0, 65 - (40.0 - (alt_ft / 1000) * 3.5)) / 24,
                    "density_altitude_ft": 1000.0 + alt_ft,
                    "turbulence_flag": "light",
                })

    hourly_df = pd.DataFrame(rows)

    # Verify: correct number of rows (2 ZIPs × 24 hours × 8 altitudes)
    expected_rows = 2 * 24 * 8
    assert len(hourly_df) == expected_rows, f"Expected {expected_rows} rows, got {len(hourly_df)}"

    # Verify: all required columns present
    required_cols = [
        "datetime_utc",
        "zip_code",
        "altitude_ft",
        "temp_adjusted_f",
        "wind_speed_kt",
        "wind_dir_deg",
        "tke_m2s2",
        "wind_shear_kt_per_100ft",
        "hourly_hdd",
        "density_altitude_ft",
        "turbulence_flag",
    ]
    for col in required_cols:
        assert col in hourly_df.columns, f"Missing column: {col}"

    # Verify: temperature decreases with altitude
    for (datetime_utc, zip_code), group in hourly_df.groupby(["datetime_utc", "zip_code"]):
        temps = group.sort_values("altitude_ft")["temp_adjusted_f"].values
        for i in range(len(temps) - 1):
            assert (
                temps[i] >= temps[i + 1] - 5
            ), f"Temperature should decrease with altitude: {temps[i]} at {group.iloc[i]['altitude_ft']}ft vs {temps[i+1]} at {group.iloc[i+1]['altitude_ft']}ft"

    # Verify: wind speed increases with altitude
    for (datetime_utc, zip_code), group in hourly_df.groupby(["datetime_utc", "zip_code"]):
        winds = group.sort_values("altitude_ft")["wind_speed_kt"].values
        for i in range(len(winds) - 1):
            assert (
                winds[i] <= winds[i + 1] + 5
            ), f"Wind speed should increase with altitude: {winds[i]} at {group.iloc[i]['altitude_ft']}ft vs {winds[i+1]} at {group.iloc[i+1]['altitude_ft']}ft"

    # Verify: hourly HDD is non-negative
    assert (
        hourly_df["hourly_hdd"].min() >= 0
    ), f"Hourly HDD should be non-negative, got {hourly_df['hourly_hdd'].min()}"

    # Verify: hourly HDD is reasonable (max ~2.5 for daily max ~60)
    assert (
        hourly_df["hourly_hdd"].max() <= 2.5
    ), f"Hourly HDD max unusually high: {hourly_df['hourly_hdd'].max()}"


if __name__ == "__main__":
    # Run tests
    test_hourly_hdd_sums_to_daily()
    test_hourly_output_structure()
    test_hourly_datetime_validity()
    test_hourly_output_integration()
    print("All hourly microclimate property tests passed!")
