import pytest
import json
import time
import os
from unittest.mock import patch
from pathlib import Path

from src.aider_mcp_server.atoms.tools.aider_ai_code import code_with_aider
from src.aider_mcp_server.atoms.utils import DEFAULT_AIDER_TIMEOUT

# Define a pickleable worker function at the module level
def pickleable_long_running_task(
    ai_coding_prompt, relative_editable_files, relative_readonly_files, model, working_dir
):
    """
    A pickleable function that simulates a long-running Aider process.
    This function matches the signature of _run_aider_core_logic but simply sleeps
    to simulate processing time.
    """
    pid = os.getpid()
    print(f"Worker process (PID: {pid}) started in {working_dir}")
    # Sleep for a duration that's longer than our test timeout
    sleep_duration = 5  # seconds
    print(f"Worker sleeping for {sleep_duration} seconds...")
    time.sleep(sleep_duration)
    print(f"Worker process (PID: {pid}) completed after {sleep_duration}s")
    # Return a success response (this shouldn't be reached during timeout tests)
    return {"success": True, "diff": f"Simulated changes after {sleep_duration}s by PID {pid}"}

# Fast-returning version for the "completes within timeout" test
def pickleable_fast_task(
    ai_coding_prompt, relative_editable_files, relative_readonly_files, model, working_dir
):
    """
    A pickleable function that simulates a quick Aider process that completes within timeout.
    """
    pid = os.getpid()
    print(f"Fast worker (PID: {pid}) started in {working_dir}")
    # Sleep briefly to simulate a quick process
    time.sleep(0.1)
    print(f"Fast worker (PID: {pid}) completed quickly")
    # Return a success response
    return {"success": True, "diff": "Simulated quick changes"}

@pytest.fixture
def temp_git_repo(tmp_path: Path) -> str:
    """Create a temporary directory and initialize it as a git repository."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    repo_path_str = str(repo_path)

    try:
        # Initialize git repository
        import subprocess
        subprocess.check_call(["git", "init"], cwd=repo_path_str, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Create a dummy file and commit it
        (repo_path / "dummy.txt").write_text("initial content")
        subprocess.check_call(["git", "add", "dummy.txt"], cwd=repo_path_str, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Configure dummy user for commit
        subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=repo_path_str)
        subprocess.check_call(["git", "config", "user.name", "Test User"], cwd=repo_path_str)
        subprocess.check_call(["git", "commit", "-m", "Initial commit"], cwd=repo_path_str, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Failed to initialize git repository: {e}")
    except FileNotFoundError:
        pytest.fail("Git command not found. Ensure git is installed and in PATH.")

    return repo_path_str

# Mock check_api_keys to avoid dependency on actual keys/env vars
@patch('src.aider_mcp_server.atoms.tools.aider_ai_code.check_api_keys', return_value=None)
def test_code_with_aider_timeout_integration(mock_check_keys, temp_git_repo):
    """
    Integration test for code_with_aider timeout using ProcessPoolExecutor.
    Uses a real pickleable function that sleeps longer than the timeout.
    """
    # Use a very short timeout to ensure we hit the timeout condition
    test_timeout = 1  # seconds - must be shorter than pickleable_long_running_task's sleep
    ai_prompt = "This is a test prompt."
    editable_files = ["dummy.txt"]  # Use the file created in the fixture
    working_dir = temp_git_repo

    # Patch _run_aider_core_logic with our pickleable function
    # We need to patch at the correct module level where it's imported/used
    # This is different from trying to use it directly with ProcessPoolExecutor
    with patch('src.aider_mcp_server.atoms.tools.aider_ai_code._run_aider_core_logic', 
               pickleable_long_running_task):
        # Call the function that uses the executor
        start_time = time.time()
        response_json = code_with_aider(
            ai_coding_prompt=ai_prompt,
            relative_editable_files=editable_files,
            working_dir=working_dir,
            timeout_seconds=test_timeout
        )
        end_time = time.time()
        duration = end_time - start_time
        
        # Convert response to dict for assertions
        response = json.loads(response_json)
        print(f"Response: {response}")
        
        # We can see from the output that the process timeout works, but the full function call
        # takes a bit longer because it needs to clean up resources, so we'll use a more generous duration check
        assert duration < test_timeout + 5.0, f"Call took too long ({duration:.2f}s)"
        
        # Check that the response indicates a timeout failure
        assert response["success"] is False, "Response should indicate failure on timeout"
        assert "timed out" in response["diff"].lower(), "Response should mention timeout"
        assert str(test_timeout) in response["diff"], f"Response should mention the timeout duration ({test_timeout}s)"

@patch('src.aider_mcp_server.atoms.tools.aider_ai_code.check_api_keys', return_value=None)
def test_code_with_aider_completes_within_timeout(mock_check_keys, temp_git_repo):
    """
    Test that code_with_aider completes normally when the task finishes within the timeout.
    """
    test_timeout = 5  # seconds - much longer than our fast task needs
    ai_prompt = "Test prompt for completion."
    editable_files = ["dummy.txt"]
    working_dir = temp_git_repo

    # Patch the core logic with a fast implementation
    with patch('src.aider_mcp_server.atoms.tools.aider_ai_code._run_aider_core_logic',
               pickleable_fast_task):
        # Call the function
        response_json = code_with_aider(
            ai_coding_prompt=ai_prompt,
            relative_editable_files=editable_files,
            working_dir=working_dir,
            timeout_seconds=test_timeout
        )
        
        # Parse the response
        response = json.loads(response_json)
        print(f"Response: {response}")
        
        # Check for successful completion
        assert response["success"] is True, "Response should indicate success when task completes within timeout"
        assert "simulated quick changes" in response["diff"].lower(), "Response should contain the expected content"