"""Test that multiple SSE tests can run in parallel without port conflicts."""

import asyncio
import os
import subprocess
import sys  # Added import for sys
import tempfile
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parallel_server_starts(free_port, server_process):
    """Test that a server can start with a dynamically allocated port."""
    # Use a test directory
    test_dir = Path(tempfile.gettempdir()) / f"test_aider_sse_{free_port}"
    test_dir.mkdir(exist_ok=True)

    # Initialize a git repo in the test directory
    subprocess.run(["git", "init"], cwd=test_dir, capture_output=True, env={**os.environ, "CLAUDECODE": "0"})  # noqa: S603, S607

    # Start the SSE server
    process = server_process(
        [
            sys.executable,  # Changed from "python" to sys.executable
            "-m",
            "aider_mcp_server",
            "--server-mode",
            "sse",
            "--current-working-dir",
            str(test_dir),
            "--port",
            str(free_port),
            "--editor-model",
            "gpt-3.5-turbo",
        ],
        cwd=Path(__file__).parent.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**subprocess.os.environ, "OPENAI_API_KEY": "test-key", "CLAUDECODE": "0"},
    )

    # Wait briefly to allow server to start, especially on slower CI
    await asyncio.sleep(3)

    # Check if started
    if process.poll() is not None:
        stdout, stderr = process.communicate()
        print(f"\n--- Server Output for test_parallel_server_starts (Port: {free_port}) ---")
        print(f"Server exited with code: {process.returncode}")
        print(f"Server stdout:\n{stdout}")
        print(f"Server stderr:\n{stderr}")
        print("------------------------------------------------------------------")
    assert process.poll() is None, "Server should still be running"

    # Cleanup is handled by the fixture


@pytest.mark.integration
@pytest.mark.asyncio
async def test_another_parallel_server(free_port, server_process):
    """Another test that runs in parallel to verify port isolation."""
    # Use a test directory
    test_dir = Path(tempfile.gettempdir()) / f"test_aider_sse_{free_port}"
    test_dir.mkdir(exist_ok=True)

    # Initialize a git repo in the test directory
    subprocess.run(["git", "init"], cwd=test_dir, capture_output=True, env={**os.environ, "CLAUDECODE": "0"})  # noqa: S603, S607

    # Start the SSE server
    process = server_process(
        [
            sys.executable,  # Changed from "python" to sys.executable
            "-m",
            "aider_mcp_server",
            "--server-mode",
            "sse",
            "--current-working-dir",
            str(test_dir),
            "--port",
            str(free_port),
            "--editor-model",
            "gpt-3.5-turbo",
        ],
        cwd=Path(__file__).parent.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**subprocess.os.environ, "OPENAI_API_KEY": "test-key", "CLAUDECODE": "0"},
    )

    # Wait briefly to allow server to start, especially on slower CI
    await asyncio.sleep(3)

    # Check if started
    if process.poll() is not None:
        stdout, stderr = process.communicate()
        print(f"\n--- Server Output for test_another_parallel_server (Port: {free_port}) ---")
        print(f"Server exited with code: {process.returncode}")
        print(f"Server stdout:\n{stdout}")
        print(f"Server stderr:\n{stderr}")
        print("------------------------------------------------------------------")
    assert process.poll() is None, "Server should still be running"

    # Cleanup is handled by the fixture
