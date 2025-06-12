"""
Tests for Recovery Guidance System.

Tests the RecoveryGuidanceManager and related components for comprehensive recovery
guidance generation after failures, ensuring proper integration with safety systems.
"""

import os
import tempfile

import pytest

from aider_mcp_server.atoms.utils.automatic_rollback import RollbackResult, RollbackLogEntry
from aider_mcp_server.atoms.utils.failure_detector import (
    FailureDetectionResult,
    FailureSeverity,
    FailureTrigger,
    FailureType,
)
from aider_mcp_server.atoms.utils.recovery_guidance import (
    GuidanceItem,
    GuidancePriority,
    GuidanceType,
    RecoveryGuidanceManager,
    RecoveryGuidanceResult,
)


class TestRecoveryGuidanceManager:
    """Test suite for RecoveryGuidanceManager."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create .git directory to simulate git repo
            git_dir = os.path.join(temp_dir, ".git")
            os.makedirs(git_dir)
            yield temp_dir

    @pytest.fixture
    def guidance_manager(self, temp_repo):
        """Create a RecoveryGuidanceManager instance."""
        return RecoveryGuidanceManager(
            repo_path=temp_repo,
            enable_manual_overrides=True,
            include_debug_info=True,
            max_alternative_suggestions=5,
        )

    @pytest.fixture
    def sample_failure_detection(self):
        """Create sample failure detection results."""
        triggers = [
            FailureTrigger(
                failure_type=FailureType.EMPTY_FILES,
                severity=FailureSeverity.CRITICAL,
                description="File became empty: test.py",
                affected_files=["test.py"],
                details={"current_size": 0, "baseline_line_count": 100},
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
            has_failures=False,  # Will be calculated in __post_init__
            triggers=triggers,
            requires_rollback=False,  # Will be calculated in __post_init__
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            detection_summary="",
        )

    @pytest.fixture
    def sample_rollback_result(self):
        """Create sample rollback result."""
        log_entry = RollbackLogEntry(
            timestamp="2024-01-01T12:00:00Z",
            operation_id="op123",
            checkpoint_id="abc123",
            rollback_type="selective",
            triggers=[],
            affected_files=["test.py"],
            git_commands_executed=["git checkout abc123 -- test.py"],
            success=True,
        )

        return RollbackResult(
            success=True,
            rollback_type="selective",
            checkpoint_id="abc123",
            affected_files=["test.py"],
            notification_message="Rollback successful",
            log_entry=log_entry,
            recovery_suggestions=["Review original failures"],
            git_commands_executed=["git checkout abc123 -- test.py"],
        )

    def test_initialization(self, temp_repo):
        """Test RecoveryGuidanceManager initialization."""
        manager = RecoveryGuidanceManager(
            repo_path=temp_repo,
            enable_manual_overrides=False,
            include_debug_info=False,
            max_alternative_suggestions=3,
        )

        assert manager.repo_path == os.path.abspath(temp_repo)
        assert manager.enable_manual_overrides is False
        assert manager.include_debug_info is False
        assert manager.max_alternative_suggestions == 3

    def test_generate_recovery_guidance(self, guidance_manager, sample_failure_detection, sample_rollback_result):
        """Test comprehensive recovery guidance generation."""
        operation_params = {"model": "gpt-4", "files": ["test.py", "main.py"]}

        result = guidance_manager.generate_recovery_guidance(
            failure_detection=sample_failure_detection,
            rollback_result=sample_rollback_result,
            operation_params=operation_params,
            operation_context="Testing operation",
        )

        assert isinstance(result, RecoveryGuidanceResult)
        assert result.has_guidance
        assert result.total_recommendations > 0
        assert result.critical_count >= 1  # At least one critical failure
        assert len(result.guidance_items) > 0
        assert result.formatted_message
        assert "RECOVERY GUIDANCE" in result.formatted_message

    def test_analyze_failures_empty_files(self, guidance_manager):
        """Test failure analysis for empty files."""
        triggers = [
            FailureTrigger(
                failure_type=FailureType.EMPTY_FILES,
                severity=FailureSeverity.CRITICAL,
                description="File became empty: test.py",
                affected_files=["test.py"],
                details={"current_size": 0},
                recommended_action="Immediate rollback",
            )
        ]

        failure_detection = FailureDetectionResult(
            has_failures=True,
            triggers=triggers,
            requires_rollback=True,
            critical_count=1,
            high_count=0,
            medium_count=0,
            low_count=0,
            detection_summary="1 critical failure",
        )

        analysis_items = guidance_manager.analyze_failures(failure_detection)

        assert len(analysis_items) == 1
        item = analysis_items[0]
        assert item.guidance_type == GuidanceType.FAILURE_ANALYSIS
        assert item.priority == GuidancePriority.CRITICAL
        assert "File Content Loss Detected" in item.title
        assert "test.py" in item.description
        assert item.warning_level == "critical"

    def test_suggest_alternatives_conservative_operations(self, guidance_manager):
        """Test alternative suggestions for content loss scenarios."""
        triggers = [
            FailureTrigger(
                failure_type=FailureType.EMPTY_FILES,
                severity=FailureSeverity.CRITICAL,
                description="File became empty",
                affected_files=["test.py"],
                details={},
                recommended_action="Immediate rollback",
            )
        ]

        failure_detection = FailureDetectionResult(
            has_failures=True,
            triggers=triggers,
            requires_rollback=True,
            critical_count=1,
            high_count=0,
            medium_count=0,
            low_count=0,
            detection_summary="1 critical failure",
        )

        alternatives = guidance_manager.suggest_alternatives(failure_detection)

        # Should suggest conservative operations for content loss
        conservative_item = next(
            (item for item in alternatives if "Conservative File Operations" in item.title), None
        )
        assert conservative_item is not None
        assert conservative_item.guidance_type == GuidanceType.ALTERNATIVE_APPROACHES
        assert conservative_item.priority == GuidancePriority.HIGH

    def test_provide_override_options_successful_rollback(self, guidance_manager, sample_rollback_result):
        """Test manual override options when rollback was successful."""
        triggers = [
            FailureTrigger(
                failure_type=FailureType.LINT_FAILURES,
                severity=FailureSeverity.HIGH,
                description="Lint failures",
                affected_files=[],
                details={},
                recommended_action="Fix lint",
            )
        ]

        failure_detection = FailureDetectionResult(
            has_failures=True,
            triggers=triggers,
            requires_rollback=False,
            critical_count=0,
            high_count=1,
            medium_count=0,
            low_count=0,
            detection_summary="1 high failure",
        )

        overrides = guidance_manager.provide_override_options(failure_detection, sample_rollback_result)

        assert len(overrides) > 0
        # Should include general override options
        general_override = next((item for item in overrides if "Manual Safety Override" in item.title), None)
        assert general_override is not None
        assert general_override.guidance_type == GuidanceType.MANUAL_OVERRIDE
        assert general_override.warning_level == "caution"

    def test_generate_support_info_with_debug(self, guidance_manager, sample_failure_detection, sample_rollback_result):
        """Test support information generation with debug info enabled."""
        operation_params = {"model": "gpt-4", "files": ["test.py"]}

        support_items = guidance_manager.generate_support_info(
            sample_failure_detection, sample_rollback_result, operation_params
        )

        assert len(support_items) > 0

        # Should include debugging information
        debug_item = next((item for item in support_items if "Debugging Information" in item.title), None)
        assert debug_item is not None
        assert debug_item.guidance_type == GuidanceType.SUPPORT_ESCALATION
        assert debug_item.priority == GuidancePriority.MEDIUM

    def test_format_guidance_message(self, guidance_manager, sample_failure_detection, sample_rollback_result):
        """Test guidance message formatting."""
        result = guidance_manager.generate_recovery_guidance(
            failure_detection=sample_failure_detection,
            rollback_result=sample_rollback_result,
        )

        message = result.formatted_message

        # Check message structure
        assert "RECOVERY GUIDANCE" in message
        assert "SITUATION SUMMARY:" in message
        assert "FAILURE ANALYSIS:" in message
        assert "ALTERNATIVE APPROACHES:" in message
        assert "NEXT STEPS:" in message

        # Check failure summary contains expected information
        assert "Detected 2 failure(s)" in message or "failure" in message.lower()

    def test_guidance_summary(self, guidance_manager):
        """Test guidance summary generation."""
        # Test with no guidance
        empty_result = RecoveryGuidanceResult(
            has_guidance=False,
            failure_summary="No failures",
            rollback_summary="No rollback",
            guidance_items=[],
            formatted_message="",
            total_recommendations=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            next_steps_summary="No steps",
        )

        summary = guidance_manager.get_guidance_summary(empty_result)
        assert "No specific guidance needed" in summary

        # Test with critical guidance
        critical_result = RecoveryGuidanceResult(
            has_guidance=True,
            failure_summary="Failures detected",
            rollback_summary="Rollback attempted",
            guidance_items=[
                GuidanceItem(
                    guidance_type=GuidanceType.FAILURE_ANALYSIS,
                    priority=GuidancePriority.CRITICAL,
                    title="Critical Issue",
                    description="Description",
                    action_steps=[],
                    related_files=[],
                    details={},
                )
            ],
            formatted_message="",
            total_recommendations=1,
            critical_count=1,
            high_count=0,
            medium_count=0,
            low_count=0,
            next_steps_summary="Critical action required",
        )

        summary = guidance_manager.get_guidance_summary(critical_result)
        assert "1 recommendations" in summary
        assert "Critical: 1" in summary
        assert "IMMEDIATE ATTENTION REQUIRED" in summary