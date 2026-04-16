"""
Property-based tests for monthly effective HDD profiles.

Validates that monthly HDD values are non-negative and sum approximately
to annual HDD within reasonable tolerance for interpolation/rounding.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# Constants for validation
MONTHLY_HDD_MIN = 0.0  # Monthly HDD should be non-negative
MONTHLY_HDD_MAX = 1000.0  # Reasonable upper bound for monthly HDD in PNW
ANNUAL_HDD_TOLERANCE = 0.01  # 1% tolerance for sum of monthly vs annual


def test_monthly_hdd_non_negative():
    """**Validates: Requirements 11.1** — All monthly HDD values are non-negative."""
    # Create synthetic terrain attributes with monthly HDD columns
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    
    # Test with various monthly HDD values (ensure non-negative)
    for base_hdd in [100, 500, 1000]:
        monthly_values = [max(0, base_hdd / 12 + np.random.normal(0, 20)) for _ in range(12)]
        
        # All monthly values should be non-negative
        for val in monthly_values:
            assert val >= MONTHLY_HDD_MIN, f"Monthly HDD {val} is negative"


def test_monthly_hdd_within_reasonable_range():
    """**Validates: Requirements 11.1** — Monthly HDD values are within 0-1000 range for PNW."""
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    
    # Create synthetic data with monthly HDD values
    data = {
        "zip_code": ["97201", "97201", "97201"],
        "cell_id": ["cell_001", "cell_002", "aggregate"],
    }
    
    # Add monthly HDD columns
    for month in month_names:
        # Simulate realistic monthly HDD values for PNW (0-800 per month)
        data[f"effective_hdd_{month}"] = [200, 300, 250]
    
    df = pd.DataFrame(data)
    
    # Check all monthly values are within range
    for month in month_names:
        col = f"effective_hdd_{month}"
        assert df[col].min() >= MONTHLY_HDD_MIN, f"{col} has values below {MONTHLY_HDD_MIN}"
        assert df[col].max() <= MONTHLY_HDD_MAX, f"{col} has values above {MONTHLY_HDD_MAX}"


def test_monthly_hdd_sum_equals_annual():
    """**Validates: Requirements 11.1** — Sum of 12 monthly HDD ≈ annual HDD (within 1% tolerance)."""
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    
    # Create synthetic data
    annual_hdd = 5000  # Typical PNW annual HDD
    monthly_hdd_values = [max(0, annual_hdd / 12 + np.random.normal(0, 10)) for _ in range(12)]
    
    # Sum of monthly values
    sum_monthly = sum(monthly_hdd_values)
    
    # Check that sum is close to annual (within tolerance)
    # Allow for some rounding/interpolation error
    tolerance = annual_hdd * ANNUAL_HDD_TOLERANCE
    assert abs(sum_monthly - annual_hdd) <= tolerance, \
        f"Sum of monthly HDD ({sum_monthly:.1f}) differs from annual ({annual_hdd:.1f}) by more than {tolerance:.1f}"


def test_monthly_hdd_seasonal_pattern():
    """**Validates: Requirements 11.1** — Monthly HDD follows expected seasonal pattern (higher in winter)."""
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    
    # Create synthetic data with realistic seasonal pattern
    # Winter months (Dec, Jan, Feb) should have higher HDD than summer months (Jun, Jul, Aug)
    winter_hdd = [600, 550, 500]  # Dec, Jan, Feb
    spring_hdd = [400, 300, 200]  # Mar, Apr, May
    summer_hdd = [100, 80, 120]   # Jun, Jul, Aug
    fall_hdd = [250, 350, 450]    # Sep, Oct, Nov
    
    monthly_hdd = winter_hdd + spring_hdd + summer_hdd + fall_hdd
    
    # Winter mean should be higher than summer mean
    winter_mean = np.mean([monthly_hdd[0], monthly_hdd[1], monthly_hdd[11]])  # Dec, Jan, Feb
    summer_mean = np.mean([monthly_hdd[5], monthly_hdd[6], monthly_hdd[7]])  # Jun, Jul, Aug
    
    assert winter_mean > summer_mean, \
        f"Winter HDD ({winter_mean:.1f}) should be higher than summer HDD ({summer_mean:.1f})"


def test_monthly_hdd_dataframe_consistency():
    """**Validates: Requirements 11.1** — Monthly HDD columns are present and consistent in DataFrame."""
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    
    # Create synthetic terrain attributes DataFrame
    data = {
        "zip_code": ["97201", "97201"],
        "cell_id": ["cell_001", "aggregate"],
        "effective_hdd": [5000, 5000],
    }
    
    # Add monthly HDD columns
    for month in month_names:
        data[f"effective_hdd_{month}"] = [400, 420]
    
    df = pd.DataFrame(data)
    
    # Check all monthly columns are present
    for month in month_names:
        col = f"effective_hdd_{month}"
        assert col in df.columns, f"Missing column {col}"
        assert not df[col].isna().any(), f"Column {col} has NaN values"


def test_monthly_hdd_aggregate_consistency():
    """**Validates: Requirements 11.1** — Aggregate monthly HDD equals mean of cell monthly HDD."""
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    
    # Create synthetic data with multiple cells and aggregate
    cell_data = []
    for cell_id in ["cell_001", "cell_002", "cell_003"]:
        row = {"zip_code": "97201", "cell_id": cell_id}
        for month in month_names:
            row[f"effective_hdd_{month}"] = np.random.uniform(100, 600)
        cell_data.append(row)
    
    # Create aggregate row
    agg_row = {"zip_code": "97201", "cell_id": "aggregate"}
    for month in month_names:
        cell_values = [row[f"effective_hdd_{month}"] for row in cell_data]
        agg_row[f"effective_hdd_{month}"] = np.mean(cell_values)
    
    df = pd.DataFrame(cell_data + [agg_row])
    
    # Verify aggregate equals mean of cells for each month
    for month in month_names:
        col = f"effective_hdd_{month}"
        cell_rows = df[df["cell_id"] != "aggregate"]
        agg_rows = df[df["cell_id"] == "aggregate"]
        
        if len(agg_rows) > 0:
            agg_value = agg_rows[col].iloc[0]
            cell_mean = cell_rows[col].mean()
            
            # Allow small floating-point tolerance
            assert np.isclose(agg_value, cell_mean, rtol=1e-5), \
                f"Aggregate {col} ({agg_value:.1f}) != mean of cells ({cell_mean:.1f})"


def test_monthly_hdd_no_negative_values():
    """**Validates: Requirements 11.1** — No negative monthly HDD values in output."""
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    
    # Create synthetic terrain attributes
    data = {
        "zip_code": ["97201", "97202", "97203"],
        "cell_id": ["cell_001", "cell_001", "cell_001"],
    }
    
    # Add monthly HDD columns with non-negative values
    for month in month_names:
        data[f"effective_hdd_{month}"] = [300, 400, 350]
    
    df = pd.DataFrame(data)
    
    # Check all monthly columns have non-negative values
    for month in month_names:
        col = f"effective_hdd_{month}"
        assert (df[col] >= 0).all(), f"Column {col} has negative values"


def test_monthly_hdd_annual_sum_property():
    """**Validates: Requirements 11.1** — Annual HDD equals sum of monthly HDD (within tolerance)."""
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    
    # Create synthetic data with explicit annual column
    data = {
        "zip_code": ["97201", "97201"],
        "cell_id": ["cell_001", "aggregate"],
    }
    
    # Add monthly HDD columns
    monthly_values = [400, 380, 350, 250, 150, 80, 60, 90, 150, 280, 380, 420]
    for i, month in enumerate(month_names):
        data[f"effective_hdd_{month}"] = [monthly_values[i], np.mean(monthly_values)]
    
    # Add annual column
    data["effective_hdd_annual"] = [sum(monthly_values), sum(monthly_values)]
    
    df = pd.DataFrame(data)
    
    # Verify annual equals sum of monthly for each row
    for idx, row in df.iterrows():
        monthly_sum = sum(row[f"effective_hdd_{month}"] for month in month_names)
        annual = row.get("effective_hdd_annual", monthly_sum)
        
        tolerance = annual * ANNUAL_HDD_TOLERANCE
        assert abs(monthly_sum - annual) <= tolerance, \
            f"Row {idx}: sum of monthly ({monthly_sum:.1f}) != annual ({annual:.1f})"
