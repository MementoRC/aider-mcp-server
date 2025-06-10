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

import os
import hashlib
import subprocess
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
        if not self.is_git_repo():
            logger.error(f"Not a git repository: {self.repo_path}")
            raise FileIntegrityError(f"Not a git repository: {self.repo_path}")

    def is_git_repo(self) -> bool:
        """
        Check if the current directory is a git repository.

        Returns:
            True if .git exists and is a directory, False otherwise.
        """
        git_dir = os.path.join(self.repo_path, ".git")
        is_repo = os.path.isdir(git_dir)
        logger.debug(f"Checking if {self.repo_path} is a git repo: {is_repo}")
        return is_repo

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
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                check=True,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                encoding="utf-8"
            )
            if capture_output:
                logger.verbose(f"Git output: {result.stdout.strip()}")
                return result.stdout
            return ""
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {' '.join(cmd)}\n{e.stderr}")
            raise FileIntegrityError(
                f"Git command failed: {' '.join(cmd)}: {e.stderr}"
            )
        except Exception as e:
            logger.error(f"Unexpected error running git command: {' '.join(cmd)}\n{e}")
            raise FileIntegrityError(
                f"Unexpected error running git command: {' '.join(cmd)}: {e}"
            )

    def calculate_checksum(self, content: str, algorithm: str = 'sha256') -> str:
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
        if algorithm not in ('md5', 'sha256'):
            logger.error(f"Unsupported checksum algorithm: {algorithm}")
            raise ValueError(f"Unsupported checksum algorithm: {algorithm}")

        data = content.encode('utf-8')
        if algorithm == 'md5':
            checksum = hashlib.md5(data).hexdigest()
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
        line_count = len(content.splitlines())
        logger.debug(f"Counted {line_count} lines")
        return line_count

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
        if ext == '.py':
            try:
                compile(content, file_path, 'exec')
                logger.debug("Python syntax valid")
                return True
            except SyntaxError as e:
                logger.error(f"Python syntax error in {file_path}: {e}")
                raise SyntaxValidationError(f"Python syntax error in {file_path}: {e}")
        elif ext in ('.js', '.ts'):
            # Use node or tsc for JS/TS syntax check
            temp_filename = None
            import tempfile
            try:
                with tempfile.NamedTemporaryFile('w', suffix=ext, delete=False) as tmp:
                    tmp.write(content)
                    temp_filename = tmp.name
                if ext == '.js':
                    cmd = ['node', '--check', temp_filename]
                else:
                    cmd = ['tsc', '--noEmit', temp_filename]
                logger.debug(f"Running syntax check: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding='utf-8'
                )
                if result.returncode != 0:
                    logger.error(f"Syntax error in {file_path}: {result.stderr.strip()}")
                    raise SyntaxValidationError(f"Syntax error in {file_path}: {result.stderr.strip()}")
                logger.debug(f"Syntax valid for {file_path}")
                return True
            finally:
                if temp_filename and os.path.exists(temp_filename):
                    os.remove(temp_filename)
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
        rel_path = os.path.relpath(file_path, self.repo_path)
        status_output = self._run_git(['status', '--porcelain', '--', rel_path], capture_output=True)
        status = status_output.strip()
        if not status:
            logger.debug(f"File {file_path} is clean in git")
            return 'clean'
        elif status.startswith('??'):
            logger.debug(f"File {file_path} is untracked in git")
            return 'untracked'
        else:
            logger.debug(f"File {file_path} has status in git: {status}")
            return status

    def capture_file_integrity_baseline(self, target_files: List[str]) -> Dict[str, Any]:
        """
        Capture the integrity baseline for a list of target files.

        Args:
            target_files: List of file paths to capture baseline for.

        Returns:
            A dictionary mapping file paths to their integrity metrics.

        Raises:
            FileNotFoundError: If a file does not exist.
            SyntaxValidationError: If syntax validation fails.
        """
        baseline = {}
        for file_path in target_files:
            abs_path = os.path.join(self.repo_path, file_path)
            if not os.path.isfile(abs_path):
                logger.error(f"File not found: {abs_path}")
                raise FileIntegrityFileNotFoundError(f"File not found: {abs_path}")
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"Error reading file {abs_path}: {e}")
                raise FileIntegrityError(f"Error reading file {abs_path}: {e}")

            # Calculate metrics
            checksum = self.calculate_checksum(content, algorithm='sha256')
            line_count = self.count_lines(content)
            self.validate_syntax(abs_path, content)
            git_status = self.get_git_status(abs_path)

            baseline[file_path] = {
                'checksum_sha256': checksum,
                'line_count': line_count,
                'git_status': git_status,
            }
            logger.info(f"Captured baseline for {file_path}: {baseline[file_path]}")
        return baseline
