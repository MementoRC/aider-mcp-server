"""
Tests for FailureDetector - Failure Detection Triggers System.

Tests all failure detection capabilities including empty files, content loss,
syntax errors, lint failures, test breakage, and suspicious patterns.
"""

import os
import subprocess
from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from aider_mcp_server.atoms.utils.failure_detector import (
    FailureDetectionResult,
    FailureDetector,
    FailureSeverity,
    FailureTrigger,
    FailureType,
)
from aider_mcp_server.atoms.utils.file_integrity import FileIntegrityError, FileIntegrityFileNotFoundError
from aider_mcp_server.atoms.utils.git_diff_analyzer import DiffAnalysisResult, SuspiciousPattern
from aider_mcp_server.atoms.utils.post_operation_verifier import (
    FileVerificationMetrics,
    VerificationResult,
    VerificationResults,
)


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Set environment to bypass Claude Code git redirector
    git_env = {**os.environ, "CLAUDECODE": "0"}

    # Initialize git repo
    # Use shell=True on Windows might be needed if git is not in PATH, but generally avoid.
    # Rely on git being in PATH for CI environments.
    subprocess.run(["git", "init"], cwd=repo_path, check=True, env=git_env)  # noqa: S603, S607
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, env=git_env)  # noqa: S603, S607
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, env=git_env)  # noqa: S603, S607

    # Create initial file
    test_file = repo_path / "test_file.py"
    test_file.write_text("print('hello world')\n")
    subprocess.run(["git", "add", "test_file.py"], cwd=repo_path, check=True, env=git_env)  # noqa: S603, S607
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, env=git_env)  # noqa: S603, S607

    return str(repo_path)


@pytest.fixture
def failure_detector(temp_git_repo):
    """Create a FailureDetector instance for testing."""
    return FailureDetector(temp_git_repo)


@pytest.fixture
def sample_baseline_metrics():
    """Sample baseline metrics for testing."""
    return {
        "test_file.py": {
            "checksum_sha256": "abc123",
            "line_count": 50,
            "git_status": "clean",
        },
        "large_file.py": {
            "checksum_sha256": "def456",
            "line_count": 1000,
            "git_status": "clean",
        },
    }


@pytest.fixture
def sample_verification_results():
    """Sample verification results for testing."""
    file_results = {
        "test_file.py": FileVerificationMetrics(
            file_path="test_file.py",
            exists=True,
            content_valid=True,
            syntax_valid=True,
            line_count_valid=True,
            semantic_valid=True,
            current_line_count=45,
            baseline_line_count=50,
            current_checksum="abc124",
            baseline_checksum="abc123",
        )
    }
    return VerificationResults(
        total_files=1,
        passed_files=1,
        failed_files=0,
        warning_files=0,
        skipped_files=0,
        file_results=file_results,
        overall_result=VerificationResult.PASS,
        verification_errors=[],
    )


@dataclass
class MockFunctionalResults:
    """Mock functional validation results."""

    overall_success: bool = True
    critical_violations: list = None
    linting_results: Mock = None
    testing_results: Mock = None

    def __post_init__(self):
        if self.critical_violations is None:
            self.critical_violations = []
        if self.linting_results is None:
            self.linting_results = Mock()
            self.linting_results.success = True
            self.linting_results.output = ""
            self.linting_results.error_details = ""
            self.linting_results.exit_code = 0
        if self.testing_results is None:
            self.testing_results = Mock()
            self.testing_results.success = True
            self.testing_results.output = ""
            self.testing_results.error_details = ""
            self.testing_results.exit_code = 0


