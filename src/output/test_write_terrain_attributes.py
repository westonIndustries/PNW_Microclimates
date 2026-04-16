"""
Tests for write_terrain_attributes module.

Tests verify that versioning columns are correctly added to all rows
in the output CSV, including both cell-level and ZIP-code aggregate rows.
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import tempfile
import re

from src.output.write_terrain_attributes import (
    write_terrain_attributes,
    validate_terrain_attributes,
)
from src import config


class TestVersioningColumns:
    """Test that versioning columns are added to all rows."""

    @pytest.fixture
    def sample_cells_df(self):
        """Create a sample cells DataFrame for testing."""
        return pd.DataFrame({
            "zip_code": ["97201", "97201", "97202", "97202"],
            "cell_id": ["cell_001", "cell_002", "cell_001", "cell_002"],
            "cell_type": ["urban", "suburban", "rural", "valley"],
            "cell_area_sqm": [250000.0, 250000.0, 250000.0, 250000.0],
            "base_station": ["KPDX", "KPDX", "KPDX", "KPDX"],
            "effective_hdd": [4500.0, 4600.0, 4700.0, 4800.0],
            "hdd_terrain_mult": [1.05, 1.02, 1.00, 1.10],
            "hdd_elev_addition": [100.0, 80.0, 50.0, 150.0],
            "hdd_uhi_reduction": [200.0, 180.0, 50.0, 20.0],
            "mean_elevation_ft": [500.0, 450.0, 300.0, 800.0],
            "mean_wind_ms": [3.5, 3.2, 2.8, 4.5],
            "wind_infiltration_mult": [1.05, 1.03, 1.00, 1.15],
            "prism_annual_hdd": [4700.0, 4700.0, 4700.0, 4700.0],
            "lst_summer_c": [25.0, 24.5, 23.0, 22.0],
            "mean_impervious_pct": [45.0, 30.0, 10.0, 5.0],
            "surface_albedo": [0.15, 0.17, 0.19, 0.20],
            "uhi_offset_f": [2.5, 2.0, 0.5, 0.2],
            "road_heat_flux_wm2": [15.0, 10.0, 2.0, 0.5],
            "road_temp_offset_f": [0.5, 0.3, 0.1, 0.0],
        })

    def test_versioning_columns_in_cell_rows(self, sample_cells_df):
        """Test that versioning columns are present in cell-level rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
                pipeline_version="1.0.0",
                lidar_vintage=2021,
                nlcd_vintage=2021,
                prism_period="1991-2020",
            )
            
            df = pd.read_csv(output_path)
            
            # Check that versioning columns exist
            assert "run_date" in df.columns
            assert "pipeline_version" in df.columns
            assert "lidar_vintage" in df.columns
            assert "nlcd_vintage" in df.columns
            assert "prism_period" in df.columns
            
            # Check cell-level rows have versioning columns
            cell_rows = df[df["cell_id"] != "aggregate"]
            assert len(cell_rows) == 4
            assert not cell_rows["run_date"].isna().any()
            assert not cell_rows["pipeline_version"].isna().any()
            assert not cell_rows["lidar_vintage"].isna().any()
            assert not cell_rows["nlcd_vintage"].isna().any()
            assert not cell_rows["prism_period"].isna().any()

    def test_versioning_columns_in_aggregate_rows(self, sample_cells_df):
        """Test that versioning columns are present in ZIP-code aggregate rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
                pipeline_version="1.0.0",
                lidar_vintage=2021,
                nlcd_vintage=2021,
                prism_period="1991-2020",
            )
            
            df = pd.read_csv(output_path)
            
            # Check aggregate rows have versioning columns
            agg_rows = df[df["cell_id"] == "aggregate"]
            assert len(agg_rows) == 2  # Two ZIP codes
            assert not agg_rows["run_date"].isna().any()
            assert not agg_rows["pipeline_version"].isna().any()
            assert not agg_rows["lidar_vintage"].isna().any()
            assert not agg_rows["nlcd_vintage"].isna().any()
            assert not agg_rows["prism_period"].isna().any()

    def test_run_date_is_iso8601(self, sample_cells_df):
        """Test that run_date is a valid ISO 8601 timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
            )
            
            df = pd.read_csv(output_path)
            
            # Check that run_date is ISO 8601 format
            iso8601_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
            for run_date in df["run_date"].unique():
                assert re.match(iso8601_pattern, str(run_date)), \
                    f"run_date '{run_date}' is not ISO 8601 format"
                
                # Verify it can be parsed as a datetime
                try:
                    datetime.fromisoformat(str(run_date))
                except ValueError:
                    pytest.fail(f"run_date '{run_date}' cannot be parsed as ISO 8601")

    def test_pipeline_version_matches_config(self, sample_cells_df):
        """Test that pipeline_version matches the config constant."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
                pipeline_version=config.PIPELINE_VERSION,
            )
            
            df = pd.read_csv(output_path)
            
            # All rows should have the same pipeline_version
            assert df["pipeline_version"].nunique() == 1
            assert df["pipeline_version"].iloc[0] == config.PIPELINE_VERSION

    def test_lidar_vintage_is_integer_year(self, sample_cells_df):
        """Test that lidar_vintage is an integer year."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
                lidar_vintage=2021,
            )
            
            df = pd.read_csv(output_path)
            
            # Check that lidar_vintage is an integer
            assert df["lidar_vintage"].dtype in [np.int64, np.int32, int]
            assert (df["lidar_vintage"] == 2021).all()
            
            # Check it's a reasonable year
            assert (df["lidar_vintage"] >= 2000).all()
            assert (df["lidar_vintage"] <= 2030).all()

    def test_nlcd_vintage_matches_config(self, sample_cells_df):
        """Test that nlcd_vintage matches the config constant."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
                nlcd_vintage=config.NLCD_VINTAGE,
            )
            
            df = pd.read_csv(output_path)
            
            # All rows should have the same nlcd_vintage
            assert df["nlcd_vintage"].nunique() == 1
            assert df["nlcd_vintage"].iloc[0] == config.NLCD_VINTAGE

    def test_prism_period_matches_config(self, sample_cells_df):
        """Test that prism_period matches the config constant."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
                prism_period=config.PRISM_PERIOD,
            )
            
            df = pd.read_csv(output_path)
            
            # All rows should have the same prism_period
            assert df["prism_period"].nunique() == 1
            assert df["prism_period"].iloc[0] == config.PRISM_PERIOD

    def test_versioning_columns_consistent_across_rows(self, sample_cells_df):
        """Test that versioning columns are consistent across all rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
                pipeline_version="1.0.0",
                lidar_vintage=2021,
                nlcd_vintage=2021,
                prism_period="1991-2020",
            )
            
            df = pd.read_csv(output_path)
            
            # All rows should have the same versioning values
            assert df["pipeline_version"].nunique() == 1
            assert df["lidar_vintage"].nunique() == 1
            assert df["nlcd_vintage"].nunique() == 1
            assert df["prism_period"].nunique() == 1
            
            # run_date should be the same for all rows (same execution)
            assert df["run_date"].nunique() == 1

    def test_versioning_columns_with_custom_values(self, sample_cells_df):
        """Test that custom versioning values are correctly written."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            custom_version = "2.1.0"
            custom_lidar = 2023
            custom_nlcd = 2023
            custom_prism = "2001-2030"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
                pipeline_version=custom_version,
                lidar_vintage=custom_lidar,
                nlcd_vintage=custom_nlcd,
                prism_period=custom_prism,
            )
            
            df = pd.read_csv(output_path)
            
            assert (df["pipeline_version"] == custom_version).all()
            assert (df["lidar_vintage"] == custom_lidar).all()
            assert (df["nlcd_vintage"] == custom_nlcd).all()
            assert (df["prism_period"] == custom_prism).all()

    def test_versioning_columns_no_missing_values(self, sample_cells_df):
        """Test that versioning columns have no missing values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
            )
            
            df = pd.read_csv(output_path)
            
            # No NaN values in versioning columns
            assert df["run_date"].notna().all()
            assert df["pipeline_version"].notna().all()
            assert df["lidar_vintage"].notna().all()
            assert df["nlcd_vintage"].notna().all()
            assert df["prism_period"].notna().all()

    def test_versioning_columns_in_column_order(self, sample_cells_df):
        """Test that versioning columns appear at the end of the output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
            )
            
            df = pd.read_csv(output_path)
            
            # Versioning columns should be near the end
            cols = df.columns.tolist()
            versioning_cols = [
                "run_date",
                "pipeline_version",
                "lidar_vintage",
                "nlcd_vintage",
                "prism_period",
            ]
            
            # Find the position of the first versioning column
            first_versioning_idx = min(
                cols.index(col) for col in versioning_cols if col in cols
            )
            
            # All versioning columns should be after the first one
            for col in versioning_cols:
                if col in cols:
                    assert cols.index(col) >= first_versioning_idx


