"""
Real-time File Monitor for Aider Safety Operations.

Provides comprehensive file monitoring capabilities including:
- File size tracking and anomaly detection
- Content validation and structure verification
- Write pattern analysis
- File lock detection

Integrates with FileIntegrityManager for baseline metrics.
Uses threading for real-time monitoring with configurable frequency.
"""

import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.utils.file_integrity import FileIntegrityManager

logger = get_logger(__name__)


class FileMonitorError(Exception):
    """Base exception for file monitoring operations."""

    pass


class FileAccessError(FileMonitorError):
    """Raised when a file becomes inaccessible."""

    pass


class ContentValidationError(FileMonitorError):
    """Raised when file content validation fails."""

    pass


class WritePatternError(FileMonitorError):
    """Raised when suspicious write patterns are detected."""

    pass


class MonitoringState(Enum):
    """States for the file monitoring system."""

    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class FileMetrics:
    """Metrics for a monitored file."""

    path: str
    size: int
    last_modified: float
    access_time: float
    baseline_size: int
    baseline_structure: Dict[str, Any]
    write_count: int = 0
    last_write_time: float = 0
    consecutive_writes: int = 0


class FileMonitor:
    """
    Real-time file monitoring system for Aider operations.

    Provides comprehensive monitoring of file changes including size tracking,
    content validation, write pattern analysis, and lock detection.
    """

    def __init__(
        self,
        repo_path: str,
        check_interval: float = 0.5,
        size_change_threshold: float = 0.5,
        max_consecutive_writes: int = 3,
        content_validation_enabled: bool = True,
    ):
        """
        Initialize the file monitor.

        Args:
            repo_path: Path to the git repository
            check_interval: Monitoring frequency in seconds
            size_change_threshold: Threshold for suspicious size changes (0-1)
            max_consecutive_writes: Maximum allowed consecutive writes
            content_validation_enabled: Enable content structure validation
        """
        self.repo_path = os.path.abspath(repo_path)
        self.check_interval = check_interval
        self.size_change_threshold = size_change_threshold
        self.max_consecutive_writes = max_consecutive_writes
        self.content_validation_enabled = content_validation_enabled

        # Initialize integrity manager for baselines
        self.integrity_manager = FileIntegrityManager(repo_path)

        # Monitoring state
        self.state = MonitoringState.INITIALIZED
        self.monitored_files: Dict[str, FileMetrics] = {}
        self.locked_files: Set[str] = set()

        # Threading controls
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        logger.info(
            f"Initialized FileMonitor for {repo_path} (interval={check_interval}s, threshold={size_change_threshold})"
        )

    def start_monitoring(self, target_files: List[str]) -> None:
        """
        Start monitoring the specified files.

        Args:
            target_files: List of file paths to monitor

        Raises:
            FileMonitorError: If monitoring cannot be started
        """
        if self.state == MonitoringState.RUNNING:
            logger.warning("File monitoring already running")
            return

        try:
            # Capture baselines for all target files
            baseline = self.integrity_manager.capture_file_integrity_baseline(target_files)

            # Initialize metrics for each file
            for file_path in target_files:
                abs_path = os.path.join(self.repo_path, file_path)
                stats = os.stat(abs_path)

                self.monitored_files[file_path] = FileMetrics(
                    path=file_path,
                    size=stats.st_size,
                    last_modified=stats.st_mtime,
                    access_time=stats.st_atime,
                    baseline_size=stats.st_size,
                    baseline_structure=baseline[file_path],
                )

            # Start monitoring thread
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._monitoring_loop, name="FileMonitor", daemon=True)
            self._monitor_thread.start()

            self.state = MonitoringState.RUNNING
            logger.info(f"Started monitoring {len(target_files)} files")

        except Exception as e:
            self.state = MonitoringState.ERROR
            logger.error(f"Failed to start monitoring: {e}")
            raise FileMonitorError(f"Failed to start monitoring: {e}") from e

    def stop_monitoring(self) -> None:
        """Stop the monitoring system."""
        if self.state != MonitoringState.RUNNING:
            return

        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)

        self.state = MonitoringState.STOPPED
        logger.info("Stopped file monitoring")

    def _monitoring_loop(self) -> None:
        """Main monitoring loop that runs in a separate thread."""
        while not self._stop_event.is_set():
            try:
                self._check_files()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                self.state = MonitoringState.ERROR
                break

    def _check_files(self) -> None:
        """Check all monitored files for changes and issues."""
        for file_path, metrics in self.monitored_files.items():
            try:
                self._check_single_file(file_path, metrics)
            except (OSError, PermissionError) as e:
                logger.error(f"Access error for {file_path}: {e}")
                self.state = MonitoringState.ERROR
                raise FileAccessError(f"Cannot access {file_path}: {e}") from e
            except Exception as e:
                logger.error(f"Error checking {file_path}: {e}")
                self.state = MonitoringState.ERROR
                raise FileMonitorError(f"Error monitoring {file_path}: {e}") from e

    def _check_single_file(self, file_path: str, metrics: FileMetrics) -> None:
        """Check a single file for changes and issues."""
        abs_path = os.path.join(self.repo_path, file_path)

        # Check if file exists and is accessible
        if not self._check_file_accessibility(file_path, abs_path):
            return

        # Get current stats
        stats = os.stat(abs_path)

        # Check for modifications
        if stats.st_mtime > metrics.last_modified:
            self._process_file_modification(file_path, abs_path, stats, metrics)

    def _check_file_accessibility(self, file_path: str, abs_path: str) -> bool:
        """Check if file exists and is accessible."""
        if not os.path.exists(abs_path):
            logger.debug(f"File does not exist: {file_path}")
            return False

        if not os.access(abs_path, os.R_OK):
            if file_path not in self.locked_files:
                self.locked_files.add(file_path)
                logger.warning(f"File became locked: {file_path}")
            return False
        elif file_path in self.locked_files:
            self.locked_files.remove(file_path)
            logger.info(f"File unlocked: {file_path}")

        return True

    def _process_file_modification(
        self, file_path: str, abs_path: str, stats: os.stat_result, metrics: FileMetrics
    ) -> None:
        """Process a detected file modification."""
        # Update write tracking
        current_time = time.time()
        if current_time - metrics.last_write_time < self.check_interval:
            metrics.consecutive_writes += 1
        else:
            metrics.consecutive_writes = 1

        metrics.write_count += 1
        metrics.last_write_time = current_time

        # Check for suspicious patterns
        if metrics.consecutive_writes > self.max_consecutive_writes:
            logger.warning(
                f"Suspicious write pattern detected for {file_path}: {metrics.consecutive_writes} consecutive writes"
            )
            self.state = MonitoringState.ERROR
            raise WritePatternError(f"Too many consecutive writes to {file_path}")

        # Check size changes
        size_change = abs(stats.st_size - metrics.size) / metrics.baseline_size
        if size_change > self.size_change_threshold:
            logger.warning(f"Suspicious size change in {file_path}: changed by {size_change:.1%}")

        # Validate content if enabled
        if self.content_validation_enabled:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.integrity_manager.validate_syntax(abs_path, content)

        # Update metrics
        metrics.size = stats.st_size
        metrics.last_modified = stats.st_mtime
        metrics.access_time = stats.st_atime
