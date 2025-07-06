"""
Tests for the comprehensive testing framework.

This module contains unit tests for the TestingFramework class and related
components to ensure the framework itself meets quality standards.
"""

import json
from pathlib import Path  # Added this import
from unittest.mock import MagicMock, patch

import pytest
from framework.testing_framework import (
    CoverageReport,
    CoverageThreshold,
    TestingFramework,
    TestResult,
    TestSuiteType,
)


class TestTestingFramework:
    """Test suite for the TestingFramework class."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project structure for testing."""
        project_root = tmp_path / "test_project"
        project_root.mkdir()

        # Create test directories
        (project_root / "tests").mkdir()
        (project_root / "src").mkdir()
        (project_root / "src" / "mypackage").mkdir()

        # Create basic source file
        (project_root / "src" / "mypackage" / "__init__.py").write_text("pass")
        (project_root / "src" / "mypackage" / "module.py").write_text("def example_function():\n    return 'hello'")

        # Create basic test file
        (project_root / "tests" / "test_module.py").write_text("def test_example():\n    assert True")

        return project_root

    def test_framework_initialization(self, temp_project):
        """Test framework initialization with default settings."""
        framework = TestingFramework(
            project_root=temp_project,
            coverage_threshold=95.0,
        )

        assert framework.project_root == temp_project
        assert framework.coverage_threshold == 95.0
        assert framework.enable_performance_testing is True
        assert framework.enable_security_testing is True
        assert framework.test_dir == temp_project / "tests"
        assert framework.coverage_dir == temp_project / "htmlcov"
        assert framework.reports_dir == temp_project / "test_reports"

    def test_framework_initialization_custom_settings(self, temp_project):
        """Test framework initialization with custom settings."""
        framework = TestingFramework(
            project_root=temp_project,
            coverage_threshold=98.0,
            enable_performance_testing=False,
            enable_security_testing=False,
        )

        assert framework.coverage_threshold == 98.0
        assert framework.enable_performance_testing is False
        assert framework.enable_security_testing is False

    def test_test_suite_type_enum(self):
        """Test TestSuiteType enum values."""
        assert TestSuiteType.UNIT.value == "unit"
        assert TestSuiteType.INTEGRATION.value == "integration"
        assert TestSuiteType.PERFORMANCE.value == "performance"
        assert TestSuiteType.SECURITY.value == "security"
        assert TestSuiteType.COMPATIBILITY.value == "compatibility"
        assert TestSuiteType.REGRESSION.value == "regression"
        assert TestSuiteType.END_TO_END.value == "end_to_end"

    def test_coverage_threshold_enum(self):
        """Test CoverageThreshold enum values."""
        assert CoverageThreshold.MINIMUM.value == 95.0
        assert CoverageThreshold.TARGET.value == 98.0
        assert CoverageThreshold.STRICT.value == 100.0

    def test_test_result_dataclass(self):
        """Test TestResult dataclass creation and defaults."""
        result = TestResult(
            suite_type=TestSuiteType.UNIT,
            passed=True,
            duration=1.5,
        )

        assert result.suite_type == TestSuiteType.UNIT
        assert result.passed is True
        assert result.duration == 1.5
        assert result.coverage_percentage is None
        assert result.failed_tests == []
        assert result.skipped_tests == []
        assert result.error_message is None
        assert result.performance_metrics == {}

    def test_coverage_report_dataclass(self):
        """Test CoverageReport dataclass creation and defaults."""
        report = CoverageReport(
            total_coverage=97.5,
            branch_coverage=95.2,
        )

        assert report.total_coverage == 97.5
        assert report.branch_coverage == 95.2
        assert report.missing_lines == []
        assert report.uncovered_files == []
        assert report.coverage_by_module == {}
        assert report.meets_threshold is False

    @patch("subprocess.run")
    def test_build_pytest_command_unit_tests(self, mock_run, temp_project):
        """Test building pytest command for unit tests."""
        framework = TestingFramework(project_root=temp_project)

        cmd = framework._build_pytest_command(TestSuiteType.UNIT)

        expected_cmd = [
            "hatch",
            "run",
            "dev:pytest",
            str(temp_project / "tests" / "atoms"),
            str(temp_project / "tests" / "molecules"),
            "-v",
            f"--cov={str(Path('src') / 'aider_mcp_server')}",
            "--cov-report=term-missing",
            "-m",
            "unit or not (integration or performance or security)",
        ]
        assert cmd == expected_cmd

    @patch("subprocess.run")
    def test_build_pytest_command_integration_tests(self, mock_run, temp_project):
        """Test building pytest command for integration tests."""
        framework = TestingFramework(project_root=temp_project)

        cmd = framework._build_pytest_command(TestSuiteType.INTEGRATION)

        expected_cmd = [
            "hatch",
            "run",
            "dev:pytest",
            str(temp_project / "tests" / "integration"),
            str(temp_project / "tests" / "managers"),
            str(temp_project / "tests" / "organisms"),
            "-v",
            f"--cov={str(Path('src') / 'aider_mcp_server')}",
            "--cov-report=term-missing",
            "-m",
            "integration",
        ]
        assert cmd == expected_cmd

    @patch("subprocess.run")
    def test_build_pytest_command_performance_tests(self, mock_run, temp_project):
        """Test building pytest command for performance tests."""
        framework = TestingFramework(project_root=temp_project)

        cmd = framework._build_pytest_command(TestSuiteType.PERFORMANCE)

        expected_cmd = [
            "hatch",
            "run",
            "dev:pytest",
            str(temp_project / "tests"),
            "-k",
            "performance or benchmark",
            "--benchmark-only",
            "-v",
            "-m",
            "performance",
        ]
        assert cmd == expected_cmd

    @patch("subprocess.run")
    def test_build_pytest_command_security_tests(self, mock_run, temp_project):
        """Test building pytest command for security tests."""
        framework = TestingFramework(project_root=temp_project)

        cmd = framework._build_pytest_command(TestSuiteType.SECURITY)

        expected_cmd = [
            "hatch",
            "run",
            "dev:pytest",
            str(temp_project / "tests"),
            "-k",
            "security or auth",
            "-v",
            "-m",
            "security",
        ]
        assert cmd == expected_cmd

    @patch("subprocess.run")
    def test_run_test_suite_success(self, mock_run, temp_project):
        """Test successful test suite execution."""
        # Mock successful subprocess run
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test_example.py::test_function PASSED\n13 passed in 1.2s"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        framework = TestingFramework(project_root=temp_project)
        result = framework._run_test_suite(TestSuiteType.UNIT)

        assert result.suite_type == TestSuiteType.UNIT
        assert result.passed is True
        assert result.duration > 0
        assert result.failed_tests == []
        assert result.error_message is None

    @patch("subprocess.run")
    def test_run_test_suite_failure(self, mock_run, temp_project):
        """Test failed test suite execution."""
        # Mock failed subprocess run
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "test_example.py::test_function FAILED\n1 failed in 0.5s"
        mock_result.stderr = "Test failed with error"
        mock_run.return_value = mock_result

        framework = TestingFramework(project_root=temp_project)
        result = framework._run_test_suite(TestSuiteType.UNIT)

        assert result.suite_type == TestSuiteType.UNIT
        assert result.passed is False
        assert result.duration > 0
        assert result.error_message == "Test failed with error"

    @patch("subprocess.run")
    def test_run_test_suite_timeout(self, mock_run, temp_project):
        """Test test suite execution timeout handling."""
        # Mock timeout exception
        from subprocess import TimeoutExpired

        mock_run.side_effect = TimeoutExpired(cmd=["pytest"], timeout=300)

        framework = TestingFramework(project_root=temp_project)
        result = framework._run_test_suite(TestSuiteType.UNIT)

        assert result.suite_type == TestSuiteType.UNIT
        assert result.passed is False
        assert "timed out" in result.error_message

    def test_parse_pytest_output(self, temp_project):
        """Test parsing pytest output for failed and skipped tests."""
        framework = TestingFramework(project_root=temp_project)

        output = """
        test_module.py::test_one PASSED
        test_module.py::test_two FAILED
        test_module.py::test_three SKIPPED
        test_module.py::test_four PASSED
        test_module.py::test_five FAILED
        """

        failed_tests, skipped_tests = framework._parse_pytest_output(output)

        assert len(failed_tests) == 2
        assert len(skipped_tests) == 1
        assert "test_module.py" in failed_tests[0]
        assert "test_module.py" in skipped_tests[0]

    def test_parse_coverage_json_success(self, temp_project):
        """Test parsing coverage from JSON report."""
        framework = TestingFramework(project_root=temp_project)

        # Create mock coverage JSON data
        coverage_data = {
            "totals": {
                "percent_covered": 97.5,
                "percent_covered_display": 95.2,
            },
            "files": {
                "src/module1.py": {
                    "summary": {"percent_covered": 98.0},
                    "missing_lines": [10, 15],
                },
                "src/module2.py": {
                    "summary": {"percent_covered": 92.0},
                    "missing_lines": [5, 8, 12],
                },
            },
        }

        # Create temporary JSON file
        json_path = temp_project / "coverage.json"
        with open(json_path, "w") as f:
            json.dump(coverage_data, f)

        report = framework._parse_coverage_json(json_path)

        assert report.total_coverage == 97.5
        assert report.branch_coverage == 95.2
        assert report.meets_threshold is True  # 97.5 > 95.0
        assert len(report.uncovered_files) == 1  # module2.py < 95%
        assert "src/module2.py" in report.uncovered_files
        assert len(report.missing_lines) == 5  # 2 + 3 missing lines

    def test_parse_coverage_terminal(self, temp_project):
        """Test parsing coverage from terminal output."""
        framework = TestingFramework(project_root=temp_project)

        terminal_output = """
        Name                 Stmts   Miss  Cover
        ----------------------------------------
        src/module1.py          50      2    96%
        src/module2.py          30      5    83%
        ----------------------------------------
        TOTAL                   80      7    88%
        """

        report = framework._parse_coverage_terminal(terminal_output)

        assert report.total_coverage == 88.0
        assert report.branch_coverage == 88.0
        assert report.meets_threshold is False  # 88 < 95

    def test_extract_performance_metrics(self, temp_project):
        """Test extracting performance metrics from benchmark output."""
        framework = TestingFramework(project_root=temp_project)

        benchmark_output = """
        test_benchmark_example min 0.001s mean 0.002s
        test_performance_check min 0.005s mean 0.008s
        """

        metrics = framework._extract_performance_metrics(benchmark_output)

        # Should detect at least one benchmark test
        assert len(metrics) >= 1
        assert "test_benchmark_example" in metrics

    @patch("subprocess.run")
    def test_generate_coverage_report_success(self, mock_run, temp_project):
        """Test successful coverage report generation."""
        # Mock successful coverage run
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "TOTAL    100    10    90%"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        framework = TestingFramework(project_root=temp_project)
        report = framework._generate_coverage_report()

        assert isinstance(report, CoverageReport)
        assert report.total_coverage >= 0.0

    @patch("subprocess.run")
    @patch.object(TestingFramework, "_generate_coverage_report")
    @patch.object(TestingFramework, "_generate_test_reports")
    @patch.object(TestingFramework, "_validate_test_results")
    def test_run_comprehensive_test_suite_success(
        self, mock_validate, mock_reports, mock_coverage, mock_run, temp_project
    ):
        """Test running comprehensive test suite successfully."""
        # Mock successful test runs
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "13 passed in 1.2s"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        # Mock coverage report
        mock_coverage.return_value = CoverageReport(
            total_coverage=97.0,
            branch_coverage=95.0,
            meets_threshold=True,
        )

        framework = TestingFramework(project_root=temp_project)
        results = framework.run_comprehensive_test_suite(
            suites=[TestSuiteType.UNIT, TestSuiteType.INTEGRATION],
            generate_reports=True,
            fail_on_coverage=True,
        )

        assert len(results) == 2
        assert TestSuiteType.UNIT in results
        assert TestSuiteType.INTEGRATION in results
        assert all(result.passed for result in results.values())

        # Verify method calls
        mock_coverage.assert_called_once()
        mock_reports.assert_called_once()
        mock_validate.assert_called_once_with(True)

    @patch("subprocess.run")
    def test_validate_test_results_success(self, mock_run, temp_project):
        """Test validation of successful test results."""
        framework = TestingFramework(project_root=temp_project)

        # Set up successful test results
        framework.test_results = {
            TestSuiteType.UNIT: TestResult(
                suite_type=TestSuiteType.UNIT,
                passed=True,
                duration=1.0,
            )
        }
        framework.coverage_report = CoverageReport(
            total_coverage=97.0,
            branch_coverage=95.0,
            meets_threshold=True,
        )

        # Should not raise exception
        framework._validate_test_results(fail_on_coverage=True)

    @patch("subprocess.run")
    def test_validate_test_results_failure(self, mock_run, temp_project):
        """Test validation of failed test results."""
        framework = TestingFramework(project_root=temp_project)

        # Set up failed test results
        framework.test_results = {
            TestSuiteType.UNIT: TestResult(
                suite_type=TestSuiteType.UNIT,
                passed=False,
                duration=1.0,
                error_message="Some tests failed",
            )
        }
        framework.coverage_report = CoverageReport(
            total_coverage=85.0,
            branch_coverage=80.0,
            meets_threshold=False,
        )

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Testing framework validation failed"):
            framework._validate_test_results(fail_on_coverage=True)

    @patch("subprocess.run")
    def test_validate_test_results_coverage_failure_ignore(self, mock_run, temp_project):
        """Test validation with coverage failure but ignore flag set."""
        framework = TestingFramework(project_root=temp_project)

        # Set up successful tests but failed coverage
        framework.test_results = {
            TestSuiteType.UNIT: TestResult(
                suite_type=TestSuiteType.UNIT,
                passed=True,
                duration=1.0,
            )
        }
        framework.coverage_report = CoverageReport(
            total_coverage=85.0,
            branch_coverage=80.0,
            meets_threshold=False,
        )

        # Should not raise exception when fail_on_coverage=False
        framework._validate_test_results(fail_on_coverage=False)

    def test_generate_test_reports(self, temp_project):
        """Test generation of test reports."""
        framework = TestingFramework(project_root=temp_project)

        # Set up test data
        framework.test_results = {
            TestSuiteType.UNIT: TestResult(
                suite_type=TestSuiteType.UNIT,
                passed=True,
                duration=1.5,
                coverage_percentage=97.0,
            )
        }
        framework.coverage_report = CoverageReport(
            total_coverage=97.0,
            branch_coverage=95.0,
            meets_threshold=True,
        )

        framework._generate_test_reports()

        # Check that report files are created
        json_report = framework.reports_dir / "test_framework_report.json"
        summary_report = framework.reports_dir / "test_summary.txt"

        assert json_report.exists()
        assert summary_report.exists()

        # Verify JSON report content
        with open(json_report) as f:
            report_data = json.load(f)

        assert "test_results" in report_data
        assert "coverage_report" in report_data
        assert report_data["coverage_threshold"] == 95.0

    def test_generate_summary_report_content(self, temp_project):
        """Test content of generated summary report."""
        framework = TestingFramework(project_root=temp_project)

        # Set up test data
        framework.test_results = {
            TestSuiteType.UNIT: TestResult(
                suite_type=TestSuiteType.UNIT,
                passed=True,
                duration=1.5,
            ),
            TestSuiteType.INTEGRATION: TestResult(
                suite_type=TestSuiteType.INTEGRATION,
                passed=False,
                duration=2.0,
                failed_tests=["test_integration_fail"],
            ),
        }
        framework.coverage_report = CoverageReport(
            total_coverage=92.0,
            branch_coverage=90.0,
            meets_threshold=False,
            uncovered_files=["src/uncovered_module.py"],
        )

        framework._generate_summary_report()

        # Check summary report content
        summary_report = framework.reports_dir / "test_summary.txt"
        content = summary_report.read_text()

        assert "COMPREHENSIVE TESTING FRAMEWORK REPORT" in content
        assert "Overall Status:" in content and "FAIL" in content
        assert "Unit" in content
        assert "Integration" in content
        assert "92.00%" in content
        assert "NO" in content  # Threshold not met


