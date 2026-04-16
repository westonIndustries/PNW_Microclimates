"""
Tests for QA checks module.

Tests the verification checks for aggregate HDD consistency, range checks,
directional sanity, cell reliability, hard failures, billing comparison,
and report generation.
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, strategies as st

from src.validation.qa_checks import (
    AGGREGATE_HDD_TOLERANCE,
    EFFECTIVE_HDD_HARD_MAX,
    EFFECTIVE_HDD_HARD_MIN,
    EFFECTIVE_HDD_MAX,
    EFFECTIVE_HDD_MIN,
    check_billing_comparison,
    check_cell_reliability,
    check_directional_sanity,
    check_effective_hdd_range,
    check_hard_failures,
    generate_qa_report,
    verify_aggregate_hdd_consistency,
)


class TestAggregateHDDConsistency:
    """Tests for verify_aggregate_hdd_consistency function."""

    def test_perfect_consistency(self):
        """Test that perfect consistency passes."""
        # Create cell rows
        cells = pd.DataFrame({
            "zip_code": ["97201", "97201", "97201"],
            "cell_id": ["cell_001", "cell_002", "cell_003"],
            "cell_effective_hdd": [5000.0, 5100.0, 4900.0],
        })

        # Create aggregate row with correct mean
        mean_hdd = cells["cell_effective_hdd"].mean()
        agg = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [mean_hdd],
        })

        combined = pd.concat([cells, agg], ignore_index=True)
        result = verify_aggregate_hdd_consistency(combined)

        assert result.passed
        assert result.num_issues == 0

    def test_aggregate_mismatch_detected(self):
        """Test that aggregate mismatch is detected."""
        # Create cell rows
        cells = pd.DataFrame({
            "zip_code": ["97201", "97201", "97201"],
            "cell_id": ["cell_001", "cell_002", "cell_003"],
            "cell_effective_hdd": [5000.0, 5100.0, 4900.0],
        })

        # Create aggregate row with incorrect mean (off by 1.0 HDD)
        mean_hdd = cells["cell_effective_hdd"].mean()
        agg = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [mean_hdd + 1.0],  # Mismatch
        })

        combined = pd.concat([cells, agg], ignore_index=True)
        result = verify_aggregate_hdd_consistency(combined, tolerance=AGGREGATE_HDD_TOLERANCE)

        assert not result.passed
        assert result.num_issues == 1
        assert "Aggregate HDD mismatch" in result.issues[0]

    def test_within_tolerance(self):
        """Test that small mismatches within tolerance pass."""
        # Create cell rows
        cells = pd.DataFrame({
            "zip_code": ["97201", "97201", "97201"],
            "cell_id": ["cell_001", "cell_002", "cell_003"],
            "cell_effective_hdd": [5000.0, 5100.0, 4900.0],
        })

        # Create aggregate row with small mismatch (within tolerance)
        mean_hdd = cells["cell_effective_hdd"].mean()
        agg = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [mean_hdd + 0.05],  # Within tolerance
        })

        combined = pd.concat([cells, agg], ignore_index=True)
        result = verify_aggregate_hdd_consistency(combined, tolerance=0.1)

        assert result.passed
        assert result.num_issues == 0

    def test_multiple_zip_codes(self):
        """Test verification across multiple ZIP codes."""
        # Create cells for two ZIP codes
        cells = pd.DataFrame({
            "zip_code": ["97201", "97201", "97202", "97202"],
            "cell_id": ["cell_001", "cell_002", "cell_001", "cell_002"],
            "cell_effective_hdd": [5000.0, 5100.0, 4500.0, 4600.0],
        })

        # Create aggregates
        agg1 = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [5050.0],  # Correct mean
        })
        agg2 = pd.DataFrame({
            "zip_code": ["97202"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [4550.0],  # Correct mean
        })

        combined = pd.concat([cells, agg1, agg2], ignore_index=True)
        result = verify_aggregate_hdd_consistency(combined)

        assert result.passed
        assert result.num_issues == 0

    def test_missing_aggregate_row(self):
        """Test that missing aggregate row is flagged."""
        # Create cell rows without aggregate
        cells = pd.DataFrame({
            "zip_code": ["97201", "97201"],
            "cell_id": ["cell_001", "cell_002"],
            "cell_effective_hdd": [5000.0, 5100.0],
        })

        result = verify_aggregate_hdd_consistency(cells)

        assert not result.passed
        assert result.num_issues == 1
        assert "No aggregate row found" in result.issues[0]

    def test_nan_values_handled(self):
        """Test that NaN values in cells are handled correctly."""
        # Create cell rows with some NaN values
        cells = pd.DataFrame({
            "zip_code": ["97201", "97201", "97201"],
            "cell_id": ["cell_001", "cell_002", "cell_003"],
            "cell_effective_hdd": [5000.0, np.nan, 4900.0],
        })

        # Aggregate should use only non-NaN values
        mean_hdd = 4950.0  # Mean of 5000 and 4900
        agg = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [mean_hdd],
        })

        combined = pd.concat([cells, agg], ignore_index=True)
        result = verify_aggregate_hdd_consistency(combined)

        assert result.passed
        assert result.num_issues == 0


class TestEffectiveHDDRange:
    """Tests for check_effective_hdd_range function."""

    def test_all_in_range(self):
        """Test that all values in range pass."""
        df = pd.DataFrame({
            "zip_code": ["97201", "97202"],
            "cell_id": ["cell_001", "cell_001"],
            "cell_effective_hdd": [5000.0, 4500.0],
        })

        result = check_effective_hdd_range(df)

        assert result.passed
        assert result.num_issues == 0

    def test_below_minimum(self):
        """Test that values below minimum are flagged."""
        df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["cell_001"],
            "cell_effective_hdd": [1500.0],  # Below 2000
        })

        result = check_effective_hdd_range(df)

        assert not result.passed
        assert result.num_issues == 1
        assert "outside range" in result.issues[0]

    def test_above_maximum(self):
        """Test that values above maximum are flagged."""
        df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["cell_001"],
            "cell_effective_hdd": [9000.0],  # Above 8000
        })

        result = check_effective_hdd_range(df)

        assert not result.passed
        assert result.num_issues == 1
        assert "outside range" in result.issues[0]


class TestDirectionalSanity:
    """Tests for check_directional_sanity function."""

    def test_urban_rural_sanity(self):
        """Test that urban < rural sanity check works."""
        df = pd.DataFrame({
            "cell_type": ["urban", "urban", "rural", "rural"],
            "cell_effective_hdd": [4500.0, 4600.0, 5000.0, 5100.0],
            "terrain_position": ["windward", "windward", "windward", "windward"],
            "mean_elevation_ft": [500.0, 500.0, 500.0, 500.0],
        })

        result = check_directional_sanity(df)

        assert result.passed
        assert result.num_issues == 0

    def test_urban_rural_violation(self):
        """Test that urban > rural violation is detected."""
        df = pd.DataFrame({
            "cell_type": ["urban", "urban", "rural", "rural"],
            "cell_effective_hdd": [5500.0, 5600.0, 5000.0, 5100.0],  # Urban > Rural
            "terrain_position": ["windward", "windward", "windward", "windward"],
            "mean_elevation_ft": [500.0, 500.0, 500.0, 500.0],
        })

        result = check_directional_sanity(df)

        assert not result.passed
        assert any("Urban cells have higher HDD" in issue for issue in result.issues)

    def test_windward_leeward_sanity(self):
        """Test that windward > leeward sanity check works."""
        df = pd.DataFrame({
            "cell_type": ["urban", "urban", "urban", "urban"],
            "cell_effective_hdd": [5200.0, 5300.0, 4800.0, 4900.0],
            "terrain_position": ["windward", "windward", "leeward", "leeward"],
            "mean_elevation_ft": [500.0, 500.0, 500.0, 500.0],
        })

        result = check_directional_sanity(df)

        assert result.passed
        assert result.num_issues == 0

    def test_elevation_sanity(self):
        """Test that high elevation > low elevation sanity check works."""
        df = pd.DataFrame({
            "cell_type": ["rural", "rural", "rural", "rural"],
            "cell_effective_hdd": [6000.0, 6100.0, 4500.0, 4600.0],
            "terrain_position": ["ridge", "ridge", "valley", "valley"],
            "mean_elevation_ft": [3000.0, 3100.0, 1000.0, 1100.0],
        })

        result = check_directional_sanity(df)

        assert result.passed
        assert result.num_issues == 0


class TestCellReliability:
    """Tests for check_cell_reliability function."""

    def test_all_reliable(self):
        """Test that cells with sufficient pixels pass."""
        df = pd.DataFrame({
            "zip_code": ["97201", "97201"],
            "cell_id": ["cell_001", "cell_002"],
            "num_valid_pixels": [100, 50],
        })

        result = check_cell_reliability(df, min_pixels=10)

        assert result.passed
        assert result.num_issues == 0

    def test_unreliable_cells_flagged(self):
        """Test that cells with too few pixels are flagged."""
        df = pd.DataFrame({
            "zip_code": ["97201", "97201"],
            "cell_id": ["cell_001", "cell_002"],
            "num_valid_pixels": [5, 50],  # First cell has too few
        })

        result = check_cell_reliability(df, min_pixels=10)

        assert not result.passed
        assert result.num_issues == 1
        assert "Only 5 valid pixels" in result.issues[0]

    def test_aggregate_rows_ignored(self):
        """Test that aggregate rows are not checked for pixel count."""
        df = pd.DataFrame({
            "zip_code": ["97201", "97201"],
            "cell_id": ["cell_001", "aggregate"],
            "num_valid_pixels": [5, 0],  # Aggregate has 0 pixels
        })

        result = check_cell_reliability(df, min_pixels=10)

        # Only cell_001 should be flagged, not aggregate
        assert not result.passed
        assert result.num_issues == 1
        assert "cell_001" in result.issues[0]


class TestHardFailures:
    """Tests for check_hard_failures function."""

    def test_no_hard_failures(self):
        """Test that valid HDD values pass."""
        df = pd.DataFrame({
            "zip_code": ["97201", "97202"],
            "cell_id": ["cell_001", "cell_001"],
            "cell_effective_hdd": [5000.0, 4500.0],
        })

        result = check_hard_failures(df)

        assert result.passed
        assert result.num_issues == 0
        assert not result.is_hard_failure

    def test_negative_hdd_flagged(self):
        """Test that negative HDD is flagged as hard failure."""
        df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["cell_001"],
            "cell_effective_hdd": [-100.0],  # Negative HDD
        })

        result = check_hard_failures(df)

        assert not result.passed
        assert result.num_issues == 1
        assert result.is_hard_failure
        assert "outside hard limits" in result.issues[0]

    def test_excessive_hdd_flagged(self):
        """Test that HDD > 15,000 is flagged as hard failure."""
        df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["cell_001"],
            "cell_effective_hdd": [20000.0],  # Excessive HDD
        })

        result = check_hard_failures(df)

        assert not result.passed
        assert result.num_issues == 1
        assert result.is_hard_failure
        assert "outside hard limits" in result.issues[0]

    def test_boundary_values(self):
        """Test that boundary values are accepted."""
        df = pd.DataFrame({
            "zip_code": ["97201", "97202"],
            "cell_id": ["cell_001", "cell_001"],
            "cell_effective_hdd": [0.0, 15000.0],  # At boundaries
        })

        result = check_hard_failures(df)

        assert result.passed
        assert result.num_issues == 0


class TestBillingComparison:
    """Tests for check_billing_comparison function."""

    def test_no_billing_csv_skipped(self):
        """Test that check is skipped when no billing CSV provided."""
        df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [5000.0],
        })

        result = check_billing_comparison(df, billing_csv_path=None)

        assert result.passed
        assert "Skipped" in result.issues[0]

    def test_missing_billing_csv_skipped(self):
        """Test that check is skipped when billing CSV doesn't exist."""
        df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [5000.0],
        })

        result = check_billing_comparison(df, billing_csv_path=Path("/nonexistent/path.csv"))

        assert result.passed
        assert "not found" in result.issues[0]

    def test_billing_comparison_within_threshold(self):
        """Test that values within threshold pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create billing CSV
            billing_path = Path(tmpdir) / "billing.csv"
            billing_df = pd.DataFrame({
                "zip_code": ["97201"],
                "therms_per_customer": [5000.0],
            })
            billing_df.to_csv(billing_path, index=False)

            # Create terrain data with matching zip_code dtype
            terrain_df = pd.DataFrame({
                "zip_code": ["97201"],
                "cell_id": ["aggregate"],
                "cell_effective_hdd": [5050.0],  # Within 15% of 5000
            })

            result = check_billing_comparison(terrain_df, billing_csv_path=billing_path)

            assert result.passed
            assert result.num_issues == 0

    def test_billing_comparison_exceeds_threshold(self):
        """Test that values exceeding threshold are flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create billing CSV
            billing_path = Path(tmpdir) / "billing.csv"
            billing_df = pd.DataFrame({
                "zip_code": ["97201"],
                "therms_per_customer": [5000.0],
            })
            billing_df.to_csv(billing_path, index=False)

            # Create terrain data with large divergence and matching dtype
            terrain_df = pd.DataFrame({
                "zip_code": ["97201"],
                "cell_id": ["aggregate"],
                "cell_effective_hdd": [6000.0],  # 20% divergence (exceeds 15%)
            })

            result = check_billing_comparison(terrain_df, billing_csv_path=billing_path)

            assert not result.passed
            assert result.num_issues == 1
            assert "diverges from" in result.issues[0]


