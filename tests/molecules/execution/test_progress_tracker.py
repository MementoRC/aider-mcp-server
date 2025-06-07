"""Tests for the progress tracker module."""

import asyncio
import time

import pytest

from aider_mcp_server.molecules.execution.progress_tracker import (
    CallbackProgressReporter,
    LoggingProgressReporter,
    MultiProgressReporter,
    ProgressEvent,
    ProgressStatus,
    ProgressStep,
    ProgressTracker,
    track_multi_step_progress,
    track_simple_progress,
)


class TestProgressEvent:
    """Test cases for ProgressEvent."""

    def test_progress_event_creation(self):
        """Test ProgressEvent creation and properties."""
        event = ProgressEvent(
            operation_id="test_op",
            event_type="test_event",
            message="Test message",
            progress_percentage=50.0,
            metadata={"key": "value"},
        )

        assert event.operation_id == "test_op"
        assert event.event_type == "test_event"
        assert event.message == "Test message"
        assert event.progress_percentage == 50.0
        assert event.metadata == {"key": "value"}
        assert isinstance(event.timestamp, float)

    def test_progress_event_to_dict(self):
        """Test ProgressEvent dictionary conversion."""
        event = ProgressEvent(
            operation_id="test_op", event_type="test_event", message="Test message", progress_percentage=75.0
        )

        event_dict = event.to_dict()
        assert event_dict["operation_id"] == "test_op"
        assert event_dict["event_type"] == "test_event"
        assert event_dict["message"] == "Test message"
        assert event_dict["progress_percentage"] == 75.0
        assert "timestamp" in event_dict


class TestProgressStep:
    """Test cases for ProgressStep."""

    def test_step_creation(self):
        """Test ProgressStep creation."""
        step = ProgressStep("test_step", weight=2.0, description="Test step description")

        assert step.name == "test_step"
        assert step.weight == 2.0
        assert step.description == "Test step description"
        assert step.status == ProgressStatus.NOT_STARTED
        assert step.progress_percentage == 0.0

    def test_step_lifecycle(self):
        """Test step lifecycle transitions."""
        step = ProgressStep("test_step")

        # Initial state
        assert step.status == ProgressStatus.NOT_STARTED
        assert step.start_time is None
        assert step.end_time is None

        # Start step
        step.start()
        assert step.status == ProgressStatus.IN_PROGRESS
        assert step.start_time is not None
        assert step.end_time is None

        # Update progress
        step.update_progress(50.0)
        assert step.progress_percentage == 50.0

        # Complete step
        step.complete()
        assert step.status == ProgressStatus.COMPLETED
        assert step.progress_percentage == 100.0
        assert step.end_time is not None

    def test_step_failure(self):
        """Test step failure handling."""
        step = ProgressStep("test_step")
        step.start()

        error = ValueError("Test error")
        step.fail(error)

        assert step.status == ProgressStatus.FAILED
        assert step.error == error
        assert step.end_time is not None

    def test_step_cancellation(self):
        """Test step cancellation."""
        step = ProgressStep("test_step")
        step.start()
        step.cancel()

        assert step.status == ProgressStatus.CANCELLED
        assert step.end_time is not None

    def test_step_duration(self):
        """Test step duration calculation."""
        step = ProgressStep("test_step")

        # No duration when not started
        assert step.get_duration() is None

        step.start()
        time.sleep(0.01)  # Small delay

        # Duration while in progress
        duration = step.get_duration()
        assert duration is not None
        assert duration > 0

        step.complete()

        # Duration after completion
        final_duration = step.get_duration()
        assert final_duration is not None
        assert final_duration >= duration

    def test_step_to_dict(self):
        """Test step dictionary conversion."""
        step = ProgressStep("test_step", weight=1.5, description="Test description")
        step.start()
        step.update_progress(75.0)
        step.complete()

        step_dict = step.to_dict()
        assert step_dict["name"] == "test_step"
        assert step_dict["weight"] == 1.5
        assert step_dict["description"] == "Test description"
        assert step_dict["status"] == "completed"
        assert step_dict["progress_percentage"] == 100.0
        assert "duration" in step_dict


