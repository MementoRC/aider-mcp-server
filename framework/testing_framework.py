"""
Comprehensive Testing Framework for Aider MCP Server

This module provides a comprehensive testing framework that supports multiple
test suite types, coverage analysis, and reporting for systematic quality assurance.
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class TestSuiteType(Enum):
    """Enumeration of available test suite types."""

    UNIT = "unit"
    INTEGRATION = "integration"
    PERFORMANCE = "performance"
    SECURITY = "security"
    COMPATIBILITY = "compatibility"
    REGRESSION = "regression"
    END_TO_END = "end_to_end"


class CoverageThreshold(Enum):
    """Standard coverage thresholds for different quality levels."""

    MINIMUM = 95.0
    TARGET = 98.0
    STRICT = 100.0


@dataclass
class TestResult:
    """Result data for a single test suite execution."""

    suite_type: TestSuiteType
    passed: bool
    duration: float
    coverage_percentage: Optional[float] = None
    failed_tests: List[str] = field(default_factory=list)
    skipped_tests: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    performance_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoverageReport:
    """Comprehensive coverage analysis report."""

    total_coverage: float
    branch_coverage: float
    missing_lines: List[str] = field(default_factory=list)
    uncovered_files: List[str] = field(default_factory=list)
    coverage_by_module: Dict[str, float] = field(default_factory=dict)
    meets_threshold: bool = False


class TestingFramework:
    """
    Comprehensive testing framework for systematic quality assurance.

    Supports multiple test suite types, coverage analysis, performance testing,
    and comprehensive reporting for enterprise-grade quality standards.
    """

    def __init__(
        self,
        project_root: Union[str, Path] = ".",
        coverage_threshold: float = CoverageThreshold.MINIMUM.value,
        enable_performance_testing: bool = True,
        enable_security_testing: bool = True,
        test_timeout: int = 300,
    ):
        """
        Initialize the testing framework.

        Args:
            project_root: Root directory of the project
            coverage_threshold: Minimum coverage percentage required
            enable_performance_testing: Whether to run performance tests
            enable_security_testing: Whether to run security tests
            test_timeout: Timeout for test execution in seconds
        """
        self.project_root = Path(project_root).resolve()
        self.coverage_threshold = coverage_threshold
        self.enable_performance_testing = enable_performance_testing
        self.enable_security_testing = enable_security_testing
        self.test_timeout = test_timeout

        # Directory setup
        self.test_dir = self.project_root / "tests"
        self.coverage_dir = self.project_root / "htmlcov"
        self.reports_dir = self.project_root / "test_reports"

        # Ensure directories exist
        self.reports_dir.mkdir(exist_ok=True)

        # Test results storage
        self.test_results: Dict[TestSuiteType, TestResult] = {}
        self.coverage_report: Optional[CoverageReport] = None

    def _build_pytest_command(self, suite_type: TestSuiteType) -> List[str]:
        """Build pytest command for specific test suite type."""
        base_cmd = ["hatch", "run", "dev:pytest"]

        if suite_type == TestSuiteType.UNIT:
            cmd = base_cmd + [
                "tests/atoms",
                "tests/molecules",
                "-v",
                "--cov=src/aider_mcp_server",
                "--cov-report=term-missing",
                "-m",
                "unit or not (integration or performance or security)",
            ]
        elif suite_type == TestSuiteType.INTEGRATION:
            cmd = base_cmd + [
                "tests/integration",
                "tests/managers",
                "tests/organisms",
                "-v",
                "--cov=src/aider_mcp_server",
                "--cov-report=term-missing",
                "-m",
                "integration",
            ]
        elif suite_type == TestSuiteType.PERFORMANCE:
            cmd = base_cmd + [
                "tests/",
                "-k",
                "performance or benchmark",
                "--benchmark-only",
                "-v",
                "-m",
                "performance",
            ]
        elif suite_type == TestSuiteType.SECURITY:
            cmd = base_cmd + [
                "tests/",
                "-k",
                "security or auth",
                "-v",
                "-m",
                "security",
            ]
        else:
            cmd = base_cmd + ["tests/", "-v"]

        return cmd

    def _run_test_suite(self, suite_type: TestSuiteType) -> TestResult:
        """Execute a specific test suite and return results."""
        start_time = time.time()
        cmd = self._build_pytest_command(suite_type)

        try:
            result = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                timeout=self.test_timeout,
                cwd=self.project_root,
                check=False,  # Allow non-zero exit codes for test failures
            )

            duration = time.time() - start_time

            # Parse test output
            failed_tests, skipped_tests = self._parse_pytest_output(result.stdout)

            # Extract performance metrics if applicable
            performance_metrics = {}
            if suite_type == TestSuiteType.PERFORMANCE:
                performance_metrics = self._extract_performance_metrics(result.stdout)

            return TestResult(
                suite_type=suite_type,
                passed=result.returncode == 0,
                duration=duration,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
                error_message=result.stderr if result.returncode != 0 else None,
                performance_metrics=performance_metrics,
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return TestResult(
                suite_type=suite_type,
                passed=False,
                duration=duration,
                error_message=f"Test suite {suite_type.value} timed out after {self.test_timeout} seconds",
            )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                suite_type=suite_type,
                passed=False,
                duration=duration,
                error_message=f"Test execution failed: {str(e)}",
            )

    def _parse_pytest_output(self, output: str) -> Tuple[List[str], List[str]]:
        """Parse pytest output to extract failed and skipped tests."""
        failed_tests = []
        skipped_tests = []

        for line in output.split("\n"):
            if "FAILED" in line:
                failed_tests.append(line.strip())
            elif "SKIPPED" in line:
                skipped_tests.append(line.strip())

        return failed_tests, skipped_tests

    def _extract_performance_metrics(self, output: str) -> Dict[str, Any]:
        """Extract performance metrics from benchmark output."""
        metrics = {}

        # Look for benchmark test patterns
        for line in output.split("\n"):
            if "benchmark" in line.lower() or "performance" in line.lower():
                # Simple metric extraction - can be enhanced
                if "min" in line or "mean" in line or "max" in line:
                    test_name = line.split()[0] if line.split() else "unknown"
                    metrics[test_name] = line.strip()

        return metrics

    def _generate_coverage_report(self) -> CoverageReport:
        """Generate comprehensive coverage report."""
        # Try to read coverage from JSON report first
        coverage_json_path = self.project_root / "coverage.json"
        if coverage_json_path.exists():
            return self._parse_coverage_json(coverage_json_path)

        # Fallback to running coverage command
        try:
            result = subprocess.run(  # noqa: S603,S607
                ["hatch", "run", "dev:pytest", "--cov=src/aider_mcp_server", "--cov-report=term"],  # noqa: S607
                capture_output=True,
                text=True,
                cwd=self.project_root,
                check=False,  # Allow non-zero exit codes
            )
            return self._parse_coverage_terminal(result.stdout)
        except Exception:
            return CoverageReport(
                total_coverage=0.0,
                branch_coverage=0.0,
                meets_threshold=False,
            )

    def _parse_coverage_json(self, json_path: Path) -> CoverageReport:
        """Parse coverage from JSON report."""
        with open(json_path) as f:
            data = json.load(f)

        total_coverage = data.get("totals", {}).get("percent_covered", 0.0)
        branch_coverage = data.get("totals", {}).get("percent_covered_display", total_coverage)

        missing_lines = []
        uncovered_files = []
        coverage_by_module = {}

        for file_path, file_data in data.get("files", {}).items():
            file_coverage = file_data.get("summary", {}).get("percent_covered", 0.0)
            coverage_by_module[file_path] = file_coverage

            if file_coverage < self.coverage_threshold:
                uncovered_files.append(file_path)

            file_missing = file_data.get("missing_lines", [])
            for line_num in file_missing:
                missing_lines.append(f"{file_path}:{line_num}")

        return CoverageReport(
            total_coverage=total_coverage,
            branch_coverage=branch_coverage,
            missing_lines=missing_lines,
            uncovered_files=uncovered_files,
            coverage_by_module=coverage_by_module,
            meets_threshold=total_coverage >= self.coverage_threshold,
        )

    def _parse_coverage_terminal(self, output: str) -> CoverageReport:
        """Parse coverage from terminal output."""
        total_coverage = 0.0

        # Look for TOTAL line in coverage output
        for line in output.split("\n"):
            if "TOTAL" in line and "%" in line:
                parts = line.split()
                for part in parts:
                    if "%" in part:
                        try:
                            total_coverage = float(part.replace("%", ""))
                            break
                        except ValueError:
                            continue

        return CoverageReport(
            total_coverage=total_coverage,
            branch_coverage=total_coverage,
            meets_threshold=total_coverage >= self.coverage_threshold,
        )

    def run_comprehensive_test_suite(
        self,
        suites: Optional[List[TestSuiteType]] = None,
        generate_reports: bool = True,
        fail_on_coverage: bool = True,
    ) -> Dict[TestSuiteType, TestResult]:
        """
        Run comprehensive test suite with all enabled test types.

        Args:
            suites: Specific test suites to run (if None, runs all enabled)
            generate_reports: Whether to generate detailed reports
            fail_on_coverage: Whether to fail if coverage threshold not met

        Returns:
            Dictionary mapping test suite types to their results
        """
        if suites is None:
            suites = [TestSuiteType.UNIT, TestSuiteType.INTEGRATION]
            if self.enable_performance_testing:
                suites.append(TestSuiteType.PERFORMANCE)
            if self.enable_security_testing:
                suites.append(TestSuiteType.SECURITY)

        # Run each test suite
        for suite_type in suites:
            print(f"Running {suite_type.value} tests...")
            result = self._run_test_suite(suite_type)
            self.test_results[suite_type] = result

            status = "✅ PASSED" if result.passed else "❌ FAILED"
            print(f"{suite_type.value.title()} tests: {status} ({result.duration:.2f}s)")

        # Generate coverage report
        print("Generating coverage report...")
        self.coverage_report = self._generate_coverage_report()

        # Generate detailed reports if requested
        if generate_reports:
            self._generate_test_reports()

        # Validate results
        self._validate_test_results(fail_on_coverage)

        return self.test_results

    def _generate_test_reports(self):
        """Generate comprehensive test reports."""
        # Generate JSON report
        json_report_path = self.reports_dir / "test_framework_report.json"
        report_data = {
            "timestamp": time.time(),
            "coverage_threshold": self.coverage_threshold,
            "test_results": {
                suite.value: {
                    "passed": result.passed,
                    "duration": result.duration,
                    "coverage_percentage": result.coverage_percentage,
                    "failed_tests": result.failed_tests,
                    "skipped_tests": result.skipped_tests,
                    "error_message": result.error_message,
                    "performance_metrics": result.performance_metrics,
                }
                for suite, result in self.test_results.items()
            },
            "coverage_report": {
                "total_coverage": self.coverage_report.total_coverage,
                "branch_coverage": self.coverage_report.branch_coverage,
                "meets_threshold": self.coverage_report.meets_threshold,
                "missing_lines": self.coverage_report.missing_lines,
                "uncovered_files": self.coverage_report.uncovered_files,
                "coverage_by_module": self.coverage_report.coverage_by_module,
            }
            if self.coverage_report
            else None,
        }

        with open(json_report_path, "w") as f:
            json.dump(report_data, f, indent=2)

        # Generate summary report
        self._generate_summary_report()

    def _generate_summary_report(self):
        """Generate human-readable summary report."""
        summary_path = self.reports_dir / "test_summary.txt"

        # Calculate overall status
        all_passed = all(result.passed for result in self.test_results.values())
        coverage_met = self.coverage_report.meets_threshold if self.coverage_report else False
        overall_status = "✅ PASS" if all_passed and coverage_met else "❌ FAIL"

        with open(summary_path, "w") as f:
            f.write("COMPREHENSIVE TESTING FRAMEWORK REPORT\n")
            f.write("=" * 50 + "\n\n")

            f.write(f"Overall Status: {overall_status}\n")
            f.write(f"Timestamp: {time.ctime()}\n\n")

            # Test suite results
            f.write("TEST SUITE RESULTS:\n")
            f.write("-" * 20 + "\n")
            for suite_type, result in self.test_results.items():
                status = "✅ PASS" if result.passed else "❌ FAIL"
                f.write(f"{suite_type.value.title()}: {status} ({result.duration:.2f}s)\n")
                if result.failed_tests:
                    f.write(f"  Failed: {len(result.failed_tests)} tests\n")
                if result.skipped_tests:
                    f.write(f"  Skipped: {len(result.skipped_tests)} tests\n")

            # Coverage report
            if self.coverage_report:
                f.write("\nCOVERAGE ANALYSIS:\n")
                f.write("-" * 18 + "\n")
                f.write(f"Total Coverage: {self.coverage_report.total_coverage:.2f}%\n")
                f.write(f"Branch Coverage: {self.coverage_report.branch_coverage:.2f}%\n")
                f.write(f"Threshold ({self.coverage_threshold}%): ")
                f.write("✅ YES\n" if self.coverage_report.meets_threshold else "❌ NO\n")

                if self.coverage_report.uncovered_files:
                    f.write(f"\nUncovered Files ({len(self.coverage_report.uncovered_files)}):\n")
                    for file_path in self.coverage_report.uncovered_files:
                        coverage = self.coverage_report.coverage_by_module.get(file_path, 0.0)
                        f.write(f"  {file_path}: {coverage:.1f}%\n")

    def _validate_test_results(self, fail_on_coverage: bool = True):
        """Validate test results and raise exception if validation fails."""
        issues = []

        # Check test failures
        for suite_type, result in self.test_results.items():
            if not result.passed:
                issues.append(f"{suite_type.value} tests failed: {result.error_message}")

        # Check coverage threshold
        if fail_on_coverage and self.coverage_report and not self.coverage_report.meets_threshold:
            issues.append(
                f"Coverage {self.coverage_report.total_coverage:.2f}% below threshold {self.coverage_threshold}%"
            )

        if issues:
            raise RuntimeError("Testing framework validation failed:\n" + "\n".join(f"  - {issue}" for issue in issues))


def main() -> int:
    """Main entry point for the testing framework CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="Comprehensive Testing Framework")
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root directory",
    )
    parser.add_argument(
        "--coverage-threshold",
        type=float,
        default=CoverageThreshold.MINIMUM.value,
        help="Coverage threshold percentage",
    )
    parser.add_argument(
        "--suites",
        nargs="+",
        choices=[s.value for s in TestSuiteType],
        help="Test suites to run",
    )
    parser.add_argument(
        "--no-performance",
        action="store_true",
        help="Disable performance testing",
    )
    parser.add_argument(
        "--no-security",
        action="store_true",
        help="Disable security testing",
    )
    parser.add_argument(
        "--no-reports",
        action="store_true",
        help="Skip report generation",
    )
    parser.add_argument(
        "--ignore-coverage",
        action="store_true",
        help="Don't fail on coverage threshold",
    )

    args = parser.parse_args()

    try:
        # Initialize framework
        framework = TestingFramework(
            project_root=args.project_root,
            coverage_threshold=args.coverage_threshold,
            enable_performance_testing=not args.no_performance,
            enable_security_testing=not args.no_security,
        )

        # Determine suites to run
        suites = None
        if args.suites:
            suites = [TestSuiteType(suite) for suite in args.suites]

        # Run tests
        results = framework.run_comprehensive_test_suite(
            suites=suites,
            generate_reports=not args.no_reports,
            fail_on_coverage=not args.ignore_coverage,
        )

        # Print summary
        passed_count = sum(1 for result in results.values() if result.passed)
        total_count = len(results)

        print(f"\nTest Summary: {passed_count}/{total_count} suites passed")

        if framework.coverage_report:
            coverage_status = "✅" if framework.coverage_report.meets_threshold else "❌"
            print(f"Coverage: {framework.coverage_report.total_coverage:.2f}% {coverage_status}")

        return 0

    except RuntimeError as e:
        print(f"❌ Testing failed: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("❌ Testing interrupted by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