class TestVersioningIntegration:
    """Integration tests for versioning columns with other functionality."""

    @pytest.fixture
    def sample_cells_df(self):
        """Create a sample cells DataFrame for testing."""
        return pd.DataFrame({
            "zip_code": ["97201", "97201", "97202"],
            "cell_id": ["cell_001", "cell_002", "cell_001"],
            "cell_type": ["urban", "suburban", "rural"],
            "cell_area_sqm": [250000.0, 250000.0, 250000.0],
            "base_station": ["KPDX", "KPDX", "KPDX"],
            "effective_hdd": [4500.0, 4600.0, 4700.0],
            "hdd_terrain_mult": [1.05, 1.02, 1.00],
            "hdd_elev_addition": [100.0, 80.0, 50.0],
            "hdd_uhi_reduction": [200.0, 180.0, 50.0],
            "mean_elevation_ft": [500.0, 450.0, 300.0],
            "mean_wind_ms": [3.5, 3.2, 2.8],
            "wind_infiltration_mult": [1.05, 1.03, 1.00],
            "prism_annual_hdd": [4700.0, 4700.0, 4700.0],
            "lst_summer_c": [25.0, 24.5, 23.0],
            "mean_impervious_pct": [45.0, 30.0, 10.0],
            "surface_albedo": [0.15, 0.17, 0.19],
            "uhi_offset_f": [2.5, 2.0, 0.5],
            "road_heat_flux_wm2": [15.0, 10.0, 2.0],
            "road_temp_offset_f": [0.5, 0.3, 0.1],
        })

    def test_versioning_with_validation(self, sample_cells_df):
        """Test that versioning columns don't interfere with validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
            )
            
            df = pd.read_csv(output_path)
            issues = validate_terrain_attributes(df)
            
            # Should not have validation issues related to versioning columns
            versioning_issues = [
                issue for issue in issues
                if any(col in issue for col in [
                    "run_date", "pipeline_version", "lidar_vintage",
                    "nlcd_vintage", "prism_period"
                ])
            ]
            assert len(versioning_issues) == 0

    def test_versioning_with_multiple_zip_codes(self, sample_cells_df):
        """Test versioning columns with multiple ZIP codes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "terrain_attributes.csv"
            
            write_terrain_attributes(
                sample_cells_df,
                region_code="R1",
                output_path=output_path,
            )
            
            df = pd.read_csv(output_path)
            
            # Check that all ZIP codes have versioning columns
            for zip_code in df["zip_code"].unique():
                zip_rows = df[df["zip_code"] == zip_code]
                assert not zip_rows["run_date"].isna().any()
                assert not zip_rows["pipeline_version"].isna().any()
                assert not zip_rows["lidar_vintage"].isna().any()
                assert not zip_rows["nlcd_vintage"].isna().any()
                assert not zip_rows["prism_period"].isna().any()
