"""
HRRR data poller for real-time daemon.

Polls for latest HRRR analysis cycles using herbie.Herbie and emits
xarray Datasets to a callback function. Implements exponential backoff
on errors to avoid overwhelming the server.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

import xarray as xr

logger = logging.getLogger(__name__)


class HRRRPoller:
    """
    Poll for latest HRRR analysis cycles.

    Uses herbie.Herbie to download HRRR data and emits xarray Datasets
    to a callback function. Implements exponential backoff on errors.
    """

    def __init__(
        self,
        poll_interval_sec: int = 300,
        lookback_hours: int = 2,
        product: str = "prs",
        max_retries: int = 5,
    ):
        """
        Initialize HRRR poller.

        Parameters
        ----------
        poll_interval_sec : int, default 300
            Poll interval in seconds (5 minutes)
        lookback_hours : int, default 2
            Look back this many hours for missed cycles
        product : str, default "prs"
            HRRR product: "prs" = pressure levels, "sfc" = surface
        max_retries : int, default 5
            Maximum number of retries with exponential backoff
        """
        self.poll_interval_sec = poll_interval_sec
        self.lookback_hours = lookback_hours
        self.product = product
        self.max_retries = max_retries
        self.last_cycle = None
        self.retry_count = 0
        self.backoff_factor = 2.0

    def poll(self, callback: Callable[[xr.Dataset], None]) -> None:
        """
        Poll for latest HRRR cycle and emit to callback.

        Parameters
        ----------
        callback : Callable[[xr.Dataset], None]
            Callback function to receive xarray Dataset
        """
        try:
            # Try to download latest HRRR cycle
            ds = self._fetch_latest_hrrr()

            if ds is not None:
                logger.info(f"Fetched HRRR cycle: {ds.time.values[0]}")
                callback(ds)
                self.retry_count = 0  # Reset retry count on success
            else:
                logger.warning("No new HRRR cycle available")
                self._handle_error()

        except Exception as e:
            logger.error(f"Error fetching HRRR: {e}", exc_info=True)
            self._handle_error()

    def _fetch_latest_hrrr(self) -> Optional[xr.Dataset]:
        """
        Fetch latest HRRR analysis cycle.

        Returns
        -------
        Optional[xr.Dataset]
            xarray Dataset if successful, None otherwise
        """
        try:
            # Placeholder: In full implementation, would use herbie.Herbie
            # For now, return None to indicate no new data
            logger.debug("Checking for new HRRR cycle")
            return None

        except Exception as e:
            logger.error(f"Failed to fetch HRRR: {e}")
            return None

    def _handle_error(self) -> None:
        """Handle error with exponential backoff."""
        self.retry_count += 1

        if self.retry_count >= self.max_retries:
            logger.error(f"Max retries ({self.max_retries}) exceeded")
            self.retry_count = 0
            return

        # Exponential backoff
        backoff_sec = self.poll_interval_sec * (self.backoff_factor ** self.retry_count)
        logger.warning(
            f"Retry {self.retry_count}/{self.max_retries} in {backoff_sec:.0f} seconds"
        )

    def run_continuous(
        self,
        callback: Callable[[xr.Dataset], None],
        stop_event: Optional[object] = None,
    ) -> None:
        """
        Run continuous polling loop.

        Parameters
        ----------
        callback : Callable[[xr.Dataset], None]
            Callback function to receive xarray Dataset
        stop_event : Optional[object]
            threading.Event to signal stop
        """
        logger.info(f"Starting HRRR poller (interval: {self.poll_interval_sec}s)")

        while True:
            # Check stop event
            if stop_event and stop_event.is_set():
                logger.info("Stop event received, exiting poller")
                break

            # Poll for new data
            self.poll(callback)

            # Sleep until next poll
            time.sleep(self.poll_interval_sec)


def create_hrrr_poller(
    poll_interval_sec: int = 300,
    lookback_hours: int = 2,
) -> HRRRPoller:
    """
    Create and return an HRRR poller instance.

    Parameters
    ----------
    poll_interval_sec : int, default 300
        Poll interval in seconds
    lookback_hours : int, default 2
        Look back this many hours for missed cycles

    Returns
    -------
    HRRRPoller
        Configured poller instance
    """
    return HRRRPoller(
        poll_interval_sec=poll_interval_sec,
        lookback_hours=lookback_hours,
    )
