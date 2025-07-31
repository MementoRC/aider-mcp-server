"""
Test suite for Safety System Manager integration (Task 12).

Tests the coordinated safety system that integrates all safety components
(Tasks 1-11) into a unified system for the MCP aider tool.
"""

import dataclasses
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from aider_mcp_server.atoms.utils.operation_risk_assessor import (
    OperationRiskAssessment,
    RiskLevel,
)
from aider_mcp_server.atoms.utils.safety_configuration import (
    ModelSpecificConfiguration,
    SafetyConfiguration,
    SafetyProfile,
    ValidationLevel,
)
from aider_mcp_server.atoms.utils.safety_system_manager import (
    SafetySystemManager,
    create_safety_system_manager,
)


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)

        import subprocess

        # Set environment to bypass Claude Code git redirector
        git_env = {**os.environ, "CLAUDECODE": "0"}

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, env=git_env)  # noqa: S603,S607
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, env=git_env)  # noqa: S603,S607
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, env=git_env)  # noqa: S603,S607

        # Create test files
        test_file = repo_path / "test.py"
        test_file.write_text("print('hello world')")

        subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True, env=git_env)  # noqa: S603,S607
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, env=git_env)  # noqa: S603,S607

        yield repo_path


class TestSafetySystemManager:
    """Test safety system manager core functionality."""

    def test_initialization_with_default_config(self):
        """Test manager initialization with default configuration."""
        with patch(
            "aider_mcp_server.atoms.utils.safety_configuration.SafetyConfigurationSystem._find_config_file",
            return_value=None,
        ):
            manager = SafetySystemManager()
            assert manager.config.profile == SafetyProfile.BALANCED
            assert manager._git_checkpoint_manager is None  # Lazy initialization

    def test_initialization_with_custom_config(self):
        """Test manager initialization with custom configuration."""
        config = SafetyConfiguration(profile=SafetyProfile.MINIMAL)
        manager = SafetySystemManager(config)

        assert manager.config.profile == SafetyProfile.MINIMAL
        assert manager.config.enable_risk_assessment is False

    def test_should_bypass_safety_parameter(self):
        """Test bypass safety via operation parameters."""
        manager = SafetySystemManager()

        # Should not bypass by default
        assert not manager.should_bypass_safety({})

        # Should bypass when parameter is set
        assert manager.should_bypass_safety({"bypass_safety": True})

    def test_should_bypass_safety_environment(self):
        """Test bypass safety via environment variable."""
        manager = SafetySystemManager()

        with patch.dict(os.environ, {"AIDER_BYPASS_SAFETY": "1"}):
            assert manager.should_bypass_safety({})

        with patch.dict(os.environ, {"AIDER_BYPASS_SAFETY": "true"}):
            assert manager.should_bypass_safety({})

    def test_should_bypass_safety_disabled_profile(self):
        """Test bypass safety when all components are disabled."""
        config = SafetyConfiguration(profile=SafetyProfile.CUSTOM)
        # Manually disable all components
        for f in dataclasses.fields(config):
            if f.name.startswith("enable_"):
                setattr(config, f.name, False)

        manager = SafetySystemManager(config)
        assert manager.should_bypass_safety({})

    def test_pre_execution_check_success(self, temp_git_repo):
        """Test successful pre-execution safety check."""
        manager = SafetySystemManager()

        result = manager.pre_execution_check(
            working_directory=temp_git_repo,
            target_files=["test.py"],
            operation_context={
                "model": "test-model",
                "prompt": "Simple test operation",
            },
        )

        assert result.is_safe is True
        assert result.reason is None

    @patch("aider_mcp_server.atoms.utils.safety_system_manager.OperationRiskAssessor")
    def test_pre_execution_check_with_risk_assessment(self, mock_assessor, temp_git_repo):
        """Test pre-execution check with risk assessment."""
        # Mock the assessor to return a base risk
        mock_assessor.return_value.assess_operation_risk.return_value = OperationRiskAssessment(
            total_score=2, risk_level=RiskLevel.LOW, factors=[], summary=""
        )

        config = SafetyConfiguration(profile=SafetyProfile.BALANCED)
        manager = SafetySystemManager(config)

        result = manager.pre_execution_check(
            working_directory=temp_git_repo,
            target_files=["test.py"],
            operation_context={
                "model": "gpt-4-turbo",  # Matches default "gpt-4*" pattern
                "prompt": "Complex operation",
            },
        )

        assert result.is_safe is True
        assert result.risk_assessment is not None
        # Base score 2 * gpt-4 multiplier 1.2 = 2.4, rounded to 2
        assert result.risk_assessment.total_score == 2
        mock_assessor.return_value.assess_operation_risk.assert_called_once()

    def test_create_checkpoint_success(self, temp_git_repo):
        """Test successful checkpoint creation."""
        manager = SafetySystemManager()

        result = manager.create_checkpoint(
            repo_path=temp_git_repo, files_to_track=[temp_git_repo / "test.py"], operation_metadata={"test": "metadata"}
        )

        assert result.success is True
        assert result.checkpoint_id is not None
        assert "aider-safety" in result.checkpoint_id

    def test_create_checkpoint_disabled(self):
        """Test checkpoint creation when disabled."""
        config = SafetyConfiguration(profile=SafetyProfile.CUSTOM, enable_git_checkpoint=False)
        manager = SafetySystemManager(config)

        result = manager.create_checkpoint(
            repo_path="/nonexistent",
            files_to_track=[],
        )

        assert result.success is True
        assert result.checkpoint_id == "disabled"

    @patch("aider_mcp_server.atoms.utils.safety_system_manager.FailureDetector")
    def test_detect_failures_no_failures(self, mock_detector, temp_git_repo):
        """Test failure detection when no failures occur."""
        # Mock failure detector to return no failures
        mock_instance = Mock()
        mock_instance.detect_failures_from_validation.return_value = Mock(
            has_failures=False, requires_rollback=False, failure_summary="No failures detected"
        )
        mock_detector.return_value = mock_instance

        manager = SafetySystemManager()

        result = manager.detect_failures(
            repo_path=temp_git_repo, target_files=["test.py"], checkpoint_id="test-checkpoint"
        )

        assert result is not None
        assert result.has_failures is False

    def test_detect_failures_disabled(self):
        """Test failure detection when disabled."""
        config = SafetyConfiguration(
            profile=SafetyProfile.CUSTOM, enable_failure_detection=False, enable_automatic_rollback=False
        )
        manager = SafetySystemManager(config)

        result = manager.detect_failures(repo_path="/nonexistent", target_files=[], checkpoint_id="test")

        assert result is None

    def test_complete_safety_operation_success(self, temp_git_repo):
        """Test complete safety operation with no failures."""
        manager = SafetySystemManager()

        # Create a checkpoint first
        checkpoint_result = manager.create_checkpoint(
            repo_path=temp_git_repo, files_to_track=[temp_git_repo / "test.py"]
        )

        result = manager.complete_safety_operation(
            repo_path=temp_git_repo,
            target_files=["test.py"],
            checkpoint_id=checkpoint_result.checkpoint_id,
            operation_context={"success": True},
        )

        assert result.success is True
        assert result.checkpoint_id == checkpoint_result.checkpoint_id
        assert result.performance_metrics is not None

    def test_complete_safety_operation_disabled_checkpoint(self, temp_git_repo):
        """Test complete safety operation with disabled checkpoint."""
        manager = SafetySystemManager()

        result = manager.complete_safety_operation(
            repo_path=temp_git_repo,
            target_files=["test.py"],
            checkpoint_id="disabled",
            operation_context={"success": True},
        )

        assert result.success is True
        assert result.failure_detection is None


