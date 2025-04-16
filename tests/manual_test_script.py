#!/usr/bin/env python3
"""
A simple script to test the Aider MCP server's timeout functionality directly.
"""

import asyncio
import json
import os
import sys
import tempfile
import subprocess
import time
from pathlib import Path

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

# Path to the server main script
SERVER_MAIN_PY = Path(__file__).parent.parent / "src" / "aider_mcp_server" / "__main__.py"
DEFAULT_EDITOR_MODEL = "gemini/gemini-2.5-pro-exp-03-25"  # Default model for testing

def run_git_command(cwd, *args):
    """Helper to run git commands in the specified directory."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,  # Add a timeout for git commands
        )
        print(f"Git command '{' '.join(args)}' stdout:\n{result.stdout}")
        if result.stderr:
            print(f"Git command '{' '.join(args)}' stderr:\n{result.stderr}")
    except Exception as e:
        print(f"Git command failed: {e}")
        raise

def setup_git_repo(repo_path):
    """Initializes a git repository, adds a dummy file, and commits."""
    if not repo_path.exists():
        repo_path.mkdir(parents=True)

    # Check if it's already a git repo
    if not (repo_path / ".git").exists():
        run_git_command(repo_path, "init")
        run_git_command(repo_path, "config", "user.email", "test@example.com")
        run_git_command(repo_path, "config", "user.name", "Test User")

    # Create, add, and commit a dummy file
    dummy_file = repo_path / "README.md"
    dummy_file.write_text("# Test Repository\nThis is a test repository for Aider MCP Server tests.\n", encoding="utf-8")
    run_git_command(repo_path, "add", str(dummy_file.name))
    run_git_command(repo_path, "commit", "-m", "Initial commit")
    print(f"Git repo initialized and initial file committed in {repo_path}")

async def test_list_models():
    """Test the list_models tool."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        repo_path = tmp_path / "test_repo"
        setup_git_repo(repo_path)

        # Ensure the server script path exists
        if not SERVER_MAIN_PY.exists():
            print(f"Server script not found at expected path: {SERVER_MAIN_PY}")
            return

        server_args = [
            str(SERVER_MAIN_PY),
            "--current-working-dir", str(repo_path),
            "--editor-model", DEFAULT_EDITOR_MODEL,
            "--default-timeout", "300",  # Default timeout in seconds
        ]

        server_params = StdioServerParameters(
            command=sys.executable,  # Use the same python interpreter
            args=server_args,
            env=os.environ.copy(),  # Pass current environment
        )

        # Connect to server
        print("Connecting to server...")
        try:
            async with stdio_client(server_params) as (read_stream, write_stream):
                print("Connected. Creating client session...")
                session = ClientSession(read_stream, write_stream)
                await session.initialize()
                
                # List tools
                print("Listing tools...")
                tools_response = await session.list_tools()
                tool_names = [tool.name for tool in tools_response.tools]
                print(f"Available tools: {tool_names}")
                
                # Test list_models
                print("\nTesting list_models tool...")
                response = await session.call_tool("list_models", {"substring": "gemini"})
                
                # Parse response
                response_text = response.content[0].text
                response_data = json.loads(response_text)
                print(f"Found {len(response_data['models'])} models matching 'gemini'")
                print("Test completed successfully!")
                
                # Clean up
                await session.shutdown()
                
        except Exception as e:
            print(f"Error: {e}")