class TestFailureDetector:
    """Test FailureDetector initialization and configuration."""

    def test_init_with_valid_repo(self, temp_git_repo):
        """Test successful initialization with valid git repository."""
        detector = FailureDetector(temp_git_repo)
        assert detector.repo_path == temp_git_repo
        assert detector.content_loss_threshold == 0.9
        assert detector.line_count_reduction_threshold == 0.9
        assert detector.enable_test_detection is True
        assert detector.enable_lint_detection is True

    def test_init_with_custom_thresholds(self, temp_git_repo):
        """Test initialization with custom threshold configurations."""
        detector = FailureDetector(
            temp_git_repo,
            content_loss_threshold=0.8,
            line_count_reduction_threshold=0.7,
            enable_test_detection=False,
            enable_lint_detection=False,
        )
        assert detector.content_loss_threshold == 0.8
        assert detector.line_count_reduction_threshold == 0.7
        assert detector.enable_test_detection is False
        assert detector.enable_lint_detection is False

    def test_init_with_nonexistent_repo(self, tmp_path):
        """Test initialization with non-existent repository."""
        nonexistent_path = tmp_path / "this_path_does_not_exist"
        assert not os.path.exists(nonexistent_path)  # Ensure it doesn't exist

        # FileIntegrityManager will now raise FileIntegrityFileNotFoundError
        with pytest.raises(FileIntegrityFileNotFoundError):
            FailureDetector(str(nonexistent_path))

    def test_init_with_non_git_directory(self, tmp_path):
        """Test initialization with an existing directory that is not a git repo."""
        non_git_dir = tmp_path / "non_git_dir"
        non_git_dir.mkdir()
        assert os.path.isdir(non_git_dir)  # Ensure it exists and is a directory

        # FileIntegrityManager will now raise FileIntegrityError because it's not a git repo
        with pytest.raises(FileIntegrityError):
            FailureDetector(str(non_git_dir))


class TestEmptyFileDetection:
    """Test empty file detection functionality."""

    def test_detect_empty_files_from_verification_results(self, failure_detector):
        """Test detection of empty files from verification results."""
        # Create verification results with empty file
        file_results = {
            "empty_file.py": FileVerificationMetrics(
                file_path="empty_file.py",
                exists=True,
                content_valid=False,  # Empty file
                syntax_valid=False,
                line_count_valid=False,
                semantic_valid=False,
                current_line_count=0,
                baseline_line_count=50,
                current_checksum="",
                baseline_checksum="abc123",
            )
        }
        verification_results = VerificationResults(
            total_files=1,
            passed_files=0,
            failed_files=1,
            warning_files=0,
            skipped_files=0,
            file_results=file_results,
            overall_result=VerificationResult.FAIL,
            verification_errors=[],
        )

        triggers = failure_detector.detect_empty_files(verification_results, None)

        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.failure_type == FailureType.EMPTY_FILES
        assert trigger.severity == FailureSeverity.CRITICAL
        assert "empty_file.py" in trigger.affected_files
        assert "File became empty" in trigger.description

    def test_detect_empty_files_direct_check(self, failure_detector, temp_git_repo):
        """Test detection of empty files through direct file system check."""
        # Create an actual empty file
        empty_file_path = os.path.join(temp_git_repo, "empty_test.py")
        open(empty_file_path, "w").close()  # Create empty file

        triggers = failure_detector.detect_empty_files(None, ["empty_test.py"])

        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.failure_type == FailureType.EMPTY_FILES
        assert trigger.severity == FailureSeverity.CRITICAL
        assert "empty_test.py" in trigger.affected_files
        assert "File is empty" in trigger.description

    def test_no_empty_files_detected(self, failure_detector, sample_verification_results):
        """Test when no empty files are detected."""
        triggers = failure_detector.detect_empty_files(sample_verification_results, None)
        assert len(triggers) == 0


