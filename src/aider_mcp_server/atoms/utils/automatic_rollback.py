"""
Automatic Rollback Mechanism for Aider Safety Operations.

Provides comprehensive automatic rollback capabilities that integrate with existing
safety infrastructure to restore files to their previous state when failures are detected.

Features:
- Git reset integration for full repository rollback
- Selective file restoration for targeted recovery
- Rich user notification with failure analysis
- Comprehensive rollback logging for audit trail
- Integration with GitCheckpointManager, FailureDetector, and GitDiffAnalyzer
- Support for both automatic and manual rollback scenarios

Author: Aider MCP Server Team
"""

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.utils.failure_detector import FailureDetectionResult
from aider_mcp_server.atoms.utils.git_diff_analyzer import DiffAnalysisResult

logger = get_logger(__name__)


class AutomaticRollbackError(Exception):
    """Base exception for automatic rollback operations."""

    pass


class RollbackExecutionError(AutomaticRollbackError):
    """Raised when rollback execution fails."""

    def __init__(self, message: str, output: Optional[str] = None):
        super().__init__(message)
        self.output = output


class InvalidCheckpointError(AutomaticRollbackError):
    """Raised when the checkpoint reference is invalid."""

    pass


@dataclass
class RollbackLogEntry:
    """Represents a detailed log entry for a rollback operation."""

    timestamp: str
    operation_id: str
    checkpoint_id: str
    rollback_type: str  # "full" or "selective"
    triggers: List[Dict[str, Any]]
    affected_files: List[str]
    git_commands_executed: List[str]
    success: bool
    error_message: Optional[str] = None
    git_output: Optional[str] = None
    file_results: Optional[Dict[str, str]] = None
    user_notification: Optional[str] = None
    recovery_suggestions: Optional[List[str]] = None


@dataclass
class RollbackResult:
    """Complete result of an automatic rollback operation."""

    success: bool
    rollback_type: str
    checkpoint_id: str
    affected_files: List[str]
    notification_message: str
    log_entry: RollbackLogEntry
    recovery_suggestions: List[str]
    git_commands_executed: List[str]
    error_details: Optional[str] = None

    def should_escalate(self) -> bool:
        """Determine if this rollback failure requires manual intervention."""
        return not self.success


