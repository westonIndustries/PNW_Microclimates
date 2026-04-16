"""
Tests for write_qa_report module.

Tests the generation of HTML and Markdown QA reports with cell-level
and ZIP-level statistics.
"""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.output.write_qa_report import (
    compute_statistics,
    write_html_report,
    write_markdown_report,
    write_qa_reports,
)
from src.validation.qa_checks import QACheckResult


@pytest.fixture
def sample_terrain_df():
    """Create a sample terrain attributes DataFrame for testing."""
    data = {
        "zip_code": ["97201", "97201", "97201", "97202", "97202"],
        "cell_id": ["cell_001", "cell_002", "aggregate", "cell_001", "aggregate"],
        "cell_effective_hdd": [4500.0, 4700.0, 4600.0, 5200.0, 5200.0],
        "hdd_terrain_mult": [1.05, 1.03, 1.04, 1.10, 1.10],
        "hdd_elev_addition": [100.0, 150.0, 125.0, 200.0, 200.0],
        "hdd_uhi_reduction": [50.0, 40.0, 45.0, 20.0, 20.0],
        "uhi_offset_f": [2.5, 2.0, 2.25, 1.0, 1.0],
        "road_temp_offset_f": [1.5, 1.0, 1.25, 0.5, 0.5],
        "wind_infiltration_mult": [1.1, 1.15, 1.125, 1.05, 1.05],
        "num_cells": [None, None, 2, None, 1],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_qa_results():
    """Create sample QA check results for testing."""
    return {
        "check_1": QACheckResult(
            check_name="Test Check 1",
            passed=True,
            num_issues=0,
            issues=[],
            severity="info",
        ),
        "check_2": QACheckResult(
            check_name="Test Check 2",
            passed=False,
            num_issues=2,
            issues=["Issue 1", "Issue 2"],
            severity="warning",
        ),
    }


def test_compute_statistics(sample_terrain_df):
    """Test computation of cell-level and ZIP-level statistics."""
    stats = compute_statistics(sample_terrain_df)

    # Check cell-level stats
    assert stats["cell_stats"]["num_cells"] == 3
    assert stats["cell_stats"]["hdd_mean"] == pytest.approx(4800.0, rel=0.01)
    assert stats["cell_stats"]["hdd_min"] == 4500.0
    assert stats["cell_stats"]["hdd_max"] == 5200.0

    # Check ZIP-level stats
    assert stats["zip_stats"]["num_zips"] == 2
    assert stats["zip_stats"]["hdd_mean"] == pytest.approx(4900.0, rel=0.01)
    assert stats["zip_stats"]["hdd_min"] == 4600.0
    assert stats["zip_stats"]["hdd_max"] == 5200.0

    # Check correction stats
    assert "hdd_terrain_mult" in stats["cell_corrections"]
    assert stats["cell_corrections"]["hdd_terrain_mult"]["mean"] == pytest.approx(1.06, rel=0.01)


def test_write_markdown_report(sample_terrain_df, sample_qa_results):
    """Test Markdown report generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "qa_report.md"
        write_markdown_report(sample_qa_results, sample_terrain_df, output_path)

        assert output_path.exists()
        content = output_path.read_text()

        # Check for key sections
        assert "# QA Report" in content
        assert "## Summary" in content
        assert "### Cell-Level Statistics" in content
        assert "### ZIP-Level Statistics" in content
        assert "## QA Check Results" in content
        assert "Test Check 1" in content
        assert "Test Check 2" in content

        # Check for statistics
        assert "Total Cells" in content and "3" in content
        assert "Total ZIP Codes" in content and "2" in content


def test_write_html_report(sample_terrain_df, sample_qa_results):
    """Test HTML report generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "qa_report.html"
        write_html_report(sample_qa_results, sample_terrain_df, output_path)

        assert output_path.exists()
        content = output_path.read_text()

        # Check for HTML structure
        assert "<!DOCTYPE html>" in content
        assert "<html>" in content
        assert "</html>" in content
        assert "<title>QA Report" in content

        # Check for key sections
        assert "Cell-Level Statistics" in content
        assert "ZIP-Level Statistics" in content
        assert "QA Check Results" in content
        assert "Test Check 1" in content
        assert "Test Check 2" in content

        # Check for statistics
        assert "Total Cells" in content
        assert "Total ZIP Codes" in content


def test_write_qa_reports(sample_terrain_df, sample_qa_results):
    """Test generation of both HTML and Markdown reports."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        html_path, md_path = write_qa_reports(sample_qa_results, sample_terrain_df, output_dir)

        # Check both files exist
        assert html_path.exists()
        assert md_path.exists()

        # Check file names
        assert html_path.name == "qa_report.html"
        assert md_path.name == "qa_report.md"

        # Check content
        html_content = html_path.read_text()
        md_content = md_path.read_text()

        assert "QA Report" in html_content
        assert "QA Report" in md_content


def test_statistics_with_empty_corrections():
    """Test statistics computation with missing correction columns."""
    data = {
        "zip_code": ["97201", "97201"],
        "cell_id": ["cell_001", "aggregate"],
        "cell_effective_hdd": [4500.0, 4500.0],
    }
    df = pd.DataFrame(data)

    stats = compute_statistics(df)

    # Should still compute basic stats
    assert stats["cell_stats"]["num_cells"] == 1
    assert stats["cell_stats"]["hdd_mean"] == 4500.0
    assert stats["zip_stats"]["num_zips"] == 1

    # Corrections should be empty
    assert len(stats["cell_corrections"]) == 0


def test_html_report_styling(sample_terrain_df, sample_qa_results):
    """Test that HTML report includes proper styling."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "qa_report.html"
        write_html_report(sample_qa_results, sample_terrain_df, output_path)

        content = output_path.read_text()

        # Check for CSS styling
        assert "<style>" in content
        assert "background:" in content
        assert "color:" in content
        assert "border" in content

        # Check for responsive design
        assert "grid-template-columns" in content
        assert "max-width" in content


def test_markdown_report_formatting(sample_terrain_df, sample_qa_results):
    """Test that Markdown report has proper formatting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "qa_report.md"
        write_markdown_report(sample_qa_results, sample_terrain_df, output_path)

        content = output_path.read_text()

        # Check for Markdown formatting
        assert "# " in content  # H1
        assert "## " in content  # H2
        assert "### " in content  # H3
        assert "- " in content  # Lists
        assert "**" in content  # Bold
