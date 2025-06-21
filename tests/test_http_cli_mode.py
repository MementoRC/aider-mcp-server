import asyncio
import os
import sys
from pathlib import Path
from typing import List, Tuple
from unittest import mock

import pytest

# Import the cli module and necessary components
import aider_mcp_server.templates.initialization.cli as cli_module
from aider_mcp_server import __version__ as mcp_server_version
from aider_mcp_server.atoms.logging.logger import Logger
from aider_mcp_server.atoms.utils.config_constants import (
    DEFAULT_EDITOR_MODEL,
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
)


# Helper function similar to run_main in test_cli.py but adapted for HTTP mode
def run_main_http(
    monkeypatch: pytest.MonkeyPatch, args: List[str]
) -> Tuple[
    mock.MagicMock,  # mock_serve_http
    mock.MagicMock,  # mock_get_logger
    mock.MagicMock,  # mock_logger_instance
    mock.MagicMock,  # mock_path_is_dir
    mock.MagicMock,  # mock_is_git_repo
    mock.MagicMock,  # mock_exit
    mock.MagicMock,  # mock_asyncio_run
    mock.MagicMock,  # mock_path_resolve
    mock.MagicMock,  # mock_path_exists
]:
    """Runs the CLI main function with mocked dependencies for HTTP mode tests."""
    mock_serve_http = mock.AsyncMock()  # Use AsyncMock as serve_http is async
    mock_logger_instance = mock.MagicMock(spec=Logger)
    mock_get_logger = mock.MagicMock(return_value=mock_logger_instance)
    mock_path_is_dir = mock.MagicMock(return_value=True)
    mock_is_git_repo = mock.MagicMock(return_value=(True, None))  # Default to True, no error
    mock_exit = mock.MagicMock(side_effect=SystemExit)

    # Mock asyncio.run to execute the coroutine. This is critical to avoid
    # "coroutine was never awaited" RuntimeWarning.
    mock_asyncio_run = mock.MagicMock(side_effect=asyncio.run)

    # Patch the functions and classes used within cli_module.main's scope
    monkeypatch.setattr(cli_module, "serve_http", mock_serve_http)
    monkeypatch.setattr(cli_module, "get_logger", mock_get_logger)

    # Mock Path methods globally
    # Default mock for Path.resolve: returns a Path object based on input
    # Needs to be a function to be setattr-ed to a class method
    def simple_resolve(self: Path, strict: bool = False) -> Path:
        # Simulate abspath for consistency in tests
        resolved_path = Path(os.path.abspath(str(self)))
        if strict and not resolved_path.exists():  # Relies on Path.exists being suitably mocked
            raise FileNotFoundError(f"Mock FileNotFoundError for {self}")
        return resolved_path

    mock_path_resolve = mock.MagicMock(side_effect=simple_resolve)
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: mock_path_resolve(self, strict=strict))

    # Default mock for Path.exists
    mock_path_exists = mock.MagicMock(return_value=True)  # Assume exists by default
    monkeypatch.setattr(Path, "exists", lambda self: mock_path_exists(self))

    # Path.is_dir is already mocked with mock_path_is_dir at the start of this function
    monkeypatch.setattr(Path, "is_dir", lambda self: mock_path_is_dir(self))

    monkeypatch.setattr(cli_module, "is_git_repository", mock_is_git_repo)
    monkeypatch.setattr(sys, "exit", mock_exit)
    monkeypatch.setattr(asyncio, "run", mock_asyncio_run)

    # Mock sys.argv for this specific run
    monkeypatch.setattr(sys, "argv", ["script_name"] + args)

    try:
        cli_module.main()
    except SystemExit:
        pass  # Capture SystemExit raised by mock_exit or argparse error
    except Exception as e:
        # If mock_serve_http was supposed to raise an error (via its side_effect),
        # and asyncio.run propagated it, we check if it's the expected one.
        if (
            mock_serve_http.side_effect
            and isinstance(mock_serve_http.side_effect, Exception)
            and e is mock_serve_http.side_effect
        ):
            pass  # Expected exception, propagated by asyncio.run
        else:
            # print(f"run_main_http caught unexpected error: {e}") # For debugging
            raise  # Re-raise unexpected exceptions

    return (
        mock_serve_http,
        mock_get_logger,
        mock_logger_instance,
        mock_path_is_dir,
        mock_is_git_repo,
        mock_exit,
        mock_asyncio_run,
        mock_path_resolve,  # Return the mock itself for assertion
        mock_path_exists,  # Return the mock itself for assertion
    )


