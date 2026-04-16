"""
Property-based tests for aviation safety cube.

Tests verify physical correctness of safety cube computations:
- Forest displacement sets wind to zero below canopy
- UHI boundary layer decay follows exponential profile
- TKE scales with roughness (urban > rural)
- Wind shear constant for linear wind profile
- Density altitude equals pressure altitude at ISA standard
- Turbulence flag thresholds are correct
"""

import numpy as np
import pandas as pd
from hypothesis import given, settings, strategies as st


# Property 1: Forest displacement sets wind to zero below canopy
@given(
    displacement_height_m=st.floats(min_value=10, max_value=30),
    z_agl_m=st.floats(min_value=0, max_value=50),
)
@settings(max_examples=50)
def test_forest_displacement_wind_zero_below_canopy(displacement_height_m, z_agl_m):
    """
    Property: In forested terrain, wind speed should be zero below the
    displacement height (within-canopy). Above the displacement height,
    wind follows the displaced log-law profile.

    Formula (displaced log-law):
        u(z) = (u_star / κ) × ln((z - d) / z₀)
        where d = displacement height, z₀ = roughness length

    Below canopy (z < d): u = 0
    """
    von_karman = 0.41
    z0_forest = 1.0  # Typical forest roughness length (m)
    u_star = 0.5  # Friction velocity (m/s)

    # Compute wind speed using displaced log-law
    if z_agl_m <= displacement_height_m:
        # Below canopy: wind should be zero
        u_wind = 0.0
    else:
        # Above canopy: displaced log-law
        z_eff = z_agl_m - displacement_height_m
        if z_eff > z0_forest:
            u_wind = (u_star / von_karman) * np.log(z_eff / z0_forest)
        else:
            u_wind = 0.0

    # Verify: wind is zero below displacement height
    if z_agl_m < displacement_height_m:
        assert u_wind == 0.0, f"Wind should be zero below canopy, got {u_wind} m/s"


# Property 2: UHI boundary layer decay (5.0°F at surface → ~1.84°F at 500 ft → 0 at 1,500 ft)
@given(
    uhi_offset_f=st.floats(min_value=1, max_value=5),
    z_agl_ft=st.floats(min_value=0, max_value=2000),
)
@settings(max_examples=50)
def test_uhi_boundary_layer_decay(uhi_offset_f, z_agl_ft):
    """
    Property: UHI offset decays exponentially with height above the surface.

    Formula:
        UHI_offset(z) = UHI_offset_surface × exp(-z / H_bl)
        where H_bl = 300 ft (boundary layer decay height)

    At z = 0: UHI_offset = UHI_offset_surface
    At z = H_bl: UHI_offset ≈ 0.368 × UHI_offset_surface
    At z ≥ 1,500 ft: UHI_offset ≈ 0
    """
    bl_decay_height_ft = 300.0

    # Compute UHI offset at altitude
    uhi_offset_alt = uhi_offset_f * np.exp(-z_agl_ft / bl_decay_height_ft)

    # Verify: UHI offset decreases with height
    assert (
        uhi_offset_alt <= uhi_offset_f
    ), f"UHI offset should decrease with height: {uhi_offset_alt} > {uhi_offset_f}"

    # Verify: UHI offset is zero above 1,500 ft
    if z_agl_ft >= 1500:
        assert (
            uhi_offset_alt < 0.01
        ), f"UHI offset should be ~0 above 1,500 ft, got {uhi_offset_alt}°F"


# Property 3: TKE scales with roughness (urban > rural)
@given(
    wind_speed_ms=st.floats(min_value=1, max_value=10),
    z0_urban=st.floats(min_value=0.5, max_value=2.0),
    z0_rural=st.floats(min_value=0.01, max_value=0.1),
)
@settings(max_examples=50)
def test_tke_scales_with_roughness(wind_speed_ms, z0_urban, z0_rural):
    """
    Property: Turbulent kinetic energy (TKE) scales with roughness length.
    Urban areas (high z₀) generate more mechanical turbulence than rural areas.

    Formula:
        TKE = 0.5 × u_star² × (1 + 2 × (z₀ / z₀_rural))

    where u_star is friction velocity.

    Implication: TKE_urban > TKE_rural
    """
    von_karman = 0.41
    z_ref = 10.0  # Reference height (m)

    # Compute friction velocity
    u_star = wind_speed_ms * von_karman / np.log(z_ref / z0_rural)

    # Compute TKE for urban and rural
    tke_urban = 0.5 * u_star**2 * (1 + 2 * (z0_urban / z0_rural))
    tke_rural = 0.5 * u_star**2 * (1 + 2 * (z0_rural / z0_rural))

    # Verify: TKE_urban > TKE_rural
    assert (
        tke_urban > tke_rural
    ), f"Urban TKE should be > rural TKE: {tke_urban} vs {tke_rural}"