class TestTestingFrameworkCLI:
    """Test suite for the testing framework CLI interface."""

    @patch("framework.testing_framework.TestingFramework")
    def test_main_function_default_args(self, mock_framework_class):
        """Test main function with default arguments."""
        # Mock the framework instance
        mock_framework = MagicMock()
        mock_framework.run_comprehensive_test_suite.return_value = {}

        # Mock coverage_report properly
        mock_coverage_report = MagicMock()
        mock_coverage_report.total_coverage = 95.0
        mock_coverage_report.meets_threshold = True
        mock_framework.coverage_report = mock_coverage_report

        mock_framework_class.return_value = mock_framework

        # Import main function
        from framework.testing_framework import main

        # Mock sys.argv
        with patch("sys.argv", ["testing_framework.py"]):
            result = main()

        assert result == 0
        mock_framework_class.assert_called_once()
        mock_framework.run_comprehensive_test_suite.assert_called_once()

    @patch("framework.testing_framework.TestingFramework")
    def test_main_function_custom_args(self, mock_framework_class):
        """Test main function with custom arguments."""
        # Mock the framework instance
        mock_framework = MagicMock()
        mock_framework.run_comprehensive_test_suite.return_value = {}

        # Mock coverage_report properly
        mock_coverage_report = MagicMock()
        mock_coverage_report.total_coverage = 98.0
        mock_coverage_report.meets_threshold = True
        mock_framework.coverage_report = mock_coverage_report

        mock_framework_class.return_value = mock_framework

        # Import main function
        from framework.testing_framework import main

        # Mock sys.argv with custom arguments
        test_args = [
            "testing_framework.py",
            "--coverage-threshold",
            "98.0",
            "--suites",
            "unit",
            "integration",
            "--no-performance",
            "--no-security",
        ]

        with patch("sys.argv", test_args):
            result = main()

        assert result == 0
        mock_framework_class.assert_called_once_with(
            project_root=".",
            coverage_threshold=98.0,
            enable_performance_testing=False,  # --no-performance flag
            enable_security_testing=False,  # --no-security flag
        )

    @patch("framework.testing_framework.TestingFramework")
    def test_main_function_runtime_error(self, mock_framework_class):
        """Test main function handling RuntimeError."""
        # Mock the framework to raise RuntimeError
        mock_framework = MagicMock()
        mock_framework.run_comprehensive_test_suite.side_effect = RuntimeError("Test failed")
        mock_framework_class.return_value = mock_framework

        # Import main function
        from framework.testing_framework import main

        with patch("sys.argv", ["testing_framework.py"]):
            result = main()

        assert result == 1

    @patch("framework.testing_framework.TestingFramework")
    def test_main_function_keyboard_interrupt(self, mock_framework_class):
        """Test main function handling KeyboardInterrupt."""
        # Mock the framework to raise KeyboardInterrupt
        mock_framework = MagicMock()
        mock_framework.run_comprehensive_test_suite.side_effect = KeyboardInterrupt()
        mock_framework_class.return_value = mock_framework

        # Import main function
        from framework.testing_framework import main

        with patch("sys.argv", ["testing_framework.py"]):
            result = main()

        assert result == 1


