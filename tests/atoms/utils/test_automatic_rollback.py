"""
Comprehensive tests for the AutomaticRollbackManager and related classes.

Covers:
- Full rollback scenarios with git reset integration
- Selective file restoration scenarios
- Notification message generation and formatting
- Rollback logging functionality
- Error handling during rollback failures
- Integration with failure detection triggers
- Various repository states and edge cases

Mocks subprocess and filesystem as needed.
"""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from aider_mcp_server.atoms.utils.automatic_rollback import (
    AutomaticRollbackError,
    AutomaticRollbackManager,
    InvalidCheckpointError,
    RollbackExecutionError,
    RollbackResult,
)
from aider_mcp_server.atoms.utils.failure_detector import (
    FailureDetectionResult,
    FailureSeverity,
    FailureTrigger,
    FailureType,
)
from aider_mcp_server.atoms.utils.git_diff_analyzer import DiffAnalysisResult

# --- Fixtures and helpers ---


@pytest.fixture
def fake_repo_path(tmp_path):
    # Initialize a proper git repository
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)  # noqa: S603,S607
    # Set basic git config to avoid warnings
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)  # noqa: S603,S607
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)  # noqa: S603,S607
    return str(tmp_path)


@pytest.fixture
def manager(fake_repo_path):
    return AutomaticRollbackManager(fake_repo_path)


@pytest.fixture
def sample_failure_detection():
    """Create a sample failure detection result for testing."""
    triggers = [
        FailureTrigger(
            failure_type=FailureType.EMPTY_FILES,
            severity=FailureSeverity.CRITICAL,
            description="File became empty: test.py",
            affected_files=["test.py"],
            details={"current_size": 0, "baseline_line_count": 50},
            recommended_action="Immediate rollback - file content lost",
        ),
        FailureTrigger(
            failure_type=FailureType.SYNTAX_ERRORS,
            severity=FailureSeverity.HIGH,
            description="Syntax error in main.py",
            affected_files=["main.py"],
            details={"syntax_error": "invalid syntax"},
            recommended_action="Fix syntax errors before proceeding",
        ),
    ]

    return FailureDetectionResult(
        has_failures=True,
        triggers=triggers,
        requires_rollback=True,
        critical_count=1,
        high_count=1,
        medium_count=0,
        low_count=0,
        detection_summary="Detected 2 failure(s): Critical: 1, High: 1, Medium: 0, Low: 0 ROLLBACK REQUIRED",
    )


@pytest.fixture
def sample_diff_analysis():
    """Create a sample diff analysis result for testing."""
    return DiffAnalysisResult(
        from_ref="abc123",
        to_ref="HEAD",
        file_changes=[],
        suspicious_patterns=[],
        large_changes=[],
        rollback_commands=["git reset --hard abc123"],
        selective_rollback_files=["test.py", "main.py"],
        total_files_changed=2,
        total_additions=10,
        total_deletions=50,
        has_critical_issues=True,
        analysis_summary="Critical issues detected",
    )


# --- Tests ---


class TestAutomaticRollbackManagerInit:
    def test_init_success(self, fake_repo_path):
        mgr = AutomaticRollbackManager(fake_repo_path)
        assert mgr.repo_path == os.path.abspath(fake_repo_path)
        assert mgr.enable_selective_rollback is True
        assert mgr.require_confirmation is False
        assert mgr.max_affected_files_for_selective == 10

    def test_init_custom_parameters(self, fake_repo_path):
        mgr = AutomaticRollbackManager(
            fake_repo_path,
            enable_selective_rollback=False,
            require_confirmation=True,
            max_affected_files_for_selective=5,
        )
        assert mgr.enable_selective_rollback is False
        assert mgr.require_confirmation is True
        assert mgr.max_affected_files_for_selective == 5

    def test_init_not_a_git_repo(self, tmp_path):
        # No .git directory
        with pytest.raises(AutomaticRollbackError):
            AutomaticRollbackManager(str(tmp_path))

    def test_is_git_repo_true(self, fake_repo_path):
        mgr = AutomaticRollbackManager(fake_repo_path)
        assert mgr._is_git_repo() is True

    def test_is_git_repo_false(self, tmp_path):
        mgr = object.__new__(AutomaticRollbackManager)
        mgr.repo_path = str(tmp_path)
        assert mgr._is_git_repo() is False