class TestGenerateQAReport:
    """Tests for generate_qa_report function."""

    def test_report_generation(self):
        """Test that HTML and MD reports are generated."""
        from src.validation.qa_checks import QACheckResult

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create mock QA results
            qa_results = {
                "test_check": QACheckResult(
                    check_name="Test Check",
                    passed=True,
                    num_issues=0,
                    issues=[],
                    severity="info",
                )
            }

            # Create terrain data
            terrain_df = pd.DataFrame({
                "zip_code": ["97201", "97201"],
                "cell_id": ["cell_001", "aggregate"],
                "cell_effective_hdd": [5000.0, 5000.0],
            })

            html_path, md_path = generate_qa_report(qa_results, terrain_df, output_dir)

            # Verify files were created
            assert html_path.exists()
            assert md_path.exists()

            # Verify HTML content
            html_content = html_path.read_text()
            assert "QA Report" in html_content
            assert "Test Check" in html_content
            assert "<!DOCTYPE html>" in html_content

            # Verify MD content
            md_content = md_path.read_text()
            assert "QA Report" in md_content
            assert "Test Check" in md_content
            assert "# " in md_content  # Markdown headers

    def test_report_includes_summary_stats(self):
        """Test that reports include summary statistics."""
        from src.validation.qa_checks import QACheckResult

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            qa_results = {
                "test": QACheckResult(
                    check_name="Test",
                    passed=True,
                    num_issues=0,
                    issues=[],
                    severity="info",
                )
            }

            terrain_df = pd.DataFrame({
                "zip_code": ["97201", "97201", "97202"],
                "cell_id": ["cell_001", "aggregate", "aggregate"],
                "cell_effective_hdd": [5000.0, 5000.0, 4500.0],
            })

            html_path, md_path = generate_qa_report(qa_results, terrain_df, output_dir)

            html_content = html_path.read_text()
            md_content = md_path.read_text()

            # Check for summary statistics
            assert "Total Cells" in html_content
            assert "Total ZIP Codes" in html_content
            assert "HDD Mean" in html_content
            assert "HDD Range" in html_content


