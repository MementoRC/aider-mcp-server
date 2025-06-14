"""
Comprehensive tests for the FileMonitor system.

Tests cover:
- Initialization and configuration
- File size tracking and anomaly detection
- Content validation
- Write pattern analysis
- File lock detection
- Threading and performance
- Error handling
"""

import os
import threading
import time
from unittest.mock import patch

import pytest

from aider_mcp_server.atoms.utils.file_integrity import FileIntegrityError
from aider_mcp_server.atoms.utils.file_monitor import (
    ContentValidationError,
    FileAccessError,
    FileMonitor,
    MonitoringState,
    WritePatternError,
)


@pytest.fixture
def monitor(temp_git_repo):
    """Create a FileMonitor instance with test configuration."""
    return FileMonitor(
        repo_path=temp_git_repo,
        check_interval=0.1,  # Faster for testing
        size_change_threshold=0.5,
        max_consecutive_writes=3,
    )


@pytest.fixture
def test_file(temp_git_repo):
    """Create a test file in the repo."""
    file_path = "test.py"
    abs_path = os.path.join(temp_git_repo, file_path)

    with open(abs_path, "w", encoding="utf-8") as f:
        f.write("def test():\n    return True\n")

    return file_path


class TestFileMonitorInit:
    def test_init_success(self, temp_git_repo):
        monitor = FileMonitor(temp_git_repo)
        assert monitor.state == MonitoringState.INITIALIZED
        assert monitor.repo_path == os.path.abspath(temp_git_repo)

    def test_init_invalid_repo(self, tmp_path):
        with pytest.raises(FileIntegrityError):
            FileMonitor(str(tmp_path))


class TestMonitoringControl:
    def test_start_monitoring(self, monitor, test_file):
        monitor.start_monitoring([test_file])
        assert monitor.state == MonitoringState.RUNNING
        assert test_file in monitor.monitored_files

        # Cleanup
        monitor.stop_monitoring()

    def test_stop_monitoring(self, monitor, test_file):
        monitor.start_monitoring([test_file])
        assert monitor.state == MonitoringState.RUNNING

        monitor.stop_monitoring()
        assert monitor.state == MonitoringState.STOPPED
        assert not monitor._monitor_thread.is_alive()

    def test_duplicate_start(self, monitor, test_file):
        monitor.start_monitoring([test_file])
        monitor.start_monitoring([test_file])  # Should not error
        assert monitor.state == MonitoringState.RUNNING

        monitor.stop_monitoring()


class TestFileSizeTracking:
    @pytest.mark.skip(reason="Flaky test - race condition with file monitoring")
    def test_detect_size_change(self, monitor, test_file):
        monitor.start_monitoring([test_file])

        # Make a large change to the file
        abs_path = os.path.join(monitor.repo_path, test_file)
        original_content = "def test():\n    return True\n"
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(original_content * 10)  # 10x size increase
            f.flush()
            os.fsync(f.fileno())

        time.sleep(0.2)  # Allow monitor to detect change

        metrics = monitor.monitored_files[test_file]
        assert metrics.size > metrics.baseline_size

        monitor.stop_monitoring()

    def test_detect_file_truncation(self, monitor, test_file):
        monitor.start_monitoring([test_file])

        # Truncate the file
        abs_path = os.path.join(monitor.repo_path, test_file)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write("")
            f.flush()
            os.fsync(f.fileno())

        time.sleep(0.2)  # Allow monitor to detect change

        metrics = monitor.monitored_files[test_file]
        assert metrics.size == 0

        monitor.stop_monitoring()


class TestContentValidation:
    def test_valid_content_change(self, monitor, test_file):
        monitor.start_monitoring([test_file])

        # Make valid change
        abs_path = os.path.join(monitor.repo_path, test_file)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write("def new_test():\n    return False\n")
            f.flush()
            os.fsync(f.fileno())

        time.sleep(0.2)  # Allow monitor to detect change
        assert monitor.state == MonitoringState.RUNNING

        monitor.stop_monitoring()

    def test_invalid_content_change(self, monitor, test_file):
        monitor.start_monitoring([test_file])

        # Make invalid change
        abs_path = os.path.join(monitor.repo_path, test_file)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write("def broken(:\n")  # Syntax error
            f.flush()
            os.fsync(f.fileno())

        time.sleep(0.2)  # Allow monitor to detect change

        # Should detect syntax error
        assert monitor.state == MonitoringState.ERROR

        monitor.stop_monitoring()