# --- Test Cases ---


def test_http_mode_default_params(monkeypatch: pytest.MonkeyPatch):
    """Test HTTP mode with default host, port, and editor model."""
    args = ["--server-mode", "http", "--current-working-dir", "."]
    (
        mock_serve_http,
        _,
        _,
        mock_path_is_dir_instance_check,
        mock_is_git_repo,
        mock_exit,
        _,
        mock_path_resolve,
        mock_path_exists_instance_check,
    ) = run_main_http(monkeypatch, args)

    cwd_path_obj = Path(".").resolve()  # Path object used in validation
    cwd_str = str(cwd_path_obj)  # String path passed to serve_http

    mock_path_resolve.assert_called_with(Path("."), strict=False)
    # Path.exists is called by Path.resolve(strict=True)
    mock_path_exists_instance_check.assert_called_with(Path(os.path.abspath(".")))
    mock_path_is_dir_instance_check.assert_called_with(cwd_path_obj)
    mock_is_git_repo.assert_called_once_with(cwd_path_obj)

    mock_serve_http.assert_called_once()
    call_kwargs = mock_serve_http.call_args.kwargs
    assert call_kwargs.get("host") == DEFAULT_HTTP_HOST
    assert call_kwargs.get("port") == DEFAULT_HTTP_PORT
    assert call_kwargs.get("editor_model") == DEFAULT_EDITOR_MODEL
    assert call_kwargs.get("current_working_dir") == cwd_str
    mock_exit.assert_not_called()


def test_http_mode_custom_params(monkeypatch: pytest.MonkeyPatch):
    """Test HTTP mode with custom host, port."""
    custom_host = "192.168.1.200"
    custom_port = 9876
    args = [
        "--server-mode",
        "http",
        "--http-host",
        custom_host,
        "--http-port",
        str(custom_port),
        "--current-working-dir",
        ".",
    ]
    (mock_serve_http, _, _, _, mock_is_git_repo, mock_exit, _, mock_path_resolve, _) = run_main_http(monkeypatch, args)

    cwd_path_obj = Path(".").resolve()
    cwd_str = str(cwd_path_obj)

    mock_path_resolve.assert_called_with(Path("."), strict=False)
    mock_is_git_repo.assert_called_once_with(cwd_path_obj)

    mock_serve_http.assert_called_once()
    call_kwargs = mock_serve_http.call_args.kwargs
    assert call_kwargs.get("host") == custom_host
    assert call_kwargs.get("port") == custom_port
    assert call_kwargs.get("editor_model") == DEFAULT_EDITOR_MODEL  # Check default editor model
    assert call_kwargs.get("current_working_dir") == cwd_str
    mock_exit.assert_not_called()


def test_http_mode_custom_editor_model(monkeypatch: pytest.MonkeyPatch):
    """Test HTTP mode with a custom editor model."""
    custom_model = "gpt-custom-http"
    args = ["--server-mode", "http", "--editor-model", custom_model, "--current-working-dir", "."]
    (mock_serve_http, _, _, _, mock_is_git_repo, mock_exit, _, mock_path_resolve, _) = run_main_http(monkeypatch, args)

    cwd_path_obj = Path(".").resolve()
    cwd_str = str(cwd_path_obj)

    mock_path_resolve.assert_called_with(Path("."), strict=False)
    mock_is_git_repo.assert_called_once_with(cwd_path_obj)

    mock_serve_http.assert_called_once()
    call_kwargs = mock_serve_http.call_args.kwargs
    assert call_kwargs.get("host") == DEFAULT_HTTP_HOST  # Check default host
    assert call_kwargs.get("port") == DEFAULT_HTTP_PORT  # Check default port
    assert call_kwargs.get("editor_model") == custom_model
    assert call_kwargs.get("current_working_dir") == cwd_str
    mock_exit.assert_not_called()