class TestProgressReporters:
    """Test cases for progress reporters."""

    def test_logging_progress_reporter(self):
        """Test LoggingProgressReporter."""
        reporter = LoggingProgressReporter()
        event = ProgressEvent("test_op", "test_event", "Test message", 50.0)

        # Should not raise an exception
        reporter.report_progress(event)

    def test_callback_progress_reporter(self):
        """Test CallbackProgressReporter."""
        reporter = CallbackProgressReporter()
        callback_calls = []

        def test_callback(event):
            callback_calls.append(event)

        reporter.add_callback(test_callback)

        event = ProgressEvent("test_op", "test_event", "Test message", 50.0)
        reporter.report_progress(event)

        assert len(callback_calls) == 1
        assert callback_calls[0] == event

    def test_callback_reporter_remove_callback(self):
        """Test callback removal in CallbackProgressReporter."""
        reporter = CallbackProgressReporter()
        callback_calls = []

        def test_callback(event):
            callback_calls.append(event)

        reporter.add_callback(test_callback)
        reporter.remove_callback(test_callback)

        event = ProgressEvent("test_op", "test_event", "Test message", 50.0)
        reporter.report_progress(event)

        assert len(callback_calls) == 0

    def test_multi_progress_reporter(self):
        """Test MultiProgressReporter."""
        reporter1 = CallbackProgressReporter()
        reporter2 = CallbackProgressReporter()
        multi_reporter = MultiProgressReporter([reporter1, reporter2])

        callback1_calls = []
        callback2_calls = []

        def callback1(event):
            callback1_calls.append(event)

        def callback2(event):
            callback2_calls.append(event)

        reporter1.add_callback(callback1)
        reporter2.add_callback(callback2)

        event = ProgressEvent("test_op", "test_event", "Test message", 50.0)
        multi_reporter.report_progress(event)

        assert len(callback1_calls) == 1
        assert len(callback2_calls) == 1

    def test_callback_reporter_error_handling(self):
        """Test error handling in callback reporter."""
        reporter = CallbackProgressReporter()

        def failing_callback(event):
            raise ValueError("Callback failed")

        def working_callback(event):
            working_callback.called = True

        working_callback.called = False

        reporter.add_callback(failing_callback)
        reporter.add_callback(working_callback)

        event = ProgressEvent("test_op", "test_event", "Test message", 50.0)

        # Should not raise exception despite failing callback
        reporter.report_progress(event)

        # Working callback should still be called
        assert working_callback.called


