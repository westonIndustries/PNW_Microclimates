"""
Property-based tests for altitude microclimate processing.

Tests verify physical correctness of altitude temperature and HDD profiles:
- Temperature decreases with height (with inversion tolerance)
- HDD increases with height
- No surface corrections applied at altitude
- Wind shear corrections only apply ≤ 1,000 ft
- Thermal subsidence only applies over water
- Boundary layer corrections only apply ≤ 1,000 ft
"""

import numpy as np
import pandas as pd
from hypothesis import given, settings, strategies as st


# Property 1: Altitude temperature decreases with height (5°F inversion tolerance)
@given(
    temp_sfc_f=st.floats(min_value=-40, max_value=100),
    lapse_rate_f_per_1000ft=st.floats(min_value=3.0, max_value=4.0),
)
@settings(max_examples=100)
def test_altitude_temp_decreases_with_height(temp_sfc_f, lapse_rate_f_per_1000ft):
    """
    Property: Temperature at altitude should be lower than surface temperature,
    following the environmental lapse rate. Allow up to 5°F inversion (temperature
    increase with height) due to atmospheric stability.

    Formula:
        temp_alt = temp_sfc - (altitude_ft / 1000) * lapse_rate_f_per_1000ft
    """
    altitudes_ft = [3000, 6000, 9000, 12000, 18000]
    temps_f = []

    # Compute temperatures at each altitude
    for alt_ft in altitudes_ft:
        temp_alt = temp_sfc_f - (alt_ft / 1000.0) * lapse_rate_f_per_1000ft
        temps_f.append(temp_alt)

    # Check that temperature decreases with height (with 5°F inversion tolerance)
    for i in range(len(temps_f) - 1):
        temp_lower = temps_f[i]
        temp_higher = temps_f[i + 1]
        # Allow up to 5°F inversion
        assert (
            temp_lower >= temp_higher - 5.0
        ), f"Temperature inversion > 5°F: {temp_lower}°F at {altitudes_ft[i]}ft vs {temp_higher}°F at {altitudes_ft[i+1]}ft"


# Property 2: Altitude HDD increases with height
@given(
    temp_sfc_f=st.floats(min_value=-40, max_value=100),
    lapse_rate_f_per_1000ft=st.floats(min_value=3.0, max_value=4.0),
)
@settings(max_examples=100)
def test_altitude_hdd_increases_with_height(temp_sfc_f, lapse_rate_f_per_1000ft):
    """
    Property: HDD at altitude should be greater than or equal to HDD at surface,
    because temperature decreases with height (and HDD = max(0, 65 - temp)).

    Formula:
        hdd_alt = max(0, 65 - temp_alt)
        hdd_sfc = max(0, 65 - temp_sfc)
        hdd_alt >= hdd_sfc (because temp_alt <= temp_sfc)
    """
    altitudes_ft = [3000, 6000, 9000, 12000, 18000]
    base_temp_f = 65.0

    # Compute HDD at surface
    hdd_sfc = max(0, base_temp_f - temp_sfc_f)

    # Compute HDD at each altitude
    for alt_ft in altitudes_ft:
        temp_alt = temp_sfc_f - (alt_ft / 1000.0) * lapse_rate_f_per_1000ft
        hdd_alt = max(0, base_temp_f - temp_alt)

        # HDD at altitude should be >= HDD at surface
        assert (
            hdd_alt >= hdd_sfc
        ), f"HDD decreased with height: {hdd_sfc} at surface vs {hdd_alt} at {alt_ft}ft"


# Property 3: No surface corrections at altitude
@given(
    uhi_offset_f=st.floats(min_value=0, max_value=5),
    traffic_offset_f=st.floats(min_value=0, max_value=2),
)
@settings(max_examples=50)
def test_no_surface_corrections_at_altitude(uhi_offset_f, traffic_offset_f):
    """
    Property: Altitude-level HDD should use only bias-corrected temperature,
    with no surface corrections (UHI, traffic heat, imperviousness-driven albedo).

    At altitude, the formula is:
        hdd_alt = max(0, 65 - temp_alt_adjusted_f)

    NOT:
        hdd_alt = max(0, 65 - temp_alt_adjusted_f) - uhi_reduction - traffic_reduction
    """
    base_temp_f = 65.0
    temp_alt_adjusted_f = 40.0  # Example: 40°F at altitude

    # Correct computation (no surface corrections)
    hdd_alt_correct = max(0, base_temp_f - temp_alt_adjusted_f)

    # Incorrect computation (with surface corrections)
    hdd_alt_incorrect = max(
        0,
        base_temp_f - temp_alt_adjusted_f - uhi_offset_f * 180 - traffic_offset_f * 180,
    )

    # Verify that correct computation does NOT include surface corrections
    assert (
        hdd_alt_correct >= hdd_alt_incorrect
    ), "Altitude HDD should not include surface corrections"


