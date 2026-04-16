"""
Write QA reports (HTML and Markdown) with cell-level and ZIP-level statistics.

This module generates comprehensive QA reports from terrain attributes data
and QA check results, including summary statistics, detailed check results,
and cell/ZIP-level distribution analysis.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from src import config
from src.validation.qa_checks import QACheckResult

logger = logging.getLogger(__name__)


def compute_statistics(terrain_df: pd.DataFrame) -> dict:
    """Compute cell-level and ZIP-level statistics from terrain data.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        DataFrame with cell-level and aggregate rows from terrain_attributes.csv.

    Returns
    -------
    dict
        Dictionary with computed statistics for both cell and ZIP levels.
    """
    # Separate cell-level and aggregate rows
    cell_rows = terrain_df[terrain_df["cell_id"] != "aggregate"]
    agg_rows = terrain_df[terrain_df["cell_id"] == "aggregate"]

    # Cell-level statistics
    cell_stats = {
        "num_cells": len(cell_rows),
        "hdd_mean": cell_rows["cell_effective_hdd"].mean(),
        "hdd_min": cell_rows["cell_effective_hdd"].min(),
        "hdd_max": cell_rows["cell_effective_hdd"].max(),
        "hdd_std": cell_rows["cell_effective_hdd"].std(),
        "hdd_median": cell_rows["cell_effective_hdd"].median(),
        "hdd_p25": cell_rows["cell_effective_hdd"].quantile(0.25),
        "hdd_p75": cell_rows["cell_effective_hdd"].quantile(0.75),
    }

    # ZIP-level statistics
    zip_stats = {
        "num_zips": len(agg_rows),
        "hdd_mean": agg_rows["cell_effective_hdd"].mean(),
        "hdd_min": agg_rows["cell_effective_hdd"].min(),
        "hdd_max": agg_rows["cell_effective_hdd"].max(),
        "hdd_std": agg_rows["cell_effective_hdd"].std(),
        "hdd_median": agg_rows["cell_effective_hdd"].median(),
        "hdd_p25": agg_rows["cell_effective_hdd"].quantile(0.25),
        "hdd_p75": agg_rows["cell_effective_hdd"].quantile(0.75),
    }

    # Cell count per ZIP
    if "num_cells" in agg_rows.columns:
        zip_stats["cells_per_zip_mean"] = agg_rows["num_cells"].mean()
        zip_stats["cells_per_zip_min"] = agg_rows["num_cells"].min()
        zip_stats["cells_per_zip_max"] = agg_rows["num_cells"].max()

    # Correction statistics (cell-level)
    correction_cols = [
        "hdd_terrain_mult",
        "hdd_elev_addition",
        "hdd_uhi_reduction",
        "uhi_offset_f",
        "road_temp_offset_f",
        "wind_infiltration_mult",
    ]

    cell_corrections = {}
    for col in correction_cols:
        if col in cell_rows.columns:
            valid_data = cell_rows[col].dropna()
            if len(valid_data) > 0:
                cell_corrections[col] = {
                    "mean": valid_data.mean(),
                    "min": valid_data.min(),
                    "max": valid_data.max(),
                    "std": valid_data.std(),
                }

    return {
        "cell_stats": cell_stats,
        "zip_stats": zip_stats,
        "cell_corrections": cell_corrections,
    }


def write_markdown_report(
    qa_results: dict[str, QACheckResult],
    terrain_df: pd.DataFrame,
    output_path: Path,
) -> None:
    """Write Markdown QA report with statistics and check results.

    Parameters
    ----------
    qa_results : dict[str, QACheckResult]
        Dictionary of QA check results.
    terrain_df : pd.DataFrame
        Terrain attributes DataFrame.
    output_path : Path
        Path to write Markdown report.
    """
    stats = compute_statistics(terrain_df)
    cell_stats = stats["cell_stats"]
    zip_stats = stats["zip_stats"]
    cell_corrections = stats["cell_corrections"]

    timestamp = datetime.now().isoformat()

    # Count issues by severity
    num_errors = sum(1 for r in qa_results.values() if r.severity == "error")
    num_warnings = sum(1 for r in qa_results.values() if r.severity == "warning")
    num_passed = sum(1 for r in qa_results.values() if r.passed)

    md_lines = [
        "# QA Report — Microclimate Pipeline",
        "",
        f"**Generated**: {timestamp}",
        f"**Pipeline Version**: {config.PIPELINE_VERSION}",
        "",
        "## Summary",
        "",
        "### Cell-Level Statistics",
        "",
        f"- **Total Cells**: {cell_stats['num_cells']}",
        f"- **Effective HDD Mean**: {cell_stats['hdd_mean']:.1f}",
        f"- **Effective HDD Median**: {cell_stats['hdd_median']:.1f}",
        f"- **Effective HDD Range**: {cell_stats['hdd_min']:.1f} — {cell_stats['hdd_max']:.1f}",
        f"- **Effective HDD Std Dev**: {cell_stats['hdd_std']:.1f}",
        f"- **Effective HDD IQR**: {cell_stats['hdd_p25']:.1f} — {cell_stats['hdd_p75']:.1f}",
        "",
        "### ZIP-Level Statistics",
        "",
        f"- **Total ZIP Codes**: {zip_stats['num_zips']}",
        f"- **Effective HDD Mean**: {zip_stats['hdd_mean']:.1f}",
        f"- **Effective HDD Median**: {zip_stats['hdd_median']:.1f}",
        f"- **Effective HDD Range**: {zip_stats['hdd_min']:.1f} — {zip_stats['hdd_max']:.1f}",
        f"- **Effective HDD Std Dev**: {zip_stats['hdd_std']:.1f}",
        f"- **Effective HDD IQR**: {zip_stats['hdd_p25']:.1f} — {zip_stats['hdd_p75']:.1f}",
    ]

    if "cells_per_zip_mean" in zip_stats:
        md_lines.extend([
            f"- **Cells per ZIP Mean**: {zip_stats['cells_per_zip_mean']:.1f}",
            f"- **Cells per ZIP Range**: {zip_stats['cells_per_zip_min']} — {zip_stats['cells_per_zip_max']}",
        ])

    md_lines.extend([
        "",
        "### Correction Statistics (Cell-Level)",
        "",
    ])

    for col, stats_dict in cell_corrections.items():
        col_label = col.replace("_", " ").title()
        md_lines.extend([
            f"**{col_label}**:",
            f"- Mean: {stats_dict['mean']:.3f}",
            f"- Range: {stats_dict['min']:.3f} — {stats_dict['max']:.3f}",
            f"- Std Dev: {stats_dict['std']:.3f}",
            "",
        ])

    md_lines.extend([
        "## QA Check Results",
        "",
        f"- **Passed**: {num_passed}/{len(qa_results)}",
        f"- **Errors**: {num_errors}",
        f"- **Warnings**: {num_warnings}",
        "",
    ])

    # Add detailed results for each check
    for check_name, result in qa_results.items():
        status = "✓ PASS" if result.passed else "✗ FAIL"
        md_lines.extend([
            f"### {result.check_name}",
            "",
            f"**Status**: {status}",
            f"**Severity**: {result.severity.upper()}",
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(md_lines), encoding="utf-8")
    logger.info(f"Markdown QA report written to {output_path}")


def write_html_report(
    qa_results: dict[str, QACheckResult],
    terrain_df: pd.DataFrame,
    output_path: Path,
) -> None:
    """Write HTML QA report with styled statistics and check results.

    Parameters
    ----------
    qa_results : dict[str, QACheckResult]
        Dictionary of QA check results.
    terrain_df : pd.DataFrame
        Terrain attributes DataFrame.
    output_path : Path
        Path to write HTML report.
    """
    stats = compute_statistics(terrain_df)
    cell_stats = stats["cell_stats"]
    zip_stats = stats["zip_stats"]
    cell_corrections = stats["cell_corrections"]

    timestamp = datetime.now().isoformat()

    # Count issues by severity
    num_errors = sum(1 for r in qa_results.values() if r.severity == "error")
    num_warnings = sum(1 for r in qa_results.values() if r.severity == "warning")
    num_passed = sum(1 for r in qa_results.values() if r.passed)

    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "  <meta charset='utf-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1'>",
        "  <title>QA Report — Microclimate Pipeline</title>",
        "  <style>",
        "    * { margin: 0; padding: 0; box-sizing: border-box; }",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }",
        "    .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }",
        "    h1 { color: #0066cc; border-bottom: 3px solid #0066cc; padding-bottom: 15px; margin-bottom: 20px; }",
        "    h2 { color: #0066cc; margin-top: 30px; margin-bottom: 15px; font-size: 1.3em; }",
        "    h3 { color: #555; margin-top: 20px; margin-bottom: 10px; font-size: 1.1em; }",
        "    .header-info { color: #666; font-size: 0.9em; margin-bottom: 20px; }",
        "    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin: 20px 0; }",
        "    .summary-card { background: #f9f9f9; padding: 15px; border-left: 4px solid #0066cc; border-radius: 4px; }",
        "    .summary-card .label { font-size: 11px; color: #999; text-transform: uppercase; letter-spacing: 0.5px; }",
        "    .summary-card .value { font-size: 22px; font-weight: bold; color: #333; margin-top: 5px; }",
        "    .summary-card .unit { font-size: 12px; color: #999; margin-top: 3px; }",
        "    table { width: 100%; border-collapse: collapse; margin: 15px 0; }",
        "    th { background: #f0f0f0; padding: 10px; text-align: left; font-weight: 600; border-bottom: 2px solid #ddd; }",
        "    td { padding: 10px; border-bottom: 1px solid #eee; }",
        "    tr:hover { background: #f9f9f9; }",
        "    .check-result { margin: 20px 0; padding: 15px; border-radius: 4px; border-left: 4px solid #ddd; }",
        "    .check-result.pass { background: #e8f5e9; border-left-color: #4caf50; }",
        "    .check-result.fail { background: #ffebee; border-left-color: #f44336; }",
        "    .check-result.warning { background: #fff3e0; border-left-color: #ff9800; }",
        "    .check-result h3 { margin-top: 0; }",
        "    .status { font-weight: bold; font-size: 13px; padding: 3px 8px; border-radius: 3px; display: inline-block; }",
        "    .status.pass { background: #4caf50; color: white; }",
        "    .status.fail { background: #f44336; color: white; }",
        "    .status.warning { background: #ff9800; color: white; }",
        "    .issues { margin-top: 10px; padding-left: 20px; }",
        "    .issues li { margin: 5px 0; font-size: 13px; color: #555; }",
        "    .timestamp { color: #999; font-size: 12px; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; }",
        "    .section { margin-bottom: 30px; }",
        "  </style>",
        "</head>",
        "<body>",
        "  <div class='container'>",
        "    <h1>QA Report — Microclimate Pipeline</h1>",
        f"    <div class='header-info'>",
        f"      <p><strong>Generated</strong>: {timestamp}</p>",
        f"      <p><strong>Pipeline Version</strong>: {config.PIPELINE_VERSION}</p>",
        f"    </div>",
        "",
        "    <div class='section'>",
        "      <h2>Cell-Level Statistics</h2>",
        "      <div class='summary-grid'>",
        f"        <div class='summary-card'><div class='label'>Total Cells</div><div class='value'>{cell_stats['num_cells']}</div></div>",
        f"        <div class='summary-card'><div class='label'>HDD Mean</div><div class='value'>{cell_stats['hdd_mean']:.0f}</div><div class='unit'>°F-days</div></div>",
        f"        <div class='summary-card'><div class='label'>HDD Median</div><div class='value'>{cell_stats['hdd_median']:.0f}</div><div class='unit'>°F-days</div></div>",
        f"        <div class='summary-card'><div class='label'>HDD Range</div><div class='value'>{cell_stats['hdd_min']:.0f}–{cell_stats['hdd_max']:.0f}</div><div class='unit'>°F-days</div></div>",
        f"        <div class='summary-card'><div class='label'>HDD Std Dev</div><div class='value'>{cell_stats['hdd_std']:.0f}</div><div class='unit'>°F-days</div></div>",
        f"        <div class='summary-card'><div class='label'>HDD IQR</div><div class='value'>{cell_stats['hdd_p25']:.0f}–{cell_stats['hdd_p75']:.0f}</div><div class='unit'>°F-days</div></div>",
        "      </div>",
        "    </div>",
        "",
        "    <div class='section'>",
        "      <h2>ZIP-Level Statistics</h2>",
        "      <div class='summary-grid'>",
        f"        <div class='summary-card'><div class='label'>Total ZIP Codes</div><div class='value'>{zip_stats['num_zips']}</div></div>",
        f"        <div class='summary-card'><div class='label'>HDD Mean</div><div class='value'>{zip_stats['hdd_mean']:.0f}</div><div class='unit'>°F-days</div></div>",
        f"        <div class='summary-card'><div class='label'>HDD Median</div><div class='value'>{zip_stats['hdd_median']:.0f}</div><div class='unit'>°F-days</div></div>",
        f"        <div class='summary-card'><div class='label'>HDD Range</div><div class='value'>{zip_stats['hdd_min']:.0f}–{zip_stats['hdd_max']:.0f}</div><div class='unit'>°F-days</div></div>",
        f"        <div class='summary-card'><div class='label'>HDD Std Dev</div><div class='value'>{zip_stats['hdd_std']:.0f}</div><div class='unit'>°F-days</div></div>",
        f"        <div class='summary-card'><div class='label'>HDD IQR</div><div class='value'>{zip_stats['hdd_p25']:.0f}–{zip_stats['hdd_p75']:.0f}</div><div class='unit'>°F-days</div></div>",
    ]

    if "cells_per_zip_mean" in zip_stats:
        html_lines.extend([
            f"        <div class='summary-card'><div class='label'>Cells per ZIP (Mean)</div><div class='value'>{zip_stats['cells_per_zip_mean']:.1f}</div></div>",
            f"        <div class='summary-card'><div class='label'>Cells per ZIP (Range)</div><div class='value'>{zip_stats['cells_per_zip_min']}–{zip_stats['cells_per_zip_max']}</div></div>",
        ])

    html_lines.extend([
        "      </div>",
        "    </div>",
        "",
    ])

    # Correction statistics table
    if cell_corrections:
        html_lines.extend([
            "    <div class='section'>",
            "      <h2>Correction Statistics (Cell-Level)</h2>",
            "      <table>",
            "        <tr>",
            "          <th>Correction Type</th>",
            "          <th>Mean</th>",
            "          <th>Min</th>",
            "          <th>Max</th>",
            "          <th>Std Dev</th>",
            "        </tr>",
        ])

        for col, stats_dict in cell_corrections.items():
            col_label = col.replace("_", " ").title()
            html_lines.extend([
                "        <tr>",
                f"          <td>{col_label}</td>",
                f"          <td>{stats_dict['mean']:.3f}</td>",
                f"          <td>{stats_dict['min']:.3f}</td>",
                f"          <td>{stats_dict['max']:.3f}</td>",
                f"          <td>{stats_dict['std']:.3f}</td>",
                "        </tr>",
            ])

        html_lines.extend([
            "      </table>",
            "    </div>",
            "",
        ])

    # QA Check Results Summary
    html_lines.extend([
        "    <div class='section'>",
        "      <h2>QA Check Results</h2>",
        "      <div class='summary-grid'>",
        f"        <div class='summary-card'><div class='label'>Passed</div><div class='value'>{num_passed}/{len(qa_results)}</div></div>",
        f"        <div class='summary-card'><div class='label'>Errors</div><div class='value' style='color: #f44336;'>{num_errors}</div></div>",
        f"        <div class='summary-card'><div class='label'>Warnings</div><div class='value' style='color: #ff9800;'>{num_warnings}</div></div>",
        "      </div>",
        "    </div>",
        "",
    ])

    # Detailed check results
    html_lines.append("    <div class='section'>")
    for check_name, result in qa_results.items():
        status_class = "pass" if result.passed else ("fail" if result.severity == "error" else "warning")
        status_text = "PASS" if result.passed else "FAIL"

        html_lines.extend([
            f"      <div class='check-result {status_class}'>",
            f"        <h3>{result.check_name}</h3>",
            f"        <p><span class='status {status_class}'>{status_text}</span> — {result.severity.upper()} ({result.num_issues} issues)</p>",
        ])

        if result.issues:
            html_lines.append("        <div class='issues'><ul>")
            for issue in result.issues[:10]:  # Show first 10 issues
                html_lines.append(f"          <li>{issue}</li>")
            if len(result.issues) > 10:
                html_lines.append(f"          <li><em>... and {len(result.issues) - 10} more issues</em></li>")
            html_lines.append("        </ul></div>")

        html_lines.append("      </div>")

    html_lines.extend([
        "    </div>",
        "",
        "    <div class='timestamp'>",
        f"      <p>Report generated at {timestamp}</p>",
        "    </div>",
        "  </div>",
        "</body>",
        "</html>",
    ])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(html_lines), encoding="utf-8")
    logger.info(f"HTML QA report written to {output_path}")


def write_qa_reports(
    qa_results: dict[str, QACheckResult],
    terrain_df: pd.DataFrame,
    output_dir: Path = Path("output/microclimate/"),
) -> tuple[Path, Path]:
    """Write both HTML and Markdown QA reports.

    Parameters
    ----------
    qa_results : dict[str, QACheckResult]
        Dictionary of QA check results from run_all_qa_checks.
    terrain_df : pd.DataFrame
        Terrain attributes DataFrame with cell-level and aggregate rows.
    output_dir : Path, optional
        Output directory for reports (default output/microclimate/).

    Returns
    -------
    tuple[Path, Path]
        Paths to generated HTML and Markdown report files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "qa_report.html"
    md_path = output_dir / "qa_report.md"

    write_html_report(qa_results, terrain_df, html_path)
    write_markdown_report(qa_results, terrain_df, md_path)

    logger.info(f"QA reports written to {output_dir}")

    return html_path, md_path
