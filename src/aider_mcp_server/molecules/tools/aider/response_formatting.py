"""
Response formatting module for Aider AI operations.

This module provides comprehensive response processing functionality including:
- Response structure definition and validation
- Data transformation and aggregation
- Event broadcasting for streaming support
- Response finalization and cleanup
- API key and provider status management
- Diff cache integration support
"""

from typing import Any, Dict, List, Optional, Union

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.event_types import EventTypes
from aider_mcp_server.atoms.types.streaming_types import AiderChangesSummary, ChangeType, FileChangesSummary
from aider_mcp_server.atoms.utils.diff_cache import DiffCache
from aider_mcp_server.molecules.tools.changes_summarizer import get_file_status_summary, summarize_changes

from .shared.types import ResponseDict

logger = get_logger(__name__)


class ResponseFormatter:
    """Handles processing and formatting of Aider AI responses."""

    def __init__(self, event_coordinator: Optional[Any] = None) -> None:
        """Initialize the ResponseFormatter with optional event coordinator for broadcasting."""
        self.event_coordinator = event_coordinator
        self.logger = logger

    def process_coder_results(
        self,
        coder_exit_code: int,
        diff_output: str,
        working_directory: str,
        diff_cache: Optional[DiffCache] = None,
        include_diff: bool = True,
        rate_limit_info: Optional[Dict[str, Union[bool, int, str, None]]] = None,
    ) -> ResponseDict:
        """
        Main orchestrator for processing results after Aider execution.

        Args:
            coder_exit_code: Exit code from the Aider coder process
            diff_output: Raw diff output from git or filesystem
            working_directory: Working directory path
            diff_cache: Optional diff cache for processing
            include_diff: Whether to include diff in response
            rate_limit_info: Rate limiting information

        Returns:
            ResponseDict: Structured response with all processing results
        """
        # Process diff cache and get final diff content
        final_diff, is_cached_diff = self.handle_diff_cache_processing(diff_output, diff_cache, working_directory)

        # Generate changes summary
        changes_summary = summarize_changes(final_diff)

        # Get file status
        file_status = get_file_status_summary([], working_directory)

        # Update summary with file status if needed
        self.update_summary_from_file_status(changes_summary, file_status)

        # Determine overall success
        success = coder_exit_code == 0 and bool(changes_summary.get("files", []))

        # Create response structure
        response: ResponseDict = {
            "success": success,
            "changes_summary": changes_summary,
            "file_status": file_status,
            "rate_limit_info": rate_limit_info or {},
            "is_cached_diff": is_cached_diff,
            "diff": "",
            "api_key_status": {},
        }

        # Finalize diff field
        self.finalize_response_diff_field(response, final_diff, include_diff)

        return response

    def handle_diff_cache_processing(
        self, diff_output: str, diff_cache: Optional[DiffCache], working_directory: str
    ) -> tuple[str, bool]:
        """
        Handle diff cache logic and return final diff content.

        Args:
            diff_output: Raw diff output
            diff_cache: Optional diff cache instance
            working_directory: Working directory path

        Returns:
            tuple: (final_diff_content, is_cached_diff)
        """
        if not diff_cache:
            return diff_output, False

        try:
            # Process through diff cache - simplified interface
            if hasattr(diff_cache, "get_cached_diff"):
                cached_diff = diff_cache.get_cached_diff(diff_output)
                if cached_diff:
                    return cached_diff, True
            return diff_output, False
        except Exception as e:
            self.logger.warning(f"Diff cache processing failed: {e}")
            return diff_output, False

    def update_summary_from_file_status(self, changes_summary: Dict[str, Any], file_status: Dict[str, Any]) -> None:
        """
        Update changes_summary with file_status information when needed.

        Args:
            changes_summary: Changes summary to update
            file_status: File status information
        """
        if not changes_summary.get("files") and file_status.get("files"):
            # If no files in changes_summary but files in file_status, merge them
            changes_summary["files"] = file_status["files"]

            # Update stats from file_status
            if file_status.get("stats"):
                if "stats" not in changes_summary:
                    changes_summary["stats"] = {}
                changes_summary["stats"].update(file_status["stats"])

    def finalize_response_diff_field(self, response: ResponseDict, final_diff: str, include_diff: bool) -> None:
        """
        Set the 'diff' field for backward compatibility.

        Args:
            response: Response dictionary to update
            final_diff: Final diff content
            include_diff: Whether to include diff in response
        """
        if include_diff:
            if final_diff:
                response["diff"] = final_diff
            elif not response["success"]:
                # Include error information in diff field for failed operations
                response["diff"] = "No changes were made."

    def broadcast_changes_summary(self, changes_summary: Dict[str, Any], request_id: Optional[str] = None) -> None:
        """
        Phase 1.3 lightweight changes summary broadcasting.

        Args:
            changes_summary: Changes summary data
            request_id: Optional request identifier
        """
        if not self.event_coordinator:
            return

        try:
            # Extract file summaries
            file_summaries = self.extract_file_summaries(changes_summary)

            # Determine change categories
            categories = self.determine_change_categories(changes_summary)

            # Estimate complexity
            complexity = self.estimate_complexity(changes_summary)

            # Create structured summary
            aider_summary: AiderChangesSummary = {
                "session_id": request_id or "unknown",
                "timestamp": 0.0,  # Will be set by event coordinator
                "total_files_changed": len(file_summaries),
                "files_created": len([f for f in file_summaries if f["change_type"] == "created"]),
                "files_modified": len([f for f in file_summaries if f["change_type"] == "modified"]),
                "files_deleted": len([f for f in file_summaries if f["change_type"] == "deleted"]),
                "total_lines_added": changes_summary.get("stats", {}).get("lines_added", 0),
                "total_lines_removed": changes_summary.get("stats", {}).get("lines_removed", 0),
                "file_summaries": file_summaries,
                "change_categories": categories,
                "estimated_complexity": complexity,
            }

            # Broadcast the event
            self.event_coordinator.broadcast_event(
                EventTypes.AIDER_CHANGES_SUMMARY,
                {
                    "request_id": request_id,
                    "changes_summary": aider_summary,
                    "timestamp": None,  # Will be set by event coordinator
                },
            )
        except Exception as e:
            self.logger.error(f"Failed to broadcast changes summary: {e}")

    def extract_file_summaries(self, changes_summary: Dict[str, Any]) -> List[FileChangesSummary]:
        """
        Extract file summaries from changes_summary data.

        Args:
            changes_summary: Changes summary data

        Returns:
            List of FileChangesSummary objects
        """
        file_summaries = []

        for file_info in changes_summary.get("files", []):
            # Map operation to ChangeType
            operation = file_info.get("operation", "modified")
            change_type = self._map_operation_to_change_type(operation)

            # Estimate impact
            lines_changed = file_info.get("lines_added", 0) + file_info.get("lines_removed", 0)
            impact = "low" if lines_changed < 10 else "medium" if lines_changed < 50 else "high"

            summary: FileChangesSummary = {
                "file_path": file_info.get("name", ""),
                "change_type": change_type.value,
                "lines_added": file_info.get("lines_added", 0),
                "lines_removed": file_info.get("lines_removed", 0),
                "lines_modified": file_info.get("lines_modified", 0),
                "change_description": f"{change_type.value} file",
                "estimated_impact": impact,
            }
            file_summaries.append(summary)

        return file_summaries

    def _map_operation_to_change_type(self, operation: str) -> ChangeType:
        """Map file operation to ChangeType enum."""
        operation_map = {
            "create": ChangeType.CREATED,
            "modify": ChangeType.MODIFIED,
            "delete": ChangeType.DELETED,
            "rename": ChangeType.RENAMED,
        }
        return operation_map.get(operation, ChangeType.MODIFIED)

    def determine_change_categories(self, changes_summary: Dict[str, Any]) -> List[str]:
        """
        Categorize changes based on summary text content.

        Args:
            changes_summary: Changes summary data

        Returns:
            List of change categories
        """
        categories = []
        summary_text = changes_summary.get("summary", "").lower()

        if any(keyword in summary_text for keyword in ["fix", "bug", "error", "issue"]):
            categories.append("bug_fix")
        if any(keyword in summary_text for keyword in ["add", "new", "create", "implement"]):
            categories.append("feature_addition")
        if any(keyword in summary_text for keyword in ["refactor", "restructure", "reorganize"]):
            categories.append("refactoring")
        if any(keyword in summary_text for keyword in ["test", "spec", "coverage"]):
            categories.append("testing")
        if any(keyword in summary_text for keyword in ["doc", "comment", "readme"]):
            categories.append("documentation")

        return categories if categories else ["general"]

    def estimate_complexity(self, changes_summary: Dict[str, Any]) -> str:
        """
        Estimate complexity based on files and lines changed.

        Args:
            changes_summary: Changes summary data

        Returns:
            Complexity level string
        """
        files_changed = len(changes_summary.get("files", []))
        lines_changed = changes_summary.get("stats", {}).get("lines_added", 0) + changes_summary.get("stats", {}).get(
            "lines_removed", 0
        )

        if files_changed <= 2 and lines_changed <= 20:
            return "simple"
        elif files_changed <= 5 and lines_changed <= 100:
            return "moderate"
        else:
            return "complex"

    def finalize_aider_response(
        self,
        response: ResponseDict,
        api_key_status: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None,
        include_diff: bool = True,
    ) -> ResponseDict:
        """
        Final response preparation with all metadata.

        Args:
            response: Response dictionary to finalize
            api_key_status: API key status information
            warnings: List of warning messages
            include_diff: Whether to include diff field

        Returns:
            Finalized ResponseDict
        """
        # Update API key status
        if api_key_status:
            self.update_api_key_status_in_response(response, api_key_status)

        # Add provider warnings (store in a custom way since ResponseDict doesn't have warnings)
        if warnings:
            # For now, we'll add warnings to the changes_summary as they're not in the base ResponseDict
            if "warnings" not in response["changes_summary"]:
                response["changes_summary"]["warnings"] = []
            response["changes_summary"]["warnings"].extend(warnings)

        # Handle diff field inclusion/exclusion
        self.handle_diff_field_in_response(response, include_diff)

        # Cleanup response fields
        self.cleanup_file_status_in_response(response)
        self.cleanup_changes_summary_in_response(response)

        return response

    def handle_diff_field_in_response(self, response: ResponseDict, include_diff: bool) -> None:
        """
        Manage diff field presence based on configuration.

        Args:
            response: Response dictionary to update
            include_diff: Whether to include diff field
        """
        if not include_diff and response.get("success"):
            # Remove diff field for successful operations when not requested
            response["diff"] = ""
        elif response.get("diff") == "" and not response.get("success"):
            # Ensure diff field has error content for failed operations
            response["diff"] = "Operation failed - no changes made."

    def cleanup_file_status_in_response(self, response: ResponseDict) -> None:
        """
        Clean up file_status field by removing empty/zero values.

        Args:
            response: Response dictionary to clean up
        """
        file_status = response.get("file_status", {})
        if isinstance(file_status, dict):
            # Remove empty files list
            if file_status.get("files") == []:
                file_status.pop("files", None)

            # Clean up stats with zero values
            stats = file_status.get("stats", {})
            if isinstance(stats, dict):
                cleaned_stats = {k: v for k, v in stats.items() if v != 0}
                if cleaned_stats:
                    file_status["stats"] = cleaned_stats
                else:
                    file_status.pop("stats", None)

    def cleanup_changes_summary_in_response(self, response: ResponseDict) -> None:
        """
        Clean up changes_summary field by removing empty stats and files.

        Args:
            response: Response dictionary to clean up
        """
        changes_summary = response.get("changes_summary", {})
        if isinstance(changes_summary, dict):
            # Remove empty files list
            if changes_summary.get("files") == []:
                changes_summary.pop("files", None)

            # Clean up stats with zero values
            stats = changes_summary.get("stats", {})
            if isinstance(stats, dict):
                cleaned_stats = {k: v for k, v in stats.items() if v != 0}
                if cleaned_stats:
                    changes_summary["stats"] = cleaned_stats
                else:
                    changes_summary.pop("stats", None)

    def update_api_key_status_in_response(self, response: ResponseDict, api_key_status: Dict[str, Any]) -> None:
        """
        Update API key status information in response.

        Args:
            response: Response dictionary to update
            api_key_status: API key status information
        """
        response["api_key_status"] = {
            "available_providers": api_key_status.get("available_providers", []),
            "missing_providers": api_key_status.get("missing_providers", []),
            "requested_provider": api_key_status.get("requested_provider"),
            "used_provider": api_key_status.get("used_provider"),
            "original_model_requested": api_key_status.get("original_model_requested"),
            "actual_model_used": api_key_status.get("actual_model_used"),
        }

    def add_provider_warning_to_response(self, response: ResponseDict, warnings: List[str]) -> None:
        """
        Add warnings when requested provider keys are missing.

        Args:
            response: Response dictionary to update
            warnings: List of warning messages
        """
        if warnings:
            # Store warnings in changes_summary since ResponseDict doesn't have warnings field
            if "warnings" not in response["changes_summary"]:
                response["changes_summary"]["warnings"] = []
            response["changes_summary"]["warnings"].extend(warnings)

    def get_rate_limit_encountered(self, response: ResponseDict) -> bool:
        """
        Safely extract rate limit status from response.

        Args:
            response: Response dictionary

        Returns:
            Whether rate limit was encountered
        """
        return bool(response.get("rate_limit_info", {}).get("encountered", False))

    def get_fallback_used(self, response: ResponseDict) -> bool:
        """
        Safely extract fallback usage status from response.

        Args:
            response: Response dictionary

        Returns:
            Whether fallback was used
        """
        rate_limit_info = response.get("rate_limit_info", {})
        return bool(rate_limit_info and rate_limit_info.get("fallback_model"))