class TestProgressTracker:
    """Test cases for ProgressTracker."""

    def test_tracker_initialization(self):
        """Test ProgressTracker initialization."""
        tracker = ProgressTracker("test_operation", total_steps=5)

        assert tracker.operation_id == "test_operation"
        assert tracker.total_steps == 5
        assert tracker.status == ProgressStatus.NOT_STARTED
        assert tracker.overall_progress == 0.0

    def test_simple_progress_tracking(self):
        """Test simple progress tracking."""
        callback_events = []

        def progress_callback(event):
            callback_events.append(event)

        reporter = CallbackProgressReporter()
        reporter.add_callback(progress_callback)

        tracker = ProgressTracker("test_op", total_steps=4, reporter=reporter)

        tracker.start("Starting operation")
        tracker.update_progress(25.0, "Quarter done")
        tracker.update_progress(50.0, "Half done")
        tracker.update_progress(75.0, "Three quarters done")
        tracker.complete("Operation completed")

        assert tracker.status == ProgressStatus.COMPLETED
        assert tracker.overall_progress == 100.0
        assert len(callback_events) == 5  # start + 3 updates + complete

    def test_multi_step_progress_tracking(self):
        """Test multi-step progress tracking."""
        tracker = ProgressTracker("multi_step_op")

        # Add steps
        tracker.add_step("step1", weight=1.0, description="First step")
        tracker.add_step("step2", weight=2.0, description="Second step")
        tracker.add_step("step3", weight=1.0, description="Third step")

        tracker.start("Starting multi-step operation")

        # Process step 1
        tracker.start_step("step1")
        tracker.update_step_progress(50.0)
        tracker.update_step_progress(100.0)
        tracker.complete_step()

        # Check progress after step 1 (weight 1 out of total weight 4)
        assert abs(tracker.overall_progress - 25.0) < 0.1

        # Process step 2
        tracker.start_step("step2")
        tracker.update_step_progress(50.0)
        tracker.complete_step()

        # Check progress after step 2 (weight 3 out of total weight 4)
        assert abs(tracker.overall_progress - 75.0) < 0.1

        # Process step 3
        tracker.start_step("step3")
        tracker.complete_step()

        tracker.complete("All steps completed")

        assert tracker.status == ProgressStatus.COMPLETED
        assert tracker.overall_progress == 100.0

    def test_step_failure_handling(self):
        """Test step failure handling."""
        tracker = ProgressTracker("failing_op")
        tracker.add_step("step1", description="Failing step")

        tracker.start()
        tracker.start_step("step1")

        error = RuntimeError("Step failed")
        tracker.fail_step(error, "Step 1 failed")

        # Operation should still be in progress (not automatically failed)
        assert tracker.status == ProgressStatus.IN_PROGRESS

        # Fail the entire operation
        tracker.fail(error, "Operation failed")
        assert tracker.status == ProgressStatus.FAILED
        assert tracker.error == error

    def test_operation_cancellation(self):
        """Test operation cancellation."""
        tracker = ProgressTracker("cancellable_op")
        tracker.add_step("step1", description="First step")
        tracker.add_step("step2", description="Second step")

        tracker.start()
        tracker.start_step("step1")

        tracker.cancel("Operation cancelled by user")

        assert tracker.status == ProgressStatus.CANCELLED

        # In-progress step should be cancelled
        step1 = tracker._steps[0]
        assert step1.status == ProgressStatus.CANCELLED

    def test_add_steps_from_list(self):
        """Test adding steps from a list."""
        tracker = ProgressTracker("test_op")

        steps = [
            "simple_step",
            {"name": "complex_step", "weight": 2.0, "description": "Complex step"},
            {"name": "another_step", "weight": 0.5},
        ]

        tracker.add_steps(steps)

        assert len(tracker._steps) == 3
        assert tracker._steps[0].name == "simple_step"
        assert tracker._steps[0].weight == 1.0
        assert tracker._steps[1].name == "complex_step"
        assert tracker._steps[1].weight == 2.0
        assert tracker._steps[1].description == "Complex step"
        assert tracker._steps[2].name == "another_step"
        assert tracker._steps[2].weight == 0.5

    def test_duration_and_eta_calculation(self):
        """Test duration and ETA calculation."""
        tracker = ProgressTracker("timed_op")

        # No duration before start
        assert tracker.get_duration() is None
        assert tracker.get_estimated_time_remaining() is None

        tracker.start()
        time.sleep(0.01)  # Small delay

        # Duration available after start
        duration = tracker.get_duration()
        assert duration is not None
        assert duration > 0

        # Update progress to calculate ETA
        tracker.update_progress(25.0)
        eta = tracker.get_estimated_time_remaining()
        assert eta is not None
        assert eta > 0

        tracker.complete()

        # Final duration
        final_duration = tracker.get_duration()
        assert final_duration is not None
        assert final_duration >= duration

    def test_get_status(self):
        """Test comprehensive status information."""
        tracker = ProgressTracker("status_test")
        tracker.add_step("step1", weight=1.0)
        tracker.add_step("step2", weight=2.0)

        tracker.start()
        tracker.start_step("step1")
        tracker.update_step_progress(50.0)

        status = tracker.get_status()

        assert status["operation_id"] == "status_test"
        assert status["status"] == "in_progress"
        assert status["current_step"] == 1
        assert status["total_steps"] == 2
        assert "overall_progress" in status
        assert "start_time" in status
        assert "steps" in status
        assert len(status["steps"]) == 2

    def test_get_events(self):
        """Test event history retrieval."""
        callback_events = []

        def progress_callback(event):
            callback_events.append(event)

        reporter = CallbackProgressReporter()
        reporter.add_callback(progress_callback)

        tracker = ProgressTracker("event_test", reporter=reporter)

        tracker.start()
        tracker.update_progress(50.0)
        tracker.complete()

        events = tracker.get_events()
        assert len(events) == 3

        # Test limited events
        limited_events = tracker.get_events(limit=2)
        assert len(limited_events) == 2

    def test_context_manager(self):
        """Test ProgressTracker as context manager."""
        with ProgressTracker("context_test") as tracker:
            tracker.update_progress(50.0)
            # Should auto-complete on exit

        assert tracker.status == ProgressStatus.COMPLETED
        assert tracker.overall_progress == 100.0

    def test_context_manager_with_exception(self):
        """Test context manager behavior with exceptions."""
        try:
            with ProgressTracker("exception_test") as tracker:
                tracker.update_progress(50.0)
                raise ValueError("Test exception")
        except ValueError:
            pass

        assert tracker.status == ProgressStatus.FAILED
        assert isinstance(tracker.error, ValueError)


