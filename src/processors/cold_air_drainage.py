"""
Cold air drainage quantification from LiDAR flow accumulation.

Computes flow accumulation using D8 (8-direction) flow routing to identify
drainage pathways and accumulation areas. Quantifies cold air drainage intensity
per cell and applies a correction to effective HDD:

- Cells with high flow accumulation (valleys) receive higher drainage intensity
- Cells with low flow accumulation (ridges) receive lower drainage intensity
- Cold air drainage multiplier: 1.0 + (drainage_intensity × 0.15)
  (15% max increase for extreme valleys)

This correction is applied AFTER terrain position corrections but BEFORE
final effective_hdd computation.
"""

from __future__ import annotations

import logging

import numpy as np
from scipy import ndimage

logger = logging.getLogger(__name__)


def compute_flow_direction_d8(dem: np.ndarray) -> np.ndarray:
    """Compute D8 flow direction from a DEM.

    D8 (8-direction) flow routing assigns each cell to one of 8 neighbors
    in the direction of steepest descent. The output is a direction code:
    - 1: E, 2: SE, 4: S, 8: SW, 16: W, 32: NW, 64: N, 128: NE
    - 0: flat or no valid neighbor (sink)

    Parameters
    ----------
    dem : np.ndarray
        Digital elevation model (2D array). NaN values are treated as invalid.

    Returns
    -------
    flow_direction : np.ndarray
        D8 flow direction codes (0–128), same shape as dem. 0 where dem is NaN.

    Notes
    -----
    - Uses a 3×3 neighborhood to compute gradients to each neighbor.
    - Steepest descent is selected; ties are broken by preferring cardinal
      directions (E, S, W, N) over diagonal directions.
    - Flat areas (no downslope neighbor) are assigned direction 0 (sink).
    """
    rows, cols = dem.shape
    flow_direction = np.zeros_like(dem, dtype=np.uint8)

    # D8 neighbor offsets: (row_offset, col_offset, direction_code)
    # Ordered: E, SE, S, SW, W, NW, N, NE
    neighbors = [
        (0, 1, 1),      # E
        (1, 1, 2),      # SE
        (1, 0, 4),      # S
        (1, -1, 8),     # SW
        (0, -1, 16),    # W
        (-1, -1, 32),   # NW
        (-1, 0, 64),    # N
        (-1, 1, 128),   # NE
    ]

    valid_mask = ~np.isnan(dem)

    for i in range(rows):
        for j in range(cols):
            if not valid_mask[i, j]:
                flow_direction[i, j] = 0
                continue

            current_elev = dem[i, j]
            max_slope = 0.0
            best_direction = 0

            for di, dj, direction_code in neighbors:
                ni, nj = i + di, j + dj
                if 0 <= ni < rows and 0 <= nj < cols and valid_mask[ni, nj]:
                    neighbor_elev = dem[ni, nj]
                    # Compute slope (elevation drop)
                    # For diagonal neighbors, account for distance
                    if di != 0 and dj != 0:
                        # Diagonal: distance = sqrt(2)
                        slope = (current_elev - neighbor_elev) / np.sqrt(2)
                    else:
                        # Cardinal: distance = 1
                        slope = current_elev - neighbor_elev

                    # Update if this is steeper (or equal but cardinal direction)
                    if slope > max_slope:
                        max_slope = slope
                        best_direction = direction_code

            flow_direction[i, j] = best_direction

    return flow_direction


def compute_flow_accumulation_d8(dem: np.ndarray) -> np.ndarray:
    """Compute D8 flow accumulation from a DEM.

    Flow accumulation is the number of upslope cells that drain into each cell.
    Computed by iteratively routing flow from high to low elevation.

    Parameters
    ----------
    dem : np.ndarray
        Digital elevation model (2D array). NaN values are treated as invalid.

    Returns
    -------
    flow_accumulation : np.ndarray
        Flow accumulation (count of upslope cells), same shape as dem.
        NaN where dem is NaN. Ranges from 1 (isolated peak) to potentially
        millions (major valley outlet).

    Notes
    -----
    - Uses a priority queue approach: process cells from high to low elevation.
    - Each cell contributes 1 to its downslope neighbor's accumulation.
    - Flat areas and sinks contribute to themselves only.
    """
    rows, cols = dem.shape
    flow_accumulation = np.ones_like(dem, dtype=np.float64)

    valid_mask = ~np.isnan(dem)
    flow_accumulation[~valid_mask] = np.nan

    # Create a sorted list of cell indices by elevation (high to low)
    valid_indices = np.where(valid_mask)
    valid_elevations = dem[valid_indices]
    sorted_indices = np.argsort(-valid_elevations)  # Descending order

    # D8 neighbor offsets: (row_offset, col_offset)
    neighbors = [
        (0, 1),      # E
        (1, 1),      # SE
        (1, 0),      # S
        (1, -1),     # SW
        (0, -1),     # W
        (-1, -1),    # NW
        (-1, 0),     # N
        (-1, 1),     # NE
    ]

    # Process cells from high to low elevation
    for idx in sorted_indices:
        i, j = valid_indices[0][idx], valid_indices[1][idx]
        current_elev = dem[i, j]
        current_accum = flow_accumulation[i, j]

        # Find the steepest downslope neighbor
        max_slope = 0.0
        best_neighbor = None

        for di, dj in neighbors:
            ni, nj = i + di, j + dj
            if 0 <= ni < rows and 0 <= nj < cols and valid_mask[ni, nj]:
                neighbor_elev = dem[ni, nj]
                if neighbor_elev < current_elev:
                    # Compute slope
                    if di != 0 and dj != 0:
                        slope = (current_elev - neighbor_elev) / np.sqrt(2)
                    else:
                        slope = current_elev - neighbor_elev

                    if slope > max_slope:
                        max_slope = slope
                        best_neighbor = (ni, nj)

        # Route flow to the steepest downslope neighbor
        if best_neighbor is not None:
            ni, nj = best_neighbor
            flow_accumulation[ni, nj] += current_accum

    return flow_accumulation


