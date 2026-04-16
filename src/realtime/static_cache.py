"""
Static feature cache for real-time daemon.

Pre-computes and serializes all static features (NLCD surface mask, LiDAR terrain,
road heat flux, UHI offsets) to .npz files for fast loading in the streaming pipeline.
Includes hash-based staleness detection to identify when cache needs rebuilding.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np

from src.config import STATIC_CACHE_DIR

logger = logging.getLogger(__name__)


def compute_file_hash(filepath: Path) -> str:
    """
    Compute SHA256 hash of a file.

    Parameters
    ----------
    filepath : Path
        Path to file

    Returns
    -------
    str
        SHA256 hash hex string
    """
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def build_static_cache(region_name: str) -> Path:
    """
    Pre-compute and serialize all static features to .npz files.

    Builds a cache of static features (NLCD surface mask, LiDAR terrain,
    road heat flux, UHI offsets) that don't change hour-to-hour. This allows
    the streaming pipeline to load pre-computed features quickly without
    re-processing rasters for each HRRR cycle.

    Parameters
    ----------
    region_name : str
        Region name (e.g., "region_1")

    Returns
    -------
    Path
        Path to cache directory
    """
    cache_dir = STATIC_CACHE_DIR / region_name
    cache_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Building static cache for {region_name} in {cache_dir}")

    # Create cache manifest
    manifest = {
        "region_name": region_name,
        "created_at": str(Path.cwd()),
        "features": {},
    }

    # Placeholder: In full implementation, would load and serialize:
    # - NLCD surface mask (z0_m, albedo, emissivity, etc.)
    # - LiDAR terrain (elevation, aspect, slope, TPI)
    # - Road heat flux (buffered and rasterized)
    # - UHI offsets (pre-computed from imperviousness)

    # For now, create dummy cache files
    dummy_data = {
        "nlcd_surface_mask": np.zeros((100, 100), dtype=np.float32),
        "lidar_terrain": np.zeros((100, 100), dtype=np.float32),
        "road_heat_flux": np.zeros((100, 100), dtype=np.float32),
        "uhi_offsets": np.zeros((100, 100), dtype=np.float32),
    }

    for feature_name, data in dummy_data.items():
        cache_file = cache_dir / f"{feature_name}.npz"
        np.savez_compressed(cache_file, data=data)
        logger.info(f"Saved {feature_name} to {cache_file}")

        # Record in manifest
        manifest["features"][feature_name] = {
            "file": str(cache_file),
            "shape": data.shape,
            "dtype": str(data.dtype),
            "hash": compute_file_hash(cache_file),
        }

    # Write manifest
    manifest_file = cache_dir / "cache_manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info(f"Wrote cache manifest to {manifest_file}")

    return cache_dir


def load_static_cache(region_name: str) -> Dict[str, np.ndarray]:
    """
    Load pre-computed static features from cache.

    Parameters
    ----------
    region_name : str
        Region name (e.g., "region_1")

    Returns
    -------
    Dict[str, np.ndarray]
        Dictionary mapping feature names to numpy arrays
    """
    cache_dir = STATIC_CACHE_DIR / region_name
    manifest_file = cache_dir / "cache_manifest.json"

    if not manifest_file.exists():
        logger.warning(f"Cache manifest not found at {manifest_file}")
        return {}

    # Load manifest
    with open(manifest_file, "r") as f:
        manifest = json.load(f)

    # Load features
    features = {}
    for feature_name, feature_info in manifest["features"].items():
        cache_file = Path(feature_info["file"])
        if cache_file.exists():
            try:
                data = np.load(cache_file)["data"]
                features[feature_name] = data
                logger.debug(f"Loaded {feature_name} from {cache_file}")
            except Exception as e:
                logger.warning(f"Failed to load {feature_name}: {e}")
        else:
            logger.warning(f"Cache file not found: {cache_file}")

    return features


def check_cache_staleness(region_name: str, source_files: list) -> bool:
    """
    Check if cache is stale based on source file hashes.

    Parameters
    ----------
    region_name : str
        Region name (e.g., "region_1")
    source_files : list
        List of source file paths to check

    Returns
    -------
    bool
        True if cache is stale (needs rebuilding), False if fresh
    """
    cache_dir = STATIC_CACHE_DIR / region_name
    manifest_file = cache_dir / "cache_manifest.json"

    if not manifest_file.exists():
        logger.info("Cache manifest not found — cache is stale")
        return True

    # Load manifest
    with open(manifest_file, "r") as f:
        manifest = json.load(f)

    # Check if any source files have changed
    for source_file in source_files:
        source_path = Path(source_file)
        if not source_path.exists():
            logger.warning(f"Source file not found: {source_path}")
            continue

        current_hash = compute_file_hash(source_path)
        stored_hash = manifest.get("source_hashes", {}).get(str(source_path))

        if stored_hash != current_hash:
            logger.info(f"Source file changed: {source_path}")
            return True

    logger.debug("Cache is fresh")
    return False


def validate_cache(region_name: str) -> dict:
    """
    Validate cache integrity.

    Parameters
    ----------
    region_name : str
        Region name (e.g., "region_1")

    Returns
    -------
    dict
        Validation results with keys:
        - 'passed': bool
        - 'warnings': list of warning messages
        - 'errors': list of error messages
    """
    warnings = []
    errors = []

    cache_dir = STATIC_CACHE_DIR / region_name
    manifest_file = cache_dir / "cache_manifest.json"

    if not manifest_file.exists():
        errors.append(f"Cache manifest not found: {manifest_file}")
        return {"passed": False, "warnings": warnings, "errors": errors}

    # Load manifest
    try:
        with open(manifest_file, "r") as f:
            manifest = json.load(f)
    except Exception as e:
        errors.append(f"Failed to load manifest: {e}")
        return {"passed": False, "warnings": warnings, "errors": errors}

    # Check each feature file
    for feature_name, feature_info in manifest.get("features", {}).items():
        cache_file = Path(feature_info["file"])
        if not cache_file.exists():
            errors.append(f"Cache file not found: {cache_file}")
            continue

        # Verify hash
        current_hash = compute_file_hash(cache_file)
        stored_hash = feature_info.get("hash")
        if current_hash != stored_hash:
            warnings.append(f"Hash mismatch for {feature_name}")

    passed = len(errors) == 0

    return {
        "passed": passed,
        "warnings": warnings,
        "errors": errors,
    }
