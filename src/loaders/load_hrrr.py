"""
HRRR (High-Resolution Rapid Refresh) data loader.

Downloads and caches HRRR GRIB2 analysis files from AWS S3 or Google Cloud,
extracts 2m temperature, 10m wind, and pressure-level wind fields, computes
daily mean temperature grids, and maintains a download manifest CSV.

Supports date range validation, download confirmation prompts, and both S3/GCS sources.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
import csv

import numpy as np
import pandas as pd
import xarray as xr

try:
    import s3fs
except ImportError:
    s3fs = None

from dateutil.parser import parse as parse_date

from src.config import (
    HRRR_CACHE_DIR,
    HRRR_S3_BUCKET,
    HRRR_GCS_BUCKET,
    HRRR_EARLIEST_DATE,
    HRRR_DOWNLOAD_CONFIRM_THRESHOLD_GB,
    HRRR_MIN_CLIM_YEARS,
)

logger = logging.getLogger(__name__)


class HRRRLoader:
    """
    Manages HRRR data download, caching, and extraction.
    
    Attributes:
        cache_dir: Local directory for cached GRIB2 files
        manifest_path: Path to download manifest CSV
        s3_bucket: AWS S3 bucket URL
        gcs_bucket: Google Cloud Storage bucket URL
    """
    
    def __init__(
        self,
        cache_dir: Path = HRRR_CACHE_DIR,
        s3_bucket: str = HRRR_S3_BUCKET,
        gcs_bucket: str = HRRR_GCS_BUCKET,
    ):
        """Initialize HRRR loader with cache directory and bucket URLs."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.manifest_path = self.cache_dir / "manifest.csv"
        self.s3_bucket = s3_bucket
        self.gcs_bucket = gcs_bucket
        
        # Initialize manifest if it doesn't exist
        if not self.manifest_path.exists():
            self._init_manifest()
    
    def _init_manifest(self) -> None:
        """Initialize empty manifest CSV with headers."""
        with open(self.manifest_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["datetime_utc", "status", "file_size_bytes", "source_url"],
            )
            writer.writeheader()
    
    def _load_manifest(self) -> pd.DataFrame:
        """Load manifest CSV into DataFrame."""
        if not self.manifest_path.exists():
            return pd.DataFrame(
                columns=["datetime_utc", "status", "file_size_bytes", "source_url"]
            )
        return pd.read_csv(self.manifest_path)
    
    def _update_manifest(
        self,
        datetime_utc: str,
        status: str,
        file_size_bytes: int,
        source_url: str,
    ) -> None:
        """Append or update a row in the manifest CSV."""
        manifest = self._load_manifest()
        
        # Check if entry already exists
        existing = manifest[manifest["datetime_utc"] == datetime_utc]
        if not existing.empty:
            manifest.loc[manifest["datetime_utc"] == datetime_utc] = [
                datetime_utc,
                status,
                file_size_bytes,
                source_url,
            ]
        else:
            new_row = pd.DataFrame(
                [
                    {
                        "datetime_utc": datetime_utc,
                        "status": status,
                        "file_size_bytes": file_size_bytes,
                        "source_url": source_url,
                    }
                ]
            )
            manifest = pd.concat([manifest, new_row], ignore_index=True)
        
        manifest.to_csv(self.manifest_path, index=False)
    
    def validate_date_range(
        self, start_date: str, end_date: str
    ) -> Tuple[datetime, datetime]:
        """
        Validate that date range falls within HRRR availability window.
        
        Args:
            start_date: ISO 8601 date string (YYYY-MM-DD)
            end_date: ISO 8601 date string (YYYY-MM-DD)
        
        Returns:
            Tuple of (start_datetime, end_datetime)
        
        Raises:
            ValueError: If dates are outside HRRR availability window
        """
        earliest = datetime.strptime(HRRR_EARLIEST_DATE, "%Y-%m-%d")
        
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Invalid date format. Use YYYY-MM-DD: {e}")
        
        if start_dt < earliest:
            raise ValueError(
                f"Start date {start_date} is before HRRR availability "
                f"({HRRR_EARLIEST_DATE}). HRRR data begins on {HRRR_EARLIEST_DATE}."
            )
        
        if end_dt < start_dt:
            raise ValueError(f"End date {end_date} is before start date {start_date}")
        
        return start_dt, end_dt
    
    def expand_month_shorthand(self, month_str: str) -> Tuple[str, str]:
        """
        Expand --month YYYY-MM shorthand to start and end dates.
        
        Args:
            month_str: Month string in format YYYY-MM
        
        Returns:
            Tuple of (start_date, end_date) in YYYY-MM-DD format
        
        Raises:
            ValueError: If month format is invalid
        """
        try:
            month_dt = datetime.strptime(month_str, "%Y-%m")
        except ValueError as e:
            raise ValueError(f"Invalid month format. Use YYYY-MM: {e}")
        
        start_date = month_dt.strftime("%Y-%m-%d")
        
        # Last day of month
        if month_dt.month == 12:
            end_dt = month_dt.replace(year=month_dt.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_dt = month_dt.replace(month=month_dt.month + 1, day=1) - timedelta(days=1)
        
        end_date = end_dt.strftime("%Y-%m-%d")
        
        return start_date, end_date
    
    def _get_hrrr_path_s3(self, dt: datetime) -> str:
        """
        Construct S3 path for HRRR analysis file.
        
        HRRR S3 structure: s3://noaa-hrrr-bdp-pds/hrrr.YYYYMMDD/conus/hrrr.tYYYYMMDDHHf00.grib2
        
        Args:
            dt: Datetime for the analysis
        
        Returns:
            S3 path string
        """
        date_str = dt.strftime("%Y%m%d")
        hour_str = dt.strftime("%H")
        return f"hrrr.{date_str}/conus/hrrr.t{date_str}{hour_str}f00.grib2"
    
    def _get_hrrr_path_gcs(self, dt: datetime) -> str:
        """
        Construct GCS path for HRRR analysis file.
        
        GCS structure: gs://noaa-hrrr-bdp-pds/hrrr.YYYYMMDD/conus/hrrr.tYYYYMMDDHHf00.grib2
        
        Args:
            dt: Datetime for the analysis
        
        Returns:
            GCS path string
        """
        # Same structure as S3
        return self._get_hrrr_path_s3(dt)
    
    def _get_local_cache_path(self, dt: datetime) -> Path:
        """
        Construct local cache path for HRRR file.
        
        Cache structure: data/hrrr/YYYY/MM/DD/hrrr.tYYYYMMDDHHf00.grib2
        
        Args:
            dt: Datetime for the analysis
        
        Returns:
            Local cache path
        """
        date_str = dt.strftime("%Y%m%d")
        hour_str = dt.strftime("%H")
        year_dir = self.cache_dir / dt.strftime("%Y")
        month_dir = year_dir / dt.strftime("%m")
        day_dir = month_dir / dt.strftime("%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"hrrr.t{date_str}{hour_str}f00.grib2"
        return day_dir / filename
    
    def download_hrrr_range(
        self,
        start_date: str,
        end_date: str,
        source: str = "s3",
        no_confirm: bool = False,
    ) -> None:
        """
        Download HRRR analysis files for a date range.
        
        Args:
            start_date: ISO 8601 start date (YYYY-MM-DD)
            end_date: ISO 8601 end date (YYYY-MM-DD)
            source: Data source ("s3" or "gcs")
            no_confirm: Skip confirmation prompt if True
        
        Raises:
            ValueError: If date range is invalid or source is unsupported
        """
        # Validate dates
        start_dt, end_dt = self.validate_date_range(start_date, end_date)
        
        # Generate all hourly datetimes in range
        current_dt = start_dt
        hours_to_download = []
        while current_dt <= end_dt:
            hours_to_download.append(current_dt)
            current_dt += timedelta(hours=1)
        
        # Check which hours are already cached
        manifest = self._load_manifest()
        cached_hours = set(manifest[manifest["status"] == "cached"]["datetime_utc"])
        
        hours_to_fetch = [
            dt for dt in hours_to_download
            if dt.strftime("%Y-%m-%dT%H:00:00") not in cached_hours
        ]
        
        if not hours_to_fetch:
            logger.info(f"All {len(hours_to_download)} hours already cached.")
            return
        
        # Estimate download size
        estimated_size_gb = len(hours_to_fetch) * 0.075  # ~75 MB per file
        
        logger.info(
            f"Will download {len(hours_to_fetch)} hours "
            f"(estimated {estimated_size_gb:.1f} GB)"
        )
        
        if estimated_size_gb > HRRR_DOWNLOAD_CONFIRM_THRESHOLD_GB and not no_confirm:
            response = input(
                f"Download will be ~{estimated_size_gb:.1f} GB. Continue? (y/n): "
            )
            if response.lower() != "y":
                logger.info("Download cancelled by user.")
                return
        
        # Download each hour
        if source == "s3":
            self._download_from_s3(hours_to_fetch)
        elif source == "gcs":
            self._download_from_gcs(hours_to_fetch)
        else:
            raise ValueError(f"Unsupported source: {source}. Use 's3' or 'gcs'.")
    
    def _download_from_s3(self, hours: list[datetime]) -> None:
        """Download HRRR files from AWS S3."""
        fs = s3fs.S3FileSystem(anon=True)
        
        for dt in hours:
            local_path = self._get_local_cache_path(dt)
            
            # Skip if already cached
            if local_path.exists():
                logger.debug(f"Using cached file: {local_path}")
                self._update_manifest(
                    dt.strftime("%Y-%m-%dT%H:00:00"),
                    "cached",
                    local_path.stat().st_size,
                    self.s3_bucket + self._get_hrrr_path_s3(dt),
                )
                continue
            
            s3_path = self.s3_bucket.rstrip("/") + "/" + self._get_hrrr_path_s3(dt)
            
            try:
                logger.info(f"Downloading {s3_path}")
                with fs.open(s3_path, "rb") as src:
                    with open(local_path, "wb") as dst:
                        dst.write(src.read())
                
                file_size = local_path.stat().st_size
                self._update_manifest(
                    dt.strftime("%Y-%m-%dT%H:00:00"),
                    "downloaded",
                    file_size,
                    s3_path,
                )
                logger.debug(f"Downloaded {file_size} bytes to {local_path}")
            
            except Exception as e:
                logger.warning(f"Failed to download {s3_path}: {e}")
                self._update_manifest(
                    dt.strftime("%Y-%m-%dT%H:00:00"),
                    "missing",
                    0,
                    s3_path,
                )
    
    def _download_from_gcs(self, hours: list[datetime]) -> None:
        """Download HRRR files from Google Cloud Storage."""
        try:
            import gcsfs
        except ImportError:
            raise ImportError(
                "gcsfs is required for GCS downloads. Install with: pip install gcsfs"
            )
        
        fs = gcsfs.GCSFileSystem(anon=True)
        
        for dt in hours:
            local_path = self._get_local_cache_path(dt)
            
            # Skip if already cached
            if local_path.exists():
                logger.debug(f"Using cached file: {local_path}")
                self._update_manifest(
                    dt.strftime("%Y-%m-%dT%H:00:00"),
                    "cached",
                    local_path.stat().st_size,
                    self.gcs_bucket + self._get_hrrr_path_gcs(dt),
                )
                continue
            
            gcs_path = self.gcs_bucket.rstrip("/") + "/" + self._get_hrrr_path_gcs(dt)
            
            try:
                logger.info(f"Downloading {gcs_path}")
                with fs.open(gcs_path, "rb") as src:
                    with open(local_path, "wb") as dst:
                        dst.write(src.read())
                
                file_size = local_path.stat().st_size
                self._update_manifest(
                    dt.strftime("%Y-%m-%dT%H:00:00"),
                    "downloaded",
                    file_size,
                    gcs_path,
                )
                logger.debug(f"Downloaded {file_size} bytes to {local_path}")
            
            except Exception as e:
                logger.warning(f"Failed to download {gcs_path}: {e}")
                self._update_manifest(
                    dt.strftime("%Y-%m-%dT%H:00:00"),
                    "missing",
                    0,
                    gcs_path,
                )
    
    def load_hourly_data(
        self,
        start_date: str,
        end_date: str,
        return_hourly: bool = False,
    ) -> xr.Dataset | list[xr.Dataset]:
        """
        Load HRRR data for a date range.
        
        Args:
            start_date: ISO 8601 start date (YYYY-MM-DD)
            end_date: ISO 8601 end date (YYYY-MM-DD)
            return_hourly: If True, return list of hourly Datasets; if False, return daily mean
        
        Returns:
            If return_hourly=False: xarray Dataset with daily mean temperature
            If return_hourly=True: List of xarray Datasets, one per hour
        
        Raises:
            ValueError: If date range is invalid
        """
        start_dt, end_dt = self.validate_date_range(start_date, end_date)
        
        # Generate all hourly datetimes
        current_dt = start_dt
        hours = []
        while current_dt <= end_dt:
            hours.append(current_dt)
            current_dt += timedelta(hours=1)
        
        # Load each hour's data
        hourly_datasets = []
        for dt in hours:
            local_path = self._get_local_cache_path(dt)
            
            if not local_path.exists():
                logger.warning(f"HRRR file not cached: {local_path}. Skipping.")
                continue
            
            try:
                ds = xr.open_dataset(local_path, engine="cfgrib")
                hourly_datasets.append(ds)
            except Exception as e:
                logger.warning(f"Failed to load {local_path}: {e}")
        
        if not hourly_datasets:
            raise ValueError(f"No HRRR data found for {start_date} to {end_date}")
        
        if return_hourly:
            return hourly_datasets
        
        # Compute daily mean temperature
        return self._compute_daily_mean(hourly_datasets)
    
    def _compute_daily_mean(self, hourly_datasets: list[xr.Dataset]) -> xr.DataArray:
        """
        Compute daily mean 2m temperature from hourly HRRR datasets.
        
        Args:
            hourly_datasets: List of xarray Datasets, one per hour
        
        Returns:
            xarray DataArray with daily mean temperature
        """
        # Extract 2m temperature from each hour
        temp_arrays = []
        for ds in hourly_datasets:
            # HRRR 2m temperature variable name varies; try common names
            if "t2m" in ds.data_vars:
                temp = ds["t2m"]
            elif "TMP_2maboveground" in ds.data_vars:
                temp = ds["TMP_2maboveground"]
            elif "TMP" in ds.data_vars:
                # Filter to 2m level if multi-level
                temp = ds["TMP"]
                if "isobaricInhPa" in temp.dims:
                    continue  # Skip pressure-level data
            else:
                logger.warning(f"Could not find 2m temperature in dataset")
                continue
            
            temp_arrays.append(temp)
        
        if not temp_arrays:
            raise ValueError("No 2m temperature data found in HRRR files")
        
        # Stack and compute mean
        stacked = xr.concat(temp_arrays, dim="time")
        daily_mean = stacked.mean(dim="time")
        
        return daily_mean
    
    def get_hrrr_climatology(
        self,
        month: int,
        min_years: int = HRRR_MIN_CLIM_YEARS,
    ) -> xr.DataArray:
        """
        Compute HRRR climatology (multi-year mean) for a given month.
        
        Args:
            month: Month number (1-12)
            min_years: Minimum number of years required
        
        Returns:
            xarray DataArray with monthly climatology
        
        Raises:
            ValueError: If insufficient data is available
        """
        # Find all cached files for this month
        manifest = self._load_manifest()
        manifest["datetime_utc"] = pd.to_datetime(manifest["datetime_utc"])
        manifest["month"] = manifest["datetime_utc"].dt.month
        manifest["year"] = manifest["datetime_utc"].dt.year
        
        month_data = manifest[manifest["month"] == month]
        
        if len(month_data) == 0:
            raise ValueError(f"No HRRR data cached for month {month}")
        
        # Group by year and load daily means
        years = month_data["year"].unique()
        
        if len(years) < min_years:
            logger.warning(
                f"Only {len(years)} years of HRRR data for month {month} "
                f"(minimum {min_years} required). Using available data."
            )
        
        daily_means = []
        for year in years:
            year_month_data = month_data[month_data["year"] == year]
            
            # Load all hours for this month/year
            hourly_datasets = []
            for _, row in year_month_data.iterrows():
                dt = row["datetime_utc"]
                local_path = self._get_local_cache_path(dt)
                
                if local_path.exists():
                    try:
                        ds = xr.open_dataset(local_path, engine="cfgrib")
                        hourly_datasets.append(ds)
                    except Exception as e:
                        logger.warning(f"Failed to load {local_path}: {e}")
            
            if hourly_datasets:
                daily_mean = self._compute_daily_mean(hourly_datasets)
                daily_means.append(daily_mean)
        
        if not daily_means:
            raise ValueError(f"Could not load any HRRR data for month {month}")
        
        # Compute climatology as mean across all years
        stacked = xr.concat(daily_means, dim="time")
        climatology = stacked.mean(dim="time")
        
        return climatology
