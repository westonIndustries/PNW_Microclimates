"""
QA checks for microclimate pipeline output.

Performs range checks, directional sanity checks, consistency verification,
hard failure detection, and optional billing comparison on the terrain_attributes.csv
output to catch implausible values before they enter the simulation pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src import config

logger = logging.getLogger(__name__)

# Constants for QA checks
EFFECTIVE_HDD_MIN = 2000  # Minimum plausible HDD for PNW
EFFECTIVE_HDD_MAX = 8000  # Maximum plausible HDD for PNW
EFFECTIVE_HDD_HARD_MIN = 0  # Hard failure threshold (below this is impossible)
EFFECTIVE_HDD_HARD_MAX = 15000  # Hard failure threshold (above this is implausible)
FLOATING_POINT_TOLERANCE = 1e-6  # Tolerance for floating-point comparisons
AGGREGATE_HDD_TOLERANCE = 0.1  # Tolerance for aggregate HDD verification (HDD units)
BILLING_DIVERGENCE_THRESHOLD = 0.15  # 15% divergence threshold for billing comparison


@dataclass
class QACheckResult:
    """Result of a single QA check."""

    check_name: str
    passed: bool
    num_issues: int
    issues: list[str]
    severity: str  # "error", "warning", "info"
    is_hard_failure: bool = False  # True if this check indicates a hard failure

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


def check_hard_failures(
    terrain_df: pd.DataFrame,
    hdd_hard_min: float = EFFECTIVE_HDD_HARD_MIN,
    hdd_hard_max: float = EFFECTIVE_HDD_HARD_MAX,
) -> QACheckResult:
    """Check for hard failures: HDD < 0 or > 15,000.

    Hard failures indicate data corruption or fundamental errors that must be
    fixed before the pipeline can proceed.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with terrain attributes. Must contain cell_effective_hdd column.
    hdd_hard_min : float, optional
        Hard minimum HDD threshold (default 0).
    hdd_hard_max : float, optional
        Hard maximum HDD threshold (default 15000).

    Returns
    -------
    QACheckResult
        Result object with check details and is_hard_failure=True if any failures detected.
    """
    issues = []

    # Check for values outside hard failure range
    hard_failures = terrain_df[
        (terrain_df["cell_effective_hdd"] < hdd_hard_min)
        | (terrain_df["cell_effective_hdd"] > hdd_hard_max)
    ]

    if len(hard_failures) > 0:
        for idx, row in hard_failures.iterrows():
            zip_code = row["zip_code"]
            cell_id = row["cell_id"]
            hdd = row["cell_effective_hdd"]
            issues.append(
                f"ZIP {zip_code} {cell_id}: HDD={hdd:.1f} outside hard limits "
                f"[{hdd_hard_min}, {hdd_hard_max}]. Data corruption suspected."
            )

    passed = len(issues) == 0
    severity = "error" if not passed else "info"

    return QACheckResult(
        check_name="Hard Failure Check",
        passed=passed,
        num_issues=len(issues),
        issues=issues,
        severity=severity,
        is_hard_failure=not passed,
    )


def check_billing_comparison(
    terrain_df: pd.DataFrame,
    billing_csv_path: Optional[Path] = None,
    divergence_threshold: float = BILLING_DIVERGENCE_THRESHOLD,
) -> QACheckResult:
    """Compare effective_hdd against billing-derived therms per customer.

    This check is optional and requires a billing reference CSV. If the CSV
    is not found, the check is skipped and a notice is logged.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with terrain attributes. Must contain zip_code and
        cell_effective_hdd columns.
    billing_csv_path : Path, optional
        Path to billing reference CSV with columns: zip_code, therms_per_customer.
        If None or file not found, check is skipped.
    divergence_threshold : float, optional
        Threshold for flagging divergence as warning (default 0.15 = 15%).

    Returns
    -------
    QACheckResult
        Result object with check details. If billing data not available,
        returns a passed result with a notice.
    """
    issues = []

    # If no billing CSV path provided, skip check
    if billing_csv_path is None:
        logger.info("Billing comparison check skipped: no billing CSV path provided")
        return QACheckResult(
            check_name="Billing Comparison",
            passed=True,
            num_issues=0,
            issues=["Skipped: no billing data provided"],
            severity="info",
        )

    # If billing CSV doesn't exist, skip check
    if not billing_csv_path.exists():
        logger.info(f"Billing comparison check skipped: {billing_csv_path} not found")
        return QACheckResult(
            check_name="Billing Comparison",
            passed=True,
            num_issues=0,
            issues=[f"Skipped: billing CSV not found at {billing_csv_path}"],
            severity="info",
        )

    # Load billing data
    try:
        billing_df = pd.read_csv(billing_csv_path)
    except Exception as e:
        logger.warning(f"Failed to load billing CSV: {e}")
        return QACheckResult(
            check_name="Billing Comparison",
            passed=True,
            num_issues=0,
            issues=[f"Skipped: error reading billing CSV: {e}"],
            severity="info",
        )

    # Validate billing CSV has required columns
    if "zip_code" not in billing_df.columns or "therms_per_customer" not in billing_df.columns:
        logger.warning("Billing CSV missing required columns (zip_code, therms_per_customer)")
        return QACheckResult(
            check_name="Billing Comparison",
            passed=True,
            num_issues=0,
            issues=["Skipped: billing CSV missing required columns"],
            severity="info",
        )

    # Get ZIP-code aggregates from terrain_df
    agg_df = terrain_df[terrain_df["cell_id"] == "aggregate"].copy()

    if len(agg_df) == 0:
        logger.warning("No aggregate rows found in terrain_df for billing comparison")
        return QACheckResult(
            check_name="Billing Comparison",
            passed=True,
            num_issues=0,
            issues=["Skipped: no aggregate rows in terrain data"],
            severity="info",
        )

    # Ensure zip_code is string in both dataframes for merge
    agg_df["zip_code"] = agg_df["zip_code"].astype(str)
    billing_df["zip_code"] = billing_df["zip_code"].astype(str)

    # Merge with billing data
    merged = agg_df.merge(
        billing_df, on="zip_code", how="inner", suffixes=("_terrain", "_billing")
    )

    if len(merged) == 0:
        logger.warning("No ZIP codes matched between terrain and billing data")
        return QACheckResult(
            check_name="Billing Comparison",
            passed=True,
            num_issues=0,
            issues=["Skipped: no matching ZIP codes in billing data"],
            severity="info",
        )

    # Compare effective_hdd to therms_per_customer
    # Assume 1 HDD ≈ 1 therm per customer (rough equivalence for comparison)
    for idx, row in merged.iterrows():
        zip_code = row["zip_code"]
        eff_hdd = row["cell_effective_hdd"]
        therms = row["therms_per_customer"]

        # Compute divergence as percentage difference
        if therms > 0:
            divergence = abs(eff_hdd - therms) / therms
        else:
            divergence = float("inf")

        if divergence > divergence_threshold:
            issues.append(
                f"ZIP {zip_code}: effective_hdd={eff_hdd:.1f} diverges from "
                f"billing therms_per_customer={therms:.1f} by {divergence*100:.1f}% "
                f"(threshold={divergence_threshold*100:.1f}%)"
            )

    passed = len(issues) == 0
    severity = "warning" if not passed else "info"

    return QACheckResult(
        check_name="Billing Comparison",
        passed=passed,
        num_issues=len(issues),
        issues=issues,
        severity=severity,
    )


def generate_qa_report(
    qa_results: dict[str, QACheckResult],
    terrain_df: pd.DataFrame,
    output_dir: Path = Path("output/microclimate/"),
) -> tuple[Path, Path]:
    """Generate HTML and Markdown QA reports.

    Parameters
    ----------
    qa_results : dict[str, QACheckResult]
        Dictionary of QA check results from run_all_qa_checks.
    terrain_df : pd.DataFrame
        Original terrain attributes DataFrame for summary statistics.
    output_dir : Path, optional
        Output directory for reports (default output/microclimate/).

    Returns
    -------
    tuple[Path, Path]
        Paths to generated HTML and Markdown report files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp
    timestamp = datetime.now().isoformat()

    # Compute summary statistics
    num_cells = len(terrain_df[terrain_df["cell_id"] != "aggregate"])
    num_zips = len(terrain_df[terrain_df["cell_id"] == "aggregate"])
    hdd_mean = terrain_df["cell_effective_hdd"].mean()
    hdd_min = terrain_df["cell_effective_hdd"].min()
    hdd_max = terrain_df["cell_effective_hdd"].max()
    hdd_std = terrain_df["cell_effective_hdd"].std()

    # Count issues by severity
    num_errors = sum(1 for r in qa_results.values() if r.severity == "error")
    num_warnings = sum(1 for r in qa_results.values() if r.severity == "warning")
    num_passed = sum(1 for r in qa_results.values() if r.passed)

    # Generate Markdown report
    md_lines = [
        "# QA Report — Microclimate Pipeline",
        "",
        f"**Generated**: {timestamp}",
        f"**Pipeline Version**: {config.PIPELINE_VERSION}",
        "",
        "## Summary",
        "",
        f"- **Total Cells**: {num_cells}",
        f"- **Total ZIP Codes**: {num_zips}",
        f"- **Effective HDD Mean**: {hdd_mean:.1f}",
        f"- **Effective HDD Range**: {hdd_min:.1f} — {hdd_max:.1f}",
        f"- **Effective HDD Std Dev**: {hdd_std:.1f}",
        "",
        "## QA Check Results",
        "",
        f"- **Passed**: {num_passed}/{len(qa_results)}",
        f"- **Errors**: {num_errors}",
        f"- **Warnings**: {num_warnings}",
        "",
    ]

    # Add detailed results for each check
    for check_name, result in qa_results.items():
        status = "✓ PASS" if result.passed else "✗ FAIL"
        md_lines.extend([
            f"### {result.check_name}",
            "",
            f"**Status**: {status}",
            f"**Severity**: {result.severity}",
            f"**Issues**: {result.num_issues}",
            "",
        ])

        if result.issues:
            md_lines.append("**Details**:")
            md_lines.append("")
            for issue in result.issues[:10]:  # Show first 10 issues
                md_lines.append(f"- {issue}")
            if len(result.issues) > 10:
                md_lines.append(f"- ... and {len(result.issues) - 10} more issues")
            md_lines.append("")

    # Write Markdown report
    md_path = output_dir / "qa_report.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    logger.info(f"Markdown QA report written to {md_path}")

    # Generate HTML report
    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "  <meta charset='utf-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1'>",
        "  <title>QA Report — Microclimate Pipeline</title>",
        "  <style>",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }",
        "    .container { max-width: 1000px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
        "    h1 { color: #333; border-bottom: 3px solid #0066cc; padding-bottom: 10px; }",
        "    h2 { color: #0066cc; margin-top: 30px; }",
        "    h3 { color: #555; margin-top: 20px; }",
        "    .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }",
        "    .summary-card { background: #f9f9f9; padding: 15px; border-left: 4px solid #0066cc; border-radius: 4px; }",
        "    .summary-card .label { font-size: 12px; color: #666; text-transform: uppercase; }",
        "    .summary-card .value { font-size: 24px; font-weight: bold; color: #333; }",
        "    .check-result { margin: 20px 0; padding: 15px; border-radius: 4px; border-left: 4px solid #ddd; }",
        "    .check-result.pass { background: #e8f5e9; border-left-color: #4caf50; }",
        "    .check-result.fail { background: #ffebee; border-left-color: #f44336; }",
        "    .check-result.warning { background: #fff3e0; border-left-color: #ff9800; }",
        "    .status { font-weight: bold; font-size: 14px; }",
        "    .status.pass { color: #4caf50; }",
        "    .status.fail { color: #f44336; }",
        "    .status.warning { color: #ff9800; }",
        "    .issues { margin-top: 10px; padding-left: 20px; }",
        "    .issues li { margin: 5px 0; font-size: 13px; color: #555; }",
        "    .timestamp { color: #999; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; }",
        "  </style>",
        "</head>",
        "<body>",
        "  <div class='container'>",
        "    <h1>QA Report — Microclimate Pipeline</h1>",
        f"    <p><strong>Generated</strong>: {timestamp}</p>",
        f"    <p><strong>Pipeline Version</strong>: {config.PIPELINE_VERSION}</p>",
        "",
        "    <h2>Summary</h2>",
        "    <div class='summary'>",
        f"      <div class='summary-card'><div class='label'>Total Cells</div><div class='value'>{num_cells}</div></div>",
        f"      <div class='summary-card'><div class='label'>Total ZIP Codes</div><div class='value'>{num_zips}</div></div>",
        f"      <div class='summary-card'><div class='label'>HDD Mean</div><div class='value'>{hdd_mean:.0f}</div></div>",
        f"      <div class='summary-card'><div class='label'>HDD Range</div><div class='value'>{hdd_min:.0f}–{hdd_max:.0f}</div></div>",
        f"      <div class='summary-card'><div class='label'>HDD Std Dev</div><div class='value'>{hdd_std:.0f}</div></div>",
        "    </div>",
        "",
        "    <h2>QA Check Results</h2>",
        "    <div class='summary'>",
        f"      <div class='summary-card'><div class='label'>Passed</div><div class='value'>{num_passed}/{len(qa_results)}</div></div>",
        f"      <div class='summary-card'><div class='label'>Errors</div><div class='value' style='color: #f44336;'>{num_errors}</div></div>",
        f"      <div class='summary-card'><div class='label'>Warnings</div><div class='value' style='color: #ff9800;'>{num_warnings}</div></div>",
        "    </div>",
        "",
    ]

    # Add detailed results for each check
    for check_name, result in qa_results.items():
        status_class = "pass" if result.passed else ("fail" if result.severity == "error" else "warning")
        status_text = "PASS" if result.passed else "FAIL"

        html_lines.extend([
            f"    <div class='check-result {status_class}'>",
            f"      <h3>{result.check_name}</h3>",
            f"      <p><span class='status {status_class}'>{status_text}</span> — {result.severity.upper()} ({result.num_issues} issues)</p>",
        ])

        if result.issues:
            html_lines.append("      <div class='issues'><ul>")
            for issue in result.issues[:10]:  # Show first 10 issues
                html_lines.append(f"        <li>{issue}</li>")
            if len(result.issues) > 10:
                html_lines.append(f"        <li><em>... and {len(result.issues) - 10} more issues</em></li>")
            html_lines.append("      </ul></div>")

        html_lines.append("    </div>")

    html_lines.extend([
        "    <div class='timestamp'>",
        f"      <p>Report generated at {timestamp}</p>",
        "    </div>",
        "  </div>",
        "</body>",
        "</html>",
    ])

    # Write HTML report
    html_path = output_dir / "qa_report.html"
    html_path.write_text("\n".join(html_lines), encoding="utf-8")
    logger.info(f"HTML QA report written to {html_path}")

    return html_path, md_path


