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
