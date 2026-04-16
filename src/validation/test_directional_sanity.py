"""
Property-based tests for directional sanity checks on microclimate output.

Validates that:
1. Urban cells have lower effective_hdd than rural cells (UHI effect reduces heating demand)
2. Windward cells have higher effective_hdd than leeward cells (wind exposure increases infiltration)
3. High-elevation cells have higher effective_hdd than low-elevation cells (lapse rate effect)
"""

import pandas as pd
import numpy as np
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from typing import Tuple


def generate_synthetic_microclimate_data(
    n_cells: int = 100,
    n_zip_codes: int = 10,
) -> pd.DataFrame:
    """
    Generate synthetic microclimate cell data for testing.
    
    Returns a DataFrame with cell-level rows that satisfy basic physical constraints
    but may violate directional sanity checks.
    """
    np.random.seed(42)
    
    data = []
    for zip_idx in range(n_zip_codes):
        zip_code = f"9720{zip_idx}"
        
        for cell_idx in range(n_cells // n_zip_codes):
            cell_id = f"cell_{cell_idx:03d}"
            
            # Generate base HDD (2000-8000 range)
            base_hdd = np.random.uniform(2000, 8000)
            
            # Terrain position (determines multiplier direction)
            terrain_position = np.random.choice(
                ["windward", "leeward", "valley", "ridge"],
                p=[0.25, 0.25, 0.25, 0.25]
            )
            
            # Cell type (urban/suburban/rural)
            cell_type = np.random.choice(
                ["urban", "suburban", "rural"],
                p=[0.3, 0.4, 0.3]
            )
            
            # Elevation (feet)
            mean_elevation_ft = np.random.uniform(100, 5000)
            
            # Imperviousness (0-100%)
            mean_impervious_pct = {
                "urban": np.random.uniform(60, 95),
                "suburban": np.random.uniform(20, 60),
                "rural": np.random.uniform(0, 20),
            }[cell_type]
            
            # Wind speed (m/s)
            mean_wind_ms = np.random.uniform(1, 8)
            
            # Compute corrections
            # Terrain multiplier: windward > leeward
            terrain_mult = {
                "windward": np.random.uniform(1.05, 1.10),
                "leeward": np.random.uniform(0.95, 1.02),
                "valley": np.random.uniform(1.00, 1.05),
                "ridge": np.random.uniform(1.10, 1.20),
            }[terrain_position]
            
            # UHI reduction: urban > rural
            uhi_reduction = {
                "urban": np.random.uniform(200, 400),
                "suburban": np.random.uniform(50, 150),
                "rural": np.random.uniform(0, 50),
            }[cell_type]
            
            # Elevation addition (lapse rate)
            station_elevation_ft = 100  # Reference station
            elev_addition = (mean_elevation_ft - station_elevation_ft) / 1000 * 630
            
            # Traffic reduction
            traffic_reduction = np.random.uniform(0, 100)
            
            # Compute effective HDD
            effective_hdd = (
                base_hdd * terrain_mult
                + elev_addition
                - uhi_reduction
                - traffic_reduction
            )
            
            data.append({
                "microclimate_id": f"R1_{zip_code}_KPDX_cell_{cell_id}",
                "zip_code": zip_code,
                "cell_id": cell_id,
                "cell_type": cell_type,
                "terrain_position": terrain_position,
                "mean_elevation_ft": mean_elevation_ft,
                "mean_impervious_pct": mean_impervious_pct,
                "mean_wind_ms": mean_wind_ms,
                "effective_hdd": effective_hdd,
                "hdd_terrain_mult": terrain_mult,
                "hdd_elev_addition": elev_addition,
                "hdd_uhi_reduction": uhi_reduction,
                "hdd_traffic_reduction": traffic_reduction,
            })
    
    return pd.DataFrame(data)


def check_urban_rural_sanity(df: pd.DataFrame) -> Tuple[bool, str]:
    """
    Property: Urban cells should have lower effective_hdd than rural cells.
    
    This reflects the UHI effect: dense impervious surfaces reduce heating demand
    by raising baseline temperatures.
    
    Returns: (passes, message)
    """
    urban_cells = df[df["cell_type"] == "urban"]
    rural_cells = df[df["cell_type"] == "rural"]
    
    if len(urban_cells) == 0 or len(rural_cells) == 0:
        return True, "Insufficient urban or rural cells to test"
    
    # Compare mean effective_hdd
    urban_mean_hdd = urban_cells["effective_hdd"].mean()
    rural_mean_hdd = rural_cells["effective_hdd"].mean()
    
    # Allow 5% tolerance for statistical noise
    tolerance = 0.05 * rural_mean_hdd
    
    passes = urban_mean_hdd < (rural_mean_hdd + tolerance)
    
    message = (
        f"Urban mean HDD: {urban_mean_hdd:.1f}, "
        f"Rural mean HDD: {rural_mean_hdd:.1f}, "
        f"Difference: {rural_mean_hdd - urban_mean_hdd:.1f} "
        f"(tolerance: {tolerance:.1f})"
    )
    
    return passes, message


def check_windward_leeward_sanity(df: pd.DataFrame) -> Tuple[bool, str]:
    """
    Property: Windward cells should have higher effective_hdd than leeward cells.
    
    This reflects wind infiltration: exposed windward slopes have higher infiltration
    loads, increasing heating demand.
    
    Returns: (passes, message)
    """
    windward_cells = df[df["terrain_position"] == "windward"]
    leeward_cells = df[df["terrain_position"] == "leeward"]
    
    if len(windward_cells) == 0 or len(leeward_cells) == 0:
        return True, "Insufficient windward or leeward cells to test"
    
    # Compare mean effective_hdd
    windward_mean_hdd = windward_cells["effective_hdd"].mean()
    leeward_mean_hdd = leeward_cells["effective_hdd"].mean()
    
    # Allow 5% tolerance for statistical noise
    tolerance = 0.05 * windward_mean_hdd
    
    passes = windward_mean_hdd > (leeward_mean_hdd - tolerance)
    
    message = (
        f"Windward mean HDD: {windward_mean_hdd:.1f}, "
        f"Leeward mean HDD: {leeward_mean_hdd:.1f}, "
        f"Difference: {windward_mean_hdd - leeward_mean_hdd:.1f} "
        f"(tolerance: {tolerance:.1f})"
    )
    
    return passes, message


def check_elevation_sanity(df: pd.DataFrame) -> Tuple[bool, str]:
    """
    Property: High-elevation cells should have higher effective_hdd than low-elevation cells.
    
    This reflects the lapse rate: temperature decreases with elevation, so higher
    elevations have more heating degree days.
    
    Returns: (passes, message)
    """
    # Split into high and low elevation groups
    median_elev = df["mean_elevation_ft"].median()
    high_elev = df[df["mean_elevation_ft"] > median_elev]
    low_elev = df[df["mean_elevation_ft"] <= median_elev]
    
    if len(high_elev) == 0 or len(low_elev) == 0:
        return True, "Insufficient elevation variation to test"
    
    # Compare mean effective_hdd
    high_elev_mean_hdd = high_elev["effective_hdd"].mean()
    low_elev_mean_hdd = low_elev["effective_hdd"].mean()
    
    # Allow 5% tolerance for statistical noise
    tolerance = 0.05 * high_elev_mean_hdd
    
    passes = high_elev_mean_hdd > (low_elev_mean_hdd - tolerance)
    
    message = (
        f"High elevation (>{median_elev:.0f} ft) mean HDD: {high_elev_mean_hdd:.1f}, "
        f"Low elevation (<={median_elev:.0f} ft) mean HDD: {low_elev_mean_hdd:.1f}, "
        f"Difference: {high_elev_mean_hdd - low_elev_mean_hdd:.1f} "
        f"(tolerance: {tolerance:.1f})"
    )
    
    return passes, message


def check_within_zip_sanity(df: pd.DataFrame) -> Tuple[bool, str]:
    """
    Property: Within each ZIP code, directional sanity should hold.
    
    Returns: (passes, message)
    """
    failures = []
    
    for zip_code in df["zip_code"].unique():
        zip_df = df[df["zip_code"] == zip_code]
        
        # Check urban < rural within this ZIP
        urban = zip_df[zip_df["cell_type"] == "urban"]
        rural = zip_df[zip_df["cell_type"] == "rural"]
        
        if len(urban) > 0 and len(rural) > 0:
            urban_mean = urban["effective_hdd"].mean()
            rural_mean = rural["effective_hdd"].mean()
            if urban_mean > rural_mean * 1.05:  # 5% tolerance
                failures.append(
                    f"ZIP {zip_code}: urban ({urban_mean:.1f}) > rural ({rural_mean:.1f})"
                )
        
        # Check windward > leeward within this ZIP
        windward = zip_df[zip_df["terrain_position"] == "windward"]
        leeward = zip_df[zip_df["terrain_position"] == "leeward"]
        
        if len(windward) > 0 and len(leeward) > 0:
            windward_mean = windward["effective_hdd"].mean()
            leeward_mean = leeward["effective_hdd"].mean()
            if windward_mean < leeward_mean * 0.95:  # 5% tolerance
                failures.append(
                    f"ZIP {zip_code}: windward ({windward_mean:.1f}) < leeward ({leeward_mean:.1f})"
                )
    
    passes = len(failures) == 0
    message = "; ".join(failures) if failures else "All ZIP codes pass sanity checks"
    
    return passes, message


@given(
    n_cells=st.integers(min_value=50, max_value=500),
    n_zip_codes=st.integers(min_value=5, max_value=20),
)
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_directional_sanity_properties(n_cells: int, n_zip_codes: int):
    """
    Property-based test: Directional sanity checks hold across synthetic data.
    """
    df = generate_synthetic_microclimate_data(n_cells=n_cells, n_zip_codes=n_zip_codes)
    
    # Run all sanity checks
    checks = [
        ("Urban < Rural", check_urban_rural_sanity(df)),
        ("Windward > Leeward", check_windward_leeward_sanity(df)),
        ("High Elevation > Low Elevation", check_elevation_sanity(df)),
        ("Within-ZIP Sanity", check_within_zip_sanity(df)),
    ]
    
    # Report results
    all_pass = True
    for check_name, (passes, message) in checks:
        status = "✓ PASS" if passes else "✗ FAIL"
        print(f"{status}: {check_name} — {message}")
        all_pass = all_pass and passes
    
    assert all_pass, "One or more directional sanity checks failed"


def test_directional_sanity_on_real_output(csv_path: str):
    """
    Validate directional sanity on actual pipeline output.
    
    Usage:
        test_directional_sanity_on_real_output("output/microclimate/terrain_attributes.csv")
    """
    df = pd.read_csv(csv_path)
    
    # Filter to cell-level rows only (exclude aggregates)
    df = df[df["cell_id"] != "aggregate"]
    
    print(f"\nValidating {len(df)} cell-level rows from {csv_path}")
    
    checks = [
        ("Urban < Rural", check_urban_rural_sanity(df)),
        ("Windward > Leeward", check_windward_leeward_sanity(df)),
        ("High Elevation > Low Elevation", check_elevation_sanity(df)),
        ("Within-ZIP Sanity", check_within_zip_sanity(df)),
    ]
    
    all_pass = True
    for check_name, (passes, message) in checks:
        status = "✓ PASS" if passes else "✗ FAIL"
        print(f"{status}: {check_name} — {message}")
        all_pass = all_pass and passes
    
    return all_pass


if __name__ == "__main__":
    # Run property-based tests
    print("Running property-based directional sanity tests...\n")
    test_directional_sanity_properties()
    print("\n✓ All property-based tests passed!")
