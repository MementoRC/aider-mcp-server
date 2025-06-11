"""
FunctionalValidator for Aider Safety Operations.

Provides a robust system for validating functional correctness of code changes
through linting, testing, building, and quality gate validation. Integrates with
hatch environments and common development tools.

Features:
- Linting validation (ruff, other configured linters)
- Test execution validation
- Build process validation
- Quality gate compliance checking
- Configurable validation levels and thresholds
- Integration with hatch environments

Author: Aider MCP Server Team
"""

import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set

from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)


class FunctionalValidationError(Exception):
    """Base exception for functional validation operations."""

    pass


class LintingError(FunctionalValidationError):
    """Raised when linting validation fails."""

    pass


class TestingError(FunctionalValidationError):
    """Raised when test execution fails."""

    pass


class BuildError(FunctionalValidationError):
    """Raised when build validation fails."""

    pass


class QualityGateError(FunctionalValidationError):
    """Raised when quality gate validation fails."""

    pass


class ValidationLevel(Enum):
    """Validation levels for functional checks."""

    CRITICAL = "critical"  # Only critical checks (F, E9)
    STANDARD = "standard"  # Standard validation suite
    STRICT = "strict"     # Full validation including style


class ValidationCategory(Enum):
    """Categories of functional validation."""

    LINTING = "linting"
    TESTING = "testing"
    BUILDING = "building"
    QUALITY = "quality"


@dataclass
class ValidationResult:
    """Results from a single validation operation."""

    category: ValidationCategory
    success: bool
    output: str
    error_details: Optional[str] = None
    exit_code: int = 0


@dataclass
class FunctionalValidationResults:
    """Complete results from all validation operations."""

    linting_results: ValidationResult
    testing_results: ValidationResult
    building_results: ValidationResult
    quality_results: ValidationResult
    critical_violations: List[str]
    overall_success: bool
    validation_level: ValidationLevel