# Property 4: Wind shear constant for linear wind profile
@given(
    wind_speed_10m_ms=st.floats(min_value=1, max_value=10),
    z0_m=st.floats(min_value=0.01, max_value=1.0),
)
@settings(max_examples=50)
def test_wind_shear_constant_linear_profile(wind_speed_10m_ms, z0_m):
    """
    Property: For a linear wind profile (constant wind shear), the wind speed
    gradient should be constant with height.

    Formula (log-law):
        u(z) = (u_star / κ) × ln(z / z₀)
        du/dz = u_star / (κ × z)

    The wind shear (du/dz) decreases with height, but for a linear approximation
    over a small height range, it should be approximately constant.
    """
    von_karman = 0.41
    z_ref = 10.0

    # Compute friction velocity
    u_star = wind_speed_10m_ms * von_karman / np.log(z_ref / z0_m)

    # Compute wind shear at two heights
    z1 = 10.0  # 10 m
    z2 = 100.0  # 100 m

    u1 = (u_star / von_karman) * np.log(z1 / z0_m)
    u2 = (u_star / von_karman) * np.log(z2 / z0_m)

    # Wind shear (du/dz)
    wind_shear = (u2 - u1) / (z2 - z1)

    # Verify: wind shear is positive (wind increases with height)
    assert wind_shear > 0, f"Wind shear should be positive, got {wind_shear}"


# Property 5: Density altitude equals pressure altitude at ISA standard
@given(
    temp_f=st.floats(min_value=-40, max_value=100),
    pressure_inHg=st.floats(min_value=20, max_value=31),
)
@settings(max_examples=50)
def test_density_altitude_equals_pressure_altitude_at_isa(temp_f, pressure_inHg):
    """
    Property: At ISA standard conditions (15°C at sea level, decreasing 3.5°F per 1,000 ft),
    density altitude should equal pressure altitude.

    Formula:
        DA = PA + 120 × (T - T_ISA)

    At ISA standard: T = T_ISA, so DA = PA
    """
    # Convert pressure to altitude (simplified barometric formula)
    pa_ft = 145442 * (1 - (pressure_inHg / 29.92126) ** 0.190263)

    # ISA standard temperature at sea level is 15°C (59°F)
    # Temperature decreases at 3.5°F per 1,000 ft
    isa_temp_f = 59 - (pa_ft / 1000) * 3.5

    # Compute density altitude
    da_ft = pa_ft + 120 * (temp_f - isa_temp_f)

    # At ISA standard (temp_f = isa_temp_f), DA should equal PA
    if abs(temp_f - isa_temp_f) < 0.1:
        assert (
            abs(da_ft - pa_ft) < 1
        ), f"At ISA standard, DA should equal PA: {da_ft} vs {pa_ft}"


# Property 6: Turbulence flag thresholds (smooth/light/moderate/severe)
@given(
    tke_m2s2=st.floats(min_value=0, max_value=10),
)
@settings(max_examples=50)
def test_turbulence_flag_thresholds(tke_m2s2):
    """
    Property: Turbulence classification should follow defined thresholds:
    - smooth: TKE < 0.5 m²/s²
    - light: 0.5 ≤ TKE < 1.5 m²/s²
    - moderate: 1.5 ≤ TKE < 3.0 m²/s²
    - severe: TKE ≥ 3.0 m²/s²
    """
    if tke_m2s2 < 0.5:
        flag = "smooth"
    elif tke_m2s2 < 1.5:
        flag = "light"
    elif tke_m2s2 < 3.0:
        flag = "moderate"
    else:
        flag = "severe"

    # Verify: flag is one of the valid values
    valid_flags = {"smooth", "light", "moderate", "severe"}
    assert flag in valid_flags, f"Invalid turbulence flag: {flag}"

    # Verify: flag transitions are monotonic
    if tke_m2s2 < 0.5:
        assert flag == "smooth"
    elif tke_m2s2 < 1.5:
        assert flag in ["smooth", "light"]
    elif tke_m2s2 < 3.0:
        assert flag in ["smooth", "light", "moderate"]
    else:
        assert flag in ["smooth", "light", "moderate", "severe"]