def run_all_qa_checks(
    terrain_df: pd.DataFrame,
    billing_csv_path: Optional[Path] = None,
) -> dict[str, QACheckResult]:
    """Run all QA checks on terrain attributes DataFrame.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with cell-level and aggregate rows from terrain_attributes.csv.
    billing_csv_path : Path, optional
        Path to billing reference CSV for optional billing comparison check.

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
    results["hard_failures"] = check_hard_failures(terrain_df)
    results["billing_comparison"] = check_billing_comparison(terrain_df, billing_csv_path)
    results["monthly_hdd_profiles"] = check_monthly_hdd_profiles(terrain_df)

    # Log summary
    num_passed = sum(1 for r in results.values() if r.passed)
    num_total = len(results)
    num_hard_failures = sum(1 for r in results.values() if r.is_hard_failure)

    logger.info(f"QA checks complete: {num_passed}/{num_total} passed")

    if num_hard_failures > 0:
        logger.error(f"HARD FAILURES DETECTED: {num_hard_failures} check(s) failed")

    for check_name, result in results.items():
        logger.info(f"  {result}")
        if result.issues:
            for issue in result.issues[:5]:  # Log first 5 issues
                logger.warning(f"    - {issue}")
            if len(result.issues) > 5:
                logger.warning(f"    ... and {len(result.issues) - 5} more issues")

    return results



def check_monthly_hdd_profiles(
    terrain_df: pd.DataFrame,
    monthly_hdd_min: float = 0.0,
    monthly_hdd_max: float = 1000.0,
    annual_tolerance: float = 0.01,
) -> QACheckResult:
    """Check monthly HDD profiles for consistency and plausibility.

    Verifies that:
    - All monthly HDD values are non-negative
    - All monthly HDD values are within reasonable range (0-1000 for PNW)
    - Sum of 12 monthly HDD values approximately equals annual HDD (within tolerance)

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with terrain attributes. Must contain monthly HDD columns
        (effective_hdd_jan through effective_hdd_dec) and effective_hdd_annual.
    monthly_hdd_min : float, optional
        Minimum plausible monthly HDD (default 0.0).
    monthly_hdd_max : float, optional
        Maximum plausible monthly HDD (default 1000.0).
    annual_tolerance : float, optional
        Tolerance for sum of monthly vs annual HDD as fraction (default 0.01 = 1%).

    Returns
    -------
    QACheckResult
        Result object with check details.
    """
    issues = []
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    monthly_cols = [f"effective_hdd_{month}" for month in month_names]

    # Check if monthly columns exist
    if not any(col in terrain_df.columns for col in monthly_cols):
        return QACheckResult(
            check_name="Monthly HDD Profiles",
            passed=True,
            num_issues=0,
            issues=["Skipped: no monthly HDD columns found"],
            severity="info",
        )

    # Check 1: All monthly values are non-negative
    for col in monthly_cols:
        if col in terrain_df.columns:
            negative_rows = terrain_df[terrain_df[col] < monthly_hdd_min]
            if len(negative_rows) > 0:
                for idx, row in negative_rows.iterrows():
                    zip_code = row["zip_code"]
                    cell_id = row["cell_id"]
                    value = row[col]
                    issues.append(
                        f"ZIP {zip_code} {cell_id}: {col}={value:.1f} is negative"
                    )

    # Check 2: All monthly values are within reasonable range
    for col in monthly_cols:
        if col in terrain_df.columns:
            out_of_range = terrain_df[
                (terrain_df[col] < monthly_hdd_min) | (terrain_df[col] > monthly_hdd_max)
            ]
            if len(out_of_range) > 0:
                for idx, row in out_of_range.iterrows():
                    zip_code = row["zip_code"]
                    cell_id = row["cell_id"]
                    value = row[col]
                    issues.append(
                        f"ZIP {zip_code} {cell_id}: {col}={value:.1f} outside range [{monthly_hdd_min}, {monthly_hdd_max}]"
                    )

    # Check 3: Sum of monthly HDD ≈ annual HDD (if annual column exists)
    if "effective_hdd_annual" in terrain_df.columns:
        for idx, row in terrain_df.iterrows():
            # Compute sum of monthly values
            monthly_values = [row.get(col, np.nan) for col in monthly_cols]
            valid_monthly = [v for v in monthly_values if not np.isnan(v)]

            if len(valid_monthly) == 12:  # Only check if all 12 months present
                sum_monthly = sum(valid_monthly)
                annual = row["effective_hdd_annual"]

                if not np.isnan(annual) and annual > 0:
                    tolerance = annual * annual_tolerance
                    diff = abs(sum_monthly - annual)

                    if diff > tolerance:
                        zip_code = row["zip_code"]
                        cell_id = row["cell_id"]
                        issues.append(
                            f"ZIP {zip_code} {cell_id}: sum of monthly HDD ({sum_monthly:.1f}) "
                            f"differs from annual ({annual:.1f}) by {diff:.1f} (tolerance={tolerance:.1f})"
                        )

    passed = len(issues) == 0
    severity = "warning" if not passed else "info"

    return QACheckResult(
        check_name="Monthly HDD Profiles",
        passed=passed,
        num_issues=len(issues),
        issues=issues,
        severity=severity,
    )