class TestContentLossDetection:
    """Test massive content loss detection functionality."""

    def test_detect_massive_content_loss_critical(self, failure_detector, sample_baseline_metrics):
        """Test detection of critical content loss (>95% reduction)."""
        # Create verification results with massive content loss
        file_results = {
            "test_file.py": FileVerificationMetrics(
                file_path="test_file.py",
                exists=True,
                content_valid=True,
                syntax_valid=True,
                line_count_valid=False,
                semantic_valid=True,
                current_line_count=2,  # From 50 to 2 = 96% reduction
                baseline_line_count=50,
                current_checksum="xyz789",
                baseline_checksum="abc123",
            )
        }
        verification_results = VerificationResults(
            total_files=1,
            passed_files=0,
            failed_files=1,
            warning_files=0,
            skipped_files=0,
            file_results=file_results,
            overall_result=VerificationResult.FAIL,
            verification_errors=[],
        )

        triggers = failure_detector.detect_massive_content_loss(sample_baseline_metrics, verification_results)

        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.failure_type == FailureType.CONTENT_LOSS
        assert trigger.severity == FailureSeverity.CRITICAL  # >95% reduction
        assert "test_file.py" in trigger.affected_files
        assert "96.0% reduction" in trigger.description

    def test_detect_massive_content_loss_high(self, failure_detector, sample_baseline_metrics):
        """Test detection of high content loss (90-95% reduction)."""
        # Create verification results with high content loss
        file_results = {
            "test_file.py": FileVerificationMetrics(
                file_path="test_file.py",
                exists=True,
                content_valid=True,
                syntax_valid=True,
                line_count_valid=False,
                semantic_valid=True,
                current_line_count=5,  # From 50 to 5 = 90% reduction
                baseline_line_count=50,
                current_checksum="xyz789",
                baseline_checksum="abc123",
            )
        }
        verification_results = VerificationResults(
            total_files=1,
            passed_files=0,
            failed_files=1,
            warning_files=0,
            skipped_files=0,
            file_results=file_results,
            overall_result=VerificationResult.FAIL,
            verification_errors=[],
        )

        triggers = failure_detector.detect_massive_content_loss(sample_baseline_metrics, verification_results)

        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.failure_type == FailureType.CONTENT_LOSS
        assert trigger.severity == FailureSeverity.HIGH  # 90-95% reduction
        assert "90.0% reduction" in trigger.description

    def test_no_content_loss_detected(self, failure_detector, sample_baseline_metrics, sample_verification_results):
        """Test when no significant content loss is detected."""
        triggers = failure_detector.detect_massive_content_loss(sample_baseline_metrics, sample_verification_results)
        assert len(triggers) == 0  # 10% reduction is below 90% threshold


class TestSyntaxErrorDetection:
    """Test syntax error detection functionality."""

    def test_detect_syntax_errors(self, failure_detector):
        """Test detection of syntax errors from verification results."""
        file_results = {
            "syntax_error.py": FileVerificationMetrics(
                file_path="syntax_error.py",
                exists=True,
                content_valid=True,
                syntax_valid=False,
                line_count_valid=True,
                semantic_valid=True,
                current_line_count=10,
                baseline_line_count=10,
                current_checksum="xyz789",
                baseline_checksum="def456",
                syntax_error="SyntaxError: invalid syntax at line 5",
            )
        }
        verification_results = VerificationResults(
            total_files=1,
            passed_files=0,
            failed_files=1,
            warning_files=0,
            skipped_files=0,
            file_results=file_results,
            overall_result=VerificationResult.FAIL,
            verification_errors=[],
        )

        triggers = failure_detector.detect_syntax_errors(verification_results)

        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.failure_type == FailureType.SYNTAX_ERRORS
        assert trigger.severity == FailureSeverity.CRITICAL
        assert "syntax_error.py" in trigger.affected_files
        assert "SyntaxError: invalid syntax at line 5" in trigger.description

    def test_no_syntax_errors_detected(self, failure_detector, sample_verification_results):
        """Test when no syntax errors are detected."""
        triggers = failure_detector.detect_syntax_errors(sample_verification_results)
        assert len(triggers) == 0


