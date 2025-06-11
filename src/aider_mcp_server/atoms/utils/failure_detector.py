"""
Failure Detection Triggers System for Aider Safety Operations.

Provides comprehensive failure detection that integrates with existing safety infrastructure
to identify critical conditions requiring automatic rollback. Detects empty files, content loss,
syntax errors, lint failures, test breakage, and suspicious change patterns.

Features:
- Empty file detection (0 bytes)
- Massive content loss detection (>90% reduction)
- Syntax error detection using FileIntegrityManager
- Critical lint failure detection (F, E9 violations)
- Test suite breakage detection
- Suspicious pattern detection using GitDiffAnalyzer
- Configurable thresholds and severity levels
- Integration with existing validation systems

Author: Aider MCP Server Team
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.utils.file_integrity import FileIntegrityManager
from aider_mcp_server.atoms.utils.git_diff_analyzer import DiffAnalysisResult
from aider_mcp_server.atoms.utils.post_operation_verifier import VerificationResults

logger = get_logger(__name__)


class FailureDetectionError(Exception):
    """Base exception for failure detection operations."""

    pass


class FailureSeverity(Enum):
    """Severity levels for detected failures."""

    CRITICAL = "critical"  # Immediate rollback required
    HIGH = "high"  # Strong rollback recommendation
    MEDIUM = "medium"  # Warning, review required
    LOW = "low"  # Informational


class FailureType(Enum):
    """Types of failures that can be detected."""

    EMPTY_FILES = "empty_files"
    CONTENT_LOSS = "content_loss"
    SYNTAX_ERRORS = "syntax_errors"
    LINT_FAILURES = "lint_failures"
    TEST_BREAKAGE = "test_breakage"
    SUSPICIOUS_PATTERNS = "suspicious_patterns"


@dataclass
class FailureTrigger:
    """Represents a detected failure trigger."""

    failure_type: FailureType
    severity: FailureSeverity
    description: str
    affected_files: List[str]
    details: Dict[str, Any]
    recommended_action: str

    def should_trigger_rollback(self) -> bool:
        """Determine if this failure should trigger automatic rollback."""
        return self.severity in [FailureSeverity.CRITICAL, FailureSeverity.HIGH]


@dataclass
class FailureDetectionResult:
    """Complete result of failure detection analysis."""

    has_failures: bool
    triggers: List[FailureTrigger]
    requires_rollback: bool
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    detection_summary: str

    def __post_init__(self) -> None:
        """Calculate statistics and summary after initialization."""
        self.critical_count = sum(1 for t in self.triggers if t.severity == FailureSeverity.CRITICAL)
        self.high_count = sum(1 for t in self.triggers if t.severity == FailureSeverity.HIGH)
        self.medium_count = sum(1 for t in self.triggers if t.severity == FailureSeverity.MEDIUM)
        self.low_count = sum(1 for t in self.triggers if t.severity == FailureSeverity.LOW)

        self.has_failures = len(self.triggers) > 0
        self.requires_rollback = any(t.should_trigger_rollback() for t in self.triggers)

        if not self.has_failures:
            self.detection_summary = "No failures detected"
        else:
            summary_parts = [
                f"Detected {len(self.triggers)} failure(s):",
                f"Critical: {self.critical_count}",
                f"High: {self.high_count}",
                f"Medium: {self.medium_count}",
                f"Low: {self.low_count}",
            ]
            if self.requires_rollback:
                summary_parts.append("ROLLBACK REQUIRED")
            self.detection_summary = " ".join(summary_parts)


class FailureDetector:
    """
    Detects failure conditions that require automatic rollback.

    Integrates with existing safety systems to detect various failure types:
    - File integrity failures (empty files, content loss)
    - Syntax validation failures
    - Critical lint violations
    - Test suite breakage
    - Suspicious change patterns

    Usage:
        detector = FailureDetector(repo_path)
        result = detector.detect_failures(
            baseline_metrics=baseline,
            verification_results=verifier_results,
            functional_results=validator_results,
            diff_analysis=diff_result
        )
        if result.requires_rollback:
            # Execute rollback
    """

    def __init__(
        self,
        repo_path: str,
        content_loss_threshold: float = 0.9,
        line_count_reduction_threshold: float = 0.9,
        enable_test_detection: bool = True,
        enable_lint_detection: bool = True,
    ):
        """
        Initialize the failure detector.

        Args:
            repo_path: Path to the git repository
            content_loss_threshold: Threshold for content loss detection (0-1)
            line_count_reduction_threshold: Threshold for line count reduction (0-1)
            enable_test_detection: Enable test breakage detection
            enable_lint_detection: Enable lint failure detection
        """
        self.repo_path = os.path.abspath(repo_path)
        self.content_loss_threshold = content_loss_threshold
        self.line_count_reduction_threshold = line_count_reduction_threshold
        self.enable_test_detection = enable_test_detection
        self.enable_lint_detection = enable_lint_detection

        # Initialize integrated systems
        self.integrity_manager = FileIntegrityManager(repo_path)

        logger.info(
            f"Initialized FailureDetector for {repo_path} "
            f"(content_loss_threshold={content_loss_threshold}, "
            f"line_count_threshold={line_count_reduction_threshold})"
        )

    def detect_failures(
        self,
        baseline_metrics: Dict[str, Any],
        verification_results: Optional[VerificationResults] = None,
        functional_results: Optional[Any] = None,
        diff_analysis: Optional[DiffAnalysisResult] = None,
        modified_files: Optional[List[str]] = None,
    ) -> FailureDetectionResult:
        """
        Perform comprehensive failure detection.

        Args:
            baseline_metrics: Baseline metrics from FileIntegrityManager
            verification_results: Results from PostOperationVerifier
            functional_results: Results from FunctionalValidator
            diff_analysis: Results from GitDiffAnalyzer
            modified_files: List of files that were modified

        Returns:
            Complete failure detection results
        """
        logger.info("Starting comprehensive failure detection")

        triggers: List[FailureTrigger] = []

        # Detect empty files
        empty_file_triggers = self.detect_empty_files(verification_results, modified_files)
        triggers.extend(empty_file_triggers)

        # Detect massive content loss
        content_loss_triggers = self.detect_massive_content_loss(baseline_metrics, verification_results)
        triggers.extend(content_loss_triggers)

        # Detect syntax errors
        syntax_error_triggers = self.detect_syntax_errors(verification_results)
        triggers.extend(syntax_error_triggers)

        # Detect critical lint failures
        if self.enable_lint_detection and functional_results:
            lint_failure_triggers = self.detect_critical_lint_failures(functional_results)
            triggers.extend(lint_failure_triggers)

        # Detect test breakage
        if self.enable_test_detection and functional_results:
            test_breakage_triggers = self.detect_test_breakage(functional_results)
            triggers.extend(test_breakage_triggers)

        # Detect suspicious patterns
        if diff_analysis:
            suspicious_pattern_triggers = self.detect_suspicious_patterns(diff_analysis)
            triggers.extend(suspicious_pattern_triggers)

        result = FailureDetectionResult(
            has_failures=False,  # Will be calculated in __post_init__
            triggers=triggers,
            requires_rollback=False,  # Will be calculated in __post_init__
            critical_count=0,  # Will be calculated in __post_init__
            high_count=0,
            medium_count=0,
            low_count=0,
            detection_summary="",  # Will be calculated in __post_init__
        )

        logger.info(f"Failure detection complete: {result.detection_summary}")
        if result.requires_rollback:
            logger.warning("ROLLBACK REQUIRED due to detected failures!")

        return result

    def detect_empty_files(
        self, verification_results: Optional[VerificationResults], modified_files: Optional[List[str]]
    ) -> List[FailureTrigger]:
        """
        Detect files that have become empty (0 bytes).

        Args:
            verification_results: Results from PostOperationVerifier
            modified_files: List of files that were modified

        Returns:
            List of failure triggers for empty files
        """
        triggers = []

        if verification_results:
            for file_path, metrics in verification_results.file_results.items():
                if not metrics.content_valid and metrics.exists and metrics.current_line_count == 0:
                    triggers.append(
                        FailureTrigger(
                            failure_type=FailureType.EMPTY_FILES,
                            severity=FailureSeverity.CRITICAL,
                            description=f"File became empty: {file_path}",
                            affected_files=[file_path],
                            details={
                                "current_size": 0,
                                "baseline_line_count": metrics.baseline_line_count,
                                "current_line_count": metrics.current_line_count,
                            },
                            recommended_action="Immediate rollback - file content lost",
                        )
                    )
                    logger.error(f"Empty file detected: {file_path}")

        # Additional check for files that exist but are empty
        if modified_files:
            for file_path in modified_files:
                abs_path = os.path.join(self.repo_path, file_path)
                if os.path.exists(abs_path) and os.path.getsize(abs_path) == 0:
                    # Check if this was already caught by verification results
                    already_detected = any(
                        t.failure_type == FailureType.EMPTY_FILES and file_path in t.affected_files for t in triggers
                    )
                    if not already_detected:
                        triggers.append(
                            FailureTrigger(
                                failure_type=FailureType.EMPTY_FILES,
                                severity=FailureSeverity.CRITICAL,
                                description=f"File is empty: {file_path}",
                                affected_files=[file_path],
                                details={"current_size": 0, "detection_method": "direct_file_check"},
                                recommended_action="Immediate rollback - file content lost",
                            )
                        )
                        logger.error(f"Empty file detected (direct check): {file_path}")

        return triggers

    def detect_massive_content_loss(
        self, baseline_metrics: Dict[str, Any], verification_results: Optional[VerificationResults]
    ) -> List[FailureTrigger]:
        """
        Detect files with massive content loss (>90% reduction).

        Args:
            baseline_metrics: Baseline metrics from FileIntegrityManager
            verification_results: Results from PostOperationVerifier

        Returns:
            List of failure triggers for massive content loss
        """
        triggers = []

        if verification_results:
            for file_path, metrics in verification_results.file_results.items():
                baseline = baseline_metrics.get(file_path, {})
                baseline_line_count = baseline.get("line_count", 0)

                if baseline_line_count > 0:
                    reduction_ratio = (baseline_line_count - metrics.current_line_count) / baseline_line_count

                    if reduction_ratio >= self.content_loss_threshold:
                        severity = FailureSeverity.CRITICAL if reduction_ratio >= 0.95 else FailureSeverity.HIGH

                        triggers.append(
                            FailureTrigger(
                                failure_type=FailureType.CONTENT_LOSS,
                                severity=severity,
                                description=f"Massive content loss in {file_path}: "
                                f"{baseline_line_count} -> {metrics.current_line_count} lines "
                                f"({reduction_ratio:.1%} reduction)",
                                affected_files=[file_path],
                                details={
                                    "baseline_line_count": baseline_line_count,
                                    "current_line_count": metrics.current_line_count,
                                    "reduction_ratio": reduction_ratio,
                                    "threshold": self.content_loss_threshold,
                                },
                                recommended_action="Review content loss - likely unintended",
                            )
                        )
                        logger.error(
                            f"Massive content loss detected in {file_path}: "
                            f"{reduction_ratio:.1%} reduction ({baseline_line_count} -> {metrics.current_line_count})"
                        )

        return triggers

    def detect_syntax_errors(self, verification_results: Optional[VerificationResults]) -> List[FailureTrigger]:
        """
        Detect syntax errors in modified files.

        Args:
            verification_results: Results from PostOperationVerifier

        Returns:
            List of failure triggers for syntax errors
        """
        triggers = []

        if verification_results:
            for file_path, metrics in verification_results.file_results.items():
                if not metrics.syntax_valid and metrics.syntax_error:
                    triggers.append(
                        FailureTrigger(
                            failure_type=FailureType.SYNTAX_ERRORS,
                            severity=FailureSeverity.CRITICAL,
                            description=f"Syntax error in {file_path}: {metrics.syntax_error}",
                            affected_files=[file_path],
                            details={
                                "syntax_error": metrics.syntax_error,
                                "file_exists": metrics.exists,
                                "content_valid": metrics.content_valid,
                            },
                            recommended_action="Fix syntax errors before proceeding",
                        )
                    )
                    logger.error(f"Syntax error detected in {file_path}: {metrics.syntax_error}")

        return triggers

    def detect_critical_lint_failures(self, functional_results: Any) -> List[FailureTrigger]:
        """
        Detect critical lint failures (F, E9 violations).

        Args:
            functional_results: Results from FunctionalValidator

        Returns:
            List of failure triggers for critical lint failures
        """
        triggers = []

        if hasattr(functional_results, "critical_violations") and functional_results.critical_violations:
            violations = functional_results.critical_violations
            severity = FailureSeverity.HIGH if len(violations) <= 5 else FailureSeverity.CRITICAL

            triggers.append(
                FailureTrigger(
                    failure_type=FailureType.LINT_FAILURES,
                    severity=severity,
                    description=f"Critical lint violations detected: {len(violations)} F/E9 violations",
                    affected_files=[],  # Lint violations may span multiple files
                    details={"violations": violations, "violation_count": len(violations)},
                    recommended_action="Fix critical lint violations before proceeding",
                )
            )
            logger.error(f"Critical lint failures detected: {len(violations)} violations")

        # Also check linting results success status
        if hasattr(functional_results, "linting_results") and not functional_results.linting_results.success:
            # Extract critical violations from output if available
            output = getattr(functional_results.linting_results, "output", "")
            error_details = getattr(functional_results.linting_results, "error_details", "")

            # Count F and E9 violations
            critical_violation_count = 0
            for line in (output + "\n" + (error_details or "")).splitlines():
                if any(code in line for code in ["F", "E9"]):
                    critical_violation_count += 1

            if critical_violation_count > 0:
                severity = FailureSeverity.HIGH if critical_violation_count <= 5 else FailureSeverity.CRITICAL

                triggers.append(
                    FailureTrigger(
                        failure_type=FailureType.LINT_FAILURES,
                        severity=severity,
                        description=f"Linting failed with {critical_violation_count} critical violations",
                        affected_files=[],
                        details={
                            "exit_code": getattr(functional_results.linting_results, "exit_code", -1),
                            "critical_violation_count": critical_violation_count,
                            "output": output,
                            "error_details": error_details,
                        },
                        recommended_action="Fix critical lint violations before proceeding",
                    )
                )
                logger.error(f"Linting failed with {critical_violation_count} critical violations")

        return triggers

    def detect_test_breakage(self, functional_results: Any) -> List[FailureTrigger]:
        """
        Detect test suite breakage.

        Args:
            functional_results: Results from FunctionalValidator

        Returns:
            List of failure triggers for test breakage
        """
        triggers = []

        if hasattr(functional_results, "testing_results") and not functional_results.testing_results.success:
            exit_code = getattr(functional_results.testing_results, "exit_code", -1)
            output = getattr(functional_results.testing_results, "output", "")
            error_details = getattr(functional_results.testing_results, "error_details", "")

            # Determine severity based on exit code and output
            if exit_code == 1:  # Test failures
                severity = FailureSeverity.HIGH
                description = "Test suite has failing tests"
            elif exit_code in (2, 3, 4, 5):  # Collection errors, internal errors, etc.
                severity = FailureSeverity.CRITICAL
                description = "Test suite has critical errors (collection/internal errors)"
            else:
                severity = FailureSeverity.HIGH
                description = f"Test suite failed with exit code {exit_code}"

            triggers.append(
                FailureTrigger(
                    failure_type=FailureType.TEST_BREAKAGE,
                    severity=severity,
                    description=description,
                    affected_files=[],  # Test failures may affect multiple files
                    details={
                        "exit_code": exit_code,
                        "output": output,
                        "error_details": error_details,
                    },
                    recommended_action="Fix test failures before proceeding",
                )
            )
            logger.error(f"Test breakage detected: {description} (exit code: {exit_code})")

        return triggers

    def detect_suspicious_patterns(self, diff_analysis: DiffAnalysisResult) -> List[FailureTrigger]:
        """
        Detect suspicious change patterns from git diff analysis.

        Args:
            diff_analysis: Results from GitDiffAnalyzer

        Returns:
            List of failure triggers for suspicious patterns
        """
        triggers = []

        for pattern in diff_analysis.suspicious_patterns:
            # Map GitDiffAnalyzer severity to FailureSeverity
            if pattern.severity == "critical":
                severity = FailureSeverity.CRITICAL
            elif pattern.severity == "high":
                severity = FailureSeverity.HIGH
            elif pattern.severity == "medium":
                severity = FailureSeverity.MEDIUM
            else:
                severity = FailureSeverity.LOW

            triggers.append(
                FailureTrigger(
                    failure_type=FailureType.SUSPICIOUS_PATTERNS,
                    severity=severity,
                    description=f"Suspicious pattern detected: {pattern.description}",
                    affected_files=[pattern.filename],
                    details={
                        "pattern_type": pattern.pattern_type,
                        "original_severity": pattern.severity,
                        "details": pattern.details,
                        "recommended_action": pattern.recommended_action,
                    },
                    recommended_action=pattern.recommended_action,
                )
            )
            logger.warning(f"Suspicious pattern detected: {pattern.pattern_type} in {pattern.filename}")

        # Also check for critical issues flag
        if diff_analysis.has_critical_issues:
            logger.warning("GitDiffAnalyzer flagged critical issues in diff analysis")

        return triggers

    def get_failure_summary(self, result: FailureDetectionResult) -> str:
        """
        Generate a detailed summary of detected failures.

        Args:
            result: Failure detection results

        Returns:
            Formatted summary string
        """
        if not result.has_failures:
            return "✅ No failures detected - operation appears successful"

        summary_lines = [
            "🚨 FAILURE DETECTION RESULTS:",
            f"   Total failures: {len(result.triggers)}",
            f"   Critical: {result.critical_count}",
            f"   High: {result.high_count}",
            f"   Medium: {result.medium_count}",
            f"   Low: {result.low_count}",
            "",
        ]

        if result.requires_rollback:
            summary_lines.append("❌ ROLLBACK REQUIRED")
        else:
            summary_lines.append("⚠️  Review recommended")

        summary_lines.append("")

        # Group triggers by type for cleaner output
        by_type: Dict[str, List[FailureTrigger]] = {}
        for trigger in result.triggers:
            type_name = trigger.failure_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(trigger)

        for failure_type, triggers in by_type.items():
            summary_lines.append(f"📋 {failure_type.upper()}:")
            for trigger in triggers:
                summary_lines.append(f"   • [{trigger.severity.value}] {trigger.description}")
                if trigger.affected_files:
                    summary_lines.append(f"     Files: {', '.join(trigger.affected_files)}")
            summary_lines.append("")

        return "\n".join(summary_lines)