class TestGitOperations:
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.subprocess.run")
    def test_run_git_success(self, mock_run, manager):
        mock_result = MagicMock()
        mock_result.stdout = "git output"
        mock_run.return_value = mock_result

        result = manager._run_git(["status"], capture_output=True)
        assert result == "git output"
        mock_run.assert_called_once()

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.subprocess.run")
    def test_run_git_failure(self, mock_run, manager):
        mock_run.side_effect = Exception("Git command failed")

        with pytest.raises(RollbackExecutionError):
            manager._run_git(["status"])

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_validate_checkpoint_valid(self, mock_run_git, manager):
        mock_run_git.return_value = "abc123"
        assert manager._validate_checkpoint("abc123") is True

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_validate_checkpoint_invalid(self, mock_run_git, manager):
        mock_run_git.side_effect = RollbackExecutionError("Invalid reference")
        assert manager._validate_checkpoint("invalid") is False


class TestRollbackStrategy:
    def test_determine_strategy_selective_small_scope(self, manager, sample_failure_detection):
        rollback_type, affected_files = manager._determine_rollback_strategy(sample_failure_detection)
        assert rollback_type == "selective"
        assert set(affected_files) == {"test.py", "main.py"}

    def test_determine_strategy_full_large_scope(self, manager, sample_failure_detection):
        # Create failure with many files
        large_failure = FailureDetectionResult(
            has_failures=True,
            triggers=[
                FailureTrigger(
                    failure_type=FailureType.CONTENT_LOSS,
                    severity=FailureSeverity.CRITICAL,
                    description="Mass content loss",
                    affected_files=[f"file_{i}.py" for i in range(15)],  # More than max threshold
                    details={},
                    recommended_action="Rollback required",
                )
            ],
            requires_rollback=True,
            critical_count=1,
            high_count=0,
            medium_count=0,
            low_count=0,
            detection_summary="Large scope failure",
        )

        rollback_type, affected_files = manager._determine_rollback_strategy(large_failure)
        assert rollback_type == "full"

    def test_determine_strategy_full_many_critical(self, manager):
        # Create failure with many critical failures
        critical_failure = FailureDetectionResult(
            has_failures=True,
            triggers=[
                FailureTrigger(
                    failure_type=FailureType.EMPTY_FILES,
                    severity=FailureSeverity.CRITICAL,
                    description=f"Critical failure {i}",
                    affected_files=[f"file_{i}.py"],
                    details={},
                    recommended_action="Rollback required",
                )
                for i in range(5)  # More than 2 critical failures
            ],
            requires_rollback=True,
            critical_count=5,
            high_count=0,
            medium_count=0,
            low_count=0,
            detection_summary="Many critical failures",
        )

        rollback_type, affected_files = manager._determine_rollback_strategy(critical_failure)
        assert rollback_type == "full"

    def test_determine_strategy_disabled_selective(self, fake_repo_path, sample_failure_detection):
        manager = AutomaticRollbackManager(fake_repo_path, enable_selective_rollback=False)
        rollback_type, affected_files = manager._determine_rollback_strategy(sample_failure_detection)
        assert rollback_type == "full"
        assert affected_files == []

    def test_determine_strategy_with_diff_analysis(self, manager, sample_failure_detection, sample_diff_analysis):
        rollback_type, affected_files = manager._determine_rollback_strategy(
            sample_failure_detection, sample_diff_analysis
        )
        assert rollback_type == "selective"
        # Should include files from both failure detection and diff analysis
        assert "test.py" in affected_files
        assert "main.py" in affected_files