class TestLintFailureDetection:
    """Test critical lint failure detection functionality."""

    def test_detect_critical_lint_failures_from_violations(self, failure_detector):
        """Test detection of critical lint failures from violations list."""
        functional_results = MockFunctionalResults(
            overall_success=False,
            critical_violations=[
                "test.py:10:1: F401 'os' imported but unused",
                "test.py:15:1: E902 IOError: No such file",
                "test.py:20:1: F821 undefined name 'unknown_var'",
            ],
        )

        triggers = failure_detector.detect_critical_lint_failures(functional_results)

        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.failure_type == FailureType.LINT_FAILURES
        assert trigger.severity == FailureSeverity.HIGH  # 3 violations <= 5
        assert "3 F/E9 violations" in trigger.description

    def test_detect_critical_lint_failures_many_violations(self, failure_detector):
        """Test detection with many critical lint violations (should be CRITICAL)."""
        violations = [f"test.py:{i}:1: F401 unused import" for i in range(10)]
        functional_results = MockFunctionalResults(overall_success=False, critical_violations=violations)

        triggers = failure_detector.detect_critical_lint_failures(functional_results)

        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.failure_type == FailureType.LINT_FAILURES
        assert trigger.severity == FailureSeverity.CRITICAL  # >5 violations
        assert "10 F/E9 violations" in trigger.description

    def test_detect_lint_failures_from_results(self, failure_detector):
        """Test detection of lint failures from linting results."""
        functional_results = MockFunctionalResults()
        functional_results.linting_results.success = False
        functional_results.linting_results.output = (
            "test.py:10:1: F401 'os' imported but unused\ntest.py:15:1: E902 IOError"
        )
        functional_results.linting_results.exit_code = 1

        triggers = failure_detector.detect_critical_lint_failures(functional_results)

        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.failure_type == FailureType.LINT_FAILURES
        assert "2 critical violations" in trigger.description

    def test_no_lint_failures_detected(self, failure_detector):
        """Test when no lint failures are detected."""
        functional_results = MockFunctionalResults(overall_success=True)
        triggers = failure_detector.detect_critical_lint_failures(functional_results)
        assert len(triggers) == 0


class TestTestBreakageDetection:
    """Test test suite breakage detection functionality."""

    def test_detect_test_failures(self, failure_detector):
        """Test detection of test failures (exit code 1)."""
        functional_results = MockFunctionalResults()
        functional_results.testing_results.success = False
        functional_results.testing_results.exit_code = 1
        functional_results.testing_results.output = "2 failed, 8 passed"

        triggers = failure_detector.detect_test_breakage(functional_results)

        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.failure_type == FailureType.TEST_BREAKAGE
        assert trigger.severity == FailureSeverity.HIGH
        assert "Test suite has failing tests" in trigger.description

    def test_detect_test_collection_errors(self, failure_detector):
        """Test detection of test collection errors (exit code 2)."""
        functional_results = MockFunctionalResults()
        functional_results.testing_results.success = False
        functional_results.testing_results.exit_code = 2
        functional_results.testing_results.error_details = "Collection failed"

        triggers = failure_detector.detect_test_breakage(functional_results)

        assert len(triggers) == 1
        trigger = triggers[0]
        assert trigger.failure_type == FailureType.TEST_BREAKAGE
        assert trigger.severity == FailureSeverity.CRITICAL  # Collection errors are critical
        assert "critical errors" in trigger.description

    def test_no_test_breakage_detected(self, failure_detector):
        """Test when no test breakage is detected."""
        functional_results = MockFunctionalResults(overall_success=True)
        triggers = failure_detector.detect_test_breakage(functional_results)
        assert len(triggers) == 0


class TestSuspiciousPatternDetection:
    """Test suspicious pattern detection functionality."""

    def test_detect_suspicious_patterns(self, failure_detector):
        """Test detection of suspicious patterns from git diff analysis."""
        suspicious_patterns = [
            SuspiciousPattern(
                pattern_type="mass_deletion",
                filename="test.py",
                severity="high",
                description="Mass deletion detected",
                details={"deletions": 100, "additions": 5},
                recommended_action="Review changes carefully",
            ),
            SuspiciousPattern(
                pattern_type="complete_replacement",
                filename="config.py",
                severity="medium",
                description="File appears completely replaced",
                details={"additions": 50, "deletions": 48},
                recommended_action="Verify replacement was intended",
            ),
        ]

        diff_analysis = Mock(spec=DiffAnalysisResult)
        diff_analysis.suspicious_patterns = suspicious_patterns
        diff_analysis.has_critical_issues = True

        triggers = failure_detector.detect_suspicious_patterns(diff_analysis)

        assert len(triggers) == 2

        # Check mass deletion trigger
        mass_deletion_trigger = next(t for t in triggers if t.affected_files == ["test.py"])
        assert mass_deletion_trigger.failure_type == FailureType.SUSPICIOUS_PATTERNS
        assert mass_deletion_trigger.severity == FailureSeverity.HIGH
        assert "Mass deletion detected" in mass_deletion_trigger.description

        # Check complete replacement trigger
        replacement_trigger = next(t for t in triggers if t.affected_files == ["config.py"])
        assert replacement_trigger.failure_type == FailureType.SUSPICIOUS_PATTERNS
        assert replacement_trigger.severity == FailureSeverity.MEDIUM
        assert "File appears completely replaced" in replacement_trigger.description

    def test_no_suspicious_patterns_detected(self, failure_detector):
        """Test when no suspicious patterns are detected."""
        diff_analysis = Mock(spec=DiffAnalysisResult)
        diff_analysis.suspicious_patterns = []
        diff_analysis.has_critical_issues = False

        triggers = failure_detector.detect_suspicious_patterns(diff_analysis)
        assert len(triggers) == 0


