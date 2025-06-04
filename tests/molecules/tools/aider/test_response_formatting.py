"""
Tests for the ResponseFormatter module.
"""

import pytest
from unittest.mock import Mock

from aider_mcp_server.molecules.tools.aider.response_formatting import ResponseFormatter
from aider_mcp_server.atoms.types.streaming_types import ChangeType


class TestResponseFormatter:
    """Test cases for ResponseFormatter class."""

    def test_initialization(self):
        """Test that ResponseFormatter initializes correctly."""
        formatter = ResponseFormatter()
        assert formatter.event_coordinator is None
        assert formatter.logger is not None

        # Test with event coordinator
        mock_coordinator = Mock()
        formatter_with_coordinator = ResponseFormatter(event_coordinator=mock_coordinator)
        assert formatter_with_coordinator.event_coordinator is mock_coordinator

    def test_process_coder_results_basic(self):
        """Test basic process_coder_results functionality."""
        formatter = ResponseFormatter()
        
        # Mock the external dependencies
        with pytest.MonkeyPatch().context() as m:
            # Mock the summarize_changes function
            mock_summarize = Mock(return_value={
                "summary": "Test changes",
                "files": [{"name": "test.py", "operation": "modify", "lines_added": 5, "lines_removed": 2}],
                "stats": {"lines_added": 5, "lines_removed": 2}
            })
            m.setattr("aider_mcp_server.molecules.tools.aider.response_formatting.summarize_changes", mock_summarize)
            
            # Mock the get_file_status_summary function
            mock_file_status = Mock(return_value={
                "has_changes": True,
                "status_summary": "1 file modified",
                "files": [{"name": "test.py", "operation": "modified"}]
            })
            m.setattr("aider_mcp_server.molecules.tools.aider.response_formatting.get_file_status_summary", mock_file_status)
            
            result = formatter.process_coder_results(
                coder_exit_code=0,
                diff_output="test diff content",
                working_directory="/test/dir",
                include_diff=True
            )
            
            assert result["success"] is True
            assert result["changes_summary"]["summary"] == "Test changes"
            assert result["diff"] == "test diff content"
            assert result["is_cached_diff"] is False

    def test_handle_diff_cache_processing_no_cache(self):
        """Test diff cache processing without cache."""
        formatter = ResponseFormatter()
        
        diff_output = "test diff"
        final_diff, is_cached = formatter.handle_diff_cache_processing(
            diff_output, None, "/test/dir"
        )
        
        assert final_diff == diff_output
        assert is_cached is False

    def test_handle_diff_cache_processing_with_cache(self):
        """Test diff cache processing with cache."""
        formatter = ResponseFormatter()
        
        # Mock diff cache
        mock_cache = Mock()
        mock_cache.get_cached_diff.return_value = "cached diff content"
        
        diff_output = "original diff"
        final_diff, is_cached = formatter.handle_diff_cache_processing(
            diff_output, mock_cache, "/test/dir"
        )
        
        assert final_diff == "cached diff content"
        assert is_cached is True

    def test_map_operation_to_change_type(self):
        """Test operation to change type mapping."""
        formatter = ResponseFormatter()
        
        assert formatter._map_operation_to_change_type("create") == ChangeType.CREATED
        assert formatter._map_operation_to_change_type("modify") == ChangeType.MODIFIED
        assert formatter._map_operation_to_change_type("delete") == ChangeType.DELETED
        assert formatter._map_operation_to_change_type("rename") == ChangeType.RENAMED
        assert formatter._map_operation_to_change_type("unknown") == ChangeType.MODIFIED

    def test_determine_change_categories(self):
        """Test change category determination."""
        formatter = ResponseFormatter()
        
        # Test bug fix detection
        summary = {"summary": "Fix critical bug in authentication"}
        categories = formatter.determine_change_categories(summary)
        assert "bug_fix" in categories
        
        # Test feature addition detection
        summary = {"summary": "Add new user dashboard feature"}
        categories = formatter.determine_change_categories(summary)
        assert "feature_addition" in categories
        
        # Test refactoring detection
        summary = {"summary": "Refactor database connection logic"}
        categories = formatter.determine_change_categories(summary)
        assert "refactoring" in categories
        
        # Test general category fallback
        summary = {"summary": "Some general changes"}
        categories = formatter.determine_change_categories(summary)
        assert categories == ["general"]

    def test_estimate_complexity(self):
        """Test complexity estimation."""
        formatter = ResponseFormatter()
        
        # Simple complexity
        summary = {
            "files": ["file1.py"],
            "stats": {"lines_added": 5, "lines_removed": 3}
        }
        complexity = formatter.estimate_complexity(summary)
        assert complexity == "simple"
        
        # Moderate complexity
        summary = {
            "files": ["file1.py", "file2.py", "file3.py"],
            "stats": {"lines_added": 30, "lines_removed": 20}
        }
        complexity = formatter.estimate_complexity(summary)
        assert complexity == "moderate"
        
        # Complex complexity
        summary = {
            "files": ["file1.py", "file2.py", "file3.py", "file4.py", "file5.py", "file6.py"],
            "stats": {"lines_added": 100, "lines_removed": 50}
        }
        complexity = formatter.estimate_complexity(summary)
        assert complexity == "complex"

    def test_update_api_key_status_in_response(self):
        """Test API key status updating."""
        formatter = ResponseFormatter()
        
        response = {
            "success": True,
            "changes_summary": {},
            "file_status": {},
            "rate_limit_info": {},
            "is_cached_diff": False,
            "diff": "",
            "api_key_status": {},
        }
        
        api_key_status = {
            "available_providers": ["openai", "anthropic"],
            "missing_providers": ["vertexai"],
            "requested_provider": "openai",
            "used_provider": "openai",
            "original_model_requested": "gpt-4",
            "actual_model_used": "gpt-4",
        }
        
        formatter.update_api_key_status_in_response(response, api_key_status)
        
        assert response["api_key_status"]["available_providers"] == ["openai", "anthropic"]
        assert response["api_key_status"]["requested_provider"] == "openai"
        assert response["api_key_status"]["actual_model_used"] == "gpt-4"

    def test_cleanup_file_status_in_response(self):
        """Test file status cleanup."""
        formatter = ResponseFormatter()
        
        response = {
            "success": True,
            "changes_summary": {},
            "file_status": {
                "files": [],
                "stats": {"lines_added": 0, "lines_removed": 0, "files_modified": 1}
            },
            "rate_limit_info": {},
            "is_cached_diff": False,
            "diff": "",
            "api_key_status": {},
        }
        
        formatter.cleanup_file_status_in_response(response)
        
        # Empty files list should be removed
        assert "files" not in response["file_status"]
        # Zero values should be removed, non-zero kept
        assert "lines_added" not in response["file_status"]["stats"]
        assert "lines_removed" not in response["file_status"]["stats"]
        assert response["file_status"]["stats"]["files_modified"] == 1

    def test_get_rate_limit_encountered(self):
        """Test rate limit status extraction."""
        formatter = ResponseFormatter()
        
        # Test with rate limit encountered
        response = {
            "rate_limit_info": {"encountered": True}
        }
        assert formatter.get_rate_limit_encountered(response) is True
        
        # Test without rate limit
        response = {
            "rate_limit_info": {"encountered": False}
        }
        assert formatter.get_rate_limit_encountered(response) is False
        
        # Test with no rate limit info
        response = {}
        assert formatter.get_rate_limit_encountered(response) is False

    def test_get_fallback_used(self):
        """Test fallback usage status extraction."""
        formatter = ResponseFormatter()
        
        # Test with fallback used
        response = {
            "rate_limit_info": {"fallback_model": "gpt-3.5-turbo"}
        }
        assert formatter.get_fallback_used(response) is True
        
        # Test without fallback
        response = {
            "rate_limit_info": {"fallback_model": None}
        }
        assert formatter.get_fallback_used(response) is False
        
        # Test with no rate limit info
        response = {}
        assert formatter.get_fallback_used(response) is False