def test_http_mode_working_dir_not_exists(monkeypatch: pytest.MonkeyPatch):
    """Test HTTP mode when specified working directory does not exist."""
    non_existent_dir = "/path/to/absolutely/non_existent_dir"
    args = ["--server-mode", "http", "--current-working-dir", non_existent_dir]

    # Configure mocks for this specific scenario
    mock_serve_http = mock.AsyncMock()
    mock_logger_instance = mock.MagicMock(spec=Logger)
    mock_get_logger = mock.MagicMock(return_value=mock_logger_instance)
    mock_exit = mock.MagicMock(side_effect=SystemExit)

    # Path.resolve(strict=True) will raise FileNotFoundError
    def specific_resolve(self: Path, strict: bool = False) -> Path:
        if str(self) == non_existent_dir and strict:
            raise FileNotFoundError(f"Mock FileNotFoundError for {self}")
        # Fallback for other paths if any (though not expected in this test flow)
        return Path(os.path.abspath(str(self)))

    mock_path_resolve_method = mock.MagicMock(side_effect=specific_resolve)

    monkeypatch.setattr(cli_module, "serve_http", mock_serve_http)
    monkeypatch.setattr(cli_module, "get_logger", mock_get_logger)
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: mock_path_resolve_method(self, strict=strict))
    # Path.exists and Path.is_dir won't be reached if resolve(strict=True) fails.
    monkeypatch.setattr(sys, "exit", mock_exit)
    monkeypatch.setattr(sys, "argv", ["script_name"] + args)

    with pytest.raises(SystemExit):
        cli_module.main()

    mock_path_resolve_method.assert_called_with(Path(non_existent_dir), strict=True)
    mock_logger_instance.critical.assert_called_once()
    assert (
        f"Error: Specified working directory does not exist: {non_existent_dir}"
        in mock_logger_instance.critical.call_args[0][0]
    )
    mock_exit.assert_called_once_with(1)
    mock_serve_http.assert_not_called()


