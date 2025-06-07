"""
Tests for aider validation utilities.

This module tests the validation functions that detect and prevent
aider empty file issues, particularly in architect mode.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from aider_mcp_server.atoms.utils.aider_validation import (
    AiderMisfireError,
    AiderValidationError,
    detect_aider_misfire,
    raise_on_aider_misfire,
    validate_aider_parameters,
    validate_file_references,
)


class TestValidateFileReferences:
    """Test the validate_file_references function."""

    def test_validate_with_existing_readonly_files_success(self, tmp_path: Path) -> None:
        """Test validation passes with existing readonly files."""
        # Create test files
        readonly_file = tmp_path / "existing.py"
        readonly_file.write_text("def test(): pass")

        # Should not raise any exception
        validate_file_references(
            relative_editable_files=["new.py"],
            relative_readonly_files=["existing.py"],
            working_directory=str(tmp_path),
            architect_mode=False,
        )

    def test_validate_architect_mode_missing_readonly_files_fails(self, tmp_path: Path) -> None:
        """Test validation fails in architect mode with missing readonly files."""
        with pytest.raises(AiderValidationError) as exc_info:
            validate_file_references(
                relative_editable_files=["new.py"],
                relative_readonly_files=["nonexistent.py"],
                working_directory=str(tmp_path),
                architect_mode=True,
            )

        assert exc_info.value.error_code == "AIDER_ARCHITECT_MISSING_READONLY_FILES"
        assert "architect mode" in exc_info.value.user_friendly_message.lower()
        assert "nonexistent.py" in exc_info.value.details["missing_readonly_files"]

    def test_validate_regular_mode_missing_readonly_files_warns_only(self, tmp_path: Path) -> None:
        """Test validation warns but doesn't fail in regular mode with missing readonly files."""
        with patch("aider_mcp_server.atoms.utils.aider_validation.logger") as mock_logger:
            # Should not raise exception in regular mode
            validate_file_references(
                relative_editable_files=["new.py"],
                relative_readonly_files=["nonexistent.py"],
                working_directory=str(tmp_path),
                architect_mode=False,
            )

            # Should log warning
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "nonexistent.py" in warning_call

    def test_validate_nonexistent_working_directory_fails(self) -> None:
        """Test validation fails with nonexistent working directory."""
        with pytest.raises(Exception):  # ResourceNotFoundError inherits from our custom exception hierarchy
            validate_file_references(
                relative_editable_files=["test.py"],
                relative_readonly_files=[],
                working_directory="/nonexistent/directory",
                architect_mode=False,
            )


class TestValidateAiderParameters:
    """Test the validate_aider_parameters function."""

    def test_validate_empty_editable_files_fails(self, tmp_path: Path) -> None:
        """Test validation fails with no editable files."""
        with pytest.raises(AiderValidationError) as exc_info:
            validate_aider_parameters(
                relative_editable_files=[],
                relative_readonly_files=[],
                working_directory=str(tmp_path),
                architect_mode=False,
            )

        assert exc_info.value.error_code == "AIDER_NO_EDITABLE_FILES"

    def test_validate_successful_parameters(self, tmp_path: Path) -> None:
        """Test validation passes with valid parameters."""
        readonly_file = tmp_path / "existing.py"
        readonly_file.write_text("def helper(): pass")

        # Should not raise any exception
        validate_aider_parameters(
            relative_editable_files=["new.py"],
            relative_readonly_files=["existing.py"],
            working_directory=str(tmp_path),
            architect_mode=False,
        )

    def test_validate_architect_mode_with_valid_files(self, tmp_path: Path) -> None:
        """Test validation passes in architect mode with existing readonly files."""
        readonly_file = tmp_path / "config.py"
        readonly_file.write_text("CONFIG = {'key': 'value'}")

        # Should not raise any exception
        validate_aider_parameters(
            relative_editable_files=["implementation.py"],
            relative_readonly_files=["config.py"],
            working_directory=str(tmp_path),
            architect_mode=True,
        )