@pytest.mark.integration
class TestTestingFrameworkIntegration:
    """Integration tests for the testing framework."""

    def test_framework_with_real_project_structure(self, tmp_path):
        """Test framework with a realistic project structure."""
        # Create a more realistic project structure
        project_root = tmp_path / "real_project"
        project_root.mkdir()

        # Create source structure
        src_dir = project_root / "src" / "myapp"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        (src_dir / "core.py").write_text("""
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
""")

        # Create test structure
        test_dir = project_root / "tests"
        test_dir.mkdir()
        (test_dir / "__init__.py").write_text("")
        (test_dir / "test_core.py").write_text("""
import pytest
from myapp.core import add, multiply, divide

def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0

def test_multiply():
    assert multiply(2, 3) == 6
    assert multiply(-1, 1) == -1

def test_divide():
    assert divide(6, 2) == 3
    with pytest.raises(ValueError):
        divide(1, 0)
""")

        # Initialize framework
        framework = TestingFramework(
            project_root=project_root,
            coverage_threshold=80.0,  # Lower threshold for testing
            enable_performance_testing=False,
            enable_security_testing=False,
        )

        # Verify framework setup
        assert framework.project_root == project_root
        assert framework.test_dir.exists()
        assert framework.reports_dir.exists()

    @pytest.mark.performance
    def test_framework_performance_metrics_extraction(self):
        """Test that framework can extract performance metrics."""
        # Sample benchmark output from pytest-benchmark
        benchmark_output = """
        test_benchmark_add                     min     10.0000ns (1 round)
        test_benchmark_multiply                mean    15.5000ns (10 rounds)
        test_performance_database_query        max     2.5000ms (5 rounds)
        """

        framework = TestingFramework(project_root=".")
        metrics = framework._extract_performance_metrics(benchmark_output)

        # Should extract test names and basic timing info
        assert len(metrics) >= 1
        # At least one benchmark test should be detected
        benchmark_tests = [name for name in metrics.keys() if "benchmark" in name or "performance" in name]
        assert len(benchmark_tests) >= 1