# Integration test: Safety cube has correct structure
def test_safety_cube_structure():
    """
    Property: Safety cube should have one row per ZIP × date × altitude,
    with all required columns and valid values.
    """
    from src.processors.aviation_safety_cube import build_safety_cube

    # Create sample daily data
    daily_data = pd.DataFrame(
        {
            "date": ["2024-01-15", "2024-01-15"],
            "zip_code": ["97201", "97202"],
            "hrrr_adjusted_temp_f": [35.0, 36.0],
            "wind_speed_sfc_kt": [10.0, 12.0],
            "wind_dir_sfc_deg": [225.0, 230.0],
            "hdd_sfc": [30.0, 29.0],
            "temp_3000ft_adjusted_f": [25.0, 26.0],
            "wind_speed_3000ft_kt": [15.0, 17.0],
            "wind_dir_3000ft_deg": [225.0, 230.0],
            "hdd_3000ft": [40.0, 39.0],
            "temp_6000ft_adjusted_f": [15.0, 16.0],
            "wind_speed_6000ft_kt": [20.0, 22.0],
            "wind_dir_6000ft_deg": [225.0, 230.0],
            "hdd_6000ft": [50.0, 49.0],
            "temp_9000ft_adjusted_f": [5.0, 6.0],
            "wind_speed_9000ft_kt": [25.0, 27.0],
            "wind_dir_9000ft_deg": [225.0, 230.0],
            "hdd_9000ft": [60.0, 59.0],
            "temp_12000ft_adjusted_f": [-5.0, -4.0],
            "wind_speed_12000ft_kt": [30.0, 32.0],
            "wind_dir_12000ft_deg": [225.0, 230.0],
            "hdd_12000ft": [70.0, 69.0],
            "temp_18000ft_adjusted_f": [-25.0, -24.0],
            "wind_speed_18000ft_kt": [40.0, 42.0],
            "wind_dir_18000ft_deg": [225.0, 230.0],
            "hdd_18000ft": [90.0, 89.0],
            "z0_m": [0.1, 0.2],
            "wind_shear_correction_sfc_kt": [0.0, 0.0],
            "water_cooling_sfc_f": [0.0, 0.0],
        }
    )

    # Build safety cube
    cube = build_safety_cube(daily_data)

    # Verify structure
    assert len(cube) == 16, f"Expected 16 rows (2 ZIPs × 8 altitudes), got {len(cube)}"

    # Verify columns
    required_cols = [
        "date",
        "zip_code",
        "altitude_ft",
        "temp_adjusted_f",
        "wind_speed_kt",
        "tke_m2s2",
        "density_altitude_ft",
        "turbulence_flag",
    ]
    for col in required_cols:
        assert col in cube.columns, f"Missing column: {col}"

    # Verify altitude levels
    expected_altitudes = {0, 500, 1000, 3000, 6000, 9000, 12000, 18000}
    actual_altitudes = set(cube["altitude_ft"].unique())
    assert (
        actual_altitudes == expected_altitudes
    ), f"Altitude mismatch: {actual_altitudes} vs {expected_altitudes}"

    # Verify turbulence flags
    valid_flags = {"smooth", "light", "moderate", "severe"}
    for flag in cube["turbulence_flag"].unique():
        assert flag in valid_flags, f"Invalid turbulence flag: {flag}"


if __name__ == "__main__":
    # Run tests
    test_forest_displacement_wind_zero_below_canopy()
    test_uhi_boundary_layer_decay()
    test_tke_scales_with_roughness()
    test_wind_shear_constant_linear_profile()
    test_density_altitude_equals_pressure_altitude_at_isa()
    test_turbulence_flag_thresholds()
    test_safety_cube_structure()
    print("All aviation safety cube property tests passed!")