class TestFullRollback:
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_perform_full_rollback_success(self, mock_run_git, manager):
        mock_run_git.side_effect = [
            "Saved working directory",  # stash output
            "HEAD is now at abc123",  # reset output
        ]

        commands, output = manager._perform_full_rollback("abc123")

        assert len(commands) == 2
        assert "git stash push" in commands[0]
        assert "git reset --hard abc123" in commands[1]
        assert "Stash output:" in output
        assert "Reset output:" in output

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_perform_full_rollback_stash_fails(self, mock_run_git, manager):
        # Stash fails but reset succeeds
        mock_run_git.side_effect = [
            RollbackExecutionError("Nothing to stash"),  # stash fails
            "HEAD is now at abc123",  # reset succeeds
        ]

        commands, output = manager._perform_full_rollback("abc123")

        assert len(commands) == 1  # Only reset command recorded
        assert "git reset --hard abc123" in commands[0]

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_perform_full_rollback_reset_fails(self, mock_run_git, manager):
        mock_run_git.side_effect = [
            "Saved working directory",  # stash succeeds
            RollbackExecutionError("Reset failed"),  # reset fails
        ]

        with pytest.raises(RollbackExecutionError):
            manager._perform_full_rollback("abc123")


class TestSelectiveRollback:
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_perform_selective_rollback_success(self, mock_run_git, manager):
        mock_run_git.side_effect = [
            "",  # checkout output for first file
            "",  # checkout output for second file
        ]

        affected_files = ["test.py", "main.py"]
        commands, file_results = manager._perform_selective_rollback("abc123", affected_files)

        assert len(commands) == 2
        assert "git checkout abc123 -- test.py" in commands[0]
        assert "git checkout abc123 -- main.py" in commands[1]

        assert file_results["test.py"].startswith("SUCCESS")
        assert file_results["main.py"].startswith("SUCCESS")

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_perform_selective_rollback_partial_failure(self, mock_run_git, manager):
        mock_run_git.side_effect = [
            "",  # First file succeeds
            RollbackExecutionError("File not found"),  # Second file fails
        ]

        affected_files = ["test.py", "nonexistent.py"]
        commands, file_results = manager._perform_selective_rollback("abc123", affected_files)

        assert len(commands) == 2
        assert file_results["test.py"].startswith("SUCCESS")
        assert file_results["nonexistent.py"].startswith("FAILED")
        assert "# FAILED" in commands[1]

    def test_perform_selective_rollback_empty_files(self, manager):
        commands, file_results = manager._perform_selective_rollback("abc123", [])
        assert commands == []
        assert file_results == {}