class TestAggregateHDDConsistencyProperty:
    """Property-based tests for aggregate HDD consistency (Task 10.5).
    
    These tests verify that ZIP-code aggregate effective_hdd values equal
    the mean of all cells within floating-point tolerance, using property-based
    testing with Hypothesis to generate diverse datasets.
    """

    @given(
        num_cells=st.integers(min_value=1, max_value=50),
        base_hdd=st.floats(
            min_value=4000.0,
            max_value=6000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_aggregate_equals_mean_of_cells(self, num_cells, base_hdd):
        """Property: Aggregate effective_hdd must equal mean of all cells.
        
        For any generated dataset with N cells and a base HDD value,
        the aggregate row's effective_hdd must equal the arithmetic mean
        of all cell effective_hdd values (within floating-point tolerance).
        """
        # Generate cell HDD values with small variations around base_hdd
        cell_hdd_values = [
            base_hdd + (i - num_cells / 2) * 10.0 for i in range(num_cells)
        ]

        # Create cell rows
        cell_data = []
        for idx, hdd in enumerate(cell_hdd_values):
            cell_data.append({
                "zip_code": "97201",
                "cell_id": f"cell_{idx:03d}",
                "cell_effective_hdd": hdd,
            })

        cells_df = pd.DataFrame(cell_data)

        # Create aggregate row with correct mean
        mean_hdd = cells_df["cell_effective_hdd"].mean()
        agg_df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [mean_hdd],
        })

        combined_df = pd.concat([cells_df, agg_df], ignore_index=True)
        result = verify_aggregate_hdd_consistency(combined_df)

        # Property: Correct aggregate mean → check passes
        assert result.passed, f"Expected pass but got issues: {result.issues}"
        assert result.num_issues == 0

    @given(
        num_cells=st.integers(min_value=1, max_value=50),
        base_hdd=st.floats(
            min_value=4000.0,
            max_value=6000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        mismatch_magnitude=st.floats(
            min_value=0.2,
            max_value=2.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_aggregate_mismatch_detected_property(self, num_cells, base_hdd, mismatch_magnitude):
        """Property: Aggregate mismatches must be detected.
        
        For any dataset where the aggregate HDD differs from the mean of cells
        by more than the tolerance, the check must fail and report the issue.
        """
        # Generate cell HDD values
        cell_hdd_values = [
            base_hdd + (i - num_cells / 2) * 10.0 for i in range(num_cells)
        ]

        # Create cell rows
        cell_data = []
        for idx, hdd in enumerate(cell_hdd_values):
            cell_data.append({
                "zip_code": "97201",
                "cell_id": f"cell_{idx:03d}",
                "cell_effective_hdd": hdd,
            })

        cells_df = pd.DataFrame(cell_data)

        # Create aggregate row with intentional mismatch
        mean_hdd = cells_df["cell_effective_hdd"].mean()
        incorrect_agg_hdd = mean_hdd + mismatch_magnitude

        agg_df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [incorrect_agg_hdd],
        })

        combined_df = pd.concat([cells_df, agg_df], ignore_index=True)
        result = verify_aggregate_hdd_consistency(combined_df, tolerance=AGGREGATE_HDD_TOLERANCE)

        # Property: Mismatch > tolerance → check fails
        assert not result.passed, "Expected fail but check passed"
        assert result.num_issues == 1
        assert "Aggregate HDD mismatch" in result.issues[0]

    @given(
        num_cells=st.integers(min_value=1, max_value=50),
        base_hdd=st.floats(
            min_value=4000.0,
            max_value=6000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_aggregate_within_tolerance_property(self, num_cells, base_hdd):
        """Property: Small mismatches within tolerance must pass.
        
        For any dataset where the aggregate HDD differs from the mean of cells
        by less than the tolerance, the check must pass.
        """
        # Generate cell HDD values
        cell_hdd_values = [
            base_hdd + (i - num_cells / 2) * 10.0 for i in range(num_cells)
        ]

        # Create cell rows
        cell_data = []
        for idx, hdd in enumerate(cell_hdd_values):
            cell_data.append({
                "zip_code": "97201",
                "cell_id": f"cell_{idx:03d}",
                "cell_effective_hdd": hdd,
            })

        cells_df = pd.DataFrame(cell_data)

        # Create aggregate row with small mismatch (within tolerance)
        mean_hdd = cells_df["cell_effective_hdd"].mean()
        small_mismatch = AGGREGATE_HDD_TOLERANCE * 0.5  # Half of tolerance
        slightly_off_agg_hdd = mean_hdd + small_mismatch

        agg_df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [slightly_off_agg_hdd],
        })

        combined_df = pd.concat([cells_df, agg_df], ignore_index=True)
        result = verify_aggregate_hdd_consistency(combined_df, tolerance=AGGREGATE_HDD_TOLERANCE)

        # Property: Mismatch < tolerance → check passes
        assert result.passed, f"Expected pass but got issues: {result.issues}"
        assert result.num_issues == 0

    @given(
        num_zips=st.integers(min_value=1, max_value=10),
        cells_per_zip=st.integers(min_value=1, max_value=20),
    )
    def test_multiple_zip_codes_consistency_property(self, num_zips, cells_per_zip):
        """Property: Consistency check must work across multiple ZIP codes.
        
        For any dataset with multiple ZIP codes, each with multiple cells,
        the check must verify consistency for each ZIP code independently.
        """
        all_cells = []
        all_aggs = []

        for zip_idx in range(num_zips):
            zip_code = f"9720{zip_idx}"
            base_hdd = 5000.0 + zip_idx * 100.0

            # Create cells for this ZIP code
            for cell_idx in range(cells_per_zip):
                hdd = base_hdd + (cell_idx - cells_per_zip / 2) * 5.0
                all_cells.append({
                    "zip_code": zip_code,
                    "cell_id": f"cell_{cell_idx:03d}",
                    "cell_effective_hdd": hdd,
                })

            # Create aggregate for this ZIP code
            zip_cells = [c for c in all_cells if c["zip_code"] == zip_code]
            mean_hdd = np.mean([c["cell_effective_hdd"] for c in zip_cells])
            all_aggs.append({
                "zip_code": zip_code,
                "cell_id": "aggregate",
                "cell_effective_hdd": mean_hdd,
            })

        combined_df = pd.DataFrame(all_cells + all_aggs)
        result = verify_aggregate_hdd_consistency(combined_df)

        # Property: All ZIP codes with correct aggregates → check passes
        assert result.passed, f"Expected pass but got issues: {result.issues}"
        assert result.num_issues == 0

    def test_aggregate_consistency_with_nan_values_property(self):
        """Property: NaN values in cells must be excluded from mean calculation.
        
        When some cells have NaN effective_hdd values, the aggregate should
        equal the mean of only the non-NaN cells.
        """
        # Create cells with some NaN values
        cell_data = [
            {"zip_code": "97201", "cell_id": "cell_001", "cell_effective_hdd": 5000.0},
            {"zip_code": "97201", "cell_id": "cell_002", "cell_effective_hdd": np.nan},
            {"zip_code": "97201", "cell_id": "cell_003", "cell_effective_hdd": 5100.0},
            {"zip_code": "97201", "cell_id": "cell_004", "cell_effective_hdd": np.nan},
            {"zip_code": "97201", "cell_id": "cell_005", "cell_effective_hdd": 4900.0},
        ]

        cells_df = pd.DataFrame(cell_data)

        # Aggregate should use only non-NaN values
        valid_hdd = cells_df["cell_effective_hdd"].dropna()
        mean_hdd = valid_hdd.mean()

        agg_df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["aggregate"],
            "cell_effective_hdd": [mean_hdd],
        })

        combined_df = pd.concat([cells_df, agg_df], ignore_index=True)
        result = verify_aggregate_hdd_consistency(combined_df)

        # Property: Aggregate of non-NaN cells → check passes
        assert result.passed, f"Expected pass but got issues: {result.issues}"
        assert result.num_issues == 0


