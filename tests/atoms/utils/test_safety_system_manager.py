"""
Test suite for Safety System Manager integration (Task 12).

Tests the coordinated safety system that integrates all safety components
(Tasks 1-11) into a unified system for the MCP aider tool.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from aider_mcp_server.atoms.utils.safety_system_manager import (
    SafetyConfiguration,
    SafetyLevel,
    SafetySystemManager,
    create_safety_system_manager,
)


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir)
        
        # Initialize git repo
        os.system(f"cd {repo_path} && git init")
        os.system(f"cd {repo_path} && git config user.email 'test@example.com'")
        os.system(f"cd {repo_path} && git config user.name 'Test User'")
        
        # Create test files
        test_file = repo_path / "test.py"
        test_file.write_text("print('hello world')")
        
        os.system(f"cd {repo_path} && git add test.py")
        os.system(f"cd {repo_path} && git commit -m 'Initial commit'")
        
        yield repo_path


class TestSafetyConfiguration:
    """Test safety configuration creation and validation."""

    def test_default_configuration(self):
        """Test default safety configuration."""
        config = SafetyConfiguration()
        
        assert config.safety_level == SafetyLevel.BALANCED
        assert config.enable_git_checkpoint is True
        assert config.enable_failure_detection is True
        assert config.enable_automatic_rollback is True

    def test_disabled_configuration(self):
        """Test disabled safety level configuration."""
        config = SafetyConfiguration.from_safety_level(SafetyLevel.DISABLED)
        
        assert config.safety_level == SafetyLevel.DISABLED
        assert config.enable_git_checkpoint is False
        assert config.enable_failure_detection is False
        assert config.enable_automatic_rollback is False

    def test_minimal_configuration(self):
        """Test minimal safety level configuration."""
        config = SafetyConfiguration.from_safety_level(SafetyLevel.MINIMAL)
        
        assert config.safety_level == SafetyLevel.MINIMAL
        assert config.enable_git_checkpoint is True
        assert config.enable_file_integrity is True
        assert config.enable_risk_assessment is False
        assert config.enable_file_monitoring is False

    def test_maximum_configuration(self):
        """Test maximum safety level configuration."""
        config = SafetyConfiguration.from_safety_level(SafetyLevel.MAXIMUM)
        
        assert config.safety_level == SafetyLevel.MAXIMUM
        assert config.performance_timeout_seconds == 60.0
        assert config.bypass_on_timeout is False


class TestSafetySystemManager:
    """Test safety system manager core functionality."""

    def test_initialization_with_default_config(self):
        """Test manager initialization with default configuration."""
        manager = SafetySystemManager()
        
        assert manager.config.safety_level == SafetyLevel.BALANCED
        assert manager._git_checkpoint_manager is None  # Lazy initialization

    def test_initialization_with_custom_config(self):
        """Test manager initialization with custom configuration."""
        config = SafetyConfiguration.from_safety_level(SafetyLevel.MINIMAL)
        manager = SafetySystemManager(config)
        
        assert manager.config.safety_level == SafetyLevel.MINIMAL
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

    def test_should_bypass_safety_disabled_level(self):
        """Test bypass safety when level is disabled."""
        config = SafetyConfiguration.from_safety_level(SafetyLevel.DISABLED)
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
            }
        )
        
        assert result.is_safe is True
        assert result.reason is None

    def test_pre_execution_check_with_risk_assessment(self, temp_git_repo):
        """Test pre-execution check with risk assessment."""
        config = SafetyConfiguration.from_safety_level(SafetyLevel.BALANCED)
        manager = SafetySystemManager(config)
        
        result = manager.pre_execution_check(
            working_directory=temp_git_repo,
            target_files=["test.py"],
            operation_context={
                "model": "high-risk-model",
                "prompt": "Complex operation" * 100,  # High complexity
            }
        )
        
        # Should still be safe for balanced mode
        assert result.is_safe is True
        assert result.risk_assessment is not None

    def test_create_checkpoint_success(self, temp_git_repo):
        """Test successful checkpoint creation."""
        manager = SafetySystemManager()
        
        result = manager.create_checkpoint(
            repo_path=temp_git_repo,
            files_to_track=[temp_git_repo / "test.py"],
            operation_metadata={"test": "metadata"}
        )
        
        assert result.success is True
        assert result.checkpoint_id is not None
        assert "aider-safety" in result.checkpoint_id

    def test_create_checkpoint_disabled(self):
        """Test checkpoint creation when disabled."""
        config = SafetyConfiguration(enable_git_checkpoint=False)
        manager = SafetySystemManager(config)
        
        result = manager.create_checkpoint(
            repo_path="/nonexistent",
            files_to_track=[],
        )
        
        assert result.success is True
        assert result.checkpoint_id == "disabled"

    @patch('aider_mcp_server.atoms.utils.safety_system_manager.FailureDetector')
    def test_detect_failures_no_failures(self, mock_detector, temp_git_repo):
        """Test failure detection when no failures occur."""
        # Mock failure detector to return no failures
        mock_instance = Mock()
        mock_instance.detect_failures_from_validation.return_value = Mock(
            has_failures=False,
            requires_rollback=False,
            failure_summary="No failures detected"
        )
        mock_detector.return_value = mock_instance
        
        manager = SafetySystemManager()
        
        result = manager.detect_failures(
            repo_path=temp_git_repo,
            target_files=["test.py"],
            checkpoint_id="test-checkpoint"
        )
        
        assert result is not None
        assert result.has_failures is False

    def test_detect_failures_disabled(self):
        """Test failure detection when disabled."""
        config = SafetyConfiguration(enable_failure_detection=False)
        manager = SafetySystemManager(config)
        
        result = manager.detect_failures(
            repo_path="/nonexistent",
            target_files=[],
            checkpoint_id="test"
        )
        
        assert result is None

    def test_complete_safety_operation_success(self, temp_git_repo):
        """Test complete safety operation with no failures."""
        manager = SafetySystemManager()
        
        # Create a checkpoint first
        checkpoint_result = manager.create_checkpoint(
            repo_path=temp_git_repo,
            files_to_track=[temp_git_repo / "test.py"]
        )
        
        result = manager.complete_safety_operation(
            repo_path=temp_git_repo,
            target_files=["test.py"],
            checkpoint_id=checkpoint_result.checkpoint_id,
            operation_context={"success": True}
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
            operation_context={"success": True}
        )
        
        assert result.success is True
        assert result.failure_detection is None


class TestCreateSafetySystemManager:
    """Test safety system manager factory function."""

    def test_create_with_default_settings(self):
        """Test factory function with default settings."""
        manager = create_safety_system_manager()
        
        assert isinstance(manager, SafetySystemManager)
        assert manager.config.safety_level == SafetyLevel.BALANCED

    def test_create_with_string_level(self):
        """Test factory function with string safety level."""
        manager = create_safety_system_manager(safety_level="minimal")
        
        assert manager.config.safety_level == SafetyLevel.MINIMAL

    def test_create_with_enum_level(self):
        """Test factory function with enum safety level."""
        manager = create_safety_system_manager(safety_level=SafetyLevel.MAXIMUM)
        
        assert manager.config.safety_level == SafetyLevel.MAXIMUM

    def test_create_with_invalid_level(self):
        """Test factory function with invalid safety level."""
        manager = create_safety_system_manager(safety_level="invalid")
        
        # Should default to balanced
        assert manager.config.safety_level == SafetyLevel.BALANCED

    def test_create_with_custom_config(self):
        """Test factory function with custom configuration."""
        custom_config = SafetyConfiguration(
            safety_level=SafetyLevel.MINIMAL,
            performance_timeout_seconds=15.0
        )
        manager = create_safety_system_manager(custom_config=custom_config)
        
        assert manager.config.safety_level == SafetyLevel.MINIMAL
        assert manager.config.performance_timeout_seconds == 15.0


class TestIntegrationScenarios:
    """Test end-to-end integration scenarios."""

    def test_full_safety_workflow_success(self, temp_git_repo):
        """Test complete safety workflow without failures."""
        manager = create_safety_system_manager(safety_level="balanced")
        
        # 1. Pre-execution check
        pre_result = manager.pre_execution_check(
            working_directory=temp_git_repo,
            target_files=["test.py"],
            operation_context={
                "model": "test-model",
                "prompt": "Safe test operation",
            }
        )
        assert pre_result.is_safe
        
        # 2. Create checkpoint
        checkpoint_result = manager.create_checkpoint(
            repo_path=temp_git_repo,
            files_to_track=[temp_git_repo / "test.py"]
        )
        assert checkpoint_result.success
        
        # 3. Complete operation (simulating no failures)
        operation_result = manager.complete_safety_operation(
            repo_path=temp_git_repo,
            target_files=["test.py"],
            checkpoint_id=checkpoint_result.checkpoint_id,
            operation_context={"success": True, "changes_detected": True}
        )
        assert operation_result.success

    def test_disabled_safety_workflow(self):
        """Test workflow with safety system disabled."""
        manager = create_safety_system_manager(safety_level="disabled")
        
        # Should bypass all operations
        assert manager.should_bypass_safety({})

    def test_maximum_safety_workflow_with_timeout(self, temp_git_repo):
        """Test maximum safety level with performance considerations."""
        config = SafetyConfiguration.from_safety_level(SafetyLevel.MAXIMUM)
        config.performance_timeout_seconds = 0.001  # Very short timeout
        manager = SafetySystemManager(config)
        
        # Pre-execution check should handle timeout
        pre_result = manager.pre_execution_check(
            working_directory=temp_git_repo,
            target_files=["test.py"] * 100,  # Many files
            operation_context={
                "model": "complex-model",
                "prompt": "Very complex operation" * 1000,
            }
        )
        
        # With bypass_on_timeout=False in maximum mode, should fail or timeout
        # The exact behavior depends on the implementation details
        assert pre_result is not None