class TestWritePatternAnalysis:
    def test_normal_write_pattern(self, monitor, test_file):
        monitor.start_monitoring([test_file])

        # Make changes with normal timing
        abs_path = os.path.join(monitor.repo_path, test_file)
        for i in range(3):
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(f"def test_{i}():\n    return True\n")
                f.flush()
                os.fsync(f.fileno())
            time.sleep(0.3)  # Normal delay between writes

        assert monitor.state == MonitoringState.RUNNING

        monitor.stop_monitoring()

    def test_suspicious_write_pattern(self, monitor, test_file):
        monitor.start_monitoring([test_file])

        # Get file metrics and create fake stats
        metrics = monitor.monitored_files[test_file]
        abs_path = os.path.join(monitor.repo_path, test_file)
        stats = os.stat(abs_path)

        try:
            # Simulate multiple rapid writes
            for _ in range(monitor.max_consecutive_writes + 1):
                monitor._process_file_modification(test_file, abs_path, stats, metrics)

            pytest.fail("Expected WritePatternError was not raised")
        except WritePatternError:
            # Verify error state
            assert monitor.state == MonitoringState.ERROR
            assert metrics.consecutive_writes > monitor.max_consecutive_writes
        finally:
            monitor.stop_monitoring()


class TestFileLockDetection:
    @patch("os.access")
    def test_detect_locked_file(self, mock_access, monitor, test_file):
        mock_access.return_value = False

        monitor.start_monitoring([test_file])
        time.sleep(0.2)  # Allow monitor to check access

        assert test_file in monitor.locked_files

        monitor.stop_monitoring()

    @patch("os.access")
    def test_detect_file_unlock(self, mock_access, monitor, test_file):
        # Start with file locked
        mock_access.return_value = False
        monitor.start_monitoring([test_file])
        time.sleep(0.2)
        assert test_file in monitor.locked_files

        # Then unlock it
        mock_access.return_value = True
        time.sleep(0.2)
        assert test_file not in monitor.locked_files

        monitor.stop_monitoring()


class TestErrorHandling:
    def test_handle_access_error(self, monitor, test_file):
        # Start monitoring first
        monitor.start_monitoring([test_file])

        # Simulate file deletion to trigger an OSError during stat
        abs_path = os.path.join(monitor.repo_path, test_file)
        os.remove(abs_path)

        # Mock os.path.exists to return True but os.stat to raise PermissionError
        with patch("aider_mcp_server.atoms.utils.file_monitor.os.path.exists", return_value=True):
            with patch("aider_mcp_server.atoms.utils.file_monitor.os.access", return_value=True):
                # This should raise FileAccessError when os.stat fails
                with pytest.raises(FileAccessError):
                    monitor._check_files()

                # Should have set state to ERROR
                assert monitor.state == MonitoringState.ERROR

        monitor.stop_monitoring()

    def test_handle_content_validation_error(self, monitor, test_file):
        monitor.start_monitoring([test_file])

        with patch.object(monitor.integrity_manager, "validate_syntax") as mock_validate:
            mock_validate.side_effect = ContentValidationError("Invalid content")

            # Trigger a file change
            abs_path = os.path.join(monitor.repo_path, test_file)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write("def test():\n    return True\n")
                f.flush()
                os.fsync(f.fileno())

            time.sleep(0.2)  # Allow monitor to process change

            assert monitor.state == MonitoringState.ERROR

            monitor.stop_monitoring()


class TestPerformance:
    def test_minimal_overhead(self, monitor, test_file):
        # Measure baseline file operation time
        start_time = time.time()
        for _ in range(10):
            abs_path = os.path.join(monitor.repo_path, test_file)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write("def test():\n    return True\n")
        baseline_time = time.time() - start_time

        # Measure time with monitoring
        monitor.start_monitoring([test_file])
        start_time = time.time()
        for _ in range(10):
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write("def test():\n    return True\n")
        monitored_time = time.time() - start_time

        # Overhead should be reasonable
        assert monitored_time < baseline_time * 2

        monitor.stop_monitoring()

    def test_thread_safety(self, monitor, test_file):
        monitor.start_monitoring([test_file])

        # Create multiple threads to modify the file
        threads = []
        for i in range(5):
            thread = threading.Thread(
                target=lambda x: open(os.path.join(monitor.repo_path, test_file), "w", encoding="utf-8").write(
                    f"def test_{x}():\n    return True\n"
                ),
                args=(i,),
            )
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for threads to complete
        for thread in threads:
            thread.join()

        # Monitor should handle concurrent access
        assert monitor.state == MonitoringState.RUNNING

        monitor.stop_monitoring()