class TestEffectiveHDDRangeProperty:
    """Property-based tests for effective_hdd range validation (Task 10.3).
    
    These tests verify that all cell effective_hdd values in the output CSV
    are within the valid range of 2,000–8,000 HDD units for the PNW climate.
    """

    @given(
        hdd_values=st.lists(
            st.floats(
                min_value=EFFECTIVE_HDD_MIN,
                max_value=EFFECTIVE_HDD_MAX,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=1,
            max_size=50,
        )
    )
    def test_all_cells_within_valid_range(self, hdd_values):
        """Property: All cell effective_hdd values must be within [2000, 8000].
        
        For any generated dataset with valid HDD values, the range check
        should pass and report zero issues.
        """
        # Create DataFrame with cells all within valid range
        cell_data = []
        for idx, hdd in enumerate(hdd_values):
            cell_data.append({
                "zip_code": "97201",
                "cell_id": f"cell_{idx:03d}",
                "cell_effective_hdd": hdd,
            })

        df = pd.DataFrame(cell_data)
        result = check_effective_hdd_range(df)

        # Property: All values in range → check passes
        assert result.passed, f"Expected pass but got issues: {result.issues}"
        assert result.num_issues == 0

    @given(
        num_valid=st.integers(min_value=1, max_value=50),
        num_invalid_low=st.integers(min_value=1, max_value=10),
        num_invalid_high=st.integers(min_value=1, max_value=10),
    )
    def test_out_of_range_values_detected(self, num_valid, num_invalid_low, num_invalid_high):
        """Property: Out-of-range values must be detected and reported.
        
        For any dataset with values outside [2000, 8000], the range check
        should fail and report exactly the number of out-of-range values.
        """
        cell_data = []

        # Add valid cells
        for i in range(num_valid):
            cell_data.append({
                "zip_code": "97201",
                "cell_id": f"cell_{i:03d}",
                "cell_effective_hdd": 5000.0,  # Valid
            })

        # Add cells below minimum
        for i in range(num_invalid_low):
            cell_data.append({
                "zip_code": "97201",
                "cell_id": f"cell_{num_valid + i:03d}",
                "cell_effective_hdd": 1500.0,  # Below 2000
            })

        # Add cells above maximum
        for i in range(num_invalid_high):
            cell_data.append({
                "zip_code": "97201",
                "cell_id": f"cell_{num_valid + num_invalid_low + i:03d}",
                "cell_effective_hdd": 9000.0,  # Above 8000
            })

        df = pd.DataFrame(cell_data)
        result = check_effective_hdd_range(df)

        # Property: Out-of-range values present → check fails
        expected_issues = num_invalid_low + num_invalid_high
        assert not result.passed, "Expected fail but check passed"
        assert result.num_issues == expected_issues, (
            f"Expected {expected_issues} issues but got {result.num_issues}"
        )

    def test_boundary_values_accepted(self):
        """Property: Boundary values (2000 and 8000) must be accepted.
        
        The range check should accept values exactly at the boundaries.
        """
        df = pd.DataFrame({
            "zip_code": ["97201", "97201"],
            "cell_id": ["cell_001", "cell_002"],
            "cell_effective_hdd": [EFFECTIVE_HDD_MIN, EFFECTIVE_HDD_MAX],
        })

        result = check_effective_hdd_range(df)

        # Property: Boundary values are valid
        assert result.passed, f"Boundary values rejected: {result.issues}"
        assert result.num_issues == 0

    def test_just_outside_boundaries_rejected(self):
        """Property: Values just outside boundaries must be rejected.
        
        Values at 1999.9 and 8000.1 should be flagged as out of range.
        """
        df = pd.DataFrame({
            "zip_code": ["97201", "97201"],
            "cell_id": ["cell_001", "cell_002"],
            "cell_effective_hdd": [EFFECTIVE_HDD_MIN - 0.1, EFFECTIVE_HDD_MAX + 0.1],
        })

        result = check_effective_hdd_range(df)

        # Property: Just-outside-boundary values are invalid
        assert not result.passed, "Just-outside-boundary values accepted"
        assert result.num_issues == 2

    @given(
        hdd_values=st.lists(
            st.floats(
                min_value=EFFECTIVE_HDD_MIN,
                max_value=EFFECTIVE_HDD_MAX,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=1,
            max_size=100,
        )
    )
    def test_all_valid_hdd_values_pass(self, hdd_values):
        """Property: Any dataset with all valid HDD values must pass.
        
        This is a generative property test that creates random datasets
        with valid HDD values and verifies they all pass the range check.
        """
        cell_data = []
        for idx, hdd in enumerate(hdd_values):
            cell_data.append({
                "zip_code": "97201",
                "cell_id": f"cell_{idx:03d}",
                "cell_effective_hdd": hdd,
            })

        df = pd.DataFrame(cell_data)
        result = check_effective_hdd_range(df)

        # Property: All valid values → pass
        assert result.passed, f"Valid values rejected: {result.issues}"
        assert result.num_issues == 0

    def test_mixed_valid_and_invalid_cells(self):
        """Property: Mixed valid/invalid cells must report only invalid ones.
        
        When a dataset contains both valid and invalid cells, only the
        invalid cells should be reported in the issues list.
        """
        df = pd.DataFrame({
            "zip_code": ["97201", "97201", "97201", "97201"],
            "cell_id": ["cell_001", "cell_002", "cell_003", "cell_004"],
            "cell_effective_hdd": [5000.0, 1500.0, 8000.0, 9000.0],
        })

        result = check_effective_hdd_range(df)

        # Property: Only invalid cells reported
        assert not result.passed
        assert result.num_issues == 2  # cell_002 and cell_004
        assert all("cell_002" in issue or "cell_004" in issue for issue in result.issues)

    def test_range_check_identifies_correct_cells(self):
        """Property: Range check must identify the exact cells that are out of range.
        
        The issues list should contain the zip_code and cell_id of each
        out-of-range cell, allowing users to locate and investigate problems.
        """
        df = pd.DataFrame({
            "zip_code": ["97201", "97202", "97203"],
            "cell_id": ["cell_001", "cell_001", "cell_001"],
            "cell_effective_hdd": [1500.0, 5000.0, 9000.0],
        })

        result = check_effective_hdd_range(df)

        # Property: Issues must identify specific cells
        assert not result.passed
        assert result.num_issues == 2
        assert any("97201" in issue and "cell_001" in issue for issue in result.issues)
        assert any("97203" in issue and "cell_001" in issue for issue in result.issues)

    def test_empty_dataframe_passes(self):
        """Property: Empty DataFrame should pass (no cells to check).
        
        An empty DataFrame has no out-of-range values, so the check passes.
        """
        df = pd.DataFrame({
            "zip_code": [],
            "cell_id": [],
            "cell_effective_hdd": [],
        })

        result = check_effective_hdd_range(df)

        # Property: Empty dataset passes
        assert result.passed
        assert result.num_issues == 0

    def test_single_cell_in_range(self):
        """Property: Single cell within range must pass.
        
        A dataset with a single cell in the valid range should pass.
        """
        df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["cell_001"],
            "cell_effective_hdd": [5000.0],
        })

        result = check_effective_hdd_range(df)

        # Property: Single valid cell passes
        assert result.passed
        assert result.num_issues == 0

    def test_single_cell_out_of_range(self):
        """Property: Single cell outside range must fail.
        
        A dataset with a single cell outside the valid range should fail.
        """
        df = pd.DataFrame({
            "zip_code": ["97201"],
            "cell_id": ["cell_001"],
            "cell_effective_hdd": [1500.0],
        })

        result = check_effective_hdd_range(df)

        # Property: Single invalid cell fails
        assert not result.passed
        assert result.num_issues == 1