class TestConvenienceFunctions:
    """Test cases for convenience functions."""

    def test_track_simple_progress(self):
        """Test track_simple_progress convenience function."""
        tracker = track_simple_progress("simple_test", total_steps=3)

        assert tracker.operation_id == "simple_test"
        assert tracker.total_steps == 3
        assert isinstance(tracker._reporter, LoggingProgressReporter)

    def test_track_multi_step_progress(self):
        """Test track_multi_step_progress convenience function."""
        steps = ["step1", "step2", "step3"]
        tracker = track_multi_step_progress("multi_test", steps)

        assert tracker.operation_id == "multi_test"
        assert len(tracker._steps) == 3
        assert tracker._steps[0].name == "step1"


class TestProgressTrackerIntegration:
    """Integration tests for ProgressTracker."""

    def test_file_processing_simulation(self):
        """Simulate file processing with progress tracking."""
        files = ["file1.txt", "file2.txt", "file3.txt", "file4.txt"]
        processed_files = []

        def progress_callback(event):
            if event.event_type == "step_completed":
                processed_files.append(event.metadata.get("step_name"))

        reporter = CallbackProgressReporter()
        reporter.add_callback(progress_callback)

        tracker = ProgressTracker("file_processing", reporter=reporter)

        # Add file processing steps
        for file_name in files:
            tracker.add_step(file_name, weight=1.0, description=f"Processing {file_name}")

        tracker.start("Starting file processing")

        # Process each file
        for file_name in files:
            tracker.start_step(file_name)

            # Simulate processing progress
            for progress in [25, 50, 75, 100]:
                tracker.update_step_progress(progress, f"Processing {file_name}: {progress}%")
                time.sleep(0.001)  # Simulate work

            tracker.complete_step(f"Completed processing {file_name}")

        tracker.complete("All files processed")

        assert tracker.status == ProgressStatus.COMPLETED
        assert tracker.overall_progress == 100.0
        assert len(processed_files) == len(files)

    @pytest.mark.asyncio
    async def test_async_operation_tracking(self):
        """Test progress tracking with async operations."""
        progress_updates = []

        def track_progress(event):
            progress_updates.append((event.event_type, event.progress_percentage))

        reporter = CallbackProgressReporter()
        reporter.add_callback(track_progress)

        tracker = ProgressTracker("async_test", reporter=reporter)

        async def async_operation():
            tracker.start("Starting async operation")

            for i in range(5):
                await asyncio.sleep(0.01)  # Simulate async work
                progress = (i + 1) * 20
                tracker.update_progress(progress, f"Step {i + 1} completed")

            tracker.complete("Async operation completed")

        await async_operation()

        assert tracker.status == ProgressStatus.COMPLETED
        assert len(progress_updates) >= 6  # start + 5 updates + complete
