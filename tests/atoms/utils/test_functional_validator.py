"""
Comprehensive tests for the FunctionalValidator.

Covers:
- Linting validation with different levels
- Test execution validation
- Build validation
- Quality gate compliance
- Critical violation detection
- Edge cases and error handling
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from aider_mcp_server.atoms.utils.functional_validator import (
    BuildError,
    FunctionalValidationError,
    FunctionalValidationResults,
    FunctionalValidator,
    LintingError,
    QualityGateError,
    TestingError,
    ValidationCategory,
    ValidationLevel,
    ValidationResult,
)


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    return str(repo_path)


@pytest.fixture
def validator(temp_repo):
    """Create a FunctionalValidator instance for testing."""
    return FunctionalValidator(temp_repo)


@pytest.fixture
def mock_subprocess_success():
    """Mock successful subprocess.run call."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Success output"
    mock_result.stderr = ""
    return mock_result


@pytest.fixture
def mock_subprocess_failure():
    """Mock failed subprocess.run call."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "Error output"
    mock_result.stderr = "Error details"
    return mock_result


def test_validator_initialization_valid_path(temp_repo):
    """Test validator initialization with valid repository path."""
    validator = FunctionalValidator(temp_repo)
    assert validator.repo_path == temp_repo


def test_validator_initialization_invalid_path():
    """Test validator initialization with invalid path."""
    with pytest.raises(FunctionalValidationError, match="Invalid repository path"):
        FunctionalValidator("/nonexistent/path")


@patch("subprocess.run")
def test_run_hatch_command_success(mock_run, validator, mock_subprocess_success):
    """Test successful hatch command execution."""
    mock_run.return_value = mock_subprocess_success

    result = validator._run_hatch_command("dev", "pytest")

    mock_run.assert_called_once()
    assert result.returncode == 0
    assert result.stdout == "Success output"


@patch("subprocess.run")
def test_run_hatch_command_failure(mock_run, validator, mock_subprocess_failure):
    """Test failed hatch command execution."""
    mock_run.return_value = mock_subprocess_failure

    result = validator._run_hatch_command("dev", "pytest")

    mock_run.assert_called_once()
    assert result.returncode == 1
    assert result.stderr == "Error details"


@patch("subprocess.run")
def test_run_hatch_command_exception(mock_run, validator):
    """Test hatch command execution with exception."""
    mock_run.side_effect = Exception("Command failed")

    with pytest.raises(FunctionalValidationError, match="Error running hatch command"):
        validator._run_hatch_command("dev", "pytest")


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_linting_critical_level(mock_run, validator, mock_subprocess_success):
    """Test linting validation at critical level."""
    mock_run.return_value = mock_subprocess_success

    result = validator._validate_linting(ValidationLevel.CRITICAL)

    mock_run.assert_called_once_with("dev", "ruff check --select=F,E9 .")
    assert result.category == ValidationCategory.LINTING
    assert result.success is True
    assert result.output == "Success output"


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_linting_standard_level(mock_run, validator, mock_subprocess_success):
    """Test linting validation at standard level."""
    mock_run.return_value = mock_subprocess_success

    result = validator._validate_linting(ValidationLevel.STANDARD)

    mock_run.assert_called_once_with("dev", "ruff check .")
    assert result.category == ValidationCategory.LINTING
    assert result.success is True


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_linting_failure(mock_run, validator, mock_subprocess_failure):
    """Test linting validation with failures."""
    mock_run.return_value = mock_subprocess_failure

    result = validator._validate_linting(ValidationLevel.STANDARD)

    assert result.success is False
    assert result.exit_code == 1
    assert result.error_details == "Error details"


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_testing_standard_level(mock_run, validator, mock_subprocess_success):
    """Test testing validation at standard level."""
    mock_run.return_value = mock_subprocess_success

    result = validator._validate_testing(ValidationLevel.STANDARD)

    mock_run.assert_called_once_with("dev", "pytest")
    assert result.category == ValidationCategory.TESTING
    assert result.success is True


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_testing_strict_level(mock_run, validator, mock_subprocess_success):
    """Test testing validation at strict level."""
    mock_run.return_value = mock_subprocess_success

    result = validator._validate_testing(ValidationLevel.STRICT)

    mock_run.assert_called_once_with("dev", "pytest --strict-markers --strict-config")
    assert result.category == ValidationCategory.TESTING
    assert result.success is True


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_testing_failure(mock_run, validator, mock_subprocess_failure):
    """Test testing validation with failures."""
    mock_run.return_value = mock_subprocess_failure

    result = validator._validate_testing(ValidationLevel.STANDARD)

    assert result.success is False
    assert result.exit_code == 1


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_build_success(mock_run, validator, mock_subprocess_success):
    """Test build validation success."""
    mock_run.return_value = mock_subprocess_success

    result = validator._validate_build()

    mock_run.assert_called_once_with("dev", "python -m build")
    assert result.category == ValidationCategory.BUILDING
    assert result.success is True


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_build_failure(mock_run, validator, mock_subprocess_failure):
    """Test build validation failure."""
    mock_run.return_value = mock_subprocess_failure

    result = validator._validate_build()

    assert result.success is False
    assert result.exit_code == 1


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_quality_gates_critical(mock_run, validator, mock_subprocess_success):
    """Test quality gate validation at critical level."""
    mock_run.return_value = mock_subprocess_success

    result = validator._validate_quality_gates(ValidationLevel.CRITICAL)

    mock_run.assert_called_once_with("dev", "ruff check --select=F,E9 .")
    assert result.category == ValidationCategory.QUALITY
    assert result.success is True


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_quality_gates_standard(mock_run, validator, mock_subprocess_success):
    """Test quality gate validation at standard level."""
    mock_run.return_value = mock_subprocess_success

    result = validator._validate_quality_gates(ValidationLevel.STANDARD)

    mock_run.assert_called_once_with("dev", "ruff check --select=F,E,W .")
    assert result.success is True


@patch.object(FunctionalValidator, "_run_hatch_command")
def test_validate_quality_gates_strict(mock_run, validator, mock_subprocess_success):
    """Test quality gate validation at strict level."""
    mock_run.return_value = mock_subprocess_success

    result = validator._validate_quality_gates(ValidationLevel.STRICT)

    mock_run.assert_called_once_with("dev", "ruff check --select=F,E,W,C,B,S .")
    assert result.success is True


def test_extract_critical_violations_empty(validator):
    """Test critical violation extraction with no violations."""
    output = "All checks passed\nNo issues found"
    violations = validator._extract_critical_violations(output)
    assert violations == []


def test_extract_critical_violations_with_issues(validator):
    """Test critical violation extraction with F and E9 violations."""
    output = """src/file.py:10:5: F401 [*] 'unused' imported but unused
