import pytest
import pytest_asyncio
import asyncio
import subprocess
import sys
import os
import uuid
import json
from pathlib import Path
from contextlib import AsyncExitStack
from typing import AsyncGenerator, Dict, Any

# Import correct MCP classes based on the package structure
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

# --- Constants ---
# Adjust this path based on the relative location of your test file to the server's main script
SERVER_MAIN_PY = Path(__file__).parent.parent / "src" / "aider_mcp_server" / "__main__.py"
DEFAULT_EDITOR_MODEL = "gemini/gemini-2.5-pro-exp-03-25" # Default model for testing
TOOL_AIDER_AI_CODE = "aider_ai_code"
TOOL_LIST_MODELS = "list_models"

# --- Helper Functions ---

def _run_git_command(cwd: Path, *args):
    """Helper to run git commands in the specified directory."""
    try:
        # Use 'git' directly, assuming it's in the PATH
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30 # Add a timeout for git commands
        )
        print(f"Git command '{' '.join(args)}' stdout:\n{result.stdout}")
        if result.stderr:
            print(f"Git command '{' '.join(args)}' stderr:\n{result.stderr}")
    except FileNotFoundError:
        pytest.fail("Git command not found. Ensure git is installed and in PATH.")
    except subprocess.CalledProcessError as e:
        pytest.fail(
            f"Git command failed: {' '.join(args)}\n"
            f"Return code: {e.returncode}\n"
            f"Stderr: {e.stderr}\n"
            f"Stdout: {e.stdout}"
        )
    except subprocess.TimeoutExpired as e:
         pytest.fail(
            f"Git command timed out: {' '.join(args)}\n"
            f"Stderr: {e.stderr}\n"
            f"Stdout: {e.stdout}"
         )

def setup_git_repo(repo_path: Path):
    """Initializes a git repository, adds a dummy file, and commits."""
    if not repo_path.exists():
        repo_path.mkdir(parents=True)

    # Check if it's already a git repo (e.g., if tmp_path is reused somehow)
    if not (repo_path / ".git").exists():
        _run_git_command(repo_path, "init")
        _run_git_command(repo_path, "config", "user.email", "test@example.com")
        _run_git_command(repo_path, "config", "user.name", "Test User")

    # Create, add, and commit a dummy file
    dummy_file = repo_path / "README.md"
    dummy_file.write_text("# Test Repository\nThis is a test repository for Aider MCP Server tests.\n", encoding="utf-8")
    _run_git_command(repo_path, "add", str(dummy_file.name))
    # Use a unique commit message to avoid issues if repo state persists unexpectedly
    _run_git_command(repo_path, "commit", "-m", f"Initial commit - {uuid.uuid4()}")
    print(f"Git repo initialized and initial file committed in {repo_path}")

# --- Pytest Fixture ---

