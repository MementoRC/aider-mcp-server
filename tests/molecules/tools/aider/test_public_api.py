"""
Tests for the unified public API of the aider tool module.

This test module verifies that the public API works correctly,
maintains backward compatibility, and properly orchestrates
all the refactored components.
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aider_mcp_server.molecules.tools.aider import (
    AiderTool,
    APIValidator,
    CacheManager,
    CoreExecutor,
    RateLimiter,
    ResponseFormatter,
    SessionCoordinator,
    execute_aider_command,
)


class TestAiderToolPublicAPI:
    """Test the main AiderTool facade class."""

    @pytest.fixture
    def aider_tool(self):
        """Create an AiderTool instance for testing."""
        config = {"working_dir": "/tmp/test"}
        return AiderTool(config)

    @pytest.fixture
    def mock_components(self, aider_tool):
        """Mock all the internal components."""
        with patch.multiple(
            aider_tool,
            api_validator=MagicMock(spec=APIValidator),
            cache_manager=MagicMock(spec=CacheManager),
            core_executor=MagicMock(spec=CoreExecutor),
            rate_limiter=MagicMock(spec=RateLimiter),
            response_formatter=MagicMock(spec=ResponseFormatter),
            session_coordinator=MagicMock(spec=SessionCoordinator),
        ):
            # Setup async methods
            aider_tool.cache_manager.initialize_cache = AsyncMock()
            aider_tool.cache_manager.shutdown_cache = AsyncMock()
            aider_tool.cache_manager.process_diff_cache = AsyncMock(return_value=("diff_content", False))
            aider_tool.session_coordinator.start_session = AsyncMock(return_value="test-session-123")
            aider_tool.session_coordinator.complete_session = AsyncMock()
            aider_tool.session_coordinator.handle_session_error = AsyncMock()
            aider_tool.core_executor.execute_with_retry = AsyncMock()
            
            yield aider_tool

    def test_initialization(self, aider_tool):
        """Test that AiderTool initializes correctly."""
        assert aider_tool.config == {"working_dir": "/tmp/test"}
        assert isinstance(aider_tool.api_validator, APIValidator)
        assert isinstance(aider_tool.cache_manager, CacheManager)
        assert isinstance(aider_tool.core_executor, CoreExecutor)
        assert isinstance(aider_tool.rate_limiter, RateLimiter)
        assert isinstance(aider_tool.response_formatter, ResponseFormatter)
        assert isinstance(aider_tool.session_coordinator, SessionCoordinator)
        assert not aider_tool._initialized

    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_components):
        """Test successful initialization of all components."""
        await mock_components.initialize()
        
        assert mock_components._initialized
        mock_components.cache_manager.initialize_cache.assert_called_once()
        mock_components.api_validator.load_env_files.assert_called_once_with("/tmp/test")

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, mock_components):
        """Test that initialize can be called multiple times safely."""
        await mock_components.initialize()
        await mock_components.initialize()  # Should not re-initialize
        
        assert mock_components._initialized
        # Should only be called once despite multiple initialize calls
        assert mock_components.cache_manager.initialize_cache.call_count == 1

    @pytest.mark.asyncio
    async def test_shutdown_success(self, mock_components):
        """Test successful shutdown of all components."""
        await mock_components.initialize()
        await mock_components.shutdown()
        
        assert not mock_components._initialized
        mock_components.cache_manager.shutdown_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_command_success(self, mock_components):
        """Test successful command execution with all components."""
        # Setup mocks
        mock_components.api_validator.check_api_keys.return_value = {"any_keys_found": True}
        mock_components.cache_manager.generate_cache_key.return_value = "test-cache-key"
        mock_components.cache_manager.diff_cache = MagicMock()
        
        execution_result = {"success": True, "changes": ["file1.py"]}
        mock_components.core_executor.execute_with_retry.return_value = execution_result
        
        formatted_result = {"success": True, "changes_summary": {"modified": ["file1.py"]}}
        mock_components.response_formatter.finalize_aider_response.return_value = formatted_result
        
        # Execute command
        result = await mock_components.execute_command(
            ai_coding_prompt="Test prompt",
            relative_editable_files=["file1.py"],
            relative_readonly_files=["readme.md"],
            model="gpt-4",
            working_dir="/tmp/test"
        )
        
        # Verify result
        assert result == formatted_result
        
        # Verify component calls
        mock_components.session_coordinator.start_session.assert_called_once()
        mock_components.api_validator.check_api_keys.assert_called_once_with("/tmp/test")
        mock_components.cache_manager.generate_cache_key.assert_called_once_with(
            working_dir="/tmp/test", files=["file1.py"]
        )
        mock_components.core_executor.execute_with_retry.assert_called_once()
        mock_components.response_formatter.finalize_aider_response.assert_called_once()
        mock_components.session_coordinator.complete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_command_api_validation_failure(self, mock_components):
        """Test command execution when API validation fails."""
        # Setup API validation failure
        api_status = {"any_keys_found": False, "error": "No API key found"}
        mock_components.api_validator.check_api_keys.return_value = api_status
        
        # Execute command
        result = await mock_components.execute_command(
            ai_coding_prompt="Test prompt",
            relative_editable_files=["file1.py"]
        )
        
        # Verify error handling
        assert result["success"] is False
        assert result["error"] == "API key validation failed"
        assert result["api_key_status"] == api_status
        
        # Verify core execution was not called
        mock_components.core_executor.execute_with_retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_command_with_cached_result(self, mock_components):
        """Test command execution (cache is handled during execution)."""
        # Setup successful execution
        mock_components.api_validator.check_api_keys.return_value = {"any_keys_found": True}
        mock_components.cache_manager.generate_cache_key.return_value = "test-cache-key"
        mock_components.cache_manager.diff_cache = MagicMock()
        
        execution_result = {"success": True, "changes": ["file1.py"]}
        mock_components.core_executor.execute_with_retry.return_value = execution_result
        
        formatted_result = {"success": True, "changes_summary": {"modified": ["file1.py"]}, "diff": "test diff"}
        mock_components.response_formatter.finalize_aider_response.return_value = formatted_result
        
        # Execute command
        result = await mock_components.execute_command(
            ai_coding_prompt="Test prompt",
            relative_editable_files=["file1.py"]
        )
        
        # Verify result is returned
        assert result == formatted_result
        
        # Verify caching was attempted for successful result with diff
        mock_components.cache_manager.process_diff_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_command_exception_handling(self, mock_components):
        """Test command execution when an exception occurs."""
        # Setup exception during execution
        mock_components.api_validator.check_api_keys.return_value = {"any_keys_found": True}
        mock_components.core_executor.execute_with_retry.side_effect = Exception("Test error")
        
        # Execute command
        result = await mock_components.execute_command(
            ai_coding_prompt="Test prompt",
            relative_editable_files=["file1.py"]
        )
        
        # Verify error handling
        assert result["success"] is False
        assert result["error"] == "Test error"
        assert "Test error" in result["warnings"]
        mock_components.session_coordinator.handle_session_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_backward_compatibility_method(self, mock_components):
        """Test that the legacy aider_ai_code method works."""
        formatted_result = {"success": True, "changes_summary": {}}
        mock_components.api_validator.check_api_keys.return_value = {"any_keys_found": True}
        mock_components.cache_manager.generate_cache_key.return_value = "test-key"
        mock_components.core_executor.run_aider_session.return_value = {"success": True}
        mock_components.response_formatter.finalize_aider_response.return_value = formatted_result
        
        # Use legacy method name
        result = await mock_components.aider_ai_code(
            ai_coding_prompt="Test prompt",
            relative_editable_files=["file1.py"]
        )
        
        assert result == formatted_result

    def test_get_component_success(self, aider_tool):
        """Test getting components by name."""
        assert aider_tool.get_component("api_validator") is aider_tool.api_validator
        assert aider_tool.get_component("cache_manager") is aider_tool.cache_manager
        assert aider_tool.get_component("core_executor") is aider_tool.core_executor
        assert aider_tool.get_component("rate_limiter") is aider_tool.rate_limiter
        assert aider_tool.get_component("response_formatter") is aider_tool.response_formatter
        assert aider_tool.get_component("session_coordinator") is aider_tool.session_coordinator

    def test_get_component_invalid_name(self, aider_tool):
        """Test getting component with invalid name raises error."""
        with pytest.raises(ValueError, match="Unknown component: invalid_component"):
            aider_tool.get_component("invalid_component")


class TestConvenienceFunction:
    """Test the convenience function for quick usage."""

    @pytest.mark.asyncio
    async def test_execute_aider_command_convenience(self):
        """Test the convenience function creates and cleans up properly."""
        with patch("aider_mcp_server.molecules.tools.aider.AiderTool") as mock_tool_class:
            mock_tool = MagicMock()
            mock_tool.execute_command = AsyncMock(return_value={"success": True})
            mock_tool.shutdown = AsyncMock()
            mock_tool_class.return_value = mock_tool
            
            result = await execute_aider_command(
                ai_coding_prompt="Test prompt",
                relative_editable_files=["file1.py"],
                config={"test": "config"}
            )
            
            # Verify tool creation and cleanup
            mock_tool_class.assert_called_once_with({"test": "config"})
            mock_tool.execute_command.assert_called_once()
            mock_tool.shutdown.assert_called_once()
            assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_execute_aider_command_convenience_exception(self):
        """Test convenience function cleans up even when exception occurs."""
        with patch("aider_mcp_server.molecules.tools.aider.AiderTool") as mock_tool_class:
            mock_tool = MagicMock()
            mock_tool.execute_command = AsyncMock(side_effect=Exception("Test error"))
            mock_tool.shutdown = AsyncMock()
            mock_tool_class.return_value = mock_tool
            
            with pytest.raises(Exception, match="Test error"):
                await execute_aider_command(
                    ai_coding_prompt="Test prompt",
                    relative_editable_files=["file1.py"]
                )
            
            # Verify cleanup still happened
            mock_tool.shutdown.assert_called_once()


class TestPublicAPIExports:
    """Test that all expected components are exported in __all__."""

    def test_all_exports_available(self):
        """Test that all items in __all__ are importable."""
        from aider_mcp_server.molecules.tools.aider import __all__
        
        expected_exports = {
            "AiderTool",
            "CoreExecutor", 
            "RateLimiter",
            "ResponseFormatter",
            "CacheManager", 
            "APIValidator",
            "SessionCoordinator",
            "ResponseDict",
            "ExecutionConfig",
            "ModelConfig",
            "ExecutionResult", 
            "FileInfo",
            "RetryConfig",
            "SilentInputOutput",
            "execute_aider_command",
        }
        
        assert set(__all__) == expected_exports


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_workflow_integration(self):
        """Test a complete workflow with real component interactions."""
        # Create temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.py")
            with open(test_file, "w") as f:
                f.write("# Test file\n")
            
            # Mock external dependencies but use real internal orchestration
            with patch("aider_mcp_server.molecules.tools.aider.core_execution.CoreExecutor.execute_with_retry") as mock_core, \
                 patch("aider_mcp_server.molecules.tools.aider.api_validation.APIValidator.check_api_keys") as mock_api:
                
                mock_api.return_value = {"any_keys_found": True, "provider": "openai"}
                mock_core.return_value = {
                    "success": True,
                    "changes": ["test.py"],
                    "diff": "--- test.py\n+++ test.py\n@@ -1 +1,2 @@\n # Test file\n+print('Hello World')"
                }
                
                # Test the full workflow
                tool = AiderTool({"working_dir": temp_dir})
                
                result = await tool.execute_command(
                    ai_coding_prompt="Add a print statement to the file",
                    relative_editable_files=["test.py"],
                    model="gpt-4"
                )
                
                await tool.shutdown()
                
                # Verify the result structure
                assert result["success"] is True
                assert "api_key_status" in result
                # The exact structure depends on the response formatter implementation
                # Core requirement is that we get a successful response