"""
QA checks for microclimate pipeline output.

Performs range checks, directional sanity checks, and consistency verification
on the terrain_attributes.csv output to catch implausible values before they
enter the simulation pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from src import config

logger = logging.getLogger(__name__)

# Constants for QA checks
EFFECTIVE_HDD_MIN = 2000  # Minimum plausible HDD for PNW
EFFECTIVE_HDD_MAX = 8000  # Maximum plausible HDD for PNW
FLOATING_POINT_TOLERANCE = 1e-6  # Tolerance for floating-point comparisons
AGGREGATE_HDD_TOLERANCE = 0.1  # Tolerance for aggregate HDD verification (HDD units)


@dataclass
class QACheckResult:
    """Result of a single QA check."""

    check_name: str
    passed: bool
    num_issues: int
    issues: list[str]
    severity: str  # "error", "warning", "info"

    def __str__(self) -> str:
        """Format result as string."""
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status} | {self.check_name} ({self.severity}): {self.num_issues} issues"


def verify_aggregate_hdd_consistency(
    terrain_df: pd.DataFrame,
    tolerance: float = AGGREGATE_HDD_TOLERANCE,
) -> QACheckResult:
    """Verify that ZIP-code aggregate effective_hdd equals mean of all cells.

    For each ZIP code, checks that the aggregate row's cell_effective_hdd
    equals the mean of all cell-level rows for that ZIP code, within a
    specified tolerance (default 0.1 HDD units).

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with cell-level and aggregate rows from terrain_attributes.csv.
        Must contain columns: zip_code, cell_id, cell_effective_hdd.
    tolerance : float, optional
        Tolerance for mismatch detection in HDD units (default 0.1).

    Returns
    -------
    QACheckResult
        Result object with check_name, passed, num_issues, issues list, and severity.
    """
    issues = []

    # Group by ZIP code
    for zip_code, group in terrain_df.groupby("zip_code"):
        # Find aggregate row for this ZIP code
        agg_rows = group[group["cell_id"] == "aggregate"]

        if len(agg_rows) == 0:
            issues.append(f"ZIP {zip_code}: No aggregate row found")
            continue

        if len(agg_rows) > 1:
            issues.append(f"ZIP {zip_code}: Multiple aggregate rows found ({len(agg_rows)})")
            continue

        agg_row = agg_rows.iloc[0]
        agg_hdd = agg_row["cell_effective_hdd"]

        # Find all cell rows for this ZIP code
        cell_rows = group[group["cell_id"] != "aggregate"]

        if len(cell_rows) == 0:
            issues.append(f"ZIP {zip_code}: No cell rows found (only aggregate)")
            continue

        # Compute mean of cell HDD values
        cell_hdd_values = cell_rows["cell_effective_hdd"].dropna()

        if len(cell_hdd_values) == 0:
            issues.append(f"ZIP {zip_code}: All cell HDD values are NaN")
            continue

        mean_cell_hdd = cell_hdd_values.mean()

        # Check if aggregate HDD matches mean of cells
        hdd_diff = abs(agg_hdd - mean_cell_hdd)

        if hdd_diff > tolerance:
            issues.append(
                f"ZIP {zip_code}: Aggregate HDD mismatch. "
                f"Aggregate={agg_hdd:.2f}, Mean of cells={mean_cell_hdd:.2f}, "
                f"Difference={hdd_diff:.2f} (tolerance={tolerance})"
            )

    passed = len(issues) == 0
    severity = "error" if not passed else "info"

    return QACheckResult(
        check_name="Aggregate HDD Consistency",
        passed=passed,
        num_issues=len(issues),
        issues=issues,
        severity=severity,
    )


def check_effective_hdd_range(
    terrain_df: pd.DataFrame,
    hdd_min: float = EFFECTIVE_HDD_MIN,
    hdd_max: float = EFFECTIVE_HDD_MAX,
) -> QACheckResult:
    """Check that all effective_hdd values are within plausible range.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with terrain attributes. Must contain cell_effective_hdd column.
    hdd_min : float, optional
        Minimum plausible HDD (default 2000).
    hdd_max : float, optional
        Maximum plausible HDD (default 8000).

    Returns
    -------
    QACheckResult
        Result object with check details.
    """
    issues = []

    # Check for values outside range
    out_of_range = terrain_df[
        (terrain_df["cell_effective_hdd"] < hdd_min) | (terrain_df["cell_effective_hdd"] > hdd_max)
    ]

    if len(out_of_range) > 0:
        for idx, row in out_of_range.iterrows():
            zip_code = row["zip_code"]
            cell_id = row["cell_id"]
            hdd = row["cell_effective_hdd"]
            issues.append(
                f"ZIP {zip_code} {cell_id}: HDD={hdd:.1f} outside range [{hdd_min}, {hdd_max}]"
            )

    passed = len(issues) == 0
    severity = "warning" if not passed else "info"

    return QACheckResult(
        check_name="Effective HDD Range",
        passed=passed,
        num_issues=len(issues),
        issues=issues,
        severity=severity,
    )


def check_directional_sanity(terrain_df: pd.DataFrame) -> QACheckResult:
    """Check directional sanity of terrain corrections.

    Verifies that:
    - Urban cells have lower effective_hdd than rural cells (UHI reduces heating demand)
    - Windward cells have higher effective_hdd than leeward cells
    - High-elevation cells have higher effective_hdd than low-elevation cells

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with terrain attributes. Must contain:
        - cell_type: urban, suburban, rural, valley, ridge, gorge
        - terrain_position: windward, leeward, valley, ridge
        - mean_elevation_ft: elevation in feet
        - cell_effective_hdd: effective HDD value

    Returns
    -------
    QACheckResult
        Result object with check details.
    """
    issues = []

    # Check 1: Urban < Rural (UHI reduces heating demand)
    if "cell_type" in terrain_df.columns:
        urban_rows = terrain_df[terrain_df["cell_type"] == "urban"]
        rural_rows = terrain_df[terrain_df["cell_type"] == "rural"]

        if len(urban_rows) > 0 and len(rural_rows) > 0:
            urban_mean = urban_rows["cell_effective_hdd"].mean()
            rural_mean = rural_rows["cell_effective_hdd"].mean()

            if urban_mean > rural_mean:
                issues.append(
                    f"Urban cells have higher HDD than rural cells. "
                    f"Urban={urban_mean:.1f}, Rural={rural_mean:.1f}. "
                    f"Expected: Urban < Rural (UHI effect)"
                )

    # Check 2: Windward > Leeward (wind exposure increases heating demand)
    if "terrain_position" in terrain_df.columns:
        windward_rows = terrain_df[terrain_df["terrain_position"] == "windward"]
        leeward_rows = terrain_df[terrain_df["terrain_position"] == "leeward"]

        if len(windward_rows) > 0 and len(leeward_rows) > 0:
            windward_mean = windward_rows["cell_effective_hdd"].mean()
            leeward_mean = leeward_rows["cell_effective_hdd"].mean()

            if windward_mean < leeward_mean:
                issues.append(
                    f"Windward cells have lower HDD than leeward cells. "
                    f"Windward={windward_mean:.1f}, Leeward={leeward_mean:.1f}. "
                    f"Expected: Windward > Leeward (wind exposure)"
                )

    # Check 3: High elevation > Low elevation (lapse rate increases HDD with elevation)
    if "mean_elevation_ft" in terrain_df.columns:
        # Split into high and low elevation groups (median split)
        median_elev = terrain_df["mean_elevation_ft"].median()
        high_elev_rows = terrain_df[terrain_df["mean_elevation_ft"] > median_elev]
        low_elev_rows = terrain_df[terrain_df["mean_elevation_ft"] <= median_elev]

        if len(high_elev_rows) > 0 and len(low_elev_rows) > 0:
            high_elev_mean = high_elev_rows["cell_effective_hdd"].mean()
            low_elev_mean = low_elev_rows["cell_effective_hdd"].mean()

            if high_elev_mean < low_elev_mean:
                issues.append(
                    f"High-elevation cells have lower HDD than low-elevation cells. "
                    f"High={high_elev_mean:.1f}, Low={low_elev_mean:.1f}. "
                    f"Expected: High > Low (lapse rate)"
                )

    passed = len(issues) == 0
    severity = "warning" if not passed else "info"

    return QACheckResult(
        check_name="Directional Sanity",
        passed=passed,
        num_issues=len(issues),
        issues=issues,
        severity=severity,
    )


def check_cell_reliability(terrain_df: pd.DataFrame, min_pixels: int = 10) -> QACheckResult:
    """Flag cells with fewer than minimum valid pixels as potentially unreliable.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with terrain attributes. Must contain num_valid_pixels column.
    min_pixels : int, optional
        Minimum number of valid 1m pixels per cell (default 10).

    Returns
    -------
    QACheckResult
        Result object with check details.
    """
    issues = []

    if "num_valid_pixels" not in terrain_df.columns:
        return QACheckResult(
            check_name="Cell Reliability",
            passed=True,
            num_issues=0,
            issues=[],
            severity="info",
        )

    # Find cells with too few valid pixels
    unreliable = terrain_df[
        (terrain_df["cell_id"] != "aggregate") & (terrain_df["num_valid_pixels"] < min_pixels)
    ]

    for idx, row in unreliable.iterrows():
        zip_code = row["zip_code"]
        cell_id = row["cell_id"]
        num_pixels = row["num_valid_pixels"]
        issues.append(
            f"ZIP {zip_code} {cell_id}: Only {num_pixels} valid pixels (< {min_pixels}). "
            f"Result may be unreliable."
        )

    passed = len(issues) == 0
    severity = "warning" if not passed else "info"

    return QACheckResult(
        check_name="Cell Reliability",
        passed=passed,
        num_issues=len(issues),
        issues=issues,
        severity=severity,
    )


def run_all_qa_checks(terrain_df: pd.DataFrame) -> dict[str, QACheckResult]:
    """Run all QA checks on terrain attributes DataFrame.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with cell-level and aggregate rows from terrain_attributes.csv.

    Returns
    -------
    dict[str, QACheckResult]
        Dictionary mapping check names to QACheckResult objects.
    """
    results = {}

    # Run all checks
    results["aggregate_hdd_consistency"] = verify_aggregate_hdd_consistency(terrain_df)
    results["effective_hdd_range"] = check_effective_hdd_range(terrain_df)
    results["directional_sanity"] = check_directional_sanity(terrain_df)
    results["cell_reliability"] = check_cell_reliability(terrain_df)

    # Log summary
    num_passed = sum(1 for r in results.values() if r.passed)
    num_total = len(results)

    logger.info(f"QA checks complete: {num_passed}/{num_total} passed")

    for check_name, result in results.items():
        logger.info(f"  {result}")
        if result.issues:
            for issue in result.issues[:5]:  # Log first 5 issues
                logger.warning(f"    - {issue}")
            if len(result.issues) > 5:
                logger.warning(f"    ... and {len(result.issues) - 5} more issues")

    return results