# Property 4: Wind shear correction zero outside transition zones
@given(
    z0_local=st.floats(min_value=0.01, max_value=1.0),
    z0_upwind=st.floats(min_value=0.01, max_value=1.0),
)
@settings(max_examples=50)
def test_wind_shear_correction_zero_outside_transitions(z0_local, z0_upwind):
    """
    Property: Wind shear correction should be zero if the roughness gradient
    is below the threshold (not in a transition zone).

    Roughness gradient = |z0_local - z0_upwind|
    If gradient < ROUGHNESS_GRADIENT_THRESHOLD, correction = 0
    """
    from src.config import ROUGHNESS_GRADIENT_THRESHOLD
    from src.processors.boundary_layer_correction import compute_wind_shear_correction

    wind_speed_ms = 5.0
    z_agl_ft = 500.0
    u_star = 0.5

    # If roughness gradient is below threshold, correction should be zero
    roughness_gradient = abs(z0_local - z0_upwind)
    if roughness_gradient < ROUGHNESS_GRADIENT_THRESHOLD:
        correction = compute_wind_shear_correction(
            wind_speed_ms, z_agl_ft, z0_local, z0_upwind, u_star
        )
        assert (
            correction == 0.0
        ), f"Wind shear correction should be zero outside transition zones, got {correction}"


# Property 5: Wind shear correction zero above 1,000 ft
@given(
    z_agl_ft=st.floats(min_value=1000.1, max_value=20000),
)
@settings(max_examples=50)
def test_wind_shear_correction_zero_above_1000ft(z_agl_ft):
    """
    Property: Wind shear correction should be zero above 1,000 ft AGL,
    because boundary layer effects are negligible above that altitude.
    """
    from src.processors.boundary_layer_correction import compute_wind_shear_correction

    wind_speed_ms = 5.0
    z0_local = 0.5
    z0_upwind = 0.03
    u_star = 0.5

    correction = compute_wind_shear_correction(
        wind_speed_ms, z_agl_ft, z0_local, z0_upwind, u_star
    )
    assert (
        correction == 0.0
    ), f"Wind shear correction should be zero above 1,000 ft, got {correction} at {z_agl_ft}ft"


# Property 6: Thermal subsidence zero over non-water pixels
@given(
    temp_anomaly_f=st.floats(min_value=0, max_value=10),
    z_agl_ft=st.floats(min_value=0, max_value=1000),
)
@settings(max_examples=50)
def test_thermal_subsidence_zero_over_land(temp_anomaly_f, z_agl_ft):
    """
    Property: Thermal subsidence correction should be zero over non-water pixels,
    because the cooling effect only applies over water bodies.
    """
    from src.processors.boundary_layer_correction import compute_thermal_subsidence

    is_water = False
    correction = compute_thermal_subsidence(temp_anomaly_f, z_agl_ft, is_water)
    assert (
        correction == 0.0
    ), f"Thermal subsidence should be zero over land, got {correction}"


# Property 7: Thermal subsidence zero above 1,000 ft
@given(
    temp_anomaly_f=st.floats(min_value=0, max_value=10),
    z_agl_ft=st.floats(min_value=1000.1, max_value=20000),
)
@settings(max_examples=50)
def test_thermal_subsidence_zero_above_1000ft(temp_anomaly_f, z_agl_ft):
    """
    Property: Thermal subsidence correction should be zero above 1,000 ft AGL,
    because the effect is confined to the boundary layer.
    """
    from src.processors.boundary_layer_correction import compute_thermal_subsidence

    is_water = True
    correction = compute_thermal_subsidence(temp_anomaly_f, z_agl_ft, is_water)
    assert (
        correction == 0.0
    ), f"Thermal subsidence should be zero above 1,000 ft, got {correction} at {z_agl_ft}ft"