class TestNotificationGeneration:
    def test_generate_notification_success_full(self, manager, sample_failure_detection):
        message = manager._generate_notification_message(
            rollback_type="full",
            checkpoint_id="abc123def",
            failure_detection=sample_failure_detection,
            success=True,
            affected_files=[],
        )

        assert "ROLLBACK SUCCESSFUL" in message
        assert "Full repository rollback to checkpoint abc123de" in message
        assert "ORIGINAL FAILURES DETECTED:" in message
        assert "EMPTY_FILES:" in message
        assert "SYNTAX_ERRORS:" in message
        assert "NEXT STEPS:" in message
        assert "Repository has been restored to a safe state" in message

    def test_generate_notification_success_selective(self, manager, sample_failure_detection):
        message = manager._generate_notification_message(
            rollback_type="selective",
            checkpoint_id="abc123def",
            failure_detection=sample_failure_detection,
            success=True,
            affected_files=["test.py", "main.py"],
        )

        assert "ROLLBACK SUCCESSFUL" in message
        assert "Selective rollback of 2 file(s)" in message
        assert "FILES RESTORED:" in message
        assert "test.py, main.py" in message

    def test_generate_notification_failure(self, manager, sample_failure_detection):
        message = manager._generate_notification_message(
            rollback_type="full",
            checkpoint_id="abc123def",
            failure_detection=sample_failure_detection,
            success=False,
            affected_files=[],
            error_details="Git command failed",
        )

        assert "ROLLBACK FAILED" in message
        assert "Error: Git command failed" in message
        assert "Manual intervention required" in message

    def test_generate_notification_with_many_files(self, manager):
        # Test file list truncation
        failure_with_many_files = FailureDetectionResult(
            has_failures=True,
            triggers=[
                FailureTrigger(
                    failure_type=FailureType.CONTENT_LOSS,
                    severity=FailureSeverity.HIGH,
                    description="Many files affected",
                    affected_files=[f"file_{i}.py" for i in range(5)],
                    details={},
                    recommended_action="Review changes",
                )
            ],
            requires_rollback=True,
            critical_count=0,
            high_count=1,
            medium_count=0,
            low_count=0,
            detection_summary="Many files failure",
        )

        message = manager._generate_notification_message(
            rollback_type="selective",
            checkpoint_id="abc123",
            failure_detection=failure_with_many_files,
            success=True,
            affected_files=[],
        )

        assert "(and 2 more)" in message  # Should truncate file list


class TestRecoverySuggestions:
    def test_generate_recovery_suggestions_success(self, manager, sample_failure_detection):
        suggestions = manager._generate_recovery_suggestions(
            rollback_type="selective",
            success=True,
            failure_detection=sample_failure_detection,
        )

        assert "Review original failure triggers before retrying operation" in suggestions
        assert "Check syntax validation before next operation" in suggestions  # Due to syntax error
        assert "Verify file preservation strategies for next operation" in suggestions  # Due to empty file

    def test_generate_recovery_suggestions_failure(self, manager, sample_failure_detection):
        suggestions = manager._generate_recovery_suggestions(
            rollback_type="full",
            success=False,
            failure_detection=sample_failure_detection,
            error_details="permission denied",
        )

        assert "Check git repository status manually" in suggestions
        assert "Check file permissions and disk space" in suggestions  # Due to permission error

    def test_generate_recovery_suggestions_various_error_types(self, manager, sample_failure_detection):
        suggestions = manager._generate_recovery_suggestions(
            rollback_type="full",
            success=False,
            failure_detection=sample_failure_detection,
            error_details="file not found",
        )

        assert "Verify git repository integrity" in suggestions


class TestPerformRollback:
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._validate_checkpoint")
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._perform_full_rollback")
    def test_perform_rollback_full_success(self, mock_full_rollback, mock_validate, manager, sample_failure_detection):
        mock_validate.return_value = True
        mock_full_rollback.return_value = (["git reset --hard abc123"], "Reset successful")

        result = manager.perform_rollback(
            checkpoint_id="abc123",
            failure_detection=sample_failure_detection,
            operation_id="test_op",
            force_full_rollback=True,
        )

        assert result.success is True
        assert result.rollback_type == "full"
        assert result.checkpoint_id == "abc123"
        assert "ROLLBACK SUCCESSFUL" in result.notification_message
        assert len(result.recovery_suggestions) > 0

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._validate_checkpoint")
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._perform_selective_rollback")
    def test_perform_rollback_selective_success(
        self, mock_selective_rollback, mock_validate, manager, sample_failure_detection
    ):
        mock_validate.return_value = True
        mock_selective_rollback.return_value = (
            ["git checkout abc123 -- test.py"],
            {"test.py": "SUCCESS: File restored"},
        )

        result = manager.perform_rollback(
            checkpoint_id="abc123",
            failure_detection=sample_failure_detection,
            operation_id="test_op",
        )

        assert result.success is True
        assert result.rollback_type == "selective"

    def test_perform_rollback_invalid_checkpoint(self, manager, sample_failure_detection):
        with pytest.raises(InvalidCheckpointError):
            manager.perform_rollback(
                checkpoint_id="invalid",
                failure_detection=sample_failure_detection,
                operation_id="test_op",
            )

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._validate_checkpoint")
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._perform_full_rollback")
    def test_perform_rollback_execution_failure(
        self, mock_full_rollback, mock_validate, manager, sample_failure_detection
    ):
        mock_validate.return_value = True
        mock_full_rollback.side_effect = RollbackExecutionError("Git failed")

        result = manager.perform_rollback(
            checkpoint_id="abc123",
            failure_detection=sample_failure_detection,
            operation_id="test_op",
            force_full_rollback=True,
        )

        assert result.success is False
        assert "ROLLBACK FAILED" in result.notification_message
        assert result.should_escalate() is True

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._validate_checkpoint")
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._perform_full_rollback")
    def test_perform_rollback_unexpected_error(
        self, mock_full_rollback, mock_validate, manager, sample_failure_detection
    ):
        mock_validate.return_value = True
        mock_full_rollback.side_effect = Exception("Unexpected error")

        result = manager.perform_rollback(
            checkpoint_id="abc123",
            failure_detection=sample_failure_detection,
            operation_id="test_op",
            force_full_rollback=True,
        )

        assert result.success is False
        assert "Unexpected error" in result.error_details


