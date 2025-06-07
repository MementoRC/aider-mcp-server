"""
Progress Tracker module for monitoring and reporting long-running operations.
Provides comprehensive progress tracking with event broadcasting and metrics collection.
"""

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol


class ProgressStatus(Enum):
    """Enumeration of progress status states."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class ProgressEvent:
    """Represents a progress event with timestamp and metadata."""

    def __init__(
        self,
        operation_id: str,
        event_type: str,
        message: str,
        progress_percentage: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.operation_id = operation_id
        self.event_type = event_type
        self.message = message
        self.progress_percentage = progress_percentage
        self.metadata = metadata or {}
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert progress event to dictionary representation."""
        return {
            "operation_id": self.operation_id,
            "event_type": self.event_type,
            "message": self.message,
            "progress_percentage": self.progress_percentage,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class ProgressReporter(ABC):
    """Abstract base class for progress reporting."""

    @abstractmethod
    def report_progress(self, event: ProgressEvent) -> None:
        """Report a progress event."""
        pass


class LoggingProgressReporter(ProgressReporter):
    """Progress reporter that logs to the standard logging system."""

    def __init__(self, logger_name: Optional[str] = None) -> None:
        self._logger: LoggerProtocol = get_logger(logger_name or __name__)

    def report_progress(self, event: ProgressEvent) -> None:
        """Report progress via logging."""
        self._logger.info(f"Progress [{event.operation_id}] {event.progress_percentage:.1f}%: {event.message}")


class CallbackProgressReporter(ProgressReporter):
    """Progress reporter that calls registered callback functions."""

    def __init__(self) -> None:
        self._callbacks: List[Callable[[ProgressEvent], None]] = []

    def add_callback(self, callback: Callable[[ProgressEvent], None]) -> None:
        """Add a progress callback function."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[ProgressEvent], None]) -> None:
        """Remove a progress callback function."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def report_progress(self, event: ProgressEvent) -> None:
        """Report progress to all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                # Don't let callback errors stop progress reporting
                print(f"Progress callback error: {e}")


class MultiProgressReporter(ProgressReporter):
    """Progress reporter that delegates to multiple reporters."""

    def __init__(self, reporters: Optional[List[ProgressReporter]] = None) -> None:
        self._reporters = reporters or []

    def add_reporter(self, reporter: ProgressReporter) -> None:
        """Add a progress reporter."""
        self._reporters.append(reporter)

    def remove_reporter(self, reporter: ProgressReporter) -> None:
        """Remove a progress reporter."""
        if reporter in self._reporters:
            self._reporters.remove(reporter)

    def report_progress(self, event: ProgressEvent) -> None:
        """Report progress to all registered reporters."""
        for reporter in self._reporters:
            try:
                reporter.report_progress(event)
            except Exception as e:
                # Don't let reporter errors stop progress reporting
                print(f"Progress reporter error: {e}")


class ProgressStep:
    """Represents a step in a multi-step operation."""

    def __init__(
        self,
        name: str,
        weight: float = 1.0,
        description: Optional[str] = None,
    ) -> None:
        self.name = name
        self.weight = weight
        self.description = description or name
        self.status = ProgressStatus.NOT_STARTED
        self.progress_percentage = 0.0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.error: Optional[Exception] = None

    def start(self) -> None:
        """Mark the step as started."""
        self.status = ProgressStatus.IN_PROGRESS
        self.start_time = time.time()

    def update_progress(self, percentage: float) -> None:
        """Update the step's progress percentage."""
        self.progress_percentage = max(0.0, min(100.0, percentage))

    def complete(self) -> None:
        """Mark the step as completed."""
        self.status = ProgressStatus.COMPLETED
        self.progress_percentage = 100.0
        self.end_time = time.time()

    def fail(self, error: Optional[Exception] = None) -> None:
        """Mark the step as failed."""
        self.status = ProgressStatus.FAILED
        self.end_time = time.time()
        self.error = error

    def cancel(self) -> None:
        """Mark the step as cancelled."""
        self.status = ProgressStatus.CANCELLED
        self.end_time = time.time()

    def get_duration(self) -> Optional[float]:
        """Get the duration of the step execution."""
        if self.start_time is None:
            return None
        end_time = self.end_time or time.time()
        return end_time - self.start_time

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary representation."""
        return {
            "name": self.name,
            "weight": self.weight,
            "description": self.description,
            "status": self.status.value,
            "progress_percentage": self.progress_percentage,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.get_duration(),
            "error": str(self.error) if self.error else None,
        }


class ProgressTracker:
    """
    Tracks progress of operations with support for multi-step processes.

    Provides comprehensive progress monitoring with event broadcasting,
    metrics collection, and flexible reporting options.
    """

    def __init__(
        self,
        operation_id: str,
        total_steps: Optional[int] = None,
        reporter: Optional[ProgressReporter] = None,
        logger_name: Optional[str] = None,
    ) -> None:
        """
        Initialize the ProgressTracker.

        Args:
            operation_id: Unique identifier for the operation
            total_steps: Total number of steps (for simple progress tracking)
            reporter: Progress reporter instance
            logger_name: Custom logger name
        """
        self.operation_id = operation_id
        self.total_steps = total_steps
        self._logger: LoggerProtocol = get_logger(logger_name or __name__)

        # Progress state
        self.status = ProgressStatus.NOT_STARTED
        self.current_step = 0
        self.overall_progress = 0.0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.error: Optional[Exception] = None

        # Multi-step support
        self._steps: List[ProgressStep] = []
        self._current_step_index = -1

        # Progress reporting
        self._reporter = reporter or LoggingProgressReporter(logger_name)

        # Event history
        self._events: List[ProgressEvent] = []

        self._logger.info(f"ProgressTracker initialized for operation: {operation_id}")

    def add_step(self, name: str, weight: float = 1.0, description: Optional[str] = None) -> None:
        """Add a step to the multi-step operation."""
        step = ProgressStep(name, weight, description)
        self._steps.append(step)
        self._logger.debug(f"Added step '{name}' with weight {weight}")

    def add_steps(self, steps: List[Union[str, Dict[str, Any]]]) -> None:
        """Add multiple steps to the operation."""
        for step in steps:
            if isinstance(step, str):
                self.add_step(step)
            else:
                name = step.get("name", "")
                weight = step.get("weight", 1.0)
                description = step.get("description")
                self.add_step(name, weight, description)

    def start(self, message: Optional[str] = None) -> None:
        """Start tracking progress."""
        self.status = ProgressStatus.IN_PROGRESS
        self.start_time = time.time()

        event_message = message or f"Started operation {self.operation_id}"
        event = ProgressEvent(
            self.operation_id,
            "operation_started",
            event_message,
            0.0,
            {"total_steps": len(self._steps) or self.total_steps},
        )

        self._add_event(event)
        self._logger.info(f"Started progress tracking: {event_message}")

    def update_progress(self, percentage: float, message: Optional[str] = None) -> None:
        """Update overall progress percentage."""
        self.overall_progress = max(0.0, min(100.0, percentage))

        event_message = message or f"Progress: {self.overall_progress:.1f}%"
        event = ProgressEvent(
            self.operation_id,
            "progress_update",
            event_message,
            self.overall_progress,
        )

        self._add_event(event)

    def start_step(self, step_name: Optional[str] = None) -> None:
        """Start the next step in a multi-step operation."""
        if not self._steps:
            raise ValueError("No steps defined for multi-step operation")

        self._current_step_index += 1

        if self._current_step_index >= len(self._steps):
            raise ValueError("All steps have already been started")

        current_step = self._steps[self._current_step_index]
        if step_name and current_step.name != step_name:
            # Find the step by name
            for i, step in enumerate(self._steps):
                if step.name == step_name:
                    self._current_step_index = i
                    current_step = step
                    break
            else:
                raise ValueError(f"Step '{step_name}' not found")

        current_step.start()
        self._update_overall_progress()

        event = ProgressEvent(
            self.operation_id,
            "step_started",
            f"Started step: {current_step.description}",
            self.overall_progress,
            {"step_name": current_step.name, "step_index": self._current_step_index},
        )

        self._add_event(event)
        self._logger.info(f"Started step: {current_step.description}")

    def update_step_progress(self, percentage: float, message: Optional[str] = None) -> None:
        """Update progress of the current step."""
        if self._current_step_index < 0 or not self._steps:
            # Fall back to simple progress update
            self.update_progress(percentage, message)
            return

        current_step = self._steps[self._current_step_index]
        current_step.update_progress(percentage)
        self._update_overall_progress()

        event_message = message or f"Step progress: {percentage:.1f}%"
        event = ProgressEvent(
            self.operation_id,
            "step_progress",
            event_message,
            self.overall_progress,
            {
                "step_name": current_step.name,
                "step_progress": percentage,
                "step_index": self._current_step_index,
            },
        )

        self._add_event(event)

    def complete_step(self, message: Optional[str] = None) -> None:
        """Mark the current step as completed."""
        if self._current_step_index < 0 or not self._steps:
            raise ValueError("No current step to complete")

        current_step = self._steps[self._current_step_index]
        current_step.complete()
        self._update_overall_progress()

        event_message = message or f"Completed step: {current_step.description}"
        event = ProgressEvent(
            self.operation_id,
            "step_completed",
            event_message,
            self.overall_progress,
            {
                "step_name": current_step.name,
                "step_index": self._current_step_index,
                "step_duration": current_step.get_duration(),
            },
        )

        self._add_event(event)
        self._logger.info(f"Completed step: {current_step.description}")

    def fail_step(self, error: Optional[Exception] = None, message: Optional[str] = None) -> None:
        """Mark the current step as failed."""
        if self._current_step_index < 0 or not self._steps:
            raise ValueError("No current step to fail")

        current_step = self._steps[self._current_step_index]
        current_step.fail(error)

        event_message = message or f"Failed step: {current_step.description}"
        if error:
            event_message += f" - {error}"

        event = ProgressEvent(
            self.operation_id,
            "step_failed",
            event_message,
            self.overall_progress,
            {
                "step_name": current_step.name,
                "step_index": self._current_step_index,
                "error": str(error) if error else None,
            },
        )

        self._add_event(event)
        self._logger.error(f"Failed step: {current_step.description} - {error}")

    def complete(self, message: Optional[str] = None) -> None:
        """Mark the operation as completed."""
        self.status = ProgressStatus.COMPLETED
        self.overall_progress = 100.0
        self.end_time = time.time()

        # Complete any remaining steps
        for step in self._steps:
            if step.status == ProgressStatus.IN_PROGRESS:
                step.complete()

        event_message = message or f"Completed operation {self.operation_id}"
        event = ProgressEvent(
            self.operation_id,
            "operation_completed",
            event_message,
            100.0,
            {"duration": self.get_duration()},
        )

        self._add_event(event)
        self._logger.info(f"Completed progress tracking: {event_message}")

    def fail(self, error: Optional[Exception] = None, message: Optional[str] = None) -> None:
        """Mark the operation as failed."""
        self.status = ProgressStatus.FAILED
        self.end_time = time.time()
        self.error = error

        event_message = message or f"Failed operation {self.operation_id}"
        if error:
            event_message += f" - {error}"

        event = ProgressEvent(
            self.operation_id,
            "operation_failed",
            event_message,
            self.overall_progress,
            {
                "duration": self.get_duration(),
                "error": str(error) if error else None,
            },
        )

        self._add_event(event)
        self._logger.error(f"Failed progress tracking: {event_message}")

    def cancel(self, message: Optional[str] = None) -> None:
        """Mark the operation as cancelled."""
        self.status = ProgressStatus.CANCELLED
        self.end_time = time.time()

        # Cancel any in-progress steps
        for step in self._steps:
            if step.status == ProgressStatus.IN_PROGRESS:
                step.cancel()

        event_message = message or f"Cancelled operation {self.operation_id}"
        event = ProgressEvent(
            self.operation_id,
            "operation_cancelled",
            event_message,
            self.overall_progress,
            {"duration": self.get_duration()},
        )

        self._add_event(event)
        self._logger.info(f"Cancelled progress tracking: {event_message}")

    def _update_overall_progress(self) -> None:
        """Update overall progress based on step progress."""
        if not self._steps:
            return

        total_weight = sum(step.weight for step in self._steps)
        completed_weight = 0.0

        for step in self._steps:
            if step.status == ProgressStatus.COMPLETED:
                completed_weight += step.weight
            elif step.status == ProgressStatus.IN_PROGRESS:
                completed_weight += step.weight * (step.progress_percentage / 100.0)

        self.overall_progress = (completed_weight / total_weight) * 100.0 if total_weight > 0 else 0.0

    def _add_event(self, event: ProgressEvent) -> None:
        """Add an event to the history and report it."""
        self._events.append(event)
        self._reporter.report_progress(event)

    def get_duration(self) -> Optional[float]:
        """Get the duration of the operation."""
        if self.start_time is None:
            return None
        end_time = self.end_time or time.time()
        return end_time - self.start_time

    def get_estimated_time_remaining(self) -> Optional[float]:
        """Estimate time remaining based on current progress."""
        if self.start_time is None or self.overall_progress <= 0:
            return None

        elapsed_time = time.time() - self.start_time
        estimated_total_time = elapsed_time / (self.overall_progress / 100.0)
        return max(0.0, estimated_total_time - elapsed_time)

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status information."""
        return {
            "operation_id": self.operation_id,
            "status": self.status.value,
            "overall_progress": self.overall_progress,
            "current_step": self._current_step_index + 1 if self._current_step_index >= 0 else None,
            "total_steps": len(self._steps) or self.total_steps,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.get_duration(),
            "estimated_time_remaining": self.get_estimated_time_remaining(),
            "error": str(self.error) if self.error else None,
            "steps": [step.to_dict() for step in self._steps],
        }

    def get_events(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get progress events history."""
        events = self._events
        if limit is not None:
            events = events[-limit:]
        return [event.to_dict() for event in events]

    def __enter__(self) -> "ProgressTracker":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        if exc_type is not None:
            self.fail(exc_val, "Operation failed with exception")
        elif self.status == ProgressStatus.IN_PROGRESS:
            self.complete()


# Convenience functions
def track_simple_progress(
    operation_id: str,
    total_steps: int,
    reporter: Optional[ProgressReporter] = None,
) -> ProgressTracker:
    """Create a progress tracker for simple step-based operations."""
    return ProgressTracker(operation_id, total_steps, reporter)


def track_multi_step_progress(
    operation_id: str,
    steps: List[Union[str, Dict[str, Any]]],
    reporter: Optional[ProgressReporter] = None,
) -> ProgressTracker:
    """Create a progress tracker for multi-step operations."""
    tracker = ProgressTracker(operation_id, reporter=reporter)
    tracker.add_steps(steps)
    return tracker