class TestCreateSafetySystemManager:
    """Test safety system manager factory function."""

    def test_create_with_default_settings(self, temp_git_repo):
        """Test factory function with default settings (no config file)."""
        manager = create_safety_system_manager(project_root=temp_git_repo)

        assert isinstance(manager, SafetySystemManager)
        assert manager.config.profile == SafetyProfile.BALANCED

    def test_create_with_cli_overrides(self, temp_git_repo):
        """Test factory function with CLI overrides."""
        overrides = {"profile": "minimal", "performance_timeout_seconds": 99}
        manager = create_safety_system_manager(project_root=temp_git_repo, cli_overrides=overrides)

        assert manager.config.profile == SafetyProfile.CUSTOM
        assert manager.config.validation_level == ValidationLevel.BASIC
        assert manager.config.performance_timeout_seconds == 99

    def test_create_with_config_file(self, temp_git_repo):
        """Test factory function loading from a config file."""
        config_data = {"profile": "maximum"}
        with (temp_git_repo / ".aider-safety.yaml").open("w") as f:
            yaml.dump(config_data, f)

        manager = create_safety_system_manager(project_root=temp_git_repo)
        assert manager.config.profile == SafetyProfile.CUSTOM
        assert manager.config.validation_level == ValidationLevel.STRICT

    def test_create_with_file_and_overrides(self, temp_git_repo):
        """Test factory with file and CLI overrides."""
        config_data = {"profile": "maximum", "enable_diff_analysis": False}
        with (temp_git_repo / ".aider-safety.yaml").open("w") as f:
            yaml.dump(config_data, f)

        overrides = {"enable_diff_analysis": True, "validation_level": "basic"}
        manager = create_safety_system_manager(project_root=temp_git_repo, cli_overrides=overrides)

        assert manager.config.profile == SafetyProfile.CUSTOM
        assert manager.config.enable_diff_analysis is True  # from override
        assert manager.config.validation_level == ValidationLevel.BASIC  # from override
        assert manager.config.rollback_on_high_failures is True  # from maximum profile base