class FunctionalValidator:
    """
    Validates functional correctness of code changes.

    Executes and validates:
    - Linting checks (ruff, configured linters)
    - Test suite execution
    - Build process validation
    - Quality gate compliance

    Usage:
        validator = FunctionalValidator(repo_path)
        results = validator.validate_changes(
            validation_level=ValidationLevel.STANDARD
        )
    """

    def __init__(self, repo_path: str):
        """
        Initialize the validator with repository path.

        Args:
            repo_path: Path to the root of the repository
        """
        self.repo_path = os.path.abspath(repo_path)
        if not os.path.isdir(self.repo_path):
            raise FunctionalValidationError(f"Invalid repository path: {self.repo_path}")

    def _run_hatch_command(self, env: str, command: str, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
        """
        Run a command in a hatch environment.

        Args:
            env: Hatch environment name
            command: Command to run
            capture_output: Whether to capture command output

        Returns:
            CompletedProcess instance with command results

        Raises:
            subprocess.CalledProcessError: If command fails
        """
        cmd = ["hatch", "-e", env, "run"] + command.split()
        try:
            logger.debug(f"Running hatch command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                check=False,  # Don't raise on non-zero exit
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                encoding="utf-8",
            )
            if result.returncode != 0:
                logger.warning(f"Command failed with exit code {result.returncode}: {' '.join(cmd)}")
            return result
        except Exception as e:
            logger.error(f"Error running hatch command: {' '.join(cmd)}\n{e}")
            raise FunctionalValidationError(f"Error running hatch command: {' '.join(cmd)}") from e

    def _validate_linting(self, level: ValidationLevel) -> ValidationResult:
        """
        Run linting validation at specified level.

        Args:
            level: Validation level to apply

        Returns:
            ValidationResult for linting checks
        """
        if level == ValidationLevel.CRITICAL:
            cmd = "ruff check --select=F,E9 ."
        else:
            cmd = "ruff check ."

        result = self._run_hatch_command("dev", cmd)
        success = result.returncode == 0
        error_details = result.stderr if result.stderr else None

        return ValidationResult(
            category=ValidationCategory.LINTING,
            success=success,
            output=result.stdout,
            error_details=error_details,
            exit_code=result.returncode,
        )

    def _validate_testing(self, level: ValidationLevel) -> ValidationResult:
        """
        Run test suite validation.

        Args:
            level: Validation level to apply

        Returns:
            ValidationResult for test execution
        """
        cmd = "pytest"
        if level == ValidationLevel.STRICT:
            cmd += " --strict-markers --strict-config"

        result = self._run_hatch_command("dev", cmd)
        success = result.returncode == 0
        error_details = result.stderr if result.stderr else None

        return ValidationResult(
            category=ValidationCategory.TESTING,
            success=success,
            output=result.stdout,
            error_details=error_details,
            exit_code=result.returncode,
        )

    def _validate_build(self) -> ValidationResult:
        """
        Validate build process.

        Returns:
            ValidationResult for build validation
        """
        cmd = "python -m build"
        result = self._run_hatch_command("dev", cmd)
        success = result.returncode == 0
        error_details = result.stderr if result.stderr else None

        return ValidationResult(
            category=ValidationCategory.BUILDING,
            success=success,
            output=result.stdout,
            error_details=error_details,
            exit_code=result.returncode,
        )

    def _validate_quality_gates(self, level: ValidationLevel) -> ValidationResult:
        """
        Check quality gate compliance.

        Args:
            level: Validation level to apply

        Returns:
            ValidationResult for quality gate checks
        """
        if level == ValidationLevel.CRITICAL:
            cmd = "ruff check --select=F,E9 ."
        elif level == ValidationLevel.STRICT:
            cmd = "ruff check --select=F,E,W,C,B,S ."
        else:
            cmd = "ruff check --select=F,E,W ."

        result = self._run_hatch_command("dev", cmd)
        success = result.returncode == 0
        error_details = result.stderr if result.stderr else None

        return ValidationResult(
            category=ValidationCategory.QUALITY,
            success=success,
            output=result.stdout,
            error_details=error_details,
            exit_code=result.returncode,
        )

    def _extract_critical_violations(self, linting_output: str) -> List[str]:
        """
        Extract critical violations from linting output.

        Args:
            linting_output: Output from linting command

        Returns:
            List of critical violation messages
        """
        violations: List[str] = []
        for line in linting_output.splitlines():
            if any(code in line for code in ["F", "E9"]):
                violations.append(line.strip())
        return violations

    def validate_changes(
        self,
        validation_level: ValidationLevel = ValidationLevel.STANDARD,
        skip_categories: Optional[Set[ValidationCategory]] = None,
    ) -> FunctionalValidationResults:
        """
        Validate code changes at specified level.

        Args:
            validation_level: Level of validation to perform
            skip_categories: Categories to skip validation for

        Returns:
            Complete validation results

        Raises:
            FunctionalValidationError: On validation system errors
        """
        skip_categories = skip_categories or set()
        logger.info(f"Starting functional validation at {validation_level.value} level")

        try:
            # Run validations (skip if category is in skip_categories)
            linting_results = (
                self._validate_linting(validation_level)
                if ValidationCategory.LINTING not in skip_categories
                else ValidationResult(ValidationCategory.LINTING, True, "Skipped", None, 0)
            )

            testing_results = (
                self._validate_testing(validation_level)
                if ValidationCategory.TESTING not in skip_categories
                else ValidationResult(ValidationCategory.TESTING, True, "Skipped", None, 0)
            )

            building_results = (
                self._validate_build()
                if ValidationCategory.BUILDING not in skip_categories
                else ValidationResult(ValidationCategory.BUILDING, True, "Skipped", None, 0)
            )

            quality_results = (
                self._validate_quality_gates(validation_level)
                if ValidationCategory.QUALITY not in skip_categories
                else ValidationResult(ValidationCategory.QUALITY, True, "Skipped", None, 0)
            )

            # Extract critical violations
            critical_violations = self._extract_critical_violations(linting_results.output)

            # Calculate overall success
            overall_success = all(
                [
                    linting_results.success,
                    testing_results.success,
                    building_results.success,
                    quality_results.success,
                ]
            )

            results = FunctionalValidationResults(
                linting_results=linting_results,
                testing_results=testing_results,
                building_results=building_results,
                quality_results=quality_results,
                critical_violations=critical_violations,
                overall_success=overall_success,
                validation_level=validation_level,
            )

            logger.info(
                f"Validation completed: success={results.overall_success}, "
                f"critical_violations={len(results.critical_violations)}"
            )
            return results

        except Exception as e:
            logger.error(f"Validation system error: {e}")
            raise FunctionalValidationError(f"Validation system error: {e}") from e