class TestFailureDetectionIntegration:
    """Test comprehensive failure detection integration."""

    def test_detect_failures_comprehensive(self, failure_detector, sample_baseline_metrics):
        """Test comprehensive failure detection with multiple failure types."""
        # Create verification results with multiple issues
        file_results = {
            "empty_file.py": FileVerificationMetrics(
                file_path="empty_file.py",
                exists=True,
                content_valid=False,
                syntax_valid=False,
                line_count_valid=False,
                semantic_valid=False,
                current_line_count=0,
                baseline_line_count=50,
                current_checksum="",
                baseline_checksum="abc123",
            ),
            "syntax_error.py": FileVerificationMetrics(
                file_path="syntax_error.py",
                exists=True,
                content_valid=True,
                syntax_valid=False,
                line_count_valid=True,
                semantic_valid=True,
                current_line_count=10,
                baseline_line_count=10,
                current_checksum="xyz789",
                baseline_checksum="def456",
                syntax_error="SyntaxError: invalid syntax",
            ),
        }
        verification_results = VerificationResults(
            total_files=2,
            passed_files=0,
            failed_files=2,
            warning_files=0,
            skipped_files=0,
            file_results=file_results,
            overall_result=VerificationResult.FAIL,
            verification_errors=[],
        )

        # Create functional results with lint failures
        functional_results = MockFunctionalResults(
            overall_success=False, critical_violations=["test.py:1:1: F401 unused import"]
        )

        # Create diff analysis with suspicious patterns
        suspicious_patterns = [
            SuspiciousPattern(
                pattern_type="mass_deletion",
                filename="large_file.py",
                severity="critical",
                description="Critical mass deletion",
                details={},
                recommended_action="Immediate review",
            )
        ]
        diff_analysis = Mock(spec=DiffAnalysisResult)
        diff_analysis.suspicious_patterns = suspicious_patterns
        diff_analysis.has_critical_issues = True

        # Update baseline to include the new files
        baseline_metrics = {
            **sample_baseline_metrics,
            "empty_file.py": {"checksum_sha256": "abc123", "line_count": 50, "git_status": "clean"},
            "syntax_error.py": {"checksum_sha256": "def456", "line_count": 10, "git_status": "clean"},
        }

        result = failure_detector.detect_failures(
            baseline_metrics=baseline_metrics,
            verification_results=verification_results,
            functional_results=functional_results,
            diff_analysis=diff_analysis,
            modified_files=["empty_file.py", "syntax_error.py"],
        )

        assert result.has_failures is True
        assert result.requires_rollback is True
        # Check counts are at least expected, as other triggers might be added later
        assert result.critical_count >= 2  # Empty file + suspicious pattern
        assert result.high_count >= 1  # Lint failures
        assert len(result.triggers) >= 3  # Empty file, Syntax error, Lint, Suspicious pattern (4 total expected)

        # Check that we have triggers for each failure type
        failure_types = {trigger.failure_type for trigger in result.triggers}
        assert FailureType.EMPTY_FILES in failure_types
        assert FailureType.SYNTAX_ERRORS in failure_types
        assert FailureType.LINT_FAILURES in failure_types
        assert FailureType.SUSPICIOUS_PATTERNS in failure_types

    def test_detect_failures_no_issues(self, failure_detector, sample_baseline_metrics, sample_verification_results):
        """Test failure detection when no issues are found."""
        functional_results = MockFunctionalResults(overall_success=True)

        diff_analysis = Mock(spec=DiffAnalysisResult)
        diff_analysis.suspicious_patterns = []
        diff_analysis.has_critical_issues = False

        result = failure_detector.detect_failures(
            baseline_metrics=sample_baseline_metrics,
            verification_results=sample_verification_results,
            functional_results=functional_results,
            diff_analysis=diff_analysis,
        )

        assert result.has_failures is False
        assert result.requires_rollback is False
        assert result.critical_count == 0
        assert result.high_count == 0
        assert len(result.triggers) == 0
        assert "No failures detected" in result.detection_summary

    def test_detect_failures_disabled_features(self, temp_git_repo, sample_baseline_metrics):
        """Test failure detection with disabled features."""
        detector = FailureDetector(
            temp_git_repo,
            enable_test_detection=False,
            enable_lint_detection=False,
        )

        assert detector.enable_test_detection is False
        assert detector.enable_lint_detection is False

        # Mock failing functional results
        functional_results = MockFunctionalResults(overall_success=False)
        functional_results.testing_results.success = False
        functional_results.linting_results.success = False

        result = detector.detect_failures(
            baseline_metrics=sample_baseline_metrics,
            functional_results=functional_results,
        )

        # Should have no triggers since detection is disabled
        failure_types = {trigger.failure_type for trigger in result.triggers}
        assert FailureType.TEST_BREAKAGE not in failure_types
        assert FailureType.LINT_FAILURES not in failure_types