@pytest.mark.unit
class TestCoverageReportParsing:
    """Unit tests for coverage report parsing functionality."""

    def test_coverage_json_parsing_comprehensive(self, tmp_path):
        """Test comprehensive coverage JSON parsing."""
        framework = TestingFramework(project_root=tmp_path)

        # Create comprehensive coverage data
        coverage_data = {
            "totals": {
                "percent_covered": 89.45,
                "percent_covered_display": 87.20,
                "covered_lines": 804,
                "num_statements": 900,
                "missing_lines": 96,
                "excluded_lines": 0,
            },
            "files": {
                "src/myapp/core.py": {
                    "summary": {
                        "percent_covered": 95.5,
                        "covered_lines": 43,
                        "num_statements": 45,
                        "missing_lines": 2,
                    },
                    "missing_lines": [15, 32],
                },
                "src/myapp/utils.py": {
                    "summary": {
                        "percent_covered": 75.0,
                        "covered_lines": 30,
                        "num_statements": 40,
                        "missing_lines": 10,
                    },
                    "missing_lines": [5, 8, 12, 18, 22, 25, 28, 31, 35, 38],
                },
                "src/myapp/advanced.py": {
                    "summary": {
                        "percent_covered": 100.0,
                        "covered_lines": 25,
                        "num_statements": 25,
                        "missing_lines": 0,
                    },
                    "missing_lines": [],
                },
            },
        }

        # Create temporary JSON file
        json_path = tmp_path / "coverage.json"
        with open(json_path, "w") as f:
            json.dump(coverage_data, f)

        report = framework._parse_coverage_json(json_path)

        # Verify parsing results
        assert report.total_coverage == 89.45
        assert report.branch_coverage == 87.20
        assert report.meets_threshold is False  # 89.45 < 95.0

        # Verify module-specific coverage
        assert len(report.coverage_by_module) == 3
        assert report.coverage_by_module["src/myapp/core.py"] == 95.5
        assert report.coverage_by_module["src/myapp/utils.py"] == 75.0
        assert report.coverage_by_module["src/myapp/advanced.py"] == 100.0

        # Verify uncovered files (below threshold)
        assert len(report.uncovered_files) == 1
        assert "src/myapp/utils.py" in report.uncovered_files

        # Verify missing lines
        assert len(report.missing_lines) == 12  # 2 + 10 + 0
        assert "src/myapp/core.py:15" in report.missing_lines
        assert "src/myapp/utils.py:5" in report.missing_lines

    def test_terminal_coverage_parsing_variations(self, tmp_path):
        """Test parsing various terminal coverage output formats."""
        framework = TestingFramework(project_root=tmp_path)

        # Test different terminal output formats
        test_cases = [
            {
                "output": "TOTAL    100     5    95%",
                "expected_coverage": 95.0,
            },
            {
                "output": """
                Name                 Stmts   Miss  Cover
                ----------------------------------------
                myapp/core.py           45      2    96%
                myapp/utils.py          40     10    75%
                ----------------------------------------
                TOTAL                   85     12    86%
                """,
                "expected_coverage": 86.0,
            },
            {
                "output": "No coverage data found",
                "expected_coverage": 0.0,
            },
        ]

        for test_case in test_cases:
            report = framework._parse_coverage_terminal(test_case["output"])
            assert report.total_coverage == test_case["expected_coverage"]
            assert report.branch_coverage == test_case["expected_coverage"]

            # Check threshold meeting
            expected_meets_threshold = test_case["expected_coverage"] >= 95.0
            assert report.meets_threshold == expected_meets_threshold
