"""
FileIntegrityManager for Aider Safety Operations.

Provides a robust system for capturing and verifying file integrity baselines
before executing Aider operations. Baselines include checksums, line counts,
syntax validation, and git status for each target file.

Features:
- File checksum calculation (MD5/SHA256)
- Line count tracking
- Syntax validation for Python, JavaScript, TypeScript
- Git status verification
- Logging and error handling consistent with codebase patterns

Author: Aider MCP Server Team
"""

import hashlib
import os
import subprocess
import tempfile
from typing import Any, Dict, List

from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)


class FileIntegrityError(Exception):
    """Base exception for file integrity operations."""

    pass


class FileIntegrityFileNotFoundError(FileIntegrityError):
    """Raised when a target file is not found."""

    pass


class SyntaxValidationError(FileIntegrityError):
    """Raised when syntax validation fails."""

    pass


class FileIntegrityManager:
    """
    Manages file integrity baselines for Aider operations.

    Usage:
        manager = FileIntegrityManager(repo_path)
        baseline = manager.capture_file_integrity_baseline(target_files)
    """

    def __init__(self, repo_path: str):
        """
        Initialize the manager with the path to the git repository.

        Args:
            repo_path: Path to the root of the git repository.
        """
        self.repo_path = os.path.abspath(repo_path)

        # Check if the path exists and is a directory before proceeding
        if not os.path.isdir(self.repo_path):
            logger.error(f"Repository path does not exist or is not a directory: {self.repo_path}")
            raise FileIntegrityFileNotFoundError(
                f"Repository path does not exist or is not a directory: {self.repo_path}"
            )

        if not self.is_git_repo():
            logger.error(f"Not a git repository: {self.repo_path}")
            raise FileIntegrityError(f"Not a git repository: {self.repo_path}")

    def is_git_repo(self) -> bool:
        """
        Check if the current directory is a git repository (supports worktrees).

        Returns:
            True if the directory is a git repo or worktree, False otherwise.
        """
        try:
            # Use --is-inside-work-tree or --is-inside-git-dir for a more robust check
            # This command exits with 0 if inside a git repo/worktree, 1 otherwise.
            # We already checked if the directory exists in __init__
            git_env = {**os.environ, "CLAUDECODE": "0"}
            subprocess.run(  # noqa: S603,S607
                ["git", "rev-parse", "--is-inside-work-tree"],  # noqa: S607
                cwd=self.repo_path,
                capture_output=True,
                check=True,  # check=True raises CalledProcessError if exit code is non-zero
                text=True,
                env=git_env,
            )
            logger.debug(f"Checking if {self.repo_path} is a git repo: True")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            # CalledProcessError indicates it's not a git repo (exit code 1)
            # FileNotFoundError indicates git command not found (less likely if check=True)
            logger.debug(f"Checking if {self.repo_path} is a git repo: False")
            return False
        except Exception as e:
            # Catch any other unexpected errors
            logger.error(f"Unexpected error checking if {self.repo_path} is a git repo: {e}")
            return False

    def _run_git(self, args: List[str], capture_output: bool = False) -> str:
        """
        Run a git command in the repository.

        Args:
            args: List of git command arguments.
            capture_output: If True, return stdout.

        Returns:
            Output of the command if capture_output is True, else empty string.

        Raises:
            FileIntegrityError: If the git command fails.
        """
        cmd = ["git"] + args
        try:
            logger.debug(f"Running git command: {' '.join(cmd)}")
            git_env = {**os.environ, "CLAUDECODE": "0"}
            result = subprocess.run(  # noqa: S603, S607
                cmd,
                cwd=self.repo_path,
                check=True,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                encoding="utf-8",
                env=git_env,
            )
            if capture_output:
                logger.verbose(f"Git output: {result.stdout.strip()}")
                return result.stdout
            return ""
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {' '.join(cmd)}\n{e.stderr}")
            # Include stdout in the error message as well, sometimes errors go there
            error_output = f"Stderr: {e.stderr}"
            if e.stdout:
                error_output += f"\nStdout: {e.stdout}"
            raise FileIntegrityError(f"Git command failed: {' '.join(cmd)}: {error_output}") from e
        except FileNotFoundError:
            # This might happen if 'git' is not in the PATH
            logger.error(f"Git executable not found when trying to run: {' '.join(cmd)}")
            raise FileIntegrityError(
                f"Git executable not found. Is git installed and in your PATH? Command: {' '.join(cmd)}"
            ) from None  # Use from None to suppress context
        except Exception as e:
            logger.error(f"Unexpected error running git command: {' '.join(cmd)}\n{e}")
            raise FileIntegrityError(f"Unexpected error running git command: {' '.join(cmd)}: {e}") from e

    def calculate_checksum(self, content: str, algorithm: str = "sha256") -> str:
        """
        Calculate the checksum of the file content.

        Args:
            content: The file content as a string.
            algorithm: 'md5' or 'sha256'.

        Returns:
            The hex digest of the checksum.

        Raises:
            ValueError: If an unsupported algorithm is specified.
        """
        if algorithm not in ("md5", "sha256"):
            logger.error(f"Unsupported checksum algorithm: {algorithm}")
            raise ValueError(f"Unsupported checksum algorithm: {algorithm}")

        data = content.encode("utf-8")
        if algorithm == "md5":
            # MD5 is used for non-security purposes (file checksums only)
            checksum = hashlib.md5(data, usedforsecurity=False).hexdigest()  # noqa: S324
        else:
            checksum = hashlib.sha256(data).hexdigest()
        logger.debug(f"Calculated {algorithm} checksum: {checksum}")
        return checksum

    def count_lines(self, content: str) -> int:
        """
        Count the number of lines in the file content.

        Args:
            content: The file content as a string.

        Returns:
            The number of lines.
        """
        # Handle empty content case
        if not content:
            return 0
        # Splitlines handles different line endings (\n, \r\n, \r)
        line_count = len(content.splitlines())
        logger.debug(f"Counted {line_count} lines")
        return line_count

    def _validate_python_syntax(self, file_path: str, content: str) -> bool:
        """Validate Python file syntax."""
        try:
            compile(content, file_path, "exec")
            logger.debug("Python syntax valid")
            return True
        except SyntaxError as e:
            logger.error(f"Python syntax error in {file_path}: {e}")
            raise SyntaxValidationError(f"Python syntax error in {file_path}: {e}") from e
        except Exception as e:
            # Catch other potential errors during compile
            logger.error(f"Unexpected error during Python syntax check for {file_path}: {e}")
            raise SyntaxValidationError(f"Unexpected error during Python syntax check for {file_path}: {e}") from e

    def _validate_js_ts_syntax(self, file_path: str, content: str, ext: str) -> bool:
        """Validate JavaScript or TypeScript file syntax."""
        temp_filename = None
        try:
            # Create a temporary file with the correct extension
            with tempfile.NamedTemporaryFile("w", suffix=ext, delete=False, encoding="utf-8") as tmp:
                tmp.write(content)
                temp_filename = tmp.name
            if ext == ".js":
                # Use 'node --check' for JS syntax validation
                cmd = ["node", "--check", temp_filename]
            else:  # ext == ".ts"
                # Use 'tsc --noEmit' for TS syntax validation
                cmd = ["tsc", "--noEmit", temp_filename]

            logger.debug(f"Running syntax check: {' '.join(cmd)}")
            # Use shell=True on Windows might help find node/tsc, but generally discouraged.
            # Let's stick to shell=False and rely on PATH.
            result = subprocess.run(  # noqa: S603, S607
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8"
            )
            if result.returncode != 0:
                error_output = result.stderr.strip() or result.stdout.strip()
                logger.error(f"Syntax error in {file_path}: {error_output}")
                raise SyntaxValidationError(f"Syntax error in {file_path}: {error_output}")
            logger.debug(f"Syntax valid for {file_path}")
            return True
        except FileNotFoundError:
            # node or tsc command not found
            logger.warning(f"Syntax check skipped for {file_path}: 'node' or 'tsc' command not found.")
            # Treat as valid if the tool isn't available
            return True
        except Exception as e:
            # Catch any other errors during subprocess execution
            logger.error(f"Unexpected error during JS/TS syntax check for {file_path}: {e}")
            raise SyntaxValidationError(f"Unexpected error during JS/TS syntax check for {file_path}: {e}") from e
        finally:
            if temp_filename and os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except OSError as e:
                    logger.warning(f"Could not remove temporary file {temp_filename}: {e}")

    def validate_syntax(self, file_path: str, content: str) -> bool:
        """
        Validate the syntax of the file based on its extension.

        Args:
            file_path: Path to the file (used to determine language).
            content: The file content as a string.

        Returns:
            True if syntax is valid, False otherwise.

        Raises:
            SyntaxValidationError: If syntax is invalid.
        """
        ext = os.path.splitext(file_path)[1].lower()
        logger.debug(f"Validating syntax for {file_path} (ext: {ext})")
        if ext == ".py":
            return self._validate_python_syntax(file_path, content)
        elif ext in (".js", ".ts"):
            return self._validate_js_ts_syntax(file_path, content, ext)
        else:
            logger.warning(f"Unsupported file extension for syntax validation: {file_path}")
            # Consider unsupported files as valid for now
            return True

    def get_git_status(self, file_path: str) -> str:
        """
        Get the git status of a file.

        Args:
            file_path: Path to the file.

        Returns:
            The git status string (e.g., 'modified', 'untracked', 'clean', etc.)
        """
        # Ensure file_path is relative to repo_path for git command
        abs_path = os.path.join(self.repo_path, file_path)
        if not os.path.exists(abs_path):
            # File doesn't exist, can't get git status
            logger.debug(f"File {file_path} does not exist, cannot get git status.")
            return "nonexistent"  # Or raise an error, depending on desired behavior

        rel_path = os.path.relpath(abs_path, self.repo_path)
        # Use --no-ahead-behind and --no-renames for simpler output
        # Use --untracked-files=no to ignore untracked files unless explicitly listed
        # Use -z for null-terminated output, safer for filenames with spaces/special chars
        # git status --porcelain=v1 -z -- <path>
        try:
            status_output = self._run_git(["status", "--porcelain=v1", "-z", "--", rel_path], capture_output=True)
            status_output = status_output.strip("\x00")  # Remove trailing null byte

            if not status_output:
                logger.debug(f"File {file_path} is clean in git")
                return "clean"
            else:
                # Status output format is like "XY filename\x00"
                # X is status in index, Y is status in work tree
                # Common codes: M=modified, A=added, D=deleted, R=renamed, C=copied, U=unmerged, ??=untracked
                # We care about the work tree status (Y) or index status (X) if Y is space
                status_code = status_output[0] if status_output[1] == " " else status_output[1]
                status_map = {
                    "M": "modified",
                    "A": "added",
                    "D": "deleted",
                    "R": "renamed",
                    "C": "copied",
                    "U": "unmerged",
                    "?": "untracked",  # This should ideally not happen with --porcelain=v1 unless file is untracked and explicitly listed
                    "!": "ignored",
                    " ": "staged",  # Staged but not modified in work tree
                }
                status = status_map.get(status_code, f"unknown ({status_output[:2]})")
                logger.debug(f"File {file_path} has status in git: {status} ({status_output.split('\x00')[0]})")
                return status
        except FileIntegrityError as e:
            logger.warning(f"Could not get git status for {file_path}: {e}")
            return "unknown"  # Return unknown status on error

    def capture_file_integrity_baseline(self, target_files: List[str]) -> Dict[str, Any]:
        """
        Capture the integrity baseline for a list of target files.

        Args:
            target_files: List of file paths to capture baseline for (relative to repo_path).

        Returns:
            A dictionary mapping file paths (relative to repo_path) to their integrity metrics.

        Raises:
            FileIntegrityFileNotFoundError: If a file does not exist.
            SyntaxValidationError: If syntax validation fails.
            FileIntegrityError: For other errors like reading the file.
        """
        baseline = {}
        for file_path in target_files:
            # Ensure file_path is treated as relative to repo_path
            abs_path = os.path.join(self.repo_path, file_path)

            if not os.path.isfile(abs_path):
                logger.error(f"File not found for baseline capture: {abs_path}")
                raise FileIntegrityFileNotFoundError(f"File not found for baseline capture: {abs_path}")
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"Error reading file {abs_path} for baseline: {e}")
                raise FileIntegrityError(f"Error reading file {abs_path} for baseline: {e}") from e

            # Calculate metrics
            checksum = self.calculate_checksum(content, algorithm="sha256")
            line_count = self.count_lines(content)
            # Syntax validation raises SyntaxValidationError on failure
            self.validate_syntax(abs_path, content)
            git_status = self.get_git_status(file_path)  # Pass relative path to get_git_status

            baseline[file_path] = {
                "checksum_sha256": checksum,
                "line_count": line_count,
                "git_status": git_status,
            }
            logger.info(f"Captured baseline for {file_path}: {baseline[file_path]}")
        return baseline
