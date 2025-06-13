"""
Test safety system integration with AiderTool.

This module tests the integration of the safety system with the refactored
AiderTool to ensure proper safety workflow execution and bypass functionality.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aider_mcp_server.molecules.tools.aider import AiderTool


class TestAiderToolSafetyIntegration:
    """Test safety system integration with AiderTool."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_safety_manager(self):
        """Create a mock safety system manager."""
        manager = MagicMock()
        manager.should_bypass_safety.return_value = False
        manager.config.safety_level.value = "balanced"

        # Mock pre-execution check
        pre_check = MagicMock()
        pre_check.is_safe = True
        pre_check.reason = None
        pre_check.user_message = None
        pre_check.details = None
        manager.pre_execution_check.return_value = pre_check

        # Mock checkpoint creation
        checkpoint_result = MagicMock()
        checkpoint_result.success = True
        checkpoint_result.checkpoint_id = "test-checkpoint-123"
        checkpoint_result.error_message = None
        manager.create_checkpoint.return_value = checkpoint_result

        # Mock safety operation completion
        safety_result = MagicMock()
        safety_result.success = True
        safety_result.failure_detection = None
        safety_result.rollback_result = None
        safety_result.recovery_guidance = None
        safety_result.performance_metrics = {"total_duration": 0.1}
        manager.complete_safety_operation.return_value = safety_result

        return manager

    @pytest.mark.asyncio
    async def test_bypass_safety_via_parameter(self, temp_dir):
        """Test that safety can be bypassed via parameter."""
        tool = AiderTool()

        with patch.object(tool, "_execute_without_safety", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"success": True, "test": "result"}

            result = await tool.execute_command(
                ai_coding_prompt="Test prompt",
                relative_editable_files=["test.py"],
                working_dir=str(temp_dir),
                bypass_safety=True,
            )

            assert result["success"] is True
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_bypass_safety_via_environment(self, temp_dir):
        """Test that safety can be bypassed via environment variable."""
        tool = AiderTool()

        with patch.dict(os.environ, {"AIDER_BYPASS_SAFETY": "1"}):
            with patch.object(tool, "_execute_without_safety", new_callable=AsyncMock) as mock_execute:
                mock_execute.return_value = {"success": True, "test": "result"}

                result = await tool.execute_command(
                    ai_coding_prompt="Test prompt",
                    relative_editable_files=["test.py"],
                    working_dir=str(temp_dir),
                )

                assert result["success"] is True
                mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_safety_system_disabled_level(self, temp_dir):
        """Test that disabled safety level bypasses safety system."""
        tool = AiderTool()

        with patch.object(tool, "_get_safety_manager") as mock_get_manager:
            # Mock safety manager with disabled level
            mock_manager = MagicMock()
            mock_manager.should_bypass_safety.return_value = True
            mock_get_manager.return_value = mock_manager

            with patch.object(tool, "_execute_without_safety", new_callable=AsyncMock) as mock_execute:
                mock_execute.return_value = {"success": True, "test": "result"}

                result = await tool.execute_command(
                    ai_coding_prompt="Test prompt",
                    relative_editable_files=["test.py"],
                    working_dir=str(temp_dir),
                    safety_level="disabled",
                )

                assert result["success"] is True
                mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_safety_system_pre_execution_failure(self, temp_dir):
        """Test safety system pre-execution check failure."""
        tool = AiderTool()

        # Mock git status to succeed (simulate git repository)
        with patch("subprocess.run") as mock_git:
            mock_git.return_value = None  # git status succeeds

            with patch.object(tool, "_get_safety_manager") as mock_get_manager:
                # Mock safety manager with pre-execution failure
                mock_manager = MagicMock()
                mock_manager.should_bypass_safety.return_value = False

                pre_check = MagicMock()
                pre_check.is_safe = False
                pre_check.reason = "High risk operation"
                pre_check.user_message = "Operation blocked due to high risk"
                pre_check.details = {"risk_score": 8}
                mock_manager.pre_execution_check.return_value = pre_check

                mock_get_manager.return_value = mock_manager

                result = await tool.execute_command(
                    ai_coding_prompt="Dangerous prompt",
                    relative_editable_files=["test.py"],
                    working_dir=str(temp_dir),
                )

                assert result["success"] is False
                assert result["error"] == "Safety check failed"
                assert "Operation blocked due to high risk" in result["warnings"]

    @pytest.mark.asyncio
    async def test_safety_system_successful_execution(self, temp_dir, mock_safety_manager):
        """Test successful execution with safety system enabled in git repository."""
        tool = AiderTool()

        # Mock git status to succeed (simulate git repository)
        with patch("subprocess.run") as mock_git:
            mock_git.return_value = None  # git status succeeds

            with patch.object(tool, "_get_safety_manager") as mock_get_manager:
                mock_get_manager.return_value = mock_safety_manager

                with patch.object(tool, "_execute_without_safety", new_callable=AsyncMock) as mock_execute:
                    mock_execute.return_value = {
                        "success": True,
                        "changes_summary": {},
                        "file_status": {},
                    }

                    result = await tool.execute_command(
                        ai_coding_prompt="Safe prompt",
                        relative_editable_files=["test.py"],
                        working_dir=str(temp_dir),
                    )

                    assert result["success"] is True
                    assert "safety_status" in result
                    assert result["safety_status"]["enabled"] is True
                    assert result["safety_status"]["level"] == "balanced"
                    assert result["safety_status"]["checkpoint_id"] == "test-checkpoint-123"

    @pytest.mark.asyncio
    async def test_safety_system_fallback_on_error(self, temp_dir):
        """Test fallback to standard execution when safety system fails."""
        tool = AiderTool()

        # Mock git status to succeed (simulate git repository)
        with patch("subprocess.run") as mock_git:
            mock_git.return_value = None  # git status succeeds

            with patch.object(tool, "_get_safety_manager") as mock_get_manager:
                # Mock safety manager that raises an exception
                mock_manager = MagicMock()
                mock_manager.should_bypass_safety.return_value = False
                mock_manager.pre_execution_check.side_effect = Exception("Safety system error")
                mock_get_manager.return_value = mock_manager

                with patch.object(tool, "_execute_without_safety", new_callable=AsyncMock) as mock_execute:
                    mock_execute.return_value = {
                        "success": True,
                        "changes_summary": {},
                        "file_status": {},
                    }

                    result = await tool.execute_command(
                        ai_coding_prompt="Test prompt",
                        relative_editable_files=["test.py"],
                        working_dir=str(temp_dir),
                    )

                    assert result["success"] is True
                    assert "safety_status" in result
                    assert result["safety_status"]["enabled"] is False
                    assert result["safety_status"]["fallback_execution"] is True
                    assert any("Safety system failed" in warning for warning in result.get("warnings", []))

    @pytest.mark.asyncio
    async def test_safety_system_bypassed_non_git_repository(self, temp_dir):
        """Test safety system is bypassed in non-git repositories."""
        tool = AiderTool()

        with patch.object(tool, "_execute_without_safety", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "success": True,
                "changes_summary": {},
                "file_status": {},
            }

            result = await tool.execute_command(
                ai_coding_prompt="Test prompt",
                relative_editable_files=["test.py"],
                working_dir=str(temp_dir),
            )

            assert result["success"] is True
            # Should not have safety_status since it was bypassed
            assert "safety_status" not in result
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_safety_system_rollback_triggered(self, temp_dir):
        """Test safety system rollback when failures are detected."""
        tool = AiderTool()

        # Mock git status to succeed (simulate git repository)
        with patch("subprocess.run") as mock_git:
            mock_git.return_value = None  # git status succeeds

            with patch.object(tool, "_get_safety_manager") as mock_get_manager:
                # Mock safety manager with rollback scenario
                mock_manager = MagicMock()
                mock_manager.should_bypass_safety.return_value = False
                mock_manager.config.safety_level.value = "balanced"

                # Mock pre-execution check (passes)
                pre_check = MagicMock()
                pre_check.is_safe = True
                mock_manager.pre_execution_check.return_value = pre_check

                # Mock checkpoint creation (succeeds)
                checkpoint_result = MagicMock()
                checkpoint_result.success = True
                checkpoint_result.checkpoint_id = "test-checkpoint-123"
                mock_manager.create_checkpoint.return_value = checkpoint_result

                # Mock safety operation completion (triggers rollback)
                safety_result = MagicMock()
                safety_result.success = False
                safety_result.rollback_result = MagicMock()
                safety_result.rollback_result.success = True
                safety_result.recovery_guidance = MagicMock()
                safety_result.recovery_guidance.total_recommendations = 3
                mock_manager.complete_safety_operation.return_value = safety_result

                mock_get_manager.return_value = mock_manager

                with patch.object(tool, "_execute_without_safety", new_callable=AsyncMock) as mock_execute:
                    mock_execute.return_value = {
                        "success": True,
                        "changes_summary": {},
                        "file_status": {},
                    }

                    result = await tool.execute_command(
                        ai_coding_prompt="Test prompt",
                        relative_editable_files=["test.py"],
                        working_dir=str(temp_dir),
                    )

                    # After rollback, the operation should be marked as failed
                    assert result["success"] is False
                    assert result["error"] == "Safety system triggered rollback due to failures"
                    assert "safety_details" in result
                    assert "Recovery guidance available" in str(result.get("warnings", []))

    @pytest.mark.asyncio
    async def test_backward_compatibility_legacy_method(self, temp_dir):
        """Test that the legacy aider_ai_code method still works."""
        tool = AiderTool()

        with patch.object(tool, "execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"success": True, "test": "result"}

            result = await tool.aider_ai_code(
                ai_coding_prompt="Test prompt",
                relative_editable_files=["test.py"],
                working_dir=str(temp_dir),
                bypass_safety=True,
            )

            assert result["success"] is True
            mock_execute.assert_called_once_with(
                ai_coding_prompt="Test prompt",
                relative_editable_files=["test.py"],
                relative_readonly_files=None,
                working_dir=str(temp_dir),
                bypass_safety=True,
            )

    def test_get_component_access(self):
        """Test that individual components can be accessed."""
        tool = AiderTool()

        # Test valid component access
        api_validator = tool.get_component("api_validator")
        assert api_validator is not None

        cache_manager = tool.get_component("cache_manager")
        assert cache_manager is not None

        # Test invalid component access
        with pytest.raises(ValueError, match="Unknown component"):
            tool.get_component("invalid_component")

    def test_safety_manager_lazy_initialization(self):
        """Test that safety manager is initialized lazily."""
        tool = AiderTool()

        # Safety manager should be None initially
        assert tool._safety_manager is None

        # Get safety manager with default settings
        manager1 = tool._get_safety_manager("/tmp", safety_level="balanced")
        assert manager1 is not None
        assert tool._safety_manager is manager1

        # Second call should return the same instance
        manager2 = tool._get_safety_manager("/tmp", safety_level="maximum")
        assert manager2 is manager1  # Same instance due to lazy initialization

    @pytest.mark.asyncio
    async def test_convenience_function(self, temp_dir):
        """Test the convenience function for one-time execution."""
        from aider_mcp_server.molecules.tools.aider import execute_aider_command

        with patch("aider_mcp_server.molecules.tools.aider.AiderTool") as mock_tool_class:
            mock_tool = MagicMock()
            mock_tool.execute_command = AsyncMock(return_value={"success": True})
            mock_tool.shutdown = AsyncMock()
            mock_tool_class.return_value = mock_tool

            result = await execute_aider_command(
                ai_coding_prompt="Test prompt",
                relative_editable_files=["test.py"],
                working_dir=str(temp_dir),
                bypass_safety=True,
            )

            assert result["success"] is True
            mock_tool.execute_command.assert_called_once()
            mock_tool.shutdown.assert_called_once()