async def test_timeout_functionality():
    """Test the timeout functionality of the aider_ai_code tool."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        repo_path = tmp_path / "test_repo"
        setup_git_repo(repo_path)

        # Create a Python file to edit
        file_to_edit_name = "calculator.py"
        file_to_edit_path = repo_path / file_to_edit_name
        file_to_edit_path.write_text("# This file should implement a calculator class\n", encoding="utf-8")
        run_git_command(repo_path, "add", file_to_edit_name)
        run_git_command(repo_path, "commit", "-m", f"Add {file_to_edit_name}")

        # Ensure the server script path exists
        if not SERVER_MAIN_PY.exists():
            print(f"Server script not found at expected path: {SERVER_MAIN_PY}")
            return

        server_args = [
            str(SERVER_MAIN_PY),
            "--current-working-dir", str(repo_path),
            "--editor-model", DEFAULT_EDITOR_MODEL,
            "--default-timeout", "300",  # Default timeout in seconds
        ]

        server_params = StdioServerParameters(
            command=sys.executable,  # Use the same python interpreter
            args=server_args,
            env=os.environ.copy(),  # Pass current environment
        )

        # Connect to server
        print("Connecting to server...")
        try:
            async with stdio_client(server_params) as (read_stream, write_stream):
                print("Connected. Creating client session...")
                session = ClientSession(read_stream, write_stream)
                await session.initialize()
                
                # Test normal timeout (should succeed)
                print("\nTesting aider_ai_code with normal timeout...")
                normal_prompt = "Create a simple Calculator class with methods for add and subtract."
                normal_params = {
                    "ai_coding_prompt": normal_prompt,
                    "relative_editable_files": [file_to_edit_name],
                    "timeout_seconds": 60  # Reasonable timeout
                }
                
                normal_response = await session.call_tool("aider_ai_code", normal_params)
                normal_response_text = normal_response.content[0].text
                normal_response_data = json.loads(normal_response_text)
                
                print(f"Normal timeout response: {normal_response_data}")
                if normal_response_data.get("success", False):
                    print("✅ Normal timeout test PASSED")
                else:
                    print("❌ Normal timeout test FAILED")
                
                # Create a file for short timeout test
                short_file_name = "complex_calculator.py"
                short_file_path = repo_path / short_file_name
                short_file_path.write_text("# This file should implement a complex calculator\n", encoding="utf-8")
                run_git_command(repo_path, "add", short_file_name)
                run_git_command(repo_path, "commit", "-m", f"Add {short_file_name}")
                
                # Test short timeout (should fail)
                print("\nTesting aider_ai_code with very short timeout...")
                short_prompt = """
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
                short_params = {
                    "ai_coding_prompt": short_prompt,
                    "relative_editable_files": [short_file_name],
                    "timeout_seconds": 1  # Very short timeout
                }
                
                short_response = await session.call_tool("aider_ai_code", short_params)
                short_response_text = short_response.content[0].text
                short_response_data = json.loads(short_response_text)
                
                print(f"Short timeout response: {short_response_data}")
                
                # Check if the response indicates a timeout
                if (not short_response_data.get("success", True) and 
                        "timeout" in short_response_data.get("diff", "").lower()):
                    print("✅ Short timeout test PASSED")
                else:
                    print("❌ Short timeout test FAILED")
                    
                # Test invalid timeout value (float)
                print("\nTesting aider_ai_code with invalid timeout (float)...")
                invalid_file_name = "simple_function.py"
                invalid_file_path = repo_path / invalid_file_name
                invalid_file_path.write_text("# This file should implement a simple function\n", encoding="utf-8")
                run_git_command(repo_path, "add", invalid_file_name)
                run_git_command(repo_path, "commit", "-m", f"Add {invalid_file_name}")
                
                invalid_prompt = "Add a simple add(a, b) function that returns the sum of a and b."
                invalid_params = {
                    "ai_coding_prompt": invalid_prompt,
                    "relative_editable_files": [invalid_file_name],
                    "timeout_seconds": 10.5  # Float value
                }
                
                invalid_response = await session.call_tool("aider_ai_code", invalid_params)
                invalid_response_text = invalid_response.content[0].text
                invalid_response_data = json.loads(invalid_response_text)
                
                print(f"Invalid timeout response: {invalid_response_data}")
                
                # Should succeed using default timeout
                if invalid_response_data.get("success", False):
                    print("✅ Invalid timeout test PASSED")
                else:
                    print("❌ Invalid timeout test FAILED")
                
                # Clean up
                await session.shutdown()
                
        except Exception as e:
            print(f"Error: {e}")

async def main():
    """Run the tests."""
    # Uncomment the test you want to run
    await test_list_models()
    # await test_timeout_functionality()

if __name__ == "__main__":
    asyncio.run(main())