class TestDetectAiderMisfire:
    """Test the detect_aider_misfire function."""

    def test_detect_misfire_with_empty_files(self, tmp_path: Path) -> None:
        """Test misfire detection with empty created files."""
        # Create empty file
        empty_file = tmp_path / "empty.py"
        empty_file.touch()

        aider_result = {"success": True, "changes_summary": {"summary": "Files created"}}

        is_misfire, details = detect_aider_misfire(
            aider_result=aider_result,
            relative_editable_files=["empty.py"],
            working_directory=str(tmp_path),
        )

        assert is_misfire is True
        assert details is not None
        assert "empty.py" in details["empty_files"]
        assert details["aider_reported_success"] is True

    def test_detect_misfire_with_meaningful_content(self, tmp_path: Path) -> None:
        """Test no misfire detected with meaningful file content."""
        # Create file with meaningful content
        content_file = tmp_path / "implementation.py"
        content_file.write_text("def main():\n    print('Hello, World!')\n")

        aider_result = {"success": True, "changes_summary": {"summary": "Implementation added"}}

        is_misfire, details = detect_aider_misfire(
            aider_result=aider_result,
            relative_editable_files=["implementation.py"],
            working_directory=str(tmp_path),
        )

        assert is_misfire is False
        assert details is None

    def test_detect_misfire_with_missing_files(self, tmp_path: Path) -> None:
        """Test misfire detection with missing expected files."""
        aider_result = {"success": True, "changes_summary": {"summary": "Files created"}}

        is_misfire, details = detect_aider_misfire(
            aider_result=aider_result,
            relative_editable_files=["missing.py"],
            working_directory=str(tmp_path),
        )

        assert is_misfire is True
        assert details is not None
        assert "missing.py" in details["missing_files"]

    def test_no_misfire_when_aider_reports_failure(self, tmp_path: Path) -> None:
        """Test no misfire detected when aider reports failure."""
        aider_result = {"success": False, "error": "Compilation failed"}

        is_misfire, details = detect_aider_misfire(
            aider_result=aider_result,
            relative_editable_files=["test.py"],
            working_directory=str(tmp_path),
        )

        assert is_misfire is False
        assert details is None

    def test_detect_misfire_with_minimal_content(self, tmp_path: Path) -> None:
        """Test misfire detection with minimal content below threshold."""
        # Create file with very little content
        minimal_file = tmp_path / "minimal.py"
        minimal_file.write_text("# TODO")

        aider_result = {"success": True, "changes_summary": {"summary": "File created"}}

        is_misfire, details = detect_aider_misfire(
            aider_result=aider_result,
            relative_editable_files=["minimal.py"],
            working_directory=str(tmp_path),
            min_content_size=10,  # Require at least 10 characters
        )

        assert is_misfire is True
        assert details is not None
        assert "minimal.py" in details["empty_files"]