src/file.py:20:10: E999 SyntaxError: invalid syntax
src/file.py:30:1: W291 trailing whitespace"""

    violations = validator._extract_critical_violations(output)
    assert len(violations) == 2
    assert "F401" in violations[0]
    assert "E999" in violations[1]


@patch.object(FunctionalValidator, "_validate_linting")
@patch.object(FunctionalValidator, "_validate_testing")
@patch.object(FunctionalValidator, "_validate_build")
@patch.object(FunctionalValidator, "_validate_quality_gates")
def test_validate_changes_all_success(mock_quality, mock_build, mock_test, mock_lint, validator):
    """Test complete validation with all checks succeeding."""
    # Mock all validation methods to return success
    mock_lint.return_value = ValidationResult(ValidationCategory.LINTING, True, "lint ok", None, 0)
    mock_test.return_value = ValidationResult(ValidationCategory.TESTING, True, "tests ok", None, 0)
    mock_build.return_value = ValidationResult(ValidationCategory.BUILDING, True, "build ok", None, 0)
    mock_quality.return_value = ValidationResult(ValidationCategory.QUALITY, True, "quality ok", None, 0)

    results = validator.validate_changes(ValidationLevel.STANDARD)

    assert results.overall_success is True
    assert results.linting_results.success is True
    assert results.testing_results.success is True
    assert results.building_results.success is True
    assert results.quality_results.success is True
    assert results.validation_level == ValidationLevel.STANDARD
    assert len(results.critical_violations) == 0


@patch.object(FunctionalValidator, "_validate_linting")
@patch.object(FunctionalValidator, "_validate_testing")
@patch.object(FunctionalValidator, "_validate_build")
@patch.object(FunctionalValidator, "_validate_quality_gates")
def test_validate_changes_with_failures(mock_quality, mock_build, mock_test, mock_lint, validator):
    """Test complete validation with some checks failing."""
    # Mock some validation methods to return failures
    mock_lint.return_value = ValidationResult(ValidationCategory.LINTING, False, "F401 error", "lint error", 1)
    mock_test.return_value = ValidationResult(ValidationCategory.TESTING, False, "test failed", "test error", 1)
    mock_build.return_value = ValidationResult(ValidationCategory.BUILDING, True, "build ok", None, 0)
    mock_quality.return_value = ValidationResult(ValidationCategory.QUALITY, True, "quality ok", None, 0)

    results = validator.validate_changes(ValidationLevel.STANDARD)

    assert results.overall_success is False
    assert results.linting_results.success is False
    assert results.testing_results.success is False
    assert results.building_results.success is True
    assert results.quality_results.success is True


@patch.object(FunctionalValidator, "_validate_linting")
@patch.object(FunctionalValidator, "_validate_testing")
@patch.object(FunctionalValidator, "_validate_build")
@patch.object(FunctionalValidator, "_validate_quality_gates")
def test_validate_changes_skip_categories(mock_quality, mock_build, mock_test, mock_lint, validator):
    """Test validation with skipped categories."""
    # Mock only the non-skipped validation methods
    mock_lint.return_value = ValidationResult(ValidationCategory.LINTING, True, "lint ok", None, 0)
    mock_quality.return_value = ValidationResult(ValidationCategory.QUALITY, True, "quality ok", None, 0)

    skip_categories = {ValidationCategory.TESTING, ValidationCategory.BUILDING}
    results = validator.validate_changes(ValidationLevel.STANDARD, skip_categories)

    # Skipped categories should not be called
    mock_test.assert_not_called()
    mock_build.assert_not_called()

    # Results should show skipped categories as successful
    assert results.testing_results.output == "Skipped"
    assert results.building_results.output == "Skipped"
    assert results.overall_success is True


@patch.object(FunctionalValidator, "_validate_linting")
def test_validate_changes_with_critical_violations(mock_lint, validator):
    """Test validation that detects critical violations."""
    lint_output = "src/file.py:10:5: F401 [*] 'unused' imported but unused"
    mock_lint.return_value = ValidationResult(ValidationCategory.LINTING, True, lint_output, None, 0)

    # Mock other validations to skip them
    skip_categories = {ValidationCategory.TESTING, ValidationCategory.BUILDING, ValidationCategory.QUALITY}
    results = validator.validate_changes(ValidationLevel.CRITICAL, skip_categories)

    assert len(results.critical_violations) == 1
    assert "F401" in results.critical_violations[0]


@patch.object(FunctionalValidator, "_validate_linting")
def test_validate_changes_exception_handling(mock_lint, validator):
    """Test validation with exception in validation method."""
    mock_lint.side_effect = Exception("Linting system error")

    with pytest.raises(FunctionalValidationError, match="Validation system error"):
        validator.validate_changes(ValidationLevel.STANDARD)


def test_validation_result_dataclass():
    """Test ValidationResult dataclass creation and attributes."""
    result = ValidationResult(
        category=ValidationCategory.LINTING, success=True, output="Success", error_details="No errors", exit_code=0
    )

    assert result.category == ValidationCategory.LINTING
    assert result.success is True
    assert result.output == "Success"
    assert result.error_details == "No errors"
    assert result.exit_code == 0


def test_functional_validation_results_dataclass():
    """Test FunctionalValidationResults dataclass creation."""
    lint_result = ValidationResult(ValidationCategory.LINTING, True, "ok", None, 0)
    test_result = ValidationResult(ValidationCategory.TESTING, True, "ok", None, 0)
    build_result = ValidationResult(ValidationCategory.BUILDING, True, "ok", None, 0)
    quality_result = ValidationResult(ValidationCategory.QUALITY, True, "ok", None, 0)

    results = FunctionalValidationResults(
        linting_results=lint_result,
        testing_results=test_result,
        building_results=build_result,
        quality_results=quality_result,
        critical_violations=[],
        overall_success=True,
        validation_level=ValidationLevel.STANDARD,
    )

    assert results.overall_success is True
    assert results.validation_level == ValidationLevel.STANDARD
    assert len(results.critical_violations) == 0


def test_validation_level_enum():
    """Test ValidationLevel enum values."""
    assert ValidationLevel.CRITICAL.value == "critical"
    assert ValidationLevel.STANDARD.value == "standard"
    assert ValidationLevel.STRICT.value == "strict"


def test_validation_category_enum():
    """Test ValidationCategory enum values."""
    assert ValidationCategory.LINTING.value == "linting"
    assert ValidationCategory.TESTING.value == "testing"
    assert ValidationCategory.BUILDING.value == "building"
    assert ValidationCategory.QUALITY.value == "quality"


def test_exception_hierarchy():
    """Test exception class hierarchy."""
    assert issubclass(LintingError, FunctionalValidationError)
    assert issubclass(TestingError, FunctionalValidationError)
    assert issubclass(BuildError, FunctionalValidationError)
    assert issubclass(QualityGateError, FunctionalValidationError)


def test_validator_repo_path_absolute_conversion(tmp_path):
    """Test that validator converts relative paths to absolute."""
    # Create a subdirectory and change to it
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # Create validator with relative path
    old_cwd = os.getcwd()
    try:
        os.chdir(str(sub_dir))
        validator = FunctionalValidator("../repo")
        assert os.path.isabs(validator.repo_path)
        assert validator.repo_path == str(repo_dir)
    finally:
        os.chdir(old_cwd)