def compute_drainage_intensity(flow_accumulation: np.ndarray) -> np.ndarray:
    """Normalize flow accumulation to drainage intensity (0–1).

    Drainage intensity is computed as:
    drainage_intensity = flow_accumulation / max(flow_accumulation)

    Cells with high flow accumulation (valleys) receive higher drainage intensity.
    Cells with low flow accumulation (ridges) receive lower drainage intensity.

    Parameters
    ----------
    flow_accumulation : np.ndarray
        Flow accumulation array (count of upslope cells).

    Returns
    -------
    drainage_intensity : np.ndarray
        Normalized drainage intensity (0–1), same shape as flow_accumulation.
        NaN where flow_accumulation is NaN.

    Notes
    -----
    - Isolated peaks (flow_accumulation = 1) receive drainage_intensity ≈ 0.
    - Major valley outlets receive drainage_intensity ≈ 1.0.
    """
    valid_mask = ~np.isnan(flow_accumulation)
    drainage_intensity = np.full_like(flow_accumulation, np.nan)

    if not valid_mask.any():
        return drainage_intensity

    max_accum = np.nanmax(flow_accumulation)
    if max_accum > 0:
        drainage_intensity[valid_mask] = flow_accumulation[valid_mask] / max_accum
    else:
        drainage_intensity[valid_mask] = 0.0

    return drainage_intensity


def compute_cold_air_drainage_multiplier(
    drainage_intensity: np.ndarray,
    max_multiplier_increase: float = 0.15,
) -> np.ndarray:
    """Compute cold air drainage HDD multiplier.

    Cells with high drainage intensity (valleys) have higher effective HDD
    (more cold air pooling = more heating needed). The multiplier is:

    cold_air_drainage_mult = 1.0 + (drainage_intensity × max_multiplier_increase)

    Parameters
    ----------
    drainage_intensity : np.ndarray
        Normalized drainage intensity (0–1).
    max_multiplier_increase : float, optional
        Maximum multiplier increase for extreme valleys (default: 0.15 = 15%).

    Returns
    -------
    cold_air_drainage_mult : np.ndarray
        Cold air drainage multiplier (1.0–1.15), same shape as drainage_intensity.
        NaN where drainage_intensity is NaN.

    Notes
    -----
    - Ridges (drainage_intensity ≈ 0) receive multiplier ≈ 1.0 (no change).
    - Extreme valleys (drainage_intensity ≈ 1.0) receive multiplier ≈ 1.15.
    """
    cold_air_drainage_mult = 1.0 + (drainage_intensity * max_multiplier_increase)
    return cold_air_drainage_mult


def compute_cold_air_drainage(dem: np.ndarray) -> dict[str, np.ndarray]:
    """Compute cold air drainage quantification from LiDAR DEM.

    Performs complete cold air drainage analysis:
    1. Compute D8 flow accumulation
    2. Normalize to drainage intensity (0–1)
    3. Compute cold air drainage multiplier (1.0–1.15)

    Parameters
    ----------
    dem : np.ndarray
        Digital elevation model (2D array) in meters.

    Returns
    -------
    dict
        Dictionary with keys:
        - 'flow_accumulation': Raw count of upslope cells draining into each cell
        - 'drainage_intensity': Normalized 0–1 score (0 = ridge, 1 = extreme valley)
        - 'cold_air_drainage_mult': HDD multiplier (1.0–1.15)

    Notes
    -----
    - All output arrays have the same shape as the input dem.
    - NaN values in the input dem are preserved in all outputs.
    - Computation is O(n log n) where n is the number of valid cells.
    """
    logger.info("Starting cold air drainage analysis...")

    # Compute flow accumulation
    flow_accumulation = compute_flow_accumulation_d8(dem)
    logger.debug(
        f"Flow accumulation range: {np.nanmin(flow_accumulation):.0f}–{np.nanmax(flow_accumulation):.0f} cells"
    )

    # Compute drainage intensity
    drainage_intensity = compute_drainage_intensity(flow_accumulation)
    logger.debug(
        f"Drainage intensity range: {np.nanmin(drainage_intensity):.3f}–{np.nanmax(drainage_intensity):.3f}"
    )

    # Compute cold air drainage multiplier
    cold_air_drainage_mult = compute_cold_air_drainage_multiplier(drainage_intensity)
    logger.debug(
        f"Cold air drainage multiplier range: {np.nanmin(cold_air_drainage_mult):.3f}–{np.nanmax(cold_air_drainage_mult):.3f}"
    )

    logger.info("Cold air drainage analysis complete.")

    return {
        "flow_accumulation": flow_accumulation,
        "drainage_intensity": drainage_intensity,
        "cold_air_drainage_mult": cold_air_drainage_mult,
    }