class AutomaticRollbackManager:
    """
    Manages automatic rollback operations for Aider safety operations.

    Integrates with existing safety systems to perform comprehensive rollback
    when failures are detected, with support for both full repository rollback
    and selective file restoration.

    Usage:
        manager = AutomaticRollbackManager(repo_path)
        result = manager.perform_rollback(
            checkpoint_id="abc123",
            failure_detection=failure_result,
            operation_id="edit456"
        )
        if not result.success:
            # Handle rollback failure
            print(result.notification_message)
    """

    def __init__(
        self,
        repo_path: str,
        enable_selective_rollback: bool = True,
        require_confirmation: bool = False,
        max_affected_files_for_selective: int = 10,
    ):
        """
        Initialize the automatic rollback manager.

        Args:
            repo_path: Path to the git repository
            enable_selective_rollback: Enable selective file restoration when possible
            require_confirmation: Require user confirmation before rollback (for manual use)
            max_affected_files_for_selective: Max files for selective rollback before going full
        """
        self.repo_path = os.path.abspath(repo_path)
        self.enable_selective_rollback = enable_selective_rollback
        self.require_confirmation = require_confirmation
        self.max_affected_files_for_selective = max_affected_files_for_selective

        if not self._is_git_repo():
            logger.error(f"Not a git repository: {self.repo_path}")
            raise AutomaticRollbackError(f"Not a git repository: {self.repo_path}")

        logger.info(
            f"Initialized AutomaticRollbackManager for {repo_path} "
            f"(selective={enable_selective_rollback}, max_files={max_affected_files_for_selective})"
        )

    def _is_git_repo(self) -> bool:
        """Check if the current directory is a git repository (supports worktrees)."""
        try:
            subprocess.run(["git", "rev-parse", "--git-dir"], cwd=self.repo_path, capture_output=True, check=True)  # noqa: S603,S607
            logger.debug(f"Checking if {self.repo_path} is a git repo: True")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.debug(f"Checking if {self.repo_path} is a git repo: False")
            return False

    def _run_git(self, args: List[str], capture_output: bool = True) -> str:
        """
        Run a git command in the repository.

        Args:
            args: List of git command arguments.
            capture_output: If True, return stdout.

        Returns:
            Output of the command if capture_output is True, else empty string.

        Raises:
            RollbackExecutionError: If the git command fails.
        """
        cmd = ["git"] + args
        try:
            logger.debug(f"Running git command: {' '.join(cmd)}")
            result = subprocess.run(  # noqa: S603
                cmd,
                cwd=self.repo_path,
                check=True,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                encoding="utf-8",
            )
            if capture_output:
                logger.verbose(f"Git output length: {len(result.stdout)} chars")
                return result.stdout
            return ""
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {' '.join(cmd)}\n{e.stderr}")
            raise RollbackExecutionError(f"Git command failed: {' '.join(cmd)}", output=e.stderr) from e
        except Exception as e:
            logger.error(f"Unexpected error running git command: {' '.join(cmd)}\n{e}")
            raise RollbackExecutionError(f"Unexpected error running git command: {' '.join(cmd)}", output=str(e)) from e

    def _validate_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Validate that a checkpoint ID exists and is valid.

        Args:
            checkpoint_id: Git commit hash or reference to validate

        Returns:
            True if the checkpoint is valid, False otherwise.
        """
        try:
            self._run_git(["rev-parse", "--verify", f"{checkpoint_id}^{{commit}}"])
            return True
        except RollbackExecutionError:
            return False

    def _determine_rollback_strategy(
        self,
        failure_detection: FailureDetectionResult,
        diff_analysis: Optional[DiffAnalysisResult] = None,
    ) -> tuple[str, List[str]]:
        """
        Determine whether to perform full or selective rollback.

        Args:
            failure_detection: Results from FailureDetector
            diff_analysis: Optional results from GitDiffAnalyzer

        Returns:
            Tuple of (rollback_type, affected_files)
        """
        if not self.enable_selective_rollback:
            return ("full", [])

        # Collect affected files from failure triggers
        affected_files = set()
        for trigger in failure_detection.triggers:
            affected_files.update(trigger.affected_files)

        # Add files from diff analysis if available
        if diff_analysis:
            affected_files.update(diff_analysis.selective_rollback_files)

        affected_files_list = list(affected_files)

        # Determine strategy based on number of files and severity
        critical_failures = [t for t in failure_detection.triggers if t.severity.value == "critical"]

        if (
            len(affected_files_list) <= self.max_affected_files_for_selective
            and len(critical_failures) <= 2
            and all(f for f in affected_files_list)  # No empty filenames
        ):
            logger.info(f"Using selective rollback for {len(affected_files_list)} files")
            return ("selective", affected_files_list)
        else:
            logger.info(
                f"Using full rollback due to scope ({len(affected_files_list)} files, {len(critical_failures)} critical)"
            )
            return ("full", affected_files_list)

    def _perform_full_rollback(self, checkpoint_id: str) -> tuple[List[str], str]:
        """
        Perform full repository rollback using git reset --hard.

        Args:
            checkpoint_id: Checkpoint to rollback to

        Returns:
            Tuple of (commands_executed, git_output)
        """
        commands_executed = []
        git_output_parts = []

        try:
            # Stash any uncommitted changes first
            stash_cmd = ["stash", "push", "-u", "-m", "Pre-rollback safety stash"]
            try:
                stash_output = self._run_git(stash_cmd)
                commands_executed.append(f"git {' '.join(stash_cmd)}")
                git_output_parts.append(f"Stash output: {stash_output}")
                logger.info("Created safety stash before rollback")
            except RollbackExecutionError as e:
                # If stash fails (e.g., nothing to stash), continue with rollback
                logger.warning(f"Stash failed (likely nothing to stash): {e}")

            # Perform hard reset to checkpoint
            reset_cmd = ["reset", "--hard", checkpoint_id]
            reset_output = self._run_git(reset_cmd)
            commands_executed.append(f"git {' '.join(reset_cmd)}")
            git_output_parts.append(f"Reset output: {reset_output}")

            logger.info(f"Successfully performed full rollback to {checkpoint_id}")
            return commands_executed, "\n".join(git_output_parts)

        except RollbackExecutionError as e:
            logger.error(f"Full rollback failed: {e}")
            raise

    def _perform_selective_rollback(
        self, checkpoint_id: str, affected_files: List[str]
    ) -> tuple[List[str], Dict[str, str]]:
        """
        Perform selective file restoration.

        Args:
            checkpoint_id: Checkpoint to rollback to
            affected_files: List of files to restore

        Returns:
            Tuple of (commands_executed, file_results)
        """
        commands_executed = []
        file_results = {}

        for file_path in affected_files:
            try:
                checkout_cmd = ["checkout", checkpoint_id, "--", file_path]
                output = self._run_git(checkout_cmd)
                commands_executed.append(f"git {' '.join(checkout_cmd)}")
                file_results[file_path] = f"SUCCESS: {output}" if output else "SUCCESS: File restored"
                logger.debug(f"Successfully restored {file_path}")
            except RollbackExecutionError as e:
                error_msg = f"FAILED: {e}"
                file_results[file_path] = error_msg
                commands_executed.append(f"git {' '.join(checkout_cmd)} # FAILED")
                logger.error(f"Failed to restore {file_path}: {e}")

        successful_restores = [f for f, result in file_results.items() if result.startswith("SUCCESS")]
        logger.info(f"Selective rollback completed: {len(successful_restores)}/{len(affected_files)} files restored")

        return commands_executed, file_results

    def _generate_status_message(
        self,
        rollback_type: str,
        checkpoint_id: str,
        success: bool,
        affected_files: List[str],
        error_details: Optional[str],
    ) -> str:
        """Generate the main status message for rollback notification."""
        if rollback_type == "full":
            rollback_desc = f"Full repository rollback to checkpoint {checkpoint_id[:8]}"
        else:
            rollback_desc = f"Selective rollback of {len(affected_files)} file(s) to checkpoint {checkpoint_id[:8]}"

        if success:
            status_msg = f"ROLLBACK SUCCESSFUL\n{rollback_desc} completed successfully."
        else:
            status_msg = f"ROLLBACK FAILED\n{rollback_desc} encountered errors."
            if error_details:
                status_msg += f"\nError: {error_details}"

        return status_msg

    def _generate_trigger_summary(self, failure_detection: FailureDetectionResult) -> List[str]:
        """Generate failure trigger summary for notification."""
        trigger_summary = ["", "ORIGINAL FAILURES DETECTED:"]

        # Group triggers by type for cleaner output
        by_type: Dict[str, List[Any]] = {}
        for trigger in failure_detection.triggers:
            type_name = trigger.failure_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(trigger)

        for failure_type, triggers in by_type.items():
            trigger_summary.append(f"   {failure_type.upper()}:")
            for trigger in triggers:
                trigger_summary.append(f"      • [{trigger.severity.value}] {trigger.description}")
                if trigger.affected_files:
                    files_str = ", ".join(trigger.affected_files[:3])
                    if len(trigger.affected_files) > 3:
                        files_str += f" (and {len(trigger.affected_files) - 3} more)"
                    trigger_summary.append(f"        Files: {files_str}")

        return trigger_summary

    def _generate_next_steps(self, success: bool) -> List[str]:
        """Generate next steps section for notification."""
        next_steps = ["", "NEXT STEPS:"]

        if success:
            next_steps.extend(
                [
                    "   • Repository has been restored to a safe state",
                    "   • Review the original failures before retrying operation",
                    "   • Consider adjusting operation parameters if needed",
                ]
            )
        else:
            next_steps.extend(
                [
                    "   • Manual intervention required",
                    "   • Check git status and repository state",
                    "   • Consider manual rollback if automatic rollback failed",
                    "   • Contact support if issues persist",
                ]
            )

        return next_steps

    def _generate_notification_message(
        self,
        rollback_type: str,
        checkpoint_id: str,
        failure_detection: FailureDetectionResult,
        success: bool,
        affected_files: List[str],
        error_details: Optional[str] = None,
    ) -> str:
        """
        Generate a comprehensive user notification message.

        Args:
            rollback_type: Type of rollback performed ("full" or "selective")
            checkpoint_id: Checkpoint that was rolled back to
            failure_detection: Original failure detection results
            success: Whether the rollback was successful
            affected_files: List of files that were affected
            error_details: Optional error details if rollback failed

        Returns:
            Formatted notification message
        """
        status_msg = self._generate_status_message(rollback_type, checkpoint_id, success, affected_files, error_details)

        trigger_summary = self._generate_trigger_summary(failure_detection)

        # Add affected files summary for selective rollback
        if rollback_type == "selective" and affected_files:
            trigger_summary.extend(["", "FILES RESTORED:", f"   {', '.join(affected_files)}"])

        next_steps = self._generate_next_steps(success)

        return status_msg + "\n".join(trigger_summary) + "\n".join(next_steps)

    def _generate_recovery_suggestions(
        self,
        rollback_type: str,
        success: bool,
        failure_detection: FailureDetectionResult,
        error_details: Optional[str] = None,
    ) -> List[str]:
        """
        Generate actionable recovery suggestions.

        Args:
            rollback_type: Type of rollback that was attempted
            success: Whether the rollback was successful
            failure_detection: Original failure detection results
            error_details: Optional error details if rollback failed

        Returns:
            List of recovery suggestions
        """
        suggestions = []

        if success:
            suggestions.extend(
                [
                    "Review original failure triggers before retrying operation",
                    "Consider using more conservative operation parameters",
                    "Verify file contents are as expected after rollback",
                ]
            )

            # Add specific suggestions based on failure types
            failure_types = {t.failure_type.value for t in failure_detection.triggers}

            if "syntax_errors" in failure_types:
                suggestions.append("Check syntax validation before next operation")
            if "lint_failures" in failure_types:
                suggestions.append("Run linting checks before next operation")
            if "test_breakage" in failure_types:
                suggestions.append("Ensure tests pass before next operation")
            if "empty_files" in failure_types:
                suggestions.append("Verify file preservation strategies for next operation")
            if "content_loss" in failure_types:
                suggestions.append("Consider smaller, incremental changes")
        else:
            suggestions.extend(
                [
                    "Check git repository status manually",
                    "Verify checkpoint existence and validity",
                    "Consider manual git reset or checkout operations",
                ]
            )

            if error_details and "permission" in error_details.lower():
                suggestions.append("Check file permissions and disk space")
            if error_details and "not found" in error_details.lower():
                suggestions.append("Verify git repository integrity")

        return suggestions

    def _create_log_entry(
        self,
        operation_id: str,
        checkpoint_id: str,
        rollback_type: str,
        failure_detection: FailureDetectionResult,
        affected_files: List[str],
        commands_executed: List[str],
        success: bool,
        notification_message: str,
        recovery_suggestions: List[str],
        error_message: Optional[str] = None,
        git_output: Optional[str] = None,
        file_results: Optional[Dict[str, str]] = None,
    ) -> RollbackLogEntry:
        """Create a detailed log entry for the rollback operation."""
        return RollbackLogEntry(
            timestamp=datetime.now(UTC).isoformat(),
            operation_id=operation_id,
            checkpoint_id=checkpoint_id,
            rollback_type=rollback_type,
            triggers=[
                {
                    "type": t.failure_type.value,
                    "severity": t.severity.value,
                    "description": t.description,
                    "affected_files": t.affected_files,
                    "details": t.details,
                }
                for t in failure_detection.triggers
            ],
            affected_files=affected_files,
            git_commands_executed=commands_executed,
            success=success,
            error_message=error_message,
            git_output=git_output,
            file_results=file_results,
            user_notification=notification_message,
            recovery_suggestions=recovery_suggestions,
        )

    def perform_rollback(
        self,
        checkpoint_id: str,
        failure_detection: FailureDetectionResult,
        operation_id: str,
        diff_analysis: Optional[DiffAnalysisResult] = None,
        force_full_rollback: bool = False,
    ) -> RollbackResult:
        """
        Perform automatic rollback based on failure detection results.

        Args:
            checkpoint_id: Git commit hash of the checkpoint to rollback to
            failure_detection: Results from FailureDetector
            operation_id: Unique identifier for the operation being rolled back
            diff_analysis: Optional results from GitDiffAnalyzer
            force_full_rollback: Force full rollback regardless of strategy

        Returns:
            Complete rollback result with success status and details
        """
        logger.info(f"Starting automatic rollback to {checkpoint_id} for operation {operation_id}")

        # Validate checkpoint
        if not self._validate_checkpoint(checkpoint_id):
            error_msg = f"Invalid checkpoint: {checkpoint_id}"
            logger.error(error_msg)
            raise InvalidCheckpointError(error_msg)

        # Determine rollback strategy
        if force_full_rollback:
            rollback_type: str = "full"
            affected_files: List[str] = []
        else:
            rollback_type, affected_files = self._determine_rollback_strategy(failure_detection, diff_analysis)

        commands_executed: List[str] = []
        success = False
        error_details: Optional[str] = None
        git_output: Optional[str] = None
        file_results: Optional[Dict[str, str]] = None

        try:
            if rollback_type == "full":
                commands_executed, git_output = self._perform_full_rollback(checkpoint_id)
            else:
                commands_executed, file_results = self._perform_selective_rollback(checkpoint_id, affected_files)

            success = True
            logger.info(f"Rollback completed successfully: {rollback_type} rollback to {checkpoint_id}")

        except RollbackExecutionError as e:
            success = False
            error_details = str(e)
            logger.error(f"Rollback failed: {e}")

        except Exception as e:
            success = False
            error_details = f"Unexpected error: {e}"
            logger.error(f"Unexpected rollback error: {e}")

        # Generate notification and recovery suggestions
        notification_message = self._generate_notification_message(
            rollback_type, checkpoint_id, failure_detection, success, affected_files, error_details
        )

        recovery_suggestions = self._generate_recovery_suggestions(
            rollback_type, success, failure_detection, error_details
        )

        # Create log entry
        log_entry = self._create_log_entry(
            operation_id=operation_id,
            checkpoint_id=checkpoint_id,
            rollback_type=rollback_type,
            failure_detection=failure_detection,
            affected_files=affected_files,
            commands_executed=commands_executed,
            success=success,
            notification_message=notification_message,
            recovery_suggestions=recovery_suggestions,
            error_message=error_details,
            git_output=git_output,
            file_results=file_results,
        )

        # Log the rollback operation
        self._log_rollback_operation(log_entry)

        result = RollbackResult(
            success=success,
            rollback_type=rollback_type,
            checkpoint_id=checkpoint_id,
            affected_files=affected_files,
            notification_message=notification_message,
            log_entry=log_entry,
            recovery_suggestions=recovery_suggestions,
            git_commands_executed=commands_executed,
            error_details=error_details,
        )

        logger.info(f"Rollback operation completed: success={success}, type={rollback_type}")
        return result

    def _log_rollback_operation(self, log_entry: RollbackLogEntry) -> None:
        """
        Log the rollback operation for audit trail and analysis.

        Args:
            log_entry: Complete log entry for the rollback operation
        """
        log_summary = (
            f"ROLLBACK {log_entry.rollback_type.upper()}: "
            f"op={log_entry.operation_id}, "
            f"checkpoint={log_entry.checkpoint_id[:8]}, "
            f"success={log_entry.success}, "
            f"triggers={len(log_entry.triggers)}, "
            f"files={len(log_entry.affected_files)}"
        )

        if log_entry.success:
            logger.info(f"✅ {log_summary}")
        else:
            logger.error(f"❌ {log_summary}")
            if log_entry.error_message:
                logger.error(f"Rollback error details: {log_entry.error_message}")

        # Log trigger details for analysis
        for trigger in log_entry.triggers:
            logger.info(f"Trigger: {trigger['type']} ({trigger['severity']}) - {trigger['description']}")

        # Log git command results
        for cmd in log_entry.git_commands_executed:
            logger.debug(f"Executed: {cmd}")

    def get_rollback_status(self, checkpoint_id: str) -> Dict[str, Any]:
        """
        Get the current repository status relative to a checkpoint.

        Args:
            checkpoint_id: Checkpoint to compare against

        Returns:
            Dictionary with status information
        """
        try:
            if not self._validate_checkpoint(checkpoint_id):
                return {"valid_checkpoint": False, "error": "Invalid checkpoint"}

            # Get current HEAD
            current_head = self._run_git(["rev-parse", "HEAD"]).strip()

            # Check if we're at the checkpoint
            at_checkpoint = current_head == checkpoint_id

            # Get status
            status_output = self._run_git(["status", "--porcelain"])
            has_uncommitted = bool(status_output.strip())

            # Get diff summary if not at checkpoint
            diff_summary = None
            if not at_checkpoint:
                try:
                    diff_output = self._run_git(["diff", "--stat", checkpoint_id, "HEAD"])
                    diff_summary = diff_output.strip()
                except RollbackExecutionError:
                    diff_summary = "Unable to get diff"

            return {
                "valid_checkpoint": True,
                "current_head": current_head,
                "checkpoint_id": checkpoint_id,
                "at_checkpoint": at_checkpoint,
                "has_uncommitted_changes": has_uncommitted,
                "diff_summary": diff_summary,
                "can_rollback": True,
            }

        except RollbackExecutionError as e:
            logger.error(f"Failed to get rollback status: {e}")
            return {"valid_checkpoint": True, "error": str(e), "can_rollback": False}
