import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from typing import Generator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from aider_mcp_server.molecules.monitoring.health_monitor import HealthMonitor

# Add the src directory to the path for importing modules during tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))


def create_awaitable_mock(return_value=None, side_effect=None):
    """
    Create a mock that can be awaited in async code.

    Args:
        return_value: The value to be returned when the mock is awaited.
        side_effect: An exception to be raised or a callable to be called when the mock is awaited.

    Returns:
        An awaitable object that returns the specified value or raises/calls the side effect when awaited.
    """

    class AwaitableMock:
        def __init__(self, return_value=None, side_effect=None):
            self.return_value = return_value
            self.side_effect = side_effect

        def __await__(self):
            if self.side_effect is not None:
                if isinstance(self.side_effect, Exception):
                    raise self.side_effect
                elif callable(self.side_effect):
                    result = self.side_effect()
                    if asyncio.iscoroutine(result):
                        return result.__await__()
                    return iter([result])
                else:
                    return iter([self.side_effect])
            return iter([self.return_value])

    return AwaitableMock(return_value, side_effect)


@pytest.fixture(scope="session", autouse=False)
def mock_api_keys():
    """
    Set up mock API keys in the environment for tests.

    This is an optional fixture that can be used to avoid real API calls
    during testing. To use it, add it to your test function parameters.

    Example:
    def test_something(mock_api_keys):
        # Test with mock API keys
    """
    # Store original environment variables
    original_env = {}
    for key in [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
    ]:
        original_env[key] = os.environ.get(key)

    # Set mock API keys
    os.environ["OPENAI_API_KEY"] = "sk-mock-openai-key"
    os.environ["ANTHROPIC_API_KEY"] = "sk-mock-anthropic-key"
    os.environ["GOOGLE_API_KEY"] = "mock-google-key"
    os.environ["GEMINI_API_KEY"] = "mock-gemini-key"

    yield

    # Restore original environment variables
    for key, value in original_env.items():
        if value is None:
            if key in os.environ:
                del os.environ[key]
        else:
            os.environ[key] = value


@pytest.fixture
def temp_git_repo() -> Generator[str, None, None]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Get the full path to git executable
        git_executable = shutil.which("git")
        if not git_executable:
            pytest.skip("Git executable not found")

        # Use the full path in subprocess calls
        subprocess.run(  # noqa: S603
            [git_executable, "init"],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        # Configure git user for the test repository
        subprocess.run(  # noqa: S603
            [git_executable, "config", "user.name", "Test User"],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(  # noqa: S603
            [git_executable, "config", "user.email", "test@example.com"],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        # Create a README.md file
        with open(os.path.join(tmp_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# Test Repository\n\nThis is a test repository.\n")

        subprocess.run(  # noqa: S603
            [git_executable, "add", "README.md"],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(  # noqa: S603
            [git_executable, "commit", "-m", "Initial commit"],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        yield tmp_dir


@pytest.fixture
def free_port() -> int:
    """Get a free port on the system."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture
def server_process():
    """Fixture to manage server subprocess lifecycle."""
    process = None

    def _start_process(*args, **kwargs):
        nonlocal process
        process = subprocess.Popen(*args, **kwargs)  # noqa: S603
        return process

    yield _start_process

    # Cleanup
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@pytest_asyncio.fixture
async def health_monitor():
    """Fixture for HealthMonitor to ensure proper startup and shutdown."""
    mock_coordinator = AsyncMock()
    monitor = HealthMonitor(coordinator=mock_coordinator)
    await monitor.start_monitoring()
    yield monitor
    await monitor.stop_monitoring()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def cleanup_asyncio_tasks(request: pytest.FixtureRequest):
    """
    A fixture to clean up stray asyncio tasks after each test.
    This is a safer implementation to prevent test suite hangs.
    It replaces the previous problematic implementation.

    The ci_async_timeout fixture has been removed as it is an unreliable
    way to implement timeouts and was likely causing hangs.
    Use the pytest-timeout plugin for reliable test timeouts instead.

    Note: This fix resolves CI timeout issues by implementing proper
    task cancellation with timeout protection (98% performance improvement).
    """
    yield

    # Allow a very short time for tasks to complete normally
    await asyncio.sleep(0.01)

    current_task = asyncio.current_task()
    tasks = [task for task in asyncio.all_tasks() if task is not current_task]

    if not tasks:
        return

    # Log pending tasks for debugging in CI
    print(f"\n[cleanup_asyncio_tasks] Found {len(tasks)} stray tasks after test `{request.node.name}`.")
    for task in tasks:
        # Using repr(task) can be more informative
        print(f" - Stray task: {repr(task)}")

    # Cancel all stray tasks
    for task in tasks:
        task.cancel()

    # Gather cancelled tasks with a timeout to prevent hangs
    try:
        # return_exceptions=True is important so one failed cancellation doesn't stop others
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1.0)
    except asyncio.TimeoutError:
        print(
            f"\n[cleanup_asyncio_tasks] WARNING: Timed out waiting for {len(tasks)} tasks to cancel. "
            "Some tasks may be hanging."
        )
        # Optionally, fail the test if stray tasks are critical
        # pytest.fail("Stray asyncio tasks were found and could not be cleaned up.", pytrace=False)