@pytest_asyncio.fixture(scope="function") # Use 'function' scope for clean state per test
async def mcp_client_session(tmp_path: Path) -> AsyncGenerator[ClientSession, None]:
    """
    Pytest fixture to set up a temporary git repo, start the Aider MCP server
    via stdio, connect a client, and yield the client session.
    Cleans up the connection afterwards.
    """
    print(f"\n--- Setting up test in {tmp_path} ---")
    repo_path = tmp_path / "test_repo"
    setup_git_repo(repo_path)

    # Ensure the server script path exists
    if not SERVER_MAIN_PY.exists():
        pytest.fail(f"Server script not found at expected path: {SERVER_MAIN_PY}")

    server_args = [
        str(SERVER_MAIN_PY),
        "--current-working-dir", str(repo_path),
        "--editor-model", DEFAULT_EDITOR_MODEL,
        "--default-timeout", "300"  # Default timeout in seconds
    ]

    server_params = StdioServerParameters(
        command=sys.executable, # Use the same python interpreter running the tests
        args=server_args,
        env=os.environ.copy(), # Pass current environment
    )

    async with AsyncExitStack() as stack:
        try:
            print(f"Starting server process: {sys.executable} {' '.join(server_args)}")
            # Connect using stdio_client
            stdio_transport = await stack.enter_async_context(stdio_client(server_params))
            stdio, write = stdio_transport

            print("Initializing MCP Client Session...")
            # Create and initialize the ClientSession
            session = await stack.enter_async_context(ClientSession(stdio, write))

            # Initialize the session (sends 'initialize' request)
            # Set a reasonable timeout for initialization
            init_timeout = 30.0
            try:
                 init_response = await asyncio.wait_for(session.initialize(), timeout=init_timeout)
                 print(f"MCP Session Initialized. Server Capabilities: {init_response.capabilities}")
            except asyncio.TimeoutError:
                 pytest.fail(f"MCP Client initialization timed out after {init_timeout} seconds.")
            except Exception as e:
                 pytest.fail(f"MCP Client initialization failed: {e}")

            # List tools on connection to verify basic communication
            try:
                list_tools_resp = await asyncio.wait_for(session.list_tools(), timeout=10.0)
                tool_names = [tool.name for tool in list_tools_resp.tools]
                print(f"Server reported available tools: {tool_names}")
                assert TOOL_AIDER_AI_CODE in tool_names, f"Expected tool {TOOL_AIDER_AI_CODE} not found in server tools"
                assert TOOL_LIST_MODELS in tool_names, f"Expected tool {TOOL_LIST_MODELS} not found in server tools"
            except asyncio.TimeoutError:
                pytest.fail("Listing tools after initialization timed out.")
            except Exception as e:
                pytest.fail(f"Failed to list tools after initialization: {e}")

            yield session # Provide the connected session to the test function

        except Exception as e:
            # Catch errors during setup/connection phase
            pytest.fail(f"Failed to set up MCP client session: {e}")
        finally:
            print(f"--- Tearing down test in {tmp_path} ---")
            # AsyncExitStack handles cleanup of stdio_client and ClientSession

# --- Test Functions ---

@pytest.mark.asyncio
async def test_list_models(mcp_client_session: ClientSession):
    """Tests the list_models tool."""
    session = mcp_client_session
    print("\n--- Running test_list_models ---")

    try:
        # Call list_models tool with substring parameter
        response = await asyncio.wait_for(
            session.call_tool(TOOL_LIST_MODELS, {"substring": "gemini"}),
            timeout=20.0 # Allow time for potential API call
        )
        print(f"list_models response: {response}")

        # The response content is a list of TextContent objects, get the first one's text
        response_text = response.content[0].text
        print(f"Response text: {response_text}")
        
        # Parse the response text as JSON
        response_data = json.loads(response_text)
        print(f"Parsed response data: {response_data}")
        
        assert "models" in response_data, "Output should contain 'models' key"
        assert isinstance(response_data["models"], list), "'models' should be a list"
        assert len(response_data["models"]) > 0, "Expected at least one model to be returned"
        
        # Check that all returned models contain 'gemini' in their ID
        for model in response_data["models"]:
            assert "gemini" in model.lower(), f"Expected model {model} to contain 'gemini'"

    except asyncio.TimeoutError:
        pytest.fail(f"Tool call '{TOOL_LIST_MODELS}' timed out.")
    except Exception as e:
        pytest.fail(f"Tool call '{TOOL_LIST_MODELS}' failed: {e}")

