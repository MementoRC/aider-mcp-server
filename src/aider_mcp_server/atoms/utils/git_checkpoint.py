"""
GitCheckpointManager for Aider Safety Operations.

Provides a robust system for creating safety checkpoints in a git repository
before executing Aider operations. Checkpoints are created as commits with
a special naming convention and include metadata for traceability.

Features:
- Safety checkpoint creation with timestamp and operation ID
- Metadata in commit messages (model, files, parameters)
- Handling of uncommitted changes (error, stash, or commit strategies)
- Git repository state checks
- Logging and error handling consistent with codebase patterns

Author: Aider MCP Server Team
"""

import os
import subprocess
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)


class GitCheckpointError(Exception):
    """Base exception for git checkpoint operations."""

    pass


class NotAGitRepositoryError(GitCheckpointError):
    """Raised when the target directory is not a git repository."""

    pass


class UncommittedChangesError(GitCheckpointError):
    """Raised when uncommitted changes are present and not allowed."""

    pass


class GitCommandError(GitCheckpointError):
    """Raised when a git command fails."""

    def __init__(self, message: str, output: Optional[str] = None):
        super().__init__(message)
        self.output = output


class GitCheckpointManager:
    """
    Manages creation of git safety checkpoints for Aider operations.

    Usage:
        manager = GitCheckpointManager(repo_path)
        manager.create_checkpoint(
            operation_id="edit123",
            model="openai/gpt-4.1",
            target_files=["main.py", "utils.py"],
            operation_params={"mode": "architect"},
            uncommitted_strategy="stash"
        )
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
            raise NotAGitRepositoryError(f"Not a git repository: {self.repo_path}")

    def is_git_repo(self) -> bool:
        """
        Check if the current directory is a git repository (supports worktrees).

        Returns:
            True if the directory is a git repo or worktree, False otherwise.
        """
        try:
            git_env = {**os.environ, "CLAUDECODE": "0"}
            subprocess.run(  # noqa: S603
                ["git", "rev-parse", "--git-dir"],  # noqa: S607
                cwd=self.repo_path,
                capture_output=True,
                check=True,
                env=git_env,
            )
            logger.debug(f"Checking if {self.repo_path} is a git repo: True")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.debug(f"Checking if {self.repo_path} is a git repo: False")
            return False

    def has_uncommitted_changes(self) -> bool:
        """
        Check for uncommitted changes in the repository.

        Returns:
            True if there are uncommitted changes, False otherwise.
        """
        result = self._run_git(["status", "--porcelain"], capture_output=True)
        has_changes = bool(result and result.strip())
        logger.debug(f"Uncommitted changes present: {has_changes}")
        return has_changes

    def _run_git(self, args: List[str], capture_output: bool = False) -> str:
        """
        Run a git command in the repository.

        Args:
            args: List of git command arguments.
            capture_output: If True, return stdout.

        Returns:
            Output of the command if capture_output is True, else empty string.

        Raises:
            GitCommandError: If the git command fails.
        """
        cmd = ["git"] + args
        try:
            logger.debug(f"Running git command: {' '.join(cmd)}")
            git_env = {**os.environ, "CLAUDECODE": "0"}
            result = subprocess.run(  # noqa: S603
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
            raise GitCommandError(f"Git command failed: {' '.join(cmd)}", output=e.stderr) from e  # B904
        except Exception as e:
            logger.error(f"Unexpected error running git command: {' '.join(cmd)}\n{e}")
            raise GitCommandError(
                f"Unexpected error running git command: {' '.join(cmd)}", output=str(e)
            ) from e  # B904

    def handle_uncommitted_changes(self, strategy: str = "error") -> None:
        """
        Handle uncommitted changes according to the specified strategy.

        Args:
            strategy: One of "error", "stash", "commit".

        Raises:
            UncommittedChangesError: If strategy is "error" and changes exist.
            GitCommandError: If git commands fail.
        """
        if not self.has_uncommitted_changes():
            logger.debug("No uncommitted changes to handle.")
            return

        if strategy == "error":
            logger.error("Uncommitted changes detected and strategy is 'error'.")
            raise UncommittedChangesError("Uncommitted changes present in the repository.")
        elif strategy == "stash":
            logger.info("Stashing uncommitted changes before checkpoint.")
            self._run_git(["stash", "push", "-u", "-m", "Aider safety checkpoint stash"])  # noqa: S603
        elif strategy == "commit":
            logger.info("Committing all uncommitted changes before checkpoint.")
            self._run_git(["add", "-A"])  # noqa: S603
            commit_msg = "Aider safety auto-commit: uncommitted changes before checkpoint"
            self._run_git(["commit", "-m", commit_msg])  # noqa: S603
        else:
            logger.error(f"Unknown uncommitted changes strategy: {strategy}")
            raise ValueError(f"Unknown uncommitted changes strategy: {strategy}")

    def create_checkpoint(
        self,
        operation_id: str,
        model: str,
        target_files: List[str],
        operation_params: Optional[Dict[str, Any]] = None,
        uncommitted_strategy: str = "error",
    ) -> str:
        """
        Create a git safety checkpoint commit.

        Args:
            operation_id: Unique identifier for the Aider operation.
            model: Name of the AI model used.
            target_files: List of files involved in the operation.
            operation_params: Additional parameters for the operation.
            uncommitted_strategy: How to handle uncommitted changes ("error", "stash", "commit").

        Returns:
            The commit hash of the created checkpoint.

        Raises:
            GitCheckpointError: On failure to create checkpoint.
        """
        logger.info(f"Creating git checkpoint for operation {operation_id} with model {model}")

        # Handle uncommitted changes as per strategy
        self.handle_uncommitted_changes(strategy=uncommitted_strategy)

        # Check if there are any changes to commit after staging
        self._run_git(["add", "-A"])  # noqa: S603
        if not self.has_uncommitted_changes():
            logger.info("No changes to commit after staging, checkpoint creation skipped")
            # Return the operation_id as checkpoint_id when no commit is needed
            return f"checkpoint-{operation_id}"

        # Prepare commit message with metadata
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        checkpoint_tag = f"AIDER_SAFETY_CHECKPOINT_{timestamp}_{operation_id}"
        params_str = "\n".join(f"{k}: {v}" for k, v in (operation_params or {}).items()) if operation_params else ""
        commit_message = (
            f"{checkpoint_tag}\n"
            f"Model: {model}\n"
            f"Target files: {', '.join(target_files)}\n"
            f"Operation parameters:\n{params_str}\n"
        )

        # Commit the checkpoint
        try:
            self._run_git(["commit", "-m", commit_message])  # noqa: S603
        except GitCommandError as e:
            # If nothing to commit, still return the current HEAD as checkpoint
            if "nothing to commit" in (e.output or ""):
                logger.warning("No changes to commit for checkpoint; using current HEAD.")
            else:
                raise

        # Get the commit hash of the checkpoint
        commit_hash = self._run_git(["rev-parse", "HEAD"], capture_output=True).strip()  # noqa: S603
        logger.info(f"Created git checkpoint {checkpoint_tag} at {commit_hash}")
        return commit_hash

    def get_latest_checkpoint(self, operation_id: Optional[str] = None) -> Optional[str]:
        """
        Retrieve the latest checkpoint commit hash, optionally filtered by operation_id.

        Args:
            operation_id: If provided, filter checkpoints by this operation ID.

        Returns:
            The commit hash of the latest checkpoint, or None if not found.
        """
        pattern = "AIDER_SAFETY_CHECKPOINT_*"
        if operation_id:
            pattern = f"AIDER_SAFETY_CHECKPOINT_*_{operation_id}"

        try:
            log_output = self._run_git(["log", "--grep", pattern, "--pretty=format:%H", "-n", "1"], capture_output=True)  # noqa: S603
            commit_hash = log_output.strip()
            if commit_hash:
                logger.debug(f"Latest checkpoint for pattern '{pattern}': {commit_hash}")
                return commit_hash
            logger.warning(f"No checkpoint found for pattern: {pattern}")
            return None
        except GitCommandError:
            logger.error("Failed to retrieve latest checkpoint.")
            return None
