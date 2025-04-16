import json
import pytest
from unittest.mock import patch, MagicMock
from concurrent.futures import TimeoutError

from aider_mcp_server.server import process_aider_ai_code_request
from aider_mcp_server.atoms.utils import DEFAULT_AIDER_TIMEOUT, DEFAULT_EDITOR_MODEL

# Mock git repository check to always return True
@pytest.fixture(autouse=True)
def mock_git_check():
    with patch('aider_mcp_server.server.is_git_repository', return_value=(True, None)) as mock:
        yield mock

# Mock os.chdir as it's not relevant for these unit tests
@pytest.fixture(autouse=True)
def mock_chdir():
    with patch('os.chdir') as mock:
        yield mock

# Mock the actual code_with_aider function
@pytest.fixture
def mock_code_with_aider():
    with patch('aider_mcp_server.server.code_with_aider') as mock:
        # Default mock behavior: return success
        mock.return_value = json.dumps({"success": True, "diff": "mock diff"})
        yield mock

# --- Test Cases ---

def test_default_timeout_used(mock_code_with_aider):
    """Verify code_with_aider is called with DEFAULT_AIDER_TIMEOUT when none is specified."""
    params = {
        "ai_coding_prompt": "test prompt",
        "relative_editable_files": ["file1.py"],
    }
    current_working_dir = "/fake/repo"
    editor_model = DEFAULT_EDITOR_MODEL
    default_timeout = DEFAULT_AIDER_TIMEOUT

    process_aider_ai_code_request(params, editor_model, current_working_dir, default_timeout)

    mock_code_with_aider.assert_called_once()
    call_args, call_kwargs = mock_code_with_aider.call_args
    assert call_kwargs.get("timeout_seconds") == DEFAULT_AIDER_TIMEOUT

def test_custom_timeout_used(mock_code_with_aider):
    """Verify code_with_aider is called with the custom timeout specified in the request."""
    custom_timeout = 120
    params = {
        "ai_coding_prompt": "test prompt",
        "relative_editable_files": ["file1.py"],
        "timeout_seconds": custom_timeout,
    }
    current_working_dir = "/fake/repo"
    editor_model = DEFAULT_EDITOR_MODEL
    default_timeout = DEFAULT_AIDER_TIMEOUT # This shouldn't be used

    process_aider_ai_code_request(params, editor_model, current_working_dir, default_timeout)

    mock_code_with_aider.assert_called_once()
    call_args, call_kwargs = mock_code_with_aider.call_args
    assert call_kwargs.get("timeout_seconds") == custom_timeout

@pytest.mark.parametrize("invalid_timeout", [-10, 0, "not_a_number", None, 10.5])
def test_invalid_timeout_uses_default(mock_code_with_aider, invalid_timeout):
    """Verify default timeout is used if the provided timeout is invalid."""
    params = {
        "ai_coding_prompt": "test prompt",
        "relative_editable_files": ["file1.py"],
    }
    # Only add timeout_seconds if it's not None, as None is handled by default logic
    if invalid_timeout is not None:
         params["timeout_seconds"] = invalid_timeout

    current_working_dir = "/fake/repo"
    editor_model = DEFAULT_EDITOR_MODEL
    default_timeout = DEFAULT_AIDER_TIMEOUT

    process_aider_ai_code_request(params, editor_model, current_working_dir, default_timeout)

    mock_code_with_aider.assert_called_once()
    call_args, call_kwargs = mock_code_with_aider.call_args
    # Expect the default timeout because the provided one was invalid or missing
    assert call_kwargs.get("timeout_seconds") == DEFAULT_AIDER_TIMEOUT


def test_timeout_occurs(mock_code_with_aider):
    """Verify correct error response when code_with_aider simulates a timeout."""
    custom_timeout = 5 # Use a specific timeout for the test
    
    # Simulate the JSON response code_with_aider would return on timeout
    timeout_response_json = json.dumps({
        "success": False,
        "diff": f"Error: Aider process timed out after {custom_timeout} seconds."
    })
    # Set the return value instead of side_effect
    mock_code_with_aider.return_value = timeout_response_json

    params = {
        "ai_coding_prompt": "test prompt",
        "relative_editable_files": ["file1.py"],
        "timeout_seconds": custom_timeout,
    }
    current_working_dir = "/fake/repo"
    editor_model = DEFAULT_EDITOR_MODEL
    default_timeout = DEFAULT_AIDER_TIMEOUT # Should use custom_timeout

    # Call the function that should use our mocked code_with_aider
    response = process_aider_ai_code_request(params, editor_model, current_working_dir, default_timeout)

    # Check that code_with_aider was called with the correct timeout
    mock_code_with_aider.assert_called_once()
    call_args, call_kwargs = mock_code_with_aider.call_args
    assert call_kwargs.get("timeout_seconds") == custom_timeout
    
    # Check the error response
    assert response["success"] is False
    assert "timed out" in response["diff"]
    assert str(custom_timeout) in response["diff"]


def test_timeout_error_response_format(mock_code_with_aider):
    """Verify the structure of the error response when a timeout occurs."""
    custom_timeout = 10
    timeout_message = f"Error: Aider process timed out after {custom_timeout} seconds."
    timeout_response_json = json.dumps({
        "success": False,
        "diff": timeout_message
    })
    mock_code_with_aider.return_value = timeout_response_json

    params = {
        "ai_coding_prompt": "test prompt",
        "relative_editable_files": ["file1.py"],
        "timeout_seconds": custom_timeout,
    }
    current_working_dir = "/fake/repo"
    editor_model = DEFAULT_EDITOR_MODEL
    default_timeout = DEFAULT_AIDER_TIMEOUT

    response = process_aider_ai_code_request(params, editor_model, current_working_dir, default_timeout)

    # Verify the structure and content of the response dictionary
    assert isinstance(response, dict)
    assert "success" in response
    assert "diff" in response
    assert response["success"] is False
    assert response["diff"] == timeout_message