@pytest.mark.asyncio
async def test_aider_ai_code_success(mcp_client_session: ClientSession, tmp_path: Path):
    """Tests the aider_ai_code tool for a successful code modification."""
    session = mcp_client_session
    repo_path = tmp_path / "test_repo"
    print("\n--- Running test_aider_ai_code_success ---")

    # Create a file for Aider to edit
    file_to_edit_name = "calculator.py"
    file_to_edit_path = repo_path / file_to_edit_name
    file_to_edit_path.write_text("# This file should implement a calculator class\n", encoding="utf-8")

    # Add and commit the new file
    _run_git_command(repo_path, "add", file_to_edit_name)
    _run_git_command(repo_path, "commit", "-m", f"Add {file_to_edit_name}")

    prompt = "Create a simple Calculator class with methods for add and subtract."
    params = {
        "ai_coding_prompt": prompt,
        "relative_editable_files": [file_to_edit_name],
        "timeout_seconds": 60  # Reasonable timeout
    }

    try:
        # Call the tool - Allow a generous timeout for AI operations
        response = await asyncio.wait_for(
            session.call_tool(TOOL_AIDER_AI_CODE, params),
            timeout=90.0 # Slightly longer than the internal timeout
        )
        print(f"aider_ai_code response: {response}")

        # The response content is a list of TextContent objects, get the first one's text
        response_text = response.content[0].text
        print(f"Response text: {response_text}")
        
        # Parse the response text as JSON
        response_data = json.loads(response_text)
        print(f"Parsed response data: {response_data}")
        
        # Verify that success is True or error is not present
        assert "success" in response_data, "Expected 'success' field in output"
        assert response_data["success"] is True, f"Expected success=True, got {response_data['success']}"
        
        # Verify the file content was modified as expected
        modified_content = file_to_edit_path.read_text(encoding="utf-8")
        print(f"Content of {file_to_edit_name} after edit:\n{modified_content}")
        assert "class Calculator" in modified_content, "File content was not modified with Calculator class"
        assert "def add" in modified_content, "Add method not found in file content"
        assert "def subtract" in modified_content, "Subtract method not found in file content"

    except asyncio.TimeoutError:
        pytest.fail(f"Tool call '{TOOL_AIDER_AI_CODE}' timed out.")
    except Exception as e:
        pytest.fail(f"Tool call '{TOOL_AIDER_AI_CODE}' failed unexpectedly: {e}")

@pytest.mark.asyncio
async def test_aider_ai_code_timeout(mcp_client_session: ClientSession, tmp_path: Path):
    """Tests the aider_ai_code tool with a very short timeout."""
    session = mcp_client_session
    repo_path = tmp_path / "test_repo"
    print("\n--- Running test_aider_ai_code_timeout ---")

    # Create a new Python file for this test
    file_to_edit_name = "complex_calculator.py"
    file_to_edit_path = repo_path / file_to_edit_name
    original_content = "# This file should implement a complex calculator with many features\n"
    file_to_edit_path.write_text(original_content, encoding="utf-8")

    # Add and commit the new file
    _run_git_command(repo_path, "add", file_to_edit_name)
    _run_git_command(repo_path, "commit", "-m", f"Add {file_to_edit_name}")

    # Use a complex prompt and very short timeout to ensure timeout occurs
    prompt = """
    Create a very complex Calculator class with the following features:
    1. Basic operations: add, subtract, multiply, divide methods
    2. Memory functions: memory_store, memory_recall, memory_clear
    3. A history feature that keeps track of operations 
    4. A method to show_history
    5. Error handling for division by zero
    6. Advanced scientific functions like sin, cos, tan, log, etc.
    7. Add complex documentation for every function
    8. Include unit tests for all functions
    9. Add proper type hints
    10. Add proper error handling
    """
    params = {
        "ai_coding_prompt": prompt,
        "relative_editable_files": [file_to_edit_name],
        "timeout_seconds": 1  # Extremely short timeout to force failure
    }

    try:
        # Call the tool with a reasonable outer timeout
        response = await asyncio.wait_for(
            session.call_tool(TOOL_AIDER_AI_CODE, params),
            timeout=20.0 # Timeout for the MCP call itself (much longer than internal timeout)
        )
        print(f"aider_ai_code (timeout test) response: {response}")

        # The response content is a list of TextContent objects, get the first one's text
        response_text = response.content[0].text
        print(f"Response text: {response_text}")
        
        # Parse the response text as JSON
        response_data = json.loads(response_text)
        print(f"Parsed response data: {response_data}")
        
        # The server should have detected the timeout and returned failure
        assert "success" in response_data, "Expected 'success' field in output"
        assert response_data["success"] is False, "Expected success=False for timeout"
        
        # Check if the diff/error message mentions timeout
        assert "diff" in response_data, "Expected 'diff' field in output"
        assert "timeout" in response_data["diff"].lower(), "Expected timeout message in diff"
        
        # Verify file content is unchanged
        current_content = file_to_edit_path.read_text(encoding="utf-8")
        assert current_content == original_content, "File should not be modified after timeout"

    except asyncio.TimeoutError:
        pytest.fail(f"Tool call '{TOOL_AIDER_AI_CODE}' timed out unexpectedly.")
    except Exception as e:
        # Check if the exception is related to the expected timeout
        if "timeout" in str(e).lower():
            print(f"Tool call raised timeout-related exception as expected: {e}")
            # Verify file content is unchanged
            current_content = file_to_edit_path.read_text(encoding="utf-8")
            assert current_content == original_content, "File should not be modified after timeout"
        else:
            pytest.fail(f"Tool call '{TOOL_AIDER_AI_CODE}' failed unexpectedly: {e}")

