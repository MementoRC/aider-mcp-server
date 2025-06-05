"""Session Coordination Module for Aider Operations.

This module handles session lifecycle management, event broadcasting,
and coordination between different components during aider sessions.
"""

import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.event_types import EventTypes
from aider_mcp_server.atoms.types.streaming_types import AiderChangesSummary, ChangeType, FileChangesSummary
from aider_mcp_server.molecules.monitoring.request_monitor import RequestMonitor

if TYPE_CHECKING:
    from aider_mcp_server.interfaces.application_coordinator import IApplicationCoordinator

logger = get_logger(__name__)


class SessionCoordinator:
    """Manages session lifecycle and event coordination for aider operations."""

    def __init__(self, coordinator: Optional["IApplicationCoordinator"] = None):
        """Initialize the session coordinator.

        Args:
            coordinator: Application coordinator for event broadcasting
        """
        self.coordinator = coordinator
        self.request_monitor: Optional[RequestMonitor] = None
        self.current_request_id: Optional[str] = None

        if coordinator:
            self.request_monitor = RequestMonitor(coordinator)

    async def start_session(
        self,
        ai_coding_prompt: str,
        relative_editable_files: List[str],
        relative_readonly_files: Optional[List[str]],
        original_model: str,
        working_dir: str,
        architect_mode: bool,
    ) -> Optional[str]:
        """Start a new aider session and broadcast the session start event.

        Args:
            ai_coding_prompt: The coding prompt for this session
            relative_editable_files: List of files that can be edited
            relative_readonly_files: List of read-only context files
            original_model: The AI model being used
            working_dir: Working directory for the session
            architect_mode: Whether architect mode is enabled

        Returns:
            Request ID if monitoring is enabled, None otherwise
        """
        # Initialize request monitoring
        request_id = None
        if self.request_monitor:
            request_context = {
                "model": original_model,
                "provider": original_model.split("/")[0] if "/" in original_model else "unknown",
                "editable_files": len(relative_editable_files),
                "readonly_files": len(relative_readonly_files) if relative_readonly_files else 0,
                "architect_mode": architect_mode,
                "working_dir": working_dir,
            }
            request_id = await self.request_monitor.track_request(context=request_context)
            self.current_request_id = request_id

        # Broadcast session start event
        await self._broadcast_session_start(
            ai_coding_prompt,
            relative_editable_files,
            relative_readonly_files,
            original_model,
            working_dir,
            architect_mode,
        )

        return request_id

    async def update_progress(self, stage: str, model: str, files_count: int) -> None:
        """Update session progress.

        Args:
            stage: Current stage of processing
            model: Model being used
            files_count: Number of files being processed
        """
        if self.request_monitor and self.current_request_id:
            await self.request_monitor.update_request_progress(
                self.current_request_id,
                {
                    "stage": stage,
                    "model": model,
                    "files_count": files_count,
                },
            )

    async def complete_session(
        self,
        response: Dict[str, Any],
        actual_model_used: str,
        original_model: str,
        relative_editable_files: List[str],
        success: bool = True,
    ) -> None:
        """Complete a session and broadcast completion events.

        Args:
            response: Response data from aider execution
            actual_model_used: The model that was actually used
            original_model: The originally requested model
            relative_editable_files: List of editable files
            success: Whether the session completed successfully
        """
        # Broadcast session completion event
        await self._broadcast_session_completed(response, actual_model_used, original_model)

        # Broadcast changes summary if successful
        if success and response.get("success", False):
            session_id = f"aider_{int(time.time() * 1000)}"
            await self._broadcast_changes_summary(response, session_id, relative_editable_files)

        # Complete request monitoring
        if self.request_monitor and self.current_request_id:
            result_data = {
                "success": success,
                "actual_model": actual_model_used,
                "files_changed": len(response.get("changes_summary", {}).get("files", [])),
                "rate_limit_encountered": bool(response.get("rate_limit_info")),
            }
            await self.request_monitor.complete_request(self.current_request_id, success=success, result=result_data)
            self.current_request_id = None

    async def handle_session_error(self, error: Exception) -> None:
        """Handle session errors and ensure proper cleanup.

        Args:
            error: The exception that occurred
        """
        # Complete request monitoring with error
        if self.request_monitor and self.current_request_id:
            error_result = {
                "success": False,
                "error": str(error),
                "error_type": type(error).__name__,
            }
            await self.request_monitor.complete_request(self.current_request_id, success=False, result=error_result)
            self.current_request_id = None

    async def broadcast_rate_limit_event(
        self,
        provider: str,
        current_model: str,
        fallback_model: Optional[str],
        attempt: int,
        max_retries: int,
        estimated_delay: float,
        error_message: str,
        will_retry: bool,
    ) -> None:
        """Broadcast a rate limit detection event.

        Args:
            provider: The AI provider that hit the rate limit
            current_model: Current model being used
            fallback_model: Fallback model to use
            attempt: Current retry attempt
            max_retries: Maximum retries allowed
            estimated_delay: Estimated delay before retry
            error_message: Error message from the rate limit
            will_retry: Whether another retry will be attempted
        """
        if not self.coordinator:
            return

        try:
            await self.coordinator.broadcast_event(
                EventTypes.AIDER_RATE_LIMIT_DETECTED,
                {
                    "provider": provider,
                    "current_model": current_model,
                    "fallback_model": fallback_model,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "estimated_delay": estimated_delay,
                    "error_message": error_message,
                    "timestamp": time.time(),
                    "will_retry": will_retry,
                },
            )
            logger.info("Broadcasted aider.rate_limit_detected event")
        except Exception as broadcast_error:
            logger.warning(f"Failed to broadcast rate_limit_detected event: {broadcast_error}")

    async def _broadcast_session_start(
        self,
        ai_coding_prompt: str,
        relative_editable_files: List[str],
        relative_readonly_files: Optional[List[str]],
        original_model: str,
        working_dir: str,
        architect_mode: bool,
    ) -> None:
        """Helper function to broadcast session start event."""
        if not self.coordinator:
            return

        try:
            await self.coordinator.broadcast_event(
                EventTypes.AIDER_SESSION_STARTED,
                {
                    "prompt": ai_coding_prompt[:100] + "..." if len(ai_coding_prompt) > 100 else ai_coding_prompt,
                    "editable_files": relative_editable_files,
                    "readonly_files": relative_readonly_files,
                    "model": original_model,
                    "working_dir": working_dir,
                    "architect_mode": architect_mode,
                    "timestamp": time.time(),
                },
            )
            logger.info("Broadcasted aider.session_started event")
        except Exception as e:
            logger.warning(f"Failed to broadcast session_started event: {e}")

    async def _broadcast_session_completed(
        self, response: Dict[str, Any], actual_model_used: str, original_model: str
    ) -> None:
        """Helper function to broadcast session completed event."""
        if not self.coordinator:
            return

        try:
            await self.coordinator.broadcast_event(
                EventTypes.AIDER_SESSION_COMPLETED,
                {
                    "success": response.get("success", False),
                    "changes_detected": response.get("success", False),
                    "changes_summary": response.get("changes_summary", {}),
                    "model_used": actual_model_used,
                    "original_model": original_model,
                    "rate_limit_encountered": _get_rate_limit_encountered(response),
                    "fallback_used": _get_fallback_used(response),
                    "timestamp": time.time(),
                },
            )
            logger.info("Broadcasted aider.session_completed event")
        except Exception as e:
            logger.warning(f"Failed to broadcast session_completed event: {e}")

    async def _broadcast_changes_summary(
        self, response: Dict[str, Any], session_id: str, relative_editable_files: List[str]
    ) -> None:
        """
        Phase 1.3: Broadcast lightweight changes summary without full diffs.
        Converts existing changes_summary to structured streaming format.
        """
        if not self.coordinator:
            return

        try:
            changes_summary = response.get("changes_summary", {})

            # Generate session ID if not provided
            if not session_id:
                session_id = f"aider_{int(time.time() * 1000)}"

            # Extract file summaries and statistics
            file_summaries = _extract_file_summaries(changes_summary)
            stats = changes_summary.get("stats", {})
            total_lines_added = stats.get("lines_added", 0) if isinstance(stats, dict) else 0
            total_lines_removed = stats.get("lines_removed", 0) if isinstance(stats, dict) else 0
            total_files_changed = len(file_summaries)

            # Count file operation types
            files_created = sum(1 for f in file_summaries if f["change_type"] == ChangeType.CREATED.value)
            files_modified = sum(1 for f in file_summaries if f["change_type"] == ChangeType.MODIFIED.value)
            files_deleted = sum(1 for f in file_summaries if f["change_type"] == ChangeType.DELETED.value)

            # Analyze change characteristics
            change_categories = _determine_change_categories(changes_summary.get("summary", ""))
            estimated_complexity = _estimate_complexity(total_files_changed, total_lines_added, total_lines_removed)

            # Create and broadcast Phase 1.3 changes summary
            aider_changes_summary: AiderChangesSummary = {
                "session_id": session_id,
                "timestamp": time.time(),
                "total_files_changed": total_files_changed,
                "files_created": files_created,
                "files_modified": files_modified,
                "files_deleted": files_deleted,
                "total_lines_added": total_lines_added,
                "total_lines_removed": total_lines_removed,
                "file_summaries": file_summaries,
                "change_categories": change_categories,
                "estimated_complexity": estimated_complexity,
            }

            await self.coordinator.broadcast_event(EventTypes.AIDER_CHANGES_SUMMARY, dict(aider_changes_summary))
            logger.info(f"Broadcasted aider.changes_summary event for {total_files_changed} files")

        except Exception as e:
            logger.warning(f"Failed to broadcast changes_summary event: {e}")


