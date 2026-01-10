import os
from typing import List, Optional

from aider_mcp_server.atoms.logging.logger import get_logger

# FIX 1: Correct import for GitCheckpointManager
from aider_mcp_server.atoms.utils.git_checkpoint import GitCheckpointManager
from aider_mcp_server.atoms.utils.package_manager import PackageManagerError, PoetryPackageManager

logger = get_logger(__name__)


class DependencyUpdaterError(Exception):
    """Base exception for dependency updater operations."""

    pass


class DependencyUpdater:
    """
    Manages dependency updates for the Aider MCP Server.

    This class handles checking for updates, applying them, and ensuring
    safety through git checkpoints.
    """

    def __init__(self, repo_path: str):
        """
        Initialize the DependencyUpdater.

        Args:
            repo_path: Path to the root of the git repository.
        """
        self.repo_path = os.path.abspath(repo_path)
        self.git_manager = GitCheckpointManager(self.repo_path)
        self.package_manager = PoetryPackageManager(self.repo_path)
        logger.info(f"Initialized DependencyUpdater for repository: {self.repo_path}")

    def check_for_updates(self) -> List[str]:
        """
        Check for available dependency updates.

        Returns:
            A list of packages with available updates.
        """
        logger.info("Checking for dependency updates...")
        try:
            # This is a placeholder. In a real scenario, this would call
            # a package manager method like poetry.show_outdated()
            # For now, simulate some outdated packages.
            outdated_packages = self.package_manager.list_outdated_packages()
            if outdated_packages:
                logger.info(f"Found updates for: {', '.join(outdated_packages)}")
            else:
                logger.info("No dependency updates found.")
            return outdated_packages
        except PackageManagerError as e:
            logger.error(f"Failed to check for updates: {e.message}")
            raise DependencyUpdaterError(f"Failed to check for updates: {e.message}") from e

    def apply_updates(
        self,
        packages: Optional[List[str]] = None,
        operation_id: str = "dependency_update",
        uncommitted_strategy: str = "stash",
    ) -> str:
        """
        Apply dependency updates, creating a git checkpoint before.

        Args:
            packages: List of specific packages to update. If None, update all.
            operation_id: Identifier for the git checkpoint.
            uncommitted_strategy: Strategy for handling uncommitted changes before checkpoint.

        Returns:
            The commit hash of the git checkpoint created.
        """
        logger.info(f"Applying dependency updates (packages: {packages or 'all'})...")

        # Create a git checkpoint before applying changes
        checkpoint_hash = self.git_manager.create_checkpoint(
            operation_id=operation_id,
            model="dependency_updater",  # Placeholder model name
            target_files=["pyproject.toml", "poetry.lock"],  # Common Poetry files
            operation_params={"packages": packages or "all"},
            uncommitted_strategy=uncommitted_strategy,
        )
        logger.info(f"Git checkpoint created: {checkpoint_hash}")

        try:
            if packages:
                self.package_manager.update_packages(packages)
            else:
                self.package_manager.update_all_packages()
            logger.info("Dependency updates applied successfully.")
            return checkpoint_hash
        except PackageManagerError as e:
            logger.error(f"Failed to apply updates: {e.message}")
            # In a real system, you might trigger a rollback here
            raise DependencyUpdaterError(f"Failed to apply updates: {e.message}") from e
