import pytest
import json
from unittest.mock import patch, MagicMock

from src.aider_mcp_server.server import process_aider_ai_code_request, handle_request
from src.aider_mcp_server.atoms.utils import DEFAULT_AIDER_TIMEOUT, DEFAULT_EDITOR_MODEL

# Mock dependencies
@pytest.fixture
def mock_code_with_aider():
    with patch('src.aider_mcp_server.server.code_with_aider') as mock:
        mock.return_value = json.dumps({"success": True, "diff": "mock diff"})
        yield mock

@pytest.fixture
def mock_git_repo():
    with patch('src.aider_mcp_server.server.is_git_repository', return_value=(True, None)):
        yield

@pytest.fixture
def mock_chdir():
    with patch('os.chdir'):
        yield

# API Tests
def test_api_accepts_timeout_parameter(mock_code_with_aider, mock_git_repo, mock_chdir):
    """Test that the server API accepts timeout_seconds parameter and passes it to code_with_aider."""
    custom_timeout = 60
    
    # Create a mock request with timeout parameter
    request = {
        "name": "aider_ai_code",
        "parameters": {
            "ai_coding_prompt": "test prompt",
            "relative_editable_files": ["test.py"],
            "timeout_seconds": custom_timeout
        }
    }
    
    # Call handle_request
    handle_request(
        request=request,
        current_working_dir="/fake/repo",
        editor_model=DEFAULT_EDITOR_MODEL,
        default_timeout=DEFAULT_AIDER_TIMEOUT
    )
    
    # Verify code_with_aider was called with the custom timeout
    mock_code_with_aider.assert_called_once()
    call_args, call_kwargs = mock_code_with_aider.call_args
    assert call_kwargs.get("timeout_seconds") == custom_timeout

def test_api_uses_default_timeout(mock_code_with_aider, mock_git_repo, mock_chdir):
    """Test that the server API uses default_timeout when no timeout_seconds is provided."""
    # Create a mock request without timeout parameter
    request = {
        "name": "aider_ai_code",
        "parameters": {
            "ai_coding_prompt": "test prompt",
            "relative_editable_files": ["test.py"]
        }
    }
    
    # Call handle_request with a specific default_timeout
    custom_default = 150
    handle_request(
        request=request,
        current_working_dir="/fake/repo",
        editor_model=DEFAULT_EDITOR_MODEL,
        default_timeout=custom_default
    )
    
    # Verify code_with_aider was called with the default_timeout
    mock_code_with_aider.assert_called_once()
    call_args, call_kwargs = mock_code_with_aider.call_args
    assert call_kwargs.get("timeout_seconds") == custom_default

def test_api_sanitizes_invalid_timeout(mock_code_with_aider, mock_git_repo, mock_chdir):
    """Test that the server API properly sanitizes invalid timeout values."""
    # Create a mock request with invalid timeout parameter
    request = {
        "name": "aider_ai_code",
        "parameters": {
            "ai_coding_prompt": "test prompt",
            "relative_editable_files": ["test.py"],
            "timeout_seconds": -10  # Invalid timeout
        }
    }
    
    # Call handle_request
    custom_default = 150
    handle_request(
        request=request,
        current_working_dir="/fake/repo",
        editor_model=DEFAULT_EDITOR_MODEL,
        default_timeout=custom_default
    )
    
    # Verify code_with_aider was called with the default_timeout (sanitized)
    mock_code_with_aider.assert_called_once()
    call_args, call_kwargs = mock_code_with_aider.call_args
    assert call_kwargs.get("timeout_seconds") == custom_default

def test_api_timeout_error_response():
    """Test that the server API returns proper error response on timeout."""
    # Mock code_with_aider to return a timeout error response
    timeout_response = json.dumps({
        "success": False,
        "diff": "Error: Aider process timed out after 10 seconds."
    })
    
    with patch('src.aider_mcp_server.server.code_with_aider', return_value=timeout_response):
        with patch('src.aider_mcp_server.server.is_git_repository', return_value=(True, None)):
            with patch('os.chdir'):
                # Create a mock request
                request = {
                    "name": "aider_ai_code",
                    "parameters": {
                        "ai_coding_prompt": "test prompt",
                        "relative_editable_files": ["test.py"],
                        "timeout_seconds": 10
                    }
                }
                
                # Call handle_request
                response = handle_request(
                    request=request,
                    current_working_dir="/fake/repo",
                    editor_model=DEFAULT_EDITOR_MODEL,
                    default_timeout=DEFAULT_AIDER_TIMEOUT
                )
                
                # Verify the response
                assert response["success"] is False
                assert "timed out" in response["diff"]
