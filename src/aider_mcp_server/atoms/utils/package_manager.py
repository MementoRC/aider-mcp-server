import os
import subprocess
from typing import List, Optional

from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)


class PackageManagerError(Exception):
    """
    Base exception for package manager operations.
    FIX 2: Constructor now accepts 'output' as a positional argument.
    """

    def __init__(self, message: str, output: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.output = output


class PoetryPackageManager:
    """
    Manages Python packages using Poetry.
    """

    def __init__(self, project_path: str):
        """
        Initialize the Poetry package manager.

        Args:
            project_path: Path to the root of the Poetry project.
        """
        self.project_path = os.path.abspath(project_path)
        if not os.path.isdir(self.project_path):
            raise ValueError(f"Project path does not exist: {self.project_path}")
        if not os.path.exists(os.path.join(self.project_path, "pyproject.toml")):
            logger.warning(f"pyproject.toml not found in {self.project_path}. This might not be a Poetry project.")
        logger.info(f"Initialized PoetryPackageManager for project: {self.project_path}")

    def _run_poetry(self, args: List[str], capture_output: bool = True) -> str:
        """
        Run a poetry command in the project directory.

        Args:
            args: List of poetry command arguments.
            capture_output: If True, return stdout.

        Returns:
            Output of the command if capture_output is True, else empty string.

        Raises:
            PackageManagerError: If the poetry command fails.
        """
        cmd = ["poetry"] + args
        try:
            logger.debug(f"Running poetry command: {' '.join(cmd)}")
            result = subprocess.run(  # noqa: S603,S607
                cmd,
                cwd=self.project_path,
                check=True,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                encoding="utf-8",
            )
            if capture_output:
                logger.verbose(f"Poetry output length: {len(result.stdout)} chars")
                return result.stdout
            return ""
        except subprocess.CalledProcessError as e:
            # FIX 2: Pass output as a positional argument to PackageManagerError
            error_message = f"Poetry command failed: {' '.join(cmd)}"
            logger.error(f"{error_message}\n{e.stderr}")
            raise PackageManagerError(error_message, e.stderr) from e
        except FileNotFoundError as e:
            error_message = "Poetry executable not found. Is Poetry installed and in PATH?"
            logger.error(error_message)
            raise PackageManagerError(error_message) from e
        except Exception as e:
            error_message = f"Unexpected error running poetry command: {' '.join(cmd)}"
            logger.error(f"{error_message}\n{e}")
            raise PackageManagerError(error_message, str(e)) from e

    def list_outdated_packages(self) -> List[str]:
        """
        List outdated packages.

        Returns:
            A list of outdated package names.
        """
        logger.info("Listing outdated packages...")
        try:
            # This is a simplified placeholder. Real poetry outdated command output parsing
            # would be more complex.
            output = self._run_poetry(["show", "--outdated", "--no-ansi"])
            lines = output.strip().split("\n")
            outdated = []
            # Assuming output format like:
            # package_name current_version -> latest_version
            for line in lines:
                parts = line.split()
                if len(parts) >= 3 and "->" in parts:
                    outdated.append(parts[0])
            logger.debug(f"Outdated packages found: {outdated}")
            return outdated
        except PackageManagerError as e:
            logger.error(f"Failed to list outdated packages: {e.message}")
            raise

    def update_packages(self, packages: List[str]) -> None:
        """
        Update specific packages.

        Args:
            packages: List of package names to update.
        """
        logger.info(f"Updating packages: {', '.join(packages)}")
        try:
            self._run_poetry(["update"] + packages)
            logger.info(f"Successfully updated packages: {', '.join(packages)}")
        except PackageManagerError as e:
            logger.error(f"Failed to update packages {', '.join(packages)}: {e.message}")
            raise

    def update_all_packages(self) -> None:
        """
        Update all packages.
        """
        logger.info("Updating all packages...")
        try:
            self._run_poetry(["update"])
            logger.info("Successfully updated all packages.")
        except PackageManagerError as e:
            logger.error(f"Failed to update all packages: {e.message}")
            raise