class TestLogEntry:
    def test_create_log_entry(self, manager, sample_failure_detection):
        log_entry = manager._create_log_entry(
            operation_id="test_op",
            checkpoint_id="abc123",
            rollback_type="selective",
            failure_detection=sample_failure_detection,
            affected_files=["test.py"],
            commands_executed=["git checkout abc123 -- test.py"],
            success=True,
            notification_message="Success message",
            recovery_suggestions=["Review changes"],
        )

        assert log_entry.operation_id == "test_op"
        assert log_entry.checkpoint_id == "abc123"
        assert log_entry.rollback_type == "selective"
        assert log_entry.success is True
        assert len(log_entry.triggers) == 2  # From sample_failure_detection
        assert log_entry.affected_files == ["test.py"]
        assert len(log_entry.git_commands_executed) == 1

    def test_log_entry_serialization(self, manager, sample_failure_detection):
        log_entry = manager._create_log_entry(
            operation_id="test_op",
            checkpoint_id="abc123",
            rollback_type="full",
            failure_detection=sample_failure_detection,
            affected_files=[],
            commands_executed=["git reset --hard abc123"],
            success=True,
            notification_message="Success",
            recovery_suggestions=[],
        )

        # Verify trigger serialization
        assert log_entry.triggers[0]["type"] == "empty_files"
        assert log_entry.triggers[0]["severity"] == "critical"
        assert log_entry.triggers[1]["type"] == "syntax_errors"
        assert log_entry.triggers[1]["severity"] == "high"


class TestRollbackStatus:
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._validate_checkpoint")
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_get_rollback_status_at_checkpoint(self, mock_run_git, mock_validate, manager):
        mock_validate.return_value = True
        mock_run_git.side_effect = [
            "abc123",  # current HEAD
            "",  # git status (clean)
        ]

        status = manager.get_rollback_status("abc123")

        assert status["valid_checkpoint"] is True
        assert status["at_checkpoint"] is True
        assert status["has_uncommitted_changes"] is False
        assert status["can_rollback"] is True

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._validate_checkpoint")
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_get_rollback_status_not_at_checkpoint(self, mock_run_git, mock_validate, manager):
        mock_validate.return_value = True
        mock_run_git.side_effect = [
            "def456",  # current HEAD (different from checkpoint)
            " M file.py",  # git status (dirty)
            "1 file changed, 5 insertions(+), 2 deletions(-)",  # diff stat
        ]

        status = manager.get_rollback_status("abc123")

        assert status["valid_checkpoint"] is True
        assert status["at_checkpoint"] is False
        assert status["has_uncommitted_changes"] is True
        assert status["diff_summary"] == "1 file changed, 5 insertions(+), 2 deletions(-)"

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._validate_checkpoint")
    def test_get_rollback_status_invalid_checkpoint(self, mock_validate, manager):
        mock_validate.return_value = False

        status = manager.get_rollback_status("invalid")

        assert status["valid_checkpoint"] is False
        assert "error" in status

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._validate_checkpoint")
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_get_rollback_status_git_error(self, mock_run_git, mock_validate, manager):
        mock_validate.return_value = True
        mock_run_git.side_effect = RollbackExecutionError("Git failed")

        status = manager.get_rollback_status("abc123")

        assert status["can_rollback"] is False
        assert "error" in status


