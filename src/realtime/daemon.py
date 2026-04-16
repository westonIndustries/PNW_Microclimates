"""
Real-time microclimate daemon.

Persistent daemon that polls for new HRRR cycles and produces safety cubes
within minutes of each release. Implements graceful shutdown and output rotation.
"""

import json
import logging
import multiprocessing
import signal
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue
from typing import Optional

from src.config import REALTIME_OUTPUT_DIR, DAEMON_STATUS_FILE, DAEMON_OUTPUT_ROTATION_HOURS
from src.realtime.hrrr_poller import create_hrrr_poller
from src.realtime.streaming_pipeline import process_hrrr_cycle
from src.output.write_safety_cube import write_safety_cube

logger = logging.getLogger(__name__)


class DaemonStatus:
    """Track daemon status and statistics."""

    def __init__(self, region_name: str):
        """
        Initialize daemon status.

        Parameters
        ----------
        region_name : str
            Region name (e.g., "region_1")
        """
        self.region_name = region_name
        self.start_time = datetime.utcnow()
        self.cycles_processed = 0
        self.cycles_failed = 0
        self.last_cycle_time = None
        self.status = "running"

    def to_dict(self) -> dict:
        """Convert status to dictionary."""
        return {
            "region_name": self.region_name,
            "status": self.status,
            "start_time": self.start_time.isoformat(),
            "last_cycle_time": self.last_cycle_time.isoformat() if self.last_cycle_time else None,
            "cycles_processed": self.cycles_processed,
            "cycles_failed": self.cycles_failed,
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
        }

    def save(self, filepath: Path) -> None:
        """Save status to JSON file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


def run_daemon(
    region_name: str,
    poll_interval_sec: int = 300,
    lookback_hours: int = 2,
    foreground: bool = False,
) -> None:
    """
    Run the real-time microclimate daemon.

    Polls for new HRRR cycles and produces safety cubes. Implements graceful
    shutdown on SIGINT/SIGTERM.

    Parameters
    ----------
    region_name : str
        Region name (e.g., "region_1")
    poll_interval_sec : int, default 300
        Poll interval in seconds
    lookback_hours : int, default 2
        Look back this many hours for missed cycles
    foreground : bool, default False
        Run in foreground (don't daemonize)
    """
    logger.info(f"Starting daemon for {region_name}")

    # Create output directory
    output_dir = REALTIME_OUTPUT_DIR / region_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize status
    status = DaemonStatus(region_name)

    # Create queue for HRRR cycles
    hrrr_queue = Queue()

    # Create poller
    poller = create_hrrr_poller(
        poll_interval_sec=poll_interval_sec,
        lookback_hours=lookback_hours,
    )

    # Stop event for graceful shutdown
    stop_event = threading.Event()

    def signal_handler(signum, frame):
        """Handle SIGINT/SIGTERM."""
        logger.info(f"Received signal {signum}, shutting down gracefully")
        stop_event.set()
        status.status = "shutting_down"
        status.save(DAEMON_STATUS_FILE)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Callback to queue HRRR cycles
    def hrrr_callback(hrrr_ds):
        """Callback to receive HRRR dataset."""
        hrrr_queue.put(hrrr_ds)

    # Start poller in separate thread
    poller_thread = threading.Thread(
        target=poller.run_continuous,
        args=(hrrr_callback, stop_event),
        daemon=True,
    )
    poller_thread.start()
    logger.info("Started HRRR poller thread")

    # Main daemon loop
    try:
        while not stop_event.is_set():
            try:
                # Get HRRR cycle from queue (with timeout)
                hrrr_ds = hrrr_queue.get(timeout=1)

                # Process cycle
                logger.info("Processing HRRR cycle")
                safety_cube = process_hrrr_cycle(
                    hrrr_ds=hrrr_ds,
                    static_cache_dir=REALTIME_OUTPUT_DIR / region_name / "cache",
                    region_name=region_name,
                )

                if safety_cube is not None:
                    # Write output
                    try:
                        write_safety_cube(
                            safety_cube,
                            region_name=region_name,
                            start_date=datetime.utcnow().strftime("%Y-%m-%d"),
                            end_date=datetime.utcnow().strftime("%Y-%m-%d"),
                            output_dir=output_dir,
                        )
                        status.cycles_processed += 1
                        status.last_cycle_time = datetime.utcnow()
                        logger.info(f"Processed cycle {status.cycles_processed}")
                    except Exception as e:
                        logger.error(f"Failed to write output: {e}")
                        status.cycles_failed += 1
                else:
                    status.cycles_failed += 1

                # Save status
                status.save(DAEMON_STATUS_FILE)

                # Check for output rotation
                _rotate_outputs(output_dir, DAEMON_OUTPUT_ROTATION_HOURS)

            except Exception as e:
                logger.error(f"Error in daemon loop: {e}", exc_info=True)
                status.cycles_failed += 1

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # Graceful shutdown
        logger.info("Shutting down daemon")
        stop_event.set()
        status.status = "stopped"
        status.save(DAEMON_STATUS_FILE)
        logger.info(f"Daemon stopped. Processed {status.cycles_processed} cycles")


def _rotate_outputs(output_dir: Path, rotation_hours: int) -> None:
    """
    Rotate output files older than rotation_hours.

    Parameters
    ----------
    output_dir : Path
        Output directory
    rotation_hours : int
        Rotate files older than this many hours
    """
    cutoff_time = datetime.utcnow() - timedelta(hours=rotation_hours)

    for parquet_file in output_dir.glob("*.parquet"):
        try:
            file_mtime = datetime.fromtimestamp(parquet_file.stat().st_mtime)
            if file_mtime < cutoff_time:
                logger.info(f"Rotating old output: {parquet_file}")
                # Archive or delete old file
                archive_dir = output_dir / "archive"
                archive_dir.mkdir(exist_ok=True)
                parquet_file.rename(archive_dir / parquet_file.name)
        except Exception as e:
            logger.warning(f"Failed to rotate {parquet_file}: {e}")


def main():
    """CLI entry point for daemon."""
    import argparse

    parser = argparse.ArgumentParser(description="Real-time microclimate daemon")
    parser.add_argument("--region", required=True, help="Region name (e.g., region_1)")
    parser.add_argument(
        "--build-cache",
        action="store_true",
        help="Build static cache before starting daemon",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=300,
        help="Poll interval in seconds (default: 300)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=2,
        help="Look back this many hours for missed cycles (default: 2)",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in foreground (don't daemonize)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Build cache if requested
    if args.build_cache:
        logger.info(f"Building static cache for {args.region}")
        from src.realtime.static_cache import build_static_cache
        build_static_cache(args.region)

    # Run daemon
    run_daemon(
        region_name=args.region,
        poll_interval_sec=args.poll_interval,
        lookback_hours=args.lookback,
        foreground=args.foreground,
    )


if __name__ == "__main__":
    main()