class TestFailureDetectionResults:
    """Test FailureDetectionResult and related data structures."""

    def test_failure_trigger_rollback_determination(self):
        """Test rollback determination for different severity levels."""
        critical_trigger = FailureTrigger(
            failure_type=FailureType.EMPTY_FILES,
            severity=FailureSeverity.CRITICAL,
            description="Critical failure",
            affected_files=["test.py"],
            details={},
            recommended_action="Rollback immediately",
        )

        high_trigger = FailureTrigger(
            failure_type=FailureType.LINT_FAILURES,
            severity=FailureSeverity.HIGH,
            description="High priority failure",
            affected_files=["test.py"],
            details={},
            recommended_action="Review and rollback",
        )

        medium_trigger = FailureTrigger(
            failure_type=FailureType.SUSPICIOUS_PATTERNS,
            severity=FailureSeverity.MEDIUM,
            description="Medium priority failure",
            affected_files=["test.py"],
            details={},
            recommended_action="Review changes",
        )

        assert critical_trigger.should_trigger_rollback() is True
        assert high_trigger.should_trigger_rollback() is True
        assert medium_trigger.should_trigger_rollback() is False

    def test_failure_detection_result_statistics(self):
        """Test statistics calculation in FailureDetectionResult."""
        triggers = [
            FailureTrigger(FailureType.EMPTY_FILES, FailureSeverity.CRITICAL, "Critical", [], {}, "Rollback"),
            FailureTrigger(FailureType.LINT_FAILURES, FailureSeverity.HIGH, "High", [], {}, "Fix"),
            FailureTrigger(FailureType.SUSPICIOUS_PATTERNS, FailureSeverity.MEDIUM, "Medium", [], {}, "Review"),
            FailureTrigger(FailureType.CONTENT_LOSS, FailureSeverity.LOW, "Low", [], {}, "Note"),
        ]

        result = FailureDetectionResult(
            has_failures=False,  # Will be calculated
            triggers=triggers,
            requires_rollback=False,  # Will be calculated
            critical_count=0,  # Will be calculated
            high_count=0,
            medium_count=0,
            low_count=0,
            detection_summary="",  # Will be calculated
        )

        assert result.has_failures is True
        assert result.requires_rollback is True  # Has critical and high severity
        assert result.critical_count == 1
        assert result.high_count == 1
        assert result.medium_count == 1
        assert result.low_count == 1
        assert "ROLLBACK REQUIRED" in result.detection_summary