class TestRollbackResult:
    def test_rollback_result_should_escalate_success(self):
        result = RollbackResult(
            success=True,
            rollback_type="full",
            checkpoint_id="abc123",
            affected_files=[],
            notification_message="Success",
            log_entry=MagicMock(),
            recovery_suggestions=[],
            git_commands_executed=[],
        )

        assert result.should_escalate() is False

    def test_rollback_result_should_escalate_failure(self):
        result = RollbackResult(
            success=False,
            rollback_type="full",
            checkpoint_id="abc123",
            affected_files=[],
            notification_message="Failed",
            log_entry=MagicMock(),
            recovery_suggestions=[],
            git_commands_executed=[],
            error_details="Git failed",
        )

        assert result.should_escalate() is True


class TestIntegrationScenarios:
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._validate_checkpoint")
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_end_to_end_selective_rollback(self, mock_run_git, mock_validate, manager, sample_failure_detection):
        mock_validate.return_value = True
        mock_run_git.side_effect = [
            "",  # checkout test.py
            "",  # checkout main.py
        ]

        result = manager.perform_rollback(
            checkpoint_id="abc123",
            failure_detection=sample_failure_detection,
            operation_id="integration_test",
        )

        assert result.success is True
        assert result.rollback_type == "selective"
        assert "test.py" in result.affected_files
        assert "main.py" in result.affected_files
        assert "ROLLBACK SUCCESSFUL" in result.notification_message
        assert len(result.recovery_suggestions) > 0

        # Verify log entry
        assert result.log_entry.success is True
        assert result.log_entry.operation_id == "integration_test"
        assert len(result.log_entry.triggers) == 2

    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._validate_checkpoint")
    @patch("aider_mcp_server.atoms.utils.automatic_rollback.AutomaticRollbackManager._run_git")
    def test_end_to_end_full_rollback_with_diff_analysis(
        self, mock_run_git, mock_validate, manager, sample_failure_detection, sample_diff_analysis
    ):
        mock_validate.return_value = True
        mock_run_git.side_effect = [
            "Saved working directory",  # stash
            "HEAD is now at abc123",  # reset
        ]

        # Force large scope to trigger full rollback
        large_failure = FailureDetectionResult(
            has_failures=True,
            triggers=[
                FailureTrigger(
                    failure_type=FailureType.CONTENT_LOSS,
                    severity=FailureSeverity.CRITICAL,
                    description="Critical system failure",
                    affected_files=[f"file_{i}.py" for i in range(15)],
                    details={},
                    recommended_action="Full rollback required",
                )
            ],
            requires_rollback=True,
            critical_count=1,
            high_count=0,
            medium_count=0,
            low_count=0,
            detection_summary="Critical failure",
        )

        result = manager.perform_rollback(
            checkpoint_id="abc123",
            failure_detection=large_failure,
            operation_id="critical_recovery",
            diff_analysis=sample_diff_analysis,
        )

        assert result.success is True
        assert result.rollback_type == "full"
        assert "git reset --hard abc123" in result.git_commands_executed[1]
        assert "Full repository rollback" in result.notification_message