def test_http_mode_working_dir_not_git_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Test HTTP mode when CWD is not a git repository."""
    not_git_dir = tmp_path / "not_a_repo_http"
    not_git_dir.mkdir()
    git_error_msg = "fatal: not a git repository (or any of the parent directories): .git"

    args = ["--server-mode", "http", "--current-working-dir", str(not_git_dir)]

    # Use run_main_http but override is_git_repository mock for this test
    # Also, ensure Path.resolve works for tmp_path
    original_path_resolve = Path.resolve

    def specific_tmp_path_resolve(self: Path, strict: bool = False) -> Path:
        # Let the original resolve handle tmp_path correctly
        # This ensures that the path object passed to is_git_repository is the resolved one
        return original_path_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", specific_tmp_path_resolve)  # Apply before run_main_http

    (mock_serve_http, _, mock_logger_instance, _, mock_is_git_repo, mock_exit, _, _, _) = run_main_http(
        monkeypatch, args
    )

    # Override the default mock_is_git_repo behavior set by run_main_http for this specific test path
    mock_is_git_repo.configure_mock(return_value=(False, git_error_msg))

    # Re-run main with the path specific mocks if run_main_http doesn't allow easy override
    # For this setup, we assume run_main_http's mocks are sufficient if configured before its call
    # or if we can re-trigger the logic.
    # Let's adjust: mock is_git_repository directly in the test setup before calling run_main_http.

    # We need to ensure the mock_is_git_repo used by run_main_http is the one we set.
    # This means we might need to set it on cli_module if run_main_http doesn't return it early enough.
    # The current run_main_http sets cli_module.is_git_repository = mock_is_git_repo.
    # So, we just need to configure this mock_is_git_repo.

    # Re-patching is_git_repository for this specific test case
    # This is a bit tricky with the helper. Let's ensure the helper uses a fresh mock or allows config.
    # The helper already patches cli_module.is_git_repository to mock_is_git_repo.
    # We need to make *that* mock_is_git_repo behave as we want for this test.
    # The simplest is to re-patch it after run_main_http has set it up, then re-run main.
    # Or, more cleanly, set the side_effect of the mock_is_git_repo *before* cli_module.main() is called by run_main_http.
    # This requires run_main_http to be more flexible or the test to be structured differently.

    # Let's try a more direct approach for this specific test:
    mock_serve_http_local = mock.AsyncMock()
    mock_logger_instance_local = mock.MagicMock(spec=Logger)
    mock_get_logger_local = mock.MagicMock(return_value=mock_logger_instance_local)
    mock_path_is_dir_local = mock.MagicMock(return_value=True)
    mock_is_git_repo_local = mock.MagicMock(return_value=(False, git_error_msg))  # Specific mock for this test
    mock_exit_local = mock.MagicMock(side_effect=SystemExit)
    mock_asyncio_run_local = mock.MagicMock(side_effect=asyncio.run)

    monkeypatch.setattr(cli_module, "serve_http", mock_serve_http_local)
    monkeypatch.setattr(cli_module, "get_logger", mock_get_logger_local)
    monkeypatch.setattr(Path, "is_dir", mock_path_is_dir_local)  # Ensure this is specific if needed
    monkeypatch.setattr(Path, "resolve", specific_tmp_path_resolve)  # Use the tmp_path aware resolver
    monkeypatch.setattr(Path, "exists", mock.MagicMock(return_value=True))  # Assume exists for this path
    monkeypatch.setattr(cli_module, "is_git_repository", mock_is_git_repo_local)
    monkeypatch.setattr(sys, "exit", mock_exit_local)
    monkeypatch.setattr(asyncio, "run", mock_asyncio_run_local)
    monkeypatch.setattr(sys, "argv", ["script_name"] + args)

    with pytest.raises(SystemExit):
        cli_module.main()

    resolved_not_git_dir = not_git_dir.resolve()
    mock_is_git_repo_local.assert_called_once_with(resolved_not_git_dir)
    mock_logger_instance_local.critical.assert_called_once()
    critical_msg = mock_logger_instance_local.critical.call_args[0][0]
    assert f"Error: Specified working directory is not a valid git repository: {resolved_not_git_dir}" in critical_msg
    assert git_error_msg in critical_msg
    mock_exit_local.assert_called_once_with(1)
    mock_serve_http_local.assert_not_called()


@pytest.mark.parametrize("invalid_port", [80, 0, 1023, 65536, 70000])
def test_http_mode_invalid_port_range(monkeypatch: pytest.MonkeyPatch, invalid_port: int):
    """Test HTTP mode with invalid port numbers (outside 1024-65535)."""
    args = ["--server-mode", "http", "--http-port", str(invalid_port), "--current-working-dir", "."]
    (mock_serve_http, _, mock_logger_instance, _, _, mock_exit, _, _, _) = run_main_http(monkeypatch, args)

    # _validate_http_config logs critical, then raises ValueError.
    # _run_server_by_mode catches ValueError and logs critical again.
    assert mock_logger_instance.critical.call_count == 2

    expected_error_msg_direct = f"Invalid HTTP port number: {invalid_port}. Port must be between 1024 and 65535."

    expected_calls = [
        mock.call(expected_error_msg_direct),  # First call from _validate_http_config
        mock.call(f"Server configuration error: {expected_error_msg_direct}"),  # Second call from _run_server_by_mode
    ]
    mock_logger_instance.critical.assert_has_calls(expected_calls, any_order=False)

    mock_exit.assert_called_once_with(1)
    mock_serve_http.assert_not_called()  # Server should not start


def test_http_mode_port_conflict(monkeypatch: pytest.MonkeyPatch):
    """Test HTTP mode when the port is already in use."""
    conflict_port = DEFAULT_HTTP_PORT
    error_message = f"HTTP server port {conflict_port} is already in use"  # Simplified, actual message might vary

    args = ["--server-mode", "http", "--http-port", str(conflict_port), "--current-working-dir", "."]

    # Manual setup for this specific test:
    mock_serve_http_local = mock.AsyncMock(side_effect=ValueError(error_message))  # Raise error when awaited
    mock_logger_instance_local = mock.MagicMock(spec=Logger)
    mock_get_logger_local = mock.MagicMock(return_value=mock_logger_instance_local)
    mock_path_is_dir_local = mock.MagicMock(return_value=True)
    mock_is_git_repo_local = mock.MagicMock(return_value=(True, None))
    mock_exit_local = mock.MagicMock(side_effect=SystemExit)

    # Mock asyncio.run to actually run the coroutine, which will raise the side_effect.
    mock_asyncio_run_local = mock.MagicMock(side_effect=asyncio.run)

    monkeypatch.setattr(cli_module, "serve_http", mock_serve_http_local)  # Patched to our mock with side_effect
    monkeypatch.setattr(cli_module, "get_logger", mock_get_logger_local)
    monkeypatch.setattr(Path, "is_dir", mock_path_is_dir_local)
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: Path(os.path.abspath(str(self))))
    monkeypatch.setattr(Path, "exists", mock.MagicMock(return_value=True))
    monkeypatch.setattr(cli_module, "is_git_repository", mock_is_git_repo_local)
    monkeypatch.setattr(sys, "exit", mock_exit_local)
    monkeypatch.setattr(asyncio, "run", mock_asyncio_run_local)
    monkeypatch.setattr(sys, "argv", ["script_name"] + args)

    with pytest.raises(SystemExit):
        cli_module.main()

    mock_serve_http_local.assert_called_once()  # Ensure it was called
    mock_logger_instance_local.critical.assert_called_once()
    assert f"Server configuration error: {error_message}" in mock_logger_instance_local.critical.call_args[0][0]
    mock_exit_local.assert_called_once_with(1)


def test_http_mode_empty_host(monkeypatch: pytest.MonkeyPatch):
    """Test HTTP mode with an empty host string."""
    args = [
        "--server-mode",
        "http",
        "--http-host",
        "",  # Empty host
        "--current-working-dir",
        ".",
    ]
    (mock_serve_http, _, mock_logger_instance, _, _, mock_exit, _, _, _) = run_main_http(monkeypatch, args)

    # _validate_http_config logs critical, then raises ValueError.
    # _run_server_by_mode catches ValueError and logs critical again.
    assert mock_logger_instance.critical.call_count == 2

    expected_error_msg_direct = "HTTP host cannot be empty"

    expected_calls = [
        mock.call(expected_error_msg_direct),  # First call from _validate_http_config
        mock.call(f"Server configuration error: {expected_error_msg_direct}"),  # Second call from _run_server_by_mode
    ]
    mock_logger_instance.critical.assert_has_calls(expected_calls, any_order=False)

    mock_exit.assert_called_once_with(1)
    mock_serve_http.assert_not_called()


def test_http_mode_version_flag(monkeypatch: pytest.MonkeyPatch, capsys):
    """Test the --version flag in HTTP mode context (behavior is mode-agnostic)."""
    args = ["--server-mode", "http", "--version"]  # CWD not needed for --version

    # For --version, main exits early. No need for full run_main_http mocks.
    mock_exit = mock.MagicMock(side_effect=SystemExit)
    monkeypatch.setattr(sys, "exit", mock_exit)
    monkeypatch.setattr(sys, "argv", ["script_name"] + args)

    # Mock __version__ where it's accessed by cli.py
    # cli.py does: from aider_mcp_server import __version__
    # So we need to mock that module-level import if it's dynamic, or ensure it's available.
    # The import is at the top of the test file, so mcp_server_version is available.
    # The cli.main function imports it locally: from aider_mcp_server import __version__

    # Minimal mocks for version flag, as main() returns early.
    # get_logger is called before arg parsing in cli.main's structure.
    mock_logger_instance = mock.MagicMock(spec=Logger)  # Create a new mock instance for logger
    mock_get_logger = mock.MagicMock(return_value=mock_logger_instance)  # mock get_logger
    monkeypatch.setattr(cli_module, "get_logger", mock_get_logger)  # Patch it in cli_module

    # cli.main() should return 0 for --version, not raise SystemExit via sys.exit()
    actual_exit_code = cli_module.main()
    assert actual_exit_code == 0

    captured = capsys.readouterr()
    assert f"Aider MCP Server version {mcp_server_version}" in captured.out.strip()
    mock_exit.assert_not_called()  # sys.exit() is not called by cli.main() for --version


def test_http_mode_missing_cwd(monkeypatch: pytest.MonkeyPatch):
    """Test HTTP mode fails if --current-working-dir is missing."""
    args = ["--server-mode", "http"]  # Missing --current-working-dir

    # No need for full run_main_http, as argparse should fail early.
    mock_exit = mock.MagicMock(side_effect=SystemExit)
    monkeypatch.setattr(sys, "exit", mock_exit)
    # We need to capture stderr for argparse errors.
    # The parser.error() call in cli.py calls sys.exit(2) by default.
    # Our mock_exit will catch this.

    # Mock get_logger because it's called before arg parsing fully completes in main()
    mock_logger_instance = mock.MagicMock(spec=Logger)
    mock_get_logger = mock.MagicMock(return_value=mock_logger_instance)
    monkeypatch.setattr(cli_module, "get_logger", mock_get_logger)

    monkeypatch.setattr(sys, "argv", ["script_name"] + args)

    with pytest.raises(SystemExit):
        cli_module.main()

    # Argparse error message goes to stderr and then sys.exit(2)
    # The cli.py explicitly calls sys.exit(1) after parser.error()
    # Let's check the exit code.
    # The parser.error() itself calls sys.exit(2).
    # cli.py has: parser.error(...); sys.exit(1)
    # So the sys.exit(1) should be what's called.

    # The critical part is that `parser.error` is called.
    # We can't easily mock `parser.error` without complex argparse mocking.
    # Instead, we check that `sys.exit` was called with the expected code.
    # The `main` function in `cli.py` has a specific check:
    # if args.current_working_dir is None:
    #     parser.error("the following arguments are required: --current-working-dir")
    #     sys.exit(1) # This is the line we expect to hit.

    # We need to ensure that the `parser.error` call doesn't cause an unhandled exit.
    # `argparse.ArgumentParser.error` prints to stderr and calls `sys.exit(2)`.
    # Our `mock_exit` will catch this.
    # The `cli.py` code has `parser.error(...)` followed by `sys.exit(1)`.
    # The `parser.error` will call `sys.exit(2)`. If `mock_exit` has `side_effect=SystemExit`,
    # then the `sys.exit(1)` line might not be reached.

    # Let's verify the call to mock_exit.
    # If parser.error calls sys.exit(2), then mock_exit will be called with 2.
    # The cli.py code is: parser.error(...); sys.exit(1).
    # parser.error() itself calls sys.exit(2), so the sys.exit(1) line is unreachable.
    mock_exit.assert_called_once_with(2)


def test_http_mode_verbose_logging(monkeypatch: pytest.MonkeyPatch):
    """Test that verbose logging is enabled with -v/--verbose in HTTP mode."""
    args = ["--server-mode", "http", "--current-working-dir", ".", "-v"]
    (mock_serve_http, mock_get_logger, mock_logger_instance, _, _, mock_exit, _, _, _) = run_main_http(
        monkeypatch, args
    )

    # Check that get_logger was called with verbose=True or level=DEBUG
    # The _setup_logging function in cli.py handles this.
    # get_logger_func(__name__, log_dir=log_dir_path, level=log_level_override, verbose=args.verbose)

    # We check the call to the get_logger mock that run_main_http sets up.
    # This mock is cli_module.get_logger.
    mock_get_logger.assert_called()
    # The last call to get_logger is from _setup_logging
    last_call_kwargs = mock_get_logger.call_args_list[-1].kwargs
    assert last_call_kwargs.get("verbose") is True
    # Also check that the logger instance (returned by get_logger) had debug called on it
    # (which _setup_logging does if verbose is true)
    mock_logger_instance.debug.assert_any_call("Verbose logging enabled via -v/--verbose flag.")

    mock_serve_http.assert_called_once()  # Ensure server still tries to start
    mock_exit.assert_not_called()
