"""
Aider validation utilities for detecting and preventing empty file issues.

This module provides validation functions to detect when aider calls may fail
or produce empty files, particularly in architect mode with nonexistent readonly files.
"""

import pathlib
from typing import Any, Dict, List, Optional, Tuple

from aider_mcp_server.atoms.errors.application_errors import InputValidationError, ResourceNotFoundError
from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)


class AiderValidationError(InputValidationError):
    """Raised when aider call parameters are invalid or likely to fail."""

    pass


class AiderMisfireError(AiderValidationError):
    """Raised when aider call produces empty or invalid results."""

    pass


def validate_file_references(
    relative_editable_files: List[str],
    relative_readonly_files: List[str],
    working_directory: str,
    architect_mode: bool = False,
) -> None:
    """
    Validate file references before making an aider call.

    Args:
        relative_editable_files: List of files that aider can edit
        relative_readonly_files: List of files that aider can read but not edit
        working_directory: Working directory for resolving relative paths
        architect_mode: Whether architect mode is enabled

    Raises:
        AiderValidationError: When file references are invalid
        ResourceNotFoundError: When required readonly files don't exist

    Note:
        In architect mode, nonexistent readonly files cause aider to create
        empty target files, so we validate them strictly.
    """
    working_path = pathlib.Path(working_directory)
    validation_errors: List[str] = []
    missing_readonly_files: List[str] = []

    # Validate working directory exists
    if not working_path.exists():
        raise ResourceNotFoundError(
            error_code="AIDER_WORKING_DIR_NOT_FOUND",
            user_friendly_message=f"Working directory does not exist: {working_directory}",
            details={"working_directory": working_directory},
        )

    # Validate editable files (can be created if they don't exist)
    for file_path in relative_editable_files:
        full_path = working_path / file_path
        try:
            # Ensure parent directory exists for files that may be created
            full_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            validation_errors.append(f"Cannot access parent directory for {file_path}: {e}")

    # Validate readonly files (must exist, especially in architect mode)
    for file_path in relative_readonly_files:
        full_path = working_path / file_path
        if not full_path.exists():
            missing_readonly_files.append(file_path)
            if architect_mode:
                # In architect mode, missing readonly files cause empty results
                validation_errors.append(f"Readonly file required for architect mode does not exist: {file_path}")
            else:
                # In regular mode, log warning but don't fail
                logger.warning(f"Readonly file does not exist (aider will skip): {file_path}")

    # Raise validation errors if any found
    if validation_errors:
        if architect_mode and missing_readonly_files:
            raise AiderValidationError(
                error_code="AIDER_ARCHITECT_MISSING_READONLY_FILES",
                user_friendly_message=(
                    "Architect mode requires all readonly files to exist. "
                    "Missing readonly files cause empty output files."
                ),
                details={
                    "missing_readonly_files": missing_readonly_files,
                    "architect_mode": architect_mode,
                    "validation_errors": validation_errors,
                },
            )
        else:
            raise AiderValidationError(
                error_code="AIDER_INVALID_FILE_REFERENCES",
                user_friendly_message="Invalid file references provided to aider",
                details={
                    "validation_errors": validation_errors,
                    "working_directory": working_directory,
                },
            )


def detect_aider_misfire(
    aider_result: Dict[str, Any],
    relative_editable_files: List[str],
    working_directory: str,
    min_content_size: int = 10,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Detect if aider reported success but produced empty or invalid files.

    Args:
        aider_result: The result dictionary from aider execution
        relative_editable_files: List of files that were supposed to be edited
        working_directory: Working directory for resolving file paths
        min_content_size: Minimum file size to consider meaningful content

    Returns:
        Tuple of (is_misfire: bool, details: Optional[Dict])

    Note:
        This function detects the common case where aider reports success
        but creates empty files due to errors like missing readonly files.
    """
    working_path = pathlib.Path(working_directory)
    misfire_details: Dict[str, Any] = {}
    empty_files: List[str] = []
    missing_files: List[str] = []

    # Check if aider reported success
    if not aider_result.get("success", False):
        return False, None  # Not a misfire if aider reported failure

    # Check each editable file for meaningful content
    for file_path in relative_editable_files:
        full_path = working_path / file_path

        if not full_path.exists():
            missing_files.append(file_path)
            continue

        try:
            file_size = full_path.stat().st_size
            if file_size == 0:
                empty_files.append(file_path)
                continue

            if file_size < min_content_size:
                # Check if file has meaningful content beyond whitespace
                content = full_path.read_text(encoding="utf-8", errors="ignore").strip()
                if len(content) < min_content_size:
                    empty_files.append(file_path)

        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Error checking file content for {file_path}: {e}")
            # Treat unreadable files as potentially problematic
            empty_files.append(file_path)

    # Determine if this is a misfire
    is_misfire = bool(empty_files or missing_files)

    if is_misfire:
        misfire_details = {
            "empty_files": empty_files,
            "missing_files": missing_files,
            "working_directory": working_directory,
            "min_content_size": min_content_size,
            "aider_reported_success": aider_result.get("success", False),
        }

        # Add additional context from aider result
        if "changes_summary" in aider_result:
            misfire_details["changes_summary"] = aider_result["changes_summary"]

        logger.warning(f"Detected aider misfire: {len(empty_files)} empty files, {len(missing_files)} missing files")

    return is_misfire, misfire_details if is_misfire else None


def raise_on_aider_misfire(
    aider_result: Dict[str, Any],
    relative_editable_files: List[str],
    working_directory: str,
    min_content_size: int = 10,
) -> None:
    """
    Check for aider misfire and raise exception if detected.

    Args:
        aider_result: The result dictionary from aider execution
        relative_editable_files: List of files that were supposed to be edited
        working_directory: Working directory for resolving file paths
        min_content_size: Minimum file size to consider meaningful content

    Raises:
        AiderMisfireError: When aider misfire is detected
    """
    is_misfire, details = detect_aider_misfire(
        aider_result, relative_editable_files, working_directory, min_content_size
    )

    if is_misfire:
        raise AiderMisfireError(
            error_code="AIDER_MISFIRE_DETECTED",
            user_friendly_message=(
                "Aider reported success but produced empty or missing files. "
                "This often occurs with missing readonly files in architect mode."
            ),
            details=details,
        )


def validate_aider_parameters(
    relative_editable_files: List[str],
    relative_readonly_files: Optional[List[str]] = None,
    working_directory: str = ".",
    architect_mode: bool = False,
    **kwargs: Any,
) -> None:
    """
    Comprehensive validation of aider parameters before execution.

    Args:
        relative_editable_files: List of files that aider can edit
        relative_readonly_files: List of files that aider can read but not edit
        working_directory: Working directory for resolving relative paths
        architect_mode: Whether architect mode is enabled
        **kwargs: Additional aider parameters (for future extensibility)

    Raises:
        AiderValidationError: When parameters are invalid
        ResourceNotFoundError: When required resources don't exist
    """
    readonly_files = relative_readonly_files or []

    # Basic parameter validation
    if not relative_editable_files:
        raise AiderValidationError(
            error_code="AIDER_NO_EDITABLE_FILES",
            user_friendly_message="At least one editable file must be specified",
            details={"relative_editable_files": relative_editable_files},
        )

    # Validate file references
    validate_file_references(
        relative_editable_files=relative_editable_files,
        relative_readonly_files=readonly_files,
        working_directory=working_directory,
        architect_mode=architect_mode,
    )

    logger.debug(
        f"Aider parameters validated: {len(relative_editable_files)} editable files, "
        f"{len(readonly_files)} readonly files, architect_mode={architect_mode}"
    )
