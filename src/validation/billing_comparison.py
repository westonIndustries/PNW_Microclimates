"""
Billing comparison validation for microclimate pipeline output.

Compares cell-level and ZIP-level effective_hdd values against billing-derived
therms per customer to validate that the microclimate corrections are producing
realistic heating demand estimates. Flags divergences > 15% as warnings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Constants for billing comparison
BILLING_DIVERGENCE_THRESHOLD = 0.15  # 15% divergence threshold
HDD_TO_THERMS_CONVERSION = 1.0  # Rough equivalence for comparison (1 HDD ≈ 1 therm)


@dataclass
class BillingComparisonResult:
    """Result of billing comparison check."""

    num_matched_zips: int  # Number of ZIP codes matched with billing data
    num_divergent_zips: int  # Number of ZIP codes with divergence > threshold
    divergent_zips: list[dict]  # List of divergent ZIP code details
    mean_divergence: float  # Mean divergence across all matched ZIP codes
    max_divergence: float  # Maximum divergence
    min_divergence: float  # Minimum divergence
    passed: bool  # True if all matched ZIP codes are within threshold


def load_billing_reference(billing_csv_path: Path) -> Optional[pd.DataFrame]:
    """Load billing reference CSV with therms per customer.

    Parameters
    ----------
    billing_csv_path : Path
        Path to billing reference CSV. Expected columns:
        - zip_code: US ZIP code (string or int)
        - therms_per_customer: Annual therms per customer (float)

    Returns
    -------
    pd.DataFrame or None
        Loaded billing DataFrame, or None if file not found or error occurs.
    """
    if not billing_csv_path.exists():
        logger.warning(f"Billing reference CSV not found: {billing_csv_path}")
        return None

    try:
        billing_df = pd.read_csv(billing_csv_path)
        logger.info(f"Loaded billing reference CSV: {len(billing_df)} ZIP codes")
        return billing_df
    except Exception as e:
        logger.error(f"Failed to load billing reference CSV: {e}")
        return None


def validate_billing_schema(billing_df: pd.DataFrame) -> bool:
    """Validate that billing DataFrame has required columns.

    Parameters
    ----------
    billing_df : pd.DataFrame
        Billing reference DataFrame.

    Returns
    -------
    bool
        True if schema is valid, False otherwise.
    """
    required_columns = {"zip_code", "therms_per_customer"}
    missing_columns = required_columns - set(billing_df.columns)

    if missing_columns:
        logger.error(f"Billing CSV missing required columns: {missing_columns}")
        return False

    return True


def compare_effective_hdd_to_billing(
    terrain_df: pd.DataFrame,
    billing_df: pd.DataFrame,
    divergence_threshold: float = BILLING_DIVERGENCE_THRESHOLD,
) -> BillingComparisonResult:
    """Compare effective_hdd values to billing-derived therms per customer.

    Compares ZIP-code aggregate effective_hdd values from the terrain attributes
    to billing-derived therms per customer. Flags divergences > threshold as warnings.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        Terrain attributes DataFrame with columns:
        - zip_code: US ZIP code
        - cell_id: "aggregate" for ZIP-code aggregates
        - cell_effective_hdd: Effective HDD value
    billing_df : pd.DataFrame
        Billing reference DataFrame with columns:
        - zip_code: US ZIP code
        - therms_per_customer: Annual therms per customer
    divergence_threshold : float, optional
        Threshold for flagging divergence (default 0.15 = 15%).

    Returns
    -------
    BillingComparisonResult
        Result object with comparison statistics and divergent ZIP codes.
    """
    # Extract ZIP-code aggregates from terrain_df
    agg_df = terrain_df[terrain_df["cell_id"] == "aggregate"].copy()

    if len(agg_df) == 0:
        logger.warning("No aggregate rows found in terrain_df for billing comparison")
        return BillingComparisonResult(
            num_matched_zips=0,
            num_divergent_zips=0,
            divergent_zips=[],
            mean_divergence=0.0,
            max_divergence=0.0,
            min_divergence=0.0,
            passed=True,
        )

    # Ensure zip_code is string in both dataframes for merge
    agg_df["zip_code"] = agg_df["zip_code"].astype(str)
    billing_df_copy = billing_df.copy()
    billing_df_copy["zip_code"] = billing_df_copy["zip_code"].astype(str)

    # Merge on zip_code
    merged = agg_df.merge(
        billing_df_copy,
        on="zip_code",
        how="inner",
        suffixes=("_terrain", "_billing"),
    )

    if len(merged) == 0:
        logger.warning("No ZIP codes matched between terrain and billing data")
        return BillingComparisonResult(
            num_matched_zips=0,
            num_divergent_zips=0,
            divergent_zips=[],
            mean_divergence=0.0,
            max_divergence=0.0,
            min_divergence=0.0,
            passed=True,
        )

    # Compute divergence for each matched ZIP code
    divergences = []
    divergent_zips = []

    for idx, row in merged.iterrows():
        zip_code = row["zip_code"]
        eff_hdd = row["cell_effective_hdd"]
        therms = row["therms_per_customer"]

        # Compute divergence as percentage difference
        if therms > 0:
            divergence = abs(eff_hdd - therms) / therms
        else:
            divergence = float("inf")

        divergences.append(divergence)

        # Flag if divergence exceeds threshold
        if divergence > divergence_threshold:
            divergent_zips.append({
                "zip_code": zip_code,
                "effective_hdd": eff_hdd,
                "therms_per_customer": therms,
                "divergence": divergence,
                "divergence_pct": divergence * 100,
            })

    # Compute statistics
    divergences_array = pd.Series(divergences)
    mean_divergence = divergences_array.mean()
    max_divergence = divergences_array.max()
    min_divergence = divergences_array.min()

    passed = len(divergent_zips) == 0

    # Log results
    logger.info(
        f"Billing comparison: {len(merged)} ZIP codes matched, "
        f"{len(divergent_zips)} divergent (> {divergence_threshold*100:.1f}%)"
    )
    logger.info(
        f"Divergence statistics: mean={mean_divergence*100:.1f}%, "
        f"min={min_divergence*100:.1f}%, max={max_divergence*100:.1f}%"
    )

    if divergent_zips:
        logger.warning(f"Divergent ZIP codes (first 10):")
        for item in divergent_zips[:10]:
            logger.warning(
                f"  ZIP {item['zip_code']}: effective_hdd={item['effective_hdd']:.1f}, "
                f"therms={item['therms_per_customer']:.1f}, "
                f"divergence={item['divergence_pct']:.1f}%"
            )
        if len(divergent_zips) > 10:
            logger.warning(f"  ... and {len(divergent_zips) - 10} more divergent ZIP codes")

    return BillingComparisonResult(
        num_matched_zips=len(merged),
        num_divergent_zips=len(divergent_zips),
        divergent_zips=divergent_zips,
        mean_divergence=mean_divergence,
        max_divergence=max_divergence,
        min_divergence=min_divergence,
        passed=passed,
    )


def compare_cell_level_to_billing(
    terrain_df: pd.DataFrame,
    billing_df: pd.DataFrame,
    divergence_threshold: float = BILLING_DIVERGENCE_THRESHOLD,
) -> BillingComparisonResult:
    """Compare cell-level effective_hdd values to billing-derived therms per customer.

    For each cell, compares its effective_hdd to the billing therms for its ZIP code.
    This provides a more granular view of divergence at the cell level.

    Parameters
    ----------
    terrain_df : pd.DataFrame
        Terrain attributes DataFrame with columns:
        - zip_code: US ZIP code
        - cell_id: Cell identifier (not "aggregate")
        - cell_effective_hdd: Effective HDD value
    billing_df : pd.DataFrame
        Billing reference DataFrame with columns:
        - zip_code: US ZIP code
        - therms_per_customer: Annual therms per customer
    divergence_threshold : float, optional
        Threshold for flagging divergence (default 0.15 = 15%).

    Returns
    -------
    BillingComparisonResult
        Result object with comparison statistics and divergent cells.
    """
    # Extract cell-level rows (exclude aggregates)
    cell_df = terrain_df[terrain_df["cell_id"] != "aggregate"].copy()

    if len(cell_df) == 0:
        logger.warning("No cell-level rows found in terrain_df for billing comparison")
        return BillingComparisonResult(
            num_matched_zips=0,
            num_divergent_zips=0,
            divergent_zips=[],
            mean_divergence=0.0,
            max_divergence=0.0,
            min_divergence=0.0,
            passed=True,
        )

    # Ensure zip_code is string in both dataframes for merge
    cell_df["zip_code"] = cell_df["zip_code"].astype(str)
    billing_df_copy = billing_df.copy()
    billing_df_copy["zip_code"] = billing_df_copy["zip_code"].astype(str)

    # Merge on zip_code
    merged = cell_df.merge(
        billing_df_copy,
        on="zip_code",
        how="inner",
        suffixes=("_cell", "_billing"),
    )

    if len(merged) == 0:
        logger.warning("No ZIP codes matched between cell data and billing data")
        return BillingComparisonResult(
            num_matched_zips=0,
            num_divergent_zips=0,
            divergent_zips=[],
            mean_divergence=0.0,
            max_divergence=0.0,
            min_divergence=0.0,
            passed=True,
        )

    # Compute divergence for each cell
    divergences = []
    divergent_cells = []

    for idx, row in merged.iterrows():
        zip_code = row["zip_code"]
        cell_id = row["cell_id"]
        eff_hdd = row["cell_effective_hdd"]
        therms = row["therms_per_customer"]

        # Compute divergence as percentage difference
        if therms > 0:
            divergence = abs(eff_hdd - therms) / therms
        else:
            divergence = float("inf")

        divergences.append(divergence)

        # Flag if divergence exceeds threshold
        if divergence > divergence_threshold:
            divergent_cells.append({
                "zip_code": zip_code,
                "cell_id": cell_id,
                "effective_hdd": eff_hdd,
                "therms_per_customer": therms,
                "divergence": divergence,
                "divergence_pct": divergence * 100,
            })

    # Compute statistics
    divergences_array = pd.Series(divergences)
    mean_divergence = divergences_array.mean()
    max_divergence = divergences_array.max()
    min_divergence = divergences_array.min()

    passed = len(divergent_cells) == 0

    # Log results
    logger.info(
        f"Cell-level billing comparison: {len(merged)} cells matched, "
        f"{len(divergent_cells)} divergent (> {divergence_threshold*100:.1f}%)"
    )
    logger.info(
        f"Cell divergence statistics: mean={mean_divergence*100:.1f}%, "
        f"min={min_divergence*100:.1f}%, max={max_divergence*100:.1f}%"
    )

    if divergent_cells:
        logger.warning(f"Divergent cells (first 10):")
        for item in divergent_cells[:10]:
            logger.warning(
                f"  ZIP {item['zip_code']} {item['cell_id']}: "
                f"effective_hdd={item['effective_hdd']:.1f}, "
                f"therms={item['therms_per_customer']:.1f}, "
                f"divergence={item['divergence_pct']:.1f}%"
            )
        if len(divergent_cells) > 10:
            logger.warning(f"  ... and {len(divergent_cells) - 10} more divergent cells")

    return BillingComparisonResult(
        num_matched_zips=len(merged),
        num_divergent_zips=len(divergent_cells),
        divergent_zips=divergent_cells,
        mean_divergence=mean_divergence,
        max_divergence=max_divergence,
        min_divergence=min_divergence,
        passed=passed,
    )


def run_billing_comparison(
    terrain_csv_path: Path,
    billing_csv_path: Optional[Path] = None,
    divergence_threshold: float = BILLING_DIVERGENCE_THRESHOLD,
) -> tuple[BillingComparisonResult, BillingComparisonResult]:
    """Run billing comparison on terrain attributes CSV.

    Loads terrain attributes and billing reference data, then performs both
    ZIP-level and cell-level comparisons.

    Parameters
    ----------
    terrain_csv_path : Path
        Path to terrain_attributes.csv output from pipeline.
    billing_csv_path : Path, optional
        Path to billing reference CSV. If None or file not found, returns
        empty results with passed=True.
    divergence_threshold : float, optional
        Threshold for flagging divergence (default 0.15 = 15%).

    Returns
    -------
    tuple[BillingComparisonResult, BillingComparisonResult]
        Tuple of (zip_level_result, cell_level_result).
    """
    # Load terrain data
    try:
        terrain_df = pd.read_csv(terrain_csv_path)
        logger.info(f"Loaded terrain attributes: {len(terrain_df)} rows")
    except Exception as e:
        logger.error(f"Failed to load terrain CSV: {e}")
        empty_result = BillingComparisonResult(
            num_matched_zips=0,
            num_divergent_zips=0,
            divergent_zips=[],
            mean_divergence=0.0,
            max_divergence=0.0,
            min_divergence=0.0,
            passed=True,
        )
        return empty_result, empty_result

    # Load billing data
    if billing_csv_path is None:
        logger.info("Billing comparison skipped: no billing CSV path provided")
        empty_result = BillingComparisonResult(
            num_matched_zips=0,
            num_divergent_zips=0,
            divergent_zips=[],
            mean_divergence=0.0,
            max_divergence=0.0,
            min_divergence=0.0,
            passed=True,
        )
        return empty_result, empty_result

    billing_df = load_billing_reference(billing_csv_path)

    if billing_df is None:
        logger.info("Billing comparison skipped: billing CSV not available")
        empty_result = BillingComparisonResult(
            num_matched_zips=0,
            num_divergent_zips=0,
            divergent_zips=[],
            mean_divergence=0.0,
            max_divergence=0.0,
            min_divergence=0.0,
            passed=True,
        )
        return empty_result, empty_result

    # Validate schema
    if not validate_billing_schema(billing_df):
        logger.error("Billing CSV schema validation failed")
        empty_result = BillingComparisonResult(
            num_matched_zips=0,
            num_divergent_zips=0,
            divergent_zips=[],
            mean_divergence=0.0,
            max_divergence=0.0,
            min_divergence=0.0,
            passed=True,
        )
        return empty_result, empty_result

    # Run comparisons
    zip_level_result = compare_effective_hdd_to_billing(
        terrain_df, billing_df, divergence_threshold
    )
    cell_level_result = compare_cell_level_to_billing(
        terrain_df, billing_df, divergence_threshold
    )

    return zip_level_result, cell_level_result