@pytest.mark.asyncio
async def test_aider_ai_code_invalid_timeout(mcp_client_session: ClientSession, tmp_path: Path):
    """Tests the aider_ai_code tool with an invalid timeout value (float)."""
    session = mcp_client_session
    repo_path = tmp_path / "test_repo"
    print("\n--- Running test_aider_ai_code_invalid_timeout ---")

    # Create a file for this test
    file_to_edit_name = "simple_function.py"
    file_to_edit_path = repo_path / file_to_edit_name
    file_to_edit_path.write_text("# This file should implement a simple function\n", encoding="utf-8")

    # Add and commit the new file
    _run_git_command(repo_path, "add", file_to_edit_name)
    _run_git_command(repo_path, "commit", "-m", f"Add {file_to_edit_name}")

    prompt = "Add a simple add(a, b) function that returns the sum of a and b."
    
    # Use a float timeout value, which the server should validate and reject
    params = {
        "ai_coding_prompt": prompt,
        "relative_editable_files": [file_to_edit_name],
        "timeout_seconds": 10.5  # Float value should be rejected
    }

    try:
        # Call the tool - we expect the server to use the default timeout
        response = await asyncio.wait_for(
            session.call_tool(TOOL_AIDER_AI_CODE, params),
            timeout=90.0 # Generous timeout for the default behavior
        )
        print(f"aider_ai_code (invalid timeout test) response: {response}")

        # The response content is a list of TextContent objects, get the first one's text
        response_text = response.content[0].text
        print(f"Response text: {response_text}")
        
        # Parse the response text as JSON
        response_data = json.loads(response_text)
        print(f"Parsed response data: {response_data}")
        
        # The server should have used the default timeout and succeeded
        assert "success" in response_data, "Expected 'success' field in output"
        assert response_data["success"] is True, f"Expected success=True despite invalid timeout, got {response_data['success']}"
        
        # Verify the file was edited correctly
        modified_content = file_to_edit_path.read_text(encoding="utf-8")
        print(f"Content of {file_to_edit_name} after edit:\n{modified_content}")
        assert "def add" in modified_content, "File should have been modified with add function"

    except asyncio.TimeoutError:
        pytest.fail(f"Tool call '{TOOL_AIDER_AI_CODE}' timed out.")
    except Exception as e:
        pytest.fail(f"Tool call '{TOOL_AIDER_AI_CODE}' failed unexpectedly: {e}")

if __name__ == "__main__":
    pytest.main(["-v", __file__])