class TestIntegrationScenarios:
    """Test end-to-end integration scenarios."""

    def test_full_safety_workflow_success(self, temp_git_repo):
        """Test complete safety workflow without failures."""
        manager = create_safety_system_manager(cli_overrides={"profile": "balanced"})

        # 1. Pre-execution check
        pre_result = manager.pre_execution_check(
            working_directory=temp_git_repo,
            target_files=["test.py"],
            operation_context={
                "model": "test-model",
                "prompt": "Safe test operation",
            },
        )
        assert pre_result.is_safe

        # 2. Create checkpoint
        checkpoint_result = manager.create_checkpoint(
            repo_path=temp_git_repo, files_to_track=[temp_git_repo / "test.py"]
        )
        assert checkpoint_result.success

        # 3. Complete operation (simulating no failures)
        operation_result = manager.complete_safety_operation(
            repo_path=temp_git_repo,
            target_files=["test.py"],
            checkpoint_id=checkpoint_result.checkpoint_id,
            operation_context={"success": True, "changes_detected": True},
        )
        assert operation_result.success

    def test_disabled_safety_workflow(self):
        """Test workflow with safety system disabled via config."""
        overrides = {f.name: False for f in dataclasses.fields(SafetyConfiguration()) if f.name.startswith("enable_")}
        manager = create_safety_system_manager(cli_overrides=overrides)
        assert manager.should_bypass_safety({})

    @patch("aider_mcp_server.atoms.utils.safety_system_manager.OperationRiskAssessor")
    def test_maximum_safety_workflow_with_timeout(self, mock_assessor, temp_git_repo):
        """Test maximum safety level with performance considerations."""
        mock_assessor.return_value.assess_operation_risk.return_value = OperationRiskAssessment(
            total_score=1, risk_level=RiskLevel.LOW, factors=[], summary=""
        )
        config = SafetyConfiguration(profile=SafetyProfile.MAXIMUM)
        config.performance_timeout_seconds = 0.001  # Very short timeout
        manager = SafetySystemManager(config)

        # Pre-execution check should handle timeout
        pre_result = manager.pre_execution_check(
            working_directory=temp_git_repo,
            target_files=["test.py"] * 100,  # Many files
            operation_context={
                "model": "complex-model",
                "prompt": "Short prompt to avoid risk failure",
            },
        )

        # With bypass_on_timeout=False in maximum mode, should fail on timeout
        assert pre_result.is_safe is False
        assert "timeout" in pre_result.reason.lower()

    @patch("aider_mcp_server.atoms.utils.safety_system_manager.OperationRiskAssessor")
    def test_model_specific_risk_blocks_operation(self, mock_assessor, temp_git_repo):
        """Test that a high-risk model can block an operation in a strict profile."""
        mock_assessor.return_value.assess_operation_risk.return_value = OperationRiskAssessment(
            total_score=8, risk_level=RiskLevel.HIGH, factors=[], summary=""
        )
        config = SafetyConfiguration(profile=SafetyProfile.MAXIMUM)  # Strict profile
        config.model_specific_configs["gemini-pro"] = ModelSpecificConfiguration(risk_multiplier=1.5)
        manager = SafetySystemManager(config)

        result = manager.pre_execution_check(
            working_directory=temp_git_repo,
            target_files=["test.py"],
            operation_context={"model": "gemini-pro"},
        )

        assert result.is_safe is False
        assert result.risk_assessment.risk_level == RiskLevel.CRITICAL
        assert result.risk_assessment.total_score == 12  # 8 * 1.5
        assert "blocked due to critical risk" in result.user_message.lower()