class TestFailureSummaryGeneration:
    """Test failure summary generation functionality."""

    def test_get_failure_summary_no_failures(self, failure_detector):
        """Test summary generation when no failures are detected."""
        result = FailureDetectionResult(
            has_failures=False,
            triggers=[],
            requires_rollback=False,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            detection_summary="No failures detected",
        )

        summary = failure_detector.get_failure_summary(result)
        assert "✅ No failures detected" in summary

    def test_get_failure_summary_with_failures(self, failure_detector):
        """Test summary generation with various failure types."""
        triggers = [
            FailureTrigger(
                FailureType.EMPTY_FILES,
                FailureSeverity.CRITICAL,
                "File became empty: test.py",
                ["test.py"],
                {},
                "Rollback",
            ),
            FailureTrigger(
                FailureType.LINT_FAILURES,
                FailureSeverity.HIGH,
                "Critical lint violations",
                [],
                {},
                "Fix lint issues",
            ),
        ]

        FailureDetectionResult(
            has_failures=True,
            triggers=triggers,
            requires_rollback=True,
            critical_count=1,
            high_count=1,
            medium_count=0,
            low_count=0,
            detection_summary="Failures detected",
        )

        # Recalculate summary as it's done in __post_init__
        # This is a bit awkward, maybe the summary should be generated on demand?
        # For now, let's manually update it or rely on the __post_init__ calculation
        # The fixture creates the object, so __post_init__ runs.
        # Let's create the object directly here to ensure __post_init__ runs on the object we test.
        result_with_post_init = FailureDetectionResult(
            has_failures=True,
            triggers=triggers,
            requires_rollback=True,  # This will be recalculated
            critical_count=0,  # This will be recalculated
            high_count=0,  # This will be recalculated
            medium_count=0,  # This will be recalculated
            low_count=0,  # This will be recalculated
            detection_summary="",  # This will be recalculated
        )

        summary = failure_detector.get_failure_summary(result_with_post_init)
        assert "🚨 FAILURE DETECTION RESULTS" in summary
        assert "❌ ROLLBACK REQUIRED" in summary
        assert "Critical: 1" in summary
        assert "High: 1" in summary
        assert "EMPTY_FILES" in summary
        assert "LINT_FAILURES" in summary
        assert "File became empty: test.py" in summary
        assert "Files: test.py" in summary


class TestConfigurationAndThresholds:
    """Test configuration options and threshold behavior."""

    def test_custom_content_loss_threshold(self, temp_git_repo):
        """Test custom content loss threshold configuration."""
        detector = FailureDetector(temp_git_repo, content_loss_threshold=0.75)  # Set to 75% to detect 75% reduction

        baseline_metrics = {"test.py": {"line_count": 100}}

        file_results = {
            "test.py": FileVerificationMetrics(
                file_path="test.py",
                exists=True,
                content_valid=True,
                syntax_valid=True,
                line_count_valid=False,
                semantic_valid=True,
                current_line_count=25,  # 75% reduction (exactly at 75% threshold)
                baseline_line_count=100,
                current_checksum="new",
                baseline_checksum="old",
            )
        }
        verification_results = VerificationResults(
            total_files=1,
            passed_files=0,
            failed_files=1,
            warning_files=0,
            skipped_files=0,
            file_results=file_results,
            overall_result=VerificationResult.FAIL,
            verification_errors=[],
        )

        triggers = detector.detect_massive_content_loss(baseline_metrics, verification_results)
        assert len(triggers) == 1  # Should detect with 75% threshold

    def test_detection_feature_toggles(self, temp_git_repo):
        """Test enabling/disabling detection features."""
        detector = FailureDetector(
            temp_git_repo,
            enable_test_detection=False,
            enable_lint_detection=False,
        )

        assert detector.enable_test_detection is False
        assert detector.enable_lint_detection is False

        # Mock failing functional results
        functional_results = MockFunctionalResults(overall_success=False)
        functional_results.testing_results.success = False
        functional_results.linting_results.success = False

        result = detector.detect_failures(
            baseline_metrics={},
            functional_results=functional_results,
        )

        # Should have no triggers since detection is disabled
        failure_types = {trigger.failure_type for trigger in result.triggers}
        assert FailureType.TEST_BREAKAGE not in failure_types
        assert FailureType.LINT_FAILURES not in failure_types