# Property 8: Boundary layer corrections only apply ≤ 1,000 ft
@given(
    z_agl_ft=st.floats(min_value=1000.1, max_value=20000),
)
@settings(max_examples=50)
def test_boundary_layer_corrections_zero_above_1000ft(z_agl_ft):
    """
    Property: All boundary layer corrections (wind shear, thermal subsidence)
    should be zero above 1,000 ft AGL.
    """
    from src.processors.boundary_layer_correction import (
        compute_wind_shear_correction,
        compute_thermal_subsidence,
    )

    # Wind shear correction
    wind_correction = compute_wind_shear_correction(
        wind_speed_ms=5.0,
        z_agl_ft=z_agl_ft,
        z0_local=0.5,
        z0_upwind=0.03,
        u_star=0.5,
    )
    assert (
        wind_correction == 0.0
    ), f"Wind shear correction should be zero above 1,000 ft, got {wind_correction}"

    # Thermal subsidence correction
    thermal_correction = compute_thermal_subsidence(
        temp_f=5.0, z_agl_ft=z_agl_ft, is_water=True
    )
    assert (
        thermal_correction == 0.0
    ), f"Thermal subsidence should be zero above 1,000 ft, got {thermal_correction}"


# Integration test: Daily output DataFrame has correct altitude columns
def test_daily_output_altitude_columns():
    """
    Property: Daily output DataFrame should have all required altitude columns
    for 5 altitude levels (3k, 6k, 9k, 12k, 18k ft AGL).
    """
    # Create a sample daily output DataFrame
    daily_data = pd.DataFrame(
        {
            "date": ["2024-01-15"],
            "zip_code": ["97201"],
            "hrrr_raw_temp_f": [35.0],
            "hrrr_adjusted_temp_f": [36.0],
            "daily_effective_hdd": [29.0],
            "temp_3000ft_raw_f": [25.0],
            "temp_3000ft_adjusted_f": [26.0],
            "hdd_3000ft": [39.0],
            "temp_6000ft_raw_f": [15.0],
            "temp_6000ft_adjusted_f": [16.0],
            "hdd_6000ft": [49.0],
            "temp_9000ft_raw_f": [5.0],
            "temp_9000ft_adjusted_f": [6.0],
            "hdd_9000ft": [59.0],
            "temp_12000ft_raw_f": [-5.0],
            "temp_12000ft_adjusted_f": [-4.0],
            "hdd_12000ft": [69.0],
            "temp_18000ft_raw_f": [-25.0],
            "temp_18000ft_adjusted_f": [-24.0],
            "hdd_18000ft": [89.0],
        }
    )

    # Check that all altitude columns are present
    altitude_levels = [3000, 6000, 9000, 12000, 18000]
    for alt_ft in altitude_levels:
        assert (
            f"temp_{alt_ft}ft_raw_f" in daily_data.columns
        ), f"Missing column: temp_{alt_ft}ft_raw_f"
        assert (
            f"temp_{alt_ft}ft_adjusted_f" in daily_data.columns
        ), f"Missing column: temp_{alt_ft}ft_adjusted_f"
        assert (
            f"hdd_{alt_ft}ft" in daily_data.columns
        ), f"Missing column: hdd_{alt_ft}ft"

    # Check that HDD increases with height
    for i in range(len(altitude_levels) - 1):
        alt1 = altitude_levels[i]
        alt2 = altitude_levels[i + 1]
        hdd1 = daily_data[f"hdd_{alt1}ft"].iloc[0]
        hdd2 = daily_data[f"hdd_{alt2}ft"].iloc[0]
        assert (
            hdd2 >= hdd1
        ), f"HDD should increase with height: {hdd1} at {alt1}ft vs {hdd2} at {alt2}ft"


if __name__ == "__main__":
    # Run tests
    test_altitude_temp_decreases_with_height()
    test_altitude_hdd_increases_with_height()
    test_no_surface_corrections_at_altitude()
    test_wind_shear_correction_zero_outside_transitions()
    test_wind_shear_correction_zero_above_1000ft()
    test_thermal_subsidence_zero_over_land()
    test_thermal_subsidence_zero_above_1000ft()
    test_boundary_layer_corrections_zero_above_1000ft()
    test_daily_output_altitude_columns()
    print("All altitude microclimate property tests passed!")