def _get_rate_limit_encountered(response: Union[Dict[str, Any], Dict[str, Any]]) -> bool:
    """Helper function to safely extract rate limit encountered status."""
    rate_limit_info = response.get("rate_limit_info")
    if rate_limit_info is None or not isinstance(rate_limit_info, dict):
        return False
    return bool(rate_limit_info.get("encountered", False))


def _get_fallback_used(response: Union[Dict[str, Any], Dict[str, Any]]) -> bool:
    """Helper function to safely extract fallback used status."""
    rate_limit_info = response.get("rate_limit_info")
    if rate_limit_info is None or not isinstance(rate_limit_info, dict):
        return False
    return bool(rate_limit_info.get("fallback_model"))


def _extract_file_summaries(changes_summary: Dict[str, Any]) -> List[FileChangesSummary]:
    """Extract file summaries from changes_summary data."""
    file_summaries: List[FileChangesSummary] = []
    changes_files = changes_summary.get("files", [])

    if isinstance(changes_files, list):
        for file_info in changes_files:
            if isinstance(file_info, dict):
                file_path = file_info.get("name", "unknown")
                operation = file_info.get("operation", "modified")

                # Map operation to ChangeType
                change_type = ChangeType.MODIFIED.value
                if operation in ["created", "added"]:
                    change_type = ChangeType.CREATED.value
                elif operation in ["deleted", "removed"]:
                    change_type = ChangeType.DELETED.value
                elif operation in ["renamed", "moved"]:
                    change_type = ChangeType.RENAMED.value

                file_summary: FileChangesSummary = {
                    "file_path": file_path,
                    "change_type": change_type,
                    "lines_added": 0,
                    "lines_removed": 0,
                    "lines_modified": 0,
                    "change_description": f"{operation.title()} {file_path}",
                    "estimated_impact": "medium",
                }
                file_summaries.append(file_summary)

    return file_summaries


def _determine_change_categories(summary_text: str) -> List[str]:
    """Determine change categories based on summary text content."""
    change_categories = []
    summary_lower = summary_text.lower()

    if any(word in summary_lower for word in ["fix", "bug", "error"]):
        change_categories.append("bug_fix")
    if any(word in summary_lower for word in ["add", "new", "feature"]):
        change_categories.append("feature_addition")
    if any(word in summary_lower for word in ["refactor", "cleanup", "reorganize"]):
        change_categories.append("refactoring")
    if any(word in summary_lower for word in ["test", "spec"]):
        change_categories.append("testing")

    return change_categories if change_categories else ["general_update"]


def _estimate_complexity(total_files_changed: int, total_lines_added: int, total_lines_removed: int) -> str:
    """Estimate complexity based on files and lines changed."""
    total_lines_changed = total_lines_added + total_lines_removed

    if total_files_changed > 10 or total_lines_changed > 300:
        return "complex"
    elif total_files_changed > 5 or total_lines_changed > 100:
        return "moderate"
    else:
        return "simple"
