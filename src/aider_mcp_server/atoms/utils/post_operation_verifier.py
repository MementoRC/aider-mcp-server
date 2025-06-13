"""
Post-Operation File Integrity Verification for Aider Safety Operations.

Provides comprehensive validation of file integrity after aider operations,
building on the FileIntegrityManager baseline system. Verifies content integrity,
syntax validation, line count changes, and basic semantic validation.

Features:
- Content verification (non-empty, corruption detection)
- Syntax validation using existing FileIntegrityManager methods
- Line count validation with configurable thresholds
- Semantic validation based on file type
- Detailed verification results with error reporting
- Integration with baseline metrics from FileIntegrityManager

Author: Aider MCP Server Team
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.utils.file_integrity import FileIntegrityManager, SyntaxValidationError

logger = get_logger(__name__)


class VerificationResult(Enum):
    """Results for verification operations."""

    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    WARNING = "warning"
    SKIPPED = "skipped"


class VerificationError(Exception):
    """Base exception for verification operations."""

    pass


class ContentVerificationError(VerificationError):
    """Raised when content verification fails."""

    pass


class LineCountVerificationError(VerificationError):
    """Raised when line count verification fails."""

    pass


class SemanticVerificationError(VerificationError):
    """Raised when semantic verification fails."""

    pass


@dataclass
class FileVerificationMetrics:
    """Metrics for a single file verification."""

    file_path: str
    exists: bool
    content_valid: bool
    syntax_valid: bool
    line_count_valid: bool
    semantic_valid: bool
    current_line_count: int
    baseline_line_count: int
    current_checksum: str
    baseline_checksum: str
    content_error: str | None = None
    syntax_error: str | None = None
    line_count_error: str | None = None
    semantic_error: str | None = None
    overall_result: VerificationResult = VerificationResult.PASS

    def calculate_overall_result(self) -> None:
        """Calculate overall result based on individual validations."""
        if not self.exists:
            self.overall_result = VerificationResult.FAIL
        elif not all([self.content_valid, self.syntax_valid, self.line_count_valid, self.semantic_valid]):
            self.overall_result = VerificationResult.FAIL
        else:
            self.overall_result = VerificationResult.PASS


@dataclass
class VerificationResults:
    """Complete verification results for all files."""

    total_files: int
    passed_files: int
    failed_files: int
    warning_files: int
    skipped_files: int
    file_results: Dict[str, FileVerificationMetrics]
    overall_result: VerificationResult
    verification_errors: List[str]

    def __post_init__(self) -> None:
        """Calculate overall result and statistics."""
        self.total_files = len(self.file_results)
        self.passed_files = sum(1 for r in self.file_results.values() if r.overall_result == VerificationResult.PASS)
        self.failed_files = sum(1 for r in self.file_results.values() if r.overall_result == VerificationResult.FAIL)
        self.warning_files = sum(
            1 for r in self.file_results.values() if r.overall_result == VerificationResult.WARNING
        )
        self.skipped_files = sum(
            1 for r in self.file_results.values() if r.overall_result == VerificationResult.SKIPPED
        )

        if self.failed_files > 0:
            self.overall_result = VerificationResult.FAIL
        elif self.warning_files > 0:
            self.overall_result = VerificationResult.WARNING
        else:
            self.overall_result = VerificationResult.PASS


class PostOperationVerifier:
    """
    Verifies file integrity after aider operations.

    Performs comprehensive validation including content verification,
    syntax validation, line count validation, and semantic validation.
    Compares current file state against baseline metrics.
    """

    def __init__(
        self,
        repo_path: str,
        line_count_reduction_threshold: float = 0.9,
        line_count_increase_threshold: float = 10.0,
        enable_semantic_validation: bool = True,
    ):
        """
        Initialize the post-operation verifier.

        Args:
            repo_path: Path to the git repository
            line_count_reduction_threshold: Threshold for suspicious line count reduction (0-1)
            line_count_increase_threshold: Threshold for suspicious line count increase (multiplier)
            enable_semantic_validation: Enable semantic validation checks
        """
        self.repo_path = os.path.abspath(repo_path)
        self.line_count_reduction_threshold = line_count_reduction_threshold
        self.line_count_increase_threshold = line_count_increase_threshold
        self.enable_semantic_validation = enable_semantic_validation

        # Initialize integrity manager for syntax validation and checksums
        self.integrity_manager = FileIntegrityManager(repo_path)

        logger.info(
            f"Initialized PostOperationVerifier for {repo_path} "
            f"(reduction_threshold={line_count_reduction_threshold}, "
            f"increase_threshold={line_count_increase_threshold}, "
            f"semantic_validation={enable_semantic_validation})"
        )

    def verify_file_integrity(self, modified_files: List[str], baseline_metrics: Dict[str, Any]) -> VerificationResults:
        """
        Verify integrity of modified files against baseline metrics.

        Args:
            modified_files: List of file paths that were modified
            baseline_metrics: Baseline metrics from FileIntegrityManager

        Returns:
            Complete verification results for all files

        Raises:
            VerificationError: If verification process fails
        """
        logger.info(f"Starting verification of {len(modified_files)} modified files")

        file_results: Dict[str, FileVerificationMetrics] = {}
        verification_errors: List[str] = []

        for file_path in modified_files:
            try:
                result = self._verify_single_file(file_path, baseline_metrics)
                file_results[file_path] = result

                if result.overall_result == VerificationResult.FAIL:
                    logger.error(f"Verification failed for {file_path}: {result}")
                elif result.overall_result == VerificationResult.WARNING:
                    logger.warning(f"Verification warning for {file_path}: {result}")
                else:
                    logger.info(f"Verification passed for {file_path}")

            except Exception as e:
                error_msg = f"Error verifying {file_path}: {e}"
                logger.error(error_msg)
                verification_errors.append(error_msg)

                # Create failed result for this file
                failed_metrics = FileVerificationMetrics(
                    file_path=file_path,
                    exists=False,
                    content_valid=False,
                    syntax_valid=False,
                    line_count_valid=False,
                    semantic_valid=False,
                    current_line_count=0,
                    baseline_line_count=baseline_metrics.get(file_path, {}).get("line_count", 0),
                    current_checksum="",
                    baseline_checksum=baseline_metrics.get(file_path, {}).get("checksum_sha256", ""),
                    content_error=str(e),
                )
                failed_metrics.calculate_overall_result()
                file_results[file_path] = failed_metrics

        results = VerificationResults(
            total_files=0,  # Will be calculated in __post_init__
            passed_files=0,
            failed_files=0,
            warning_files=0,
            skipped_files=0,
            file_results=file_results,
            overall_result=VerificationResult.PASS,  # Will be calculated in __post_init__
            verification_errors=verification_errors,
        )

        logger.info(
            f"Verification complete: {results.passed_files} passed, "
            f"{results.failed_files} failed, {results.warning_files} warnings, "
            f"overall result: {results.overall_result.value}"
        )

        return results

    def _verify_single_file(self, file_path: str, baseline_metrics: Dict[str, Any]) -> FileVerificationMetrics:
        """
        Verify a single file against its baseline metrics.

        Args:
            file_path: Path to the file to verify
            baseline_metrics: Baseline metrics for this file

        Returns:
            Verification metrics for the file
        """
        abs_path = os.path.join(self.repo_path, file_path)
        baseline = baseline_metrics.get(file_path, {})

        logger.debug(f"Verifying file: {file_path}")

        # Initialize metrics
        metrics = FileVerificationMetrics(
            file_path=file_path,
            exists=os.path.exists(abs_path),
            content_valid=False,
            syntax_valid=False,
            line_count_valid=False,
            semantic_valid=False,
            current_line_count=0,
            baseline_line_count=baseline.get("line_count", 0),
            current_checksum="",
            baseline_checksum=baseline.get("checksum_sha256", ""),
        )

        # Check if file exists
        if not metrics.exists:
            metrics.content_error = "File does not exist after operation"
            logger.error(f"File does not exist: {abs_path}")
            metrics.calculate_overall_result()
            return metrics

        # Read file content
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            metrics.content_error = f"Cannot read file: {e}"
            logger.error(f"Cannot read file {abs_path}: {e}")
            metrics.calculate_overall_result()
            return metrics

        # Content verification
        metrics.content_valid = self._verify_content(content, file_path)
        if not metrics.content_valid:
            metrics.content_error = "File is empty or corrupted"

        # Calculate current metrics
        metrics.current_checksum = self.integrity_manager.calculate_checksum(content)
        metrics.current_line_count = self.integrity_manager.count_lines(content)

        # Syntax validation
        try:
            self.integrity_manager.validate_syntax(abs_path, content)
            metrics.syntax_valid = True
            logger.debug(f"Syntax validation passed for {file_path}")
        except SyntaxValidationError as e:
            metrics.syntax_valid = False
            metrics.syntax_error = str(e)
            logger.error(f"Syntax validation failed for {file_path}: {e}")

        # Line count validation
        metrics.line_count_valid = self._verify_line_count(
            metrics.current_line_count, metrics.baseline_line_count, file_path
        )
        if not metrics.line_count_valid:
            reduction_pct = (
                (metrics.baseline_line_count - metrics.current_line_count) / max(metrics.baseline_line_count, 1)
            ) * 100
            increase_mult = metrics.current_line_count / max(metrics.baseline_line_count, 1)
            metrics.line_count_error = (
                f"Suspicious line count change: {metrics.baseline_line_count} -> "
                f"{metrics.current_line_count} ({reduction_pct:.1f}% change, "
                f"{increase_mult:.1f}x multiplier)"
            )

        # Semantic validation
        if self.enable_semantic_validation:
            try:
                metrics.semantic_valid = self._verify_semantics(content, file_path)
                if not metrics.semantic_valid:
                    metrics.semantic_error = "Basic semantic validation failed"
            except SemanticVerificationError as e:
                metrics.semantic_valid = False
                metrics.semantic_error = str(e)
                logger.error(f"Semantic validation failed for {file_path}: {e}")
        else:
            metrics.semantic_valid = True
            logger.debug(f"Semantic validation skipped for {file_path}")

        # Calculate overall result after all validations
        metrics.calculate_overall_result()

        return metrics

    def _verify_content(self, content: str, file_path: str) -> bool:
        """
        Verify file content is not empty or corrupted.

        Args:
            content: File content to verify
            file_path: Path to the file (for logging)

        Returns:
            True if content is valid, False otherwise
        """
        if len(content) == 0:
            logger.warning(f"File is empty: {file_path}")
            return False

        # Check for binary/corrupted content (basic heuristic)
        try:
            content.encode("utf-8")
        except UnicodeEncodeError:
            logger.error(f"File contains invalid UTF-8 content: {file_path}")
            return False

        logger.debug(f"Content verification passed for {file_path}")
        return True

    def _verify_line_count(self, current_count: int, baseline_count: int, file_path: str) -> bool:
        """
        Verify line count changes are reasonable.

        Args:
            current_count: Current line count
            baseline_count: Baseline line count
            file_path: Path to the file (for logging)

        Returns:
            True if line count change is reasonable, False otherwise
        """
        if baseline_count == 0:
            # New file should have content
            is_valid = current_count > 0
            if not is_valid:
                logger.warning(f"New file has no content: {file_path}")
            return is_valid

        # Check for excessive reduction
        reduction_percentage = (baseline_count - current_count) / baseline_count
        if reduction_percentage > self.line_count_reduction_threshold:
            logger.warning(
                f"Suspicious line count reduction in {file_path}: "
                f"{baseline_count} -> {current_count} ({reduction_percentage:.1%} reduction)"
            )
            return False

        # Check for excessive increase
        increase_multiplier = current_count / baseline_count
        if increase_multiplier > self.line_count_increase_threshold:
            logger.warning(
                f"Suspicious line count increase in {file_path}: "
                f"{baseline_count} -> {current_count} ({increase_multiplier:.1f}x increase)"
            )
            return False

        logger.debug(f"Line count validation passed for {file_path}: {baseline_count} -> {current_count}")
        return True

    def _verify_semantics(self, content: str, file_path: str) -> bool:
        """
        Perform basic semantic validation based on file type.

        Args:
            content: File content to validate
            file_path: Path to the file (used to determine language)

        Returns:
            True if semantic validation passes, False otherwise

        Raises:
            SemanticVerificationError: If semantic validation fails critically
        """
        ext = os.path.splitext(file_path)[1].lower()
        logger.debug(f"Performing semantic validation for {file_path} (ext: {ext})")

        if ext == ".py":
            return self._verify_python_semantics(content, file_path)
        elif ext in (".js", ".ts"):
            return self._verify_js_semantics(content, file_path)
        elif ext == ".json":
            return self._verify_json_semantics(content, file_path)
        elif ext in (".yml", ".yaml"):
            return self._verify_yaml_semantics(content, file_path)
        else:
            logger.debug(f"No semantic validation for file type: {ext}")
            return True  # Default to valid for unsupported types

    def _verify_python_semantics(self, content: str, file_path: str) -> bool:
        """Verify Python file has reasonable semantic structure."""
        lines = content.strip().split("\n")

        # Check for basic Python elements
        has_import = any(line.strip().startswith(("import ", "from ")) for line in lines)
        has_function = any(line.strip().startswith("def ") for line in lines)
        has_class = any(line.strip().startswith("class ") for line in lines)
        has_content = any(line.strip() and not line.strip().startswith("#") for line in lines)

        if not has_content:
            logger.warning(f"Python file has no meaningful content: {file_path}")
            return False

        # Python files should typically have imports, functions, or classes
        if len(lines) > 5 and not (has_import or has_function or has_class):
            logger.warning(f"Python file lacks typical structure (imports/functions/classes): {file_path}")
            return False

        logger.debug(f"Python semantic validation passed for {file_path}")
        return True

    def _verify_js_semantics(self, content: str, file_path: str) -> bool:
        """Verify JavaScript/TypeScript file has reasonable semantic structure."""
        lines = content.strip().split("\n")

        # Check for basic JS/TS elements
        has_content = any(line.strip() and not line.strip().startswith("//") for line in lines)

        if not has_content:
            logger.warning(f"JS/TS file has no meaningful content: {file_path}")
            return False

        logger.debug(f"JS/TS semantic validation passed for {file_path}")
        return True

    def _verify_json_semantics(self, content: str, file_path: str) -> bool:
        """Verify JSON file is valid."""
        try:
            import json

            json.loads(content)
            logger.debug(f"JSON semantic validation passed for {file_path}")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {file_path}: {e}")
            raise SemanticVerificationError(f"Invalid JSON: {e}") from e

    def _verify_yaml_semantics(self, content: str, file_path: str) -> bool:
        """Verify YAML file is valid."""
        try:
            import yaml  # type: ignore[import-untyped]

            yaml.safe_load(content)
            logger.debug(f"YAML semantic validation passed for {file_path}")
            return True
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in {file_path}: {e}")
            raise SemanticVerificationError(f"Invalid YAML: {e}") from e