class TestRaiseOnAiderMisfire:
    """Test the raise_on_aider_misfire function."""

    def test_raise_on_misfire_with_empty_files(self, tmp_path: Path) -> None:
        """Test exception raised when misfire detected."""
        # Create empty file
        empty_file = tmp_path / "empty.py"
        empty_file.touch()

        aider_result = {"success": True, "changes_summary": {"summary": "Files created"}}

        with pytest.raises(AiderMisfireError) as exc_info:
            raise_on_aider_misfire(
                aider_result=aider_result,
                relative_editable_files=["empty.py"],
                working_directory=str(tmp_path),
            )

        assert exc_info.value.error_code == "AIDER_MISFIRE_DETECTED"
        assert "empty" in exc_info.value.user_friendly_message.lower()
        assert "empty.py" in exc_info.value.details["empty_files"]

    def test_no_exception_with_valid_content(self, tmp_path: Path) -> None:
        """Test no exception raised with valid file content."""
        # Create file with meaningful content
        content_file = tmp_path / "valid.py"
        content_file.write_text("def calculate(x, y):\n    return x + y\n")

        aider_result = {"success": True, "changes_summary": {"summary": "Function added"}}

        # Should not raise any exception
        raise_on_aider_misfire(
            aider_result=aider_result,
            relative_editable_files=["valid.py"],
            working_directory=str(tmp_path),
        )


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""

    def test_architect_mode_missing_readonly_scenario(self, tmp_path: Path) -> None:
        """Test the exact scenario that causes empty files in architect mode."""
        # This simulates the original problem:
        # - Architect mode enabled
        # - Readonly files don't exist
        # - Should fail validation before aider is called

        with pytest.raises(AiderValidationError) as exc_info:
            validate_aider_parameters(
                relative_editable_files=["tests/molecules/tools/aider/test_api_validation.py"],
                relative_readonly_files=[
                    "src/aider_mcp_server/molecules/tools/aider/api_validation.py",
                    "tests/conftest.py",
                ],
                working_directory=str(tmp_path),
                architect_mode=True,
            )

        # Should catch the exact error that causes empty files
        assert exc_info.value.error_code == "AIDER_ARCHITECT_MISSING_READONLY_FILES"
        assert "architect mode" in exc_info.value.user_friendly_message.lower()

    def test_successful_architect_mode_scenario(self, tmp_path: Path) -> None:
        """Test successful architect mode with all files present."""
        # Create the readonly files that architect mode needs
        api_validation_dir = tmp_path / "src" / "aider_mcp_server" / "molecules" / "tools" / "aider"
        api_validation_dir.mkdir(parents=True)
        api_validation_file = api_validation_dir / "api_validation.py"
        api_validation_file.write_text("def validate_api_keys(): pass")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        conftest_file = tests_dir / "conftest.py"
        conftest_file.write_text("import pytest")

        # Should not raise any exception
        validate_aider_parameters(
            relative_editable_files=["tests/molecules/tools/aider/test_api_validation.py"],
            relative_readonly_files=[
                "src/aider_mcp_server/molecules/tools/aider/api_validation.py",
                "tests/conftest.py",
            ],
            working_directory=str(tmp_path),
            architect_mode=True,
        )

    def test_post_execution_misfire_detection(self, tmp_path: Path) -> None:
        """Test detecting misfire after aider execution completes."""
        # Simulate the scenario where aider reports success but creates empty files
        test_dir = tmp_path / "tests" / "molecules" / "tools" / "aider"
        test_dir.mkdir(parents=True)

        # Create the empty file that would be created by a misfire
        empty_test_file = test_dir / "test_api_validation.py"
        empty_test_file.touch()

        # Simulate aider response that reports success
        aider_result = {
            "success": True,
            "changes_summary": {
                "summary": "No git-tracked changes detected, but filesystem changes detected: 1 files created/empty (tests/molecules/tools/aider/test_api_validation.py)",
                "files": [{"name": "tests/molecules/tools/aider/test_api_validation.py", "operation": "created"}],
            },
            "file_status": {
                "has_changes": True,
                "status_summary": "Filesystem changes detected: 1 files created/empty (tests/molecules/tools/aider/test_api_validation.py)",
            },
        }

        # Should detect the misfire
        with pytest.raises(AiderMisfireError) as exc_info:
            raise_on_aider_misfire(
                aider_result=aider_result,
                relative_editable_files=["tests/molecules/tools/aider/test_api_validation.py"],
                working_directory=str(tmp_path),
            )

        assert exc_info.value.error_code == "AIDER_MISFIRE_DETECTED"
        # The full relative path should be in the empty_files list
        empty_files = exc_info.value.details["empty_files"]
        assert len(empty_files) == 1
        assert "tests/molecules/tools/aider/test_api_validation.py" in empty_files


class TestErrorMessages:
    """Test that error messages are clear and actionable."""

    def test_architect_mode_error_message_clarity(self, tmp_path: Path) -> None:
        """Test that architect mode error messages are clear and actionable."""
        with pytest.raises(AiderValidationError) as exc_info:
            validate_file_references(
                relative_editable_files=["new.py"],
                relative_readonly_files=["missing1.py", "missing2.py"],
                working_directory=str(tmp_path),
                architect_mode=True,
            )

        error = exc_info.value
        assert "architect mode" in error.user_friendly_message.lower()
        assert "readonly files" in error.user_friendly_message.lower()
        assert "empty output" in error.user_friendly_message.lower()
        assert error.details["architect_mode"] is True
        assert "missing1.py" in error.details["missing_readonly_files"]
        assert "missing2.py" in error.details["missing_readonly_files"]

    def test_misfire_error_message_clarity(self, tmp_path: Path) -> None:
        """Test that misfire error messages are clear and helpful."""
        empty_file = tmp_path / "empty.py"
        empty_file.touch()

        aider_result = {"success": True}

        with pytest.raises(AiderMisfireError) as exc_info:
            raise_on_aider_misfire(
                aider_result=aider_result,
                relative_editable_files=["empty.py"],
                working_directory=str(tmp_path),
            )

        error = exc_info.value
        assert "aider reported success" in error.user_friendly_message.lower()
        assert "empty" in error.user_friendly_message.lower()
        assert "readonly files" in error.user_friendly_message.lower()
        assert "architect mode" in error.user_friendly_message.lower()
        assert error.error_code == "AIDER_MISFIRE_DETECTED"
