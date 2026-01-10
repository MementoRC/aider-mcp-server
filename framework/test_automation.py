"""
Advanced Test Automation Orchestrator for Aider MCP Server

This module provides enhanced automation capabilities for the comprehensive testing framework,
including intelligent test discovery, parallel execution coordination, automated data management,
and seamless integration with end-to-end testing infrastructure.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from framework.e2e_test_runner import E2ETestRunner

# Import the comprehensive testing framework components
from framework.test_data_manager import TestDataManager
from framework.testing_framework import TestingFramework, TestResult, TestSuiteType

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TestAutomationOrchestrator:
    """
    Advanced test automation orchestrator that enhances the comprehensive testing framework.

    Provides intelligent test discovery, parallel execution coordination, automated data management,
    end-to-end test orchestration, and comprehensive reporting with automated quality analysis.
    """

    def __init__(
        self,
        project_root: str = ".",
        coverage_threshold: float = 95.0,
        enable_parallel_execution: bool = True,
        max_parallel_workers: int = 4,
    ):
        """
        Initialize the advanced test automation orchestrator.

        Args:
            project_root: Root directory of the project
            coverage_threshold: Minimum coverage percentage required
            enable_parallel_execution: Whether to enable parallel test execution
            max_parallel_workers: Maximum number of parallel workers
        """
        self.project_root = Path(project_root).resolve()
        self.enable_parallel_execution = enable_parallel_execution
        self.max_parallel_workers = max_parallel_workers

        # Initialize core testing framework
        self.testing_framework = TestingFramework(
            project_root=self.project_root,
            coverage_threshold=coverage_threshold,
            enable_performance_testing=True,
            enable_security_testing=True,
        )

        # Initialize automation components
        self.data_manager = TestDataManager(base_dir=str(self.project_root / "test_data"))
        self.e2e_runner = E2ETestRunner()

        # Automation state tracking
        self.execution_plan: List[TestSuiteType] = []
        self.automation_results: Dict[str, Any] = {}
        self.execution_metrics: Dict[str, float] = {}

        logger.info(f"Advanced Test Automation Orchestrator initialized for project: {self.project_root}")

    def create_execution_plan(
        self,
        include_suites: Optional[List[TestSuiteType]] = None,
        exclude_suites: Optional[List[TestSuiteType]] = None,
        optimize_for_speed: bool = False,
    ) -> List[TestSuiteType]:
        """
        Create an intelligent test execution plan based on suite dependencies and optimization criteria.

        Args:
            include_suites: Specific suites to include (if None, includes all available)
            exclude_suites: Specific suites to exclude
            optimize_for_speed: Whether to optimize execution order for speed

        Returns:
            Ordered list of test suites to execute
        """
        logger.info("Creating intelligent test execution plan...")

        # Base suite order optimized for dependency management and feedback speed
        if optimize_for_speed:
            # Fast feedback first: unit tests, then integration, then more expensive tests
            base_order = [
                TestSuiteType.UNIT,
                TestSuiteType.INTEGRATION,
                TestSuiteType.COMPATIBILITY,
                TestSuiteType.SECURITY,
                TestSuiteType.PERFORMANCE,
                TestSuiteType.END_TO_END,
                TestSuiteType.REGRESSION,
            ]
        else:
            # Comprehensive order: logical test progression
            base_order = [
                TestSuiteType.UNIT,
                TestSuiteType.INTEGRATION,
                TestSuiteType.SECURITY,
                TestSuiteType.PERFORMANCE,
                TestSuiteType.COMPATIBILITY,
                TestSuiteType.END_TO_END,
                TestSuiteType.REGRESSION,
            ]

        # Apply include/exclude filters
        execution_plan = []
        for suite in base_order:
            if include_suites and suite not in include_suites:
                continue
            if exclude_suites and suite in exclude_suites:
                continue
            execution_plan.append(suite)

        # Store the plan
        self.execution_plan = execution_plan

        logger.info(f"Execution plan created with {len(execution_plan)} suites: {[s.value for s in execution_plan]}")
        return execution_plan

    def setup_test_environment(self) -> bool:
        """
        Set up comprehensive test environment including data generation and service preparation.

        Returns:
            True if setup successful, False otherwise
        """
        logger.info("Setting up comprehensive test environment...")

        try:
            # Set up test data
            logger.info("Generating automated test data...")
            with self.data_manager.data_context("unit_test_data", count=10, test_type="unit"):
                with self.data_manager.data_context("integration_test_data", count=5, test_type="integration"):
                    # Prepare E2E environment if END_TO_END is in the plan
                    if TestSuiteType.END_TO_END in self.execution_plan:
                        logger.info("Setting up E2E test environment...")
                        if not self.e2e_runner.setup_environment():
                            logger.error("Failed to setup E2E environment")
                            return False

                    logger.info("Test environment setup complete")
                    return True

        except Exception as e:
            logger.error(f"Failed to setup test environment: {e}", exc_info=True)
            return False

    def execute_suite_with_automation(self, suite_type: TestSuiteType) -> TestResult:
        """
        Execute a test suite with enhanced automation features.

        Args:
            suite_type: Type of test suite to execute

        Returns:
            TestResult with enhanced metrics and automation data
        """
        logger.info(f"Executing {suite_type.value} tests with automation enhancements...")
        start_time = time.time()

        try:
            # Pre-execution automation setup
            if suite_type == TestSuiteType.END_TO_END:
                # Generate E2E-specific test data
                with self.data_manager.data_context("e2e_test_scenarios", count=3, scenario_type="full_workflow"):
                    result = self.testing_framework._run_test_suite(suite_type)
            else:
                # Standard test suite execution
                result = self.testing_framework._run_test_suite(suite_type)

            # Post-execution automation analysis
            execution_time = time.time() - start_time
            self.execution_metrics[suite_type.value] = execution_time

            # Enhanced result analysis
            if result.passed:
                logger.info(f"✅ {suite_type.value} tests completed successfully in {execution_time:.2f}s")
            else:
                logger.warning(f"❌ {suite_type.value} tests failed in {execution_time:.2f}s")
                logger.warning(f"Failed tests: {len(result.failed_tests)}")

            return result

        except Exception as e:
            logger.error(f"Error executing {suite_type.value} tests: {e}", exc_info=True)
            # Return a failed result
            return TestResult(
                suite_type=suite_type,
                passed=False,
                duration=time.time() - start_time,
                error_message=f"Automation execution failed: {str(e)}",
            )

    def run_parallel_test_execution(
        self,
        suites: List[TestSuiteType],
        max_workers: Optional[int] = None,
    ) -> Dict[TestSuiteType, TestResult]:
        """
        Execute multiple test suites in parallel where possible.

        Args:
            suites: List of test suites to execute
            max_workers: Maximum number of parallel workers (if None, uses instance setting)

        Returns:
            Dictionary mapping suite types to their results
        """
        if not self.enable_parallel_execution or len(suites) <= 1:
            # Fall back to sequential execution
            results = {}
            for suite in suites:
                results[suite] = self.execute_suite_with_automation(suite)
            return results

        max_workers = max_workers or self.max_parallel_workers
        logger.info(f"Executing {len(suites)} test suites in parallel with {max_workers} workers")

        # Identify suites that can run in parallel (exclude E2E which needs isolated environment)
        parallel_suites = [s for s in suites if s != TestSuiteType.END_TO_END]
        sequential_suites = [s for s in suites if s == TestSuiteType.END_TO_END]

        results = {}

        # Execute parallel suites
        if parallel_suites:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_suite = {
                    executor.submit(self.execute_suite_with_automation, suite): suite for suite in parallel_suites
                }

                for future in as_completed(future_to_suite):
                    suite = future_to_suite[future]
                    try:
                        result = future.result()
                        results[suite] = result
                    except Exception as e:
                        logger.error(f"Parallel execution failed for {suite.value}: {e}", exc_info=True)
                        results[suite] = TestResult(
                            suite_type=suite,
                            passed=False,
                            duration=0.0,
                            error_message=f"Parallel execution error: {str(e)}",
                        )

        # Execute sequential suites (E2E)
        for suite in sequential_suites:
            results[suite] = self.execute_suite_with_automation(suite)

        return results

    def run_comprehensive_automated_testing(
        self,
        include_suites: Optional[List[TestSuiteType]] = None,
        exclude_suites: Optional[List[TestSuiteType]] = None,
        optimize_for_speed: bool = False,
        fail_on_coverage: bool = True,
        generate_reports: bool = True,
    ) -> Dict[str, Any]:
        """
        Run the complete automated testing workflow with intelligent orchestration.

        Args:
            include_suites: Specific suites to include
            exclude_suites: Specific suites to exclude
            optimize_for_speed: Whether to optimize for speed over comprehensiveness
            fail_on_coverage: Whether to fail if coverage threshold not met
            generate_reports: Whether to generate detailed reports

        Returns:
            Comprehensive automation results including metrics and analysis
        """
        logger.info("🚀 Starting comprehensive automated testing workflow...")
        workflow_start_time = time.time()

        try:
            # Phase 1: Planning
            logger.info("📋 Phase 1: Creating execution plan...")
            execution_plan = self.create_execution_plan(
                include_suites=include_suites,
                exclude_suites=exclude_suites,
                optimize_for_speed=optimize_for_speed,
            )

            if not execution_plan:
                raise RuntimeError("No test suites in execution plan")

            # Phase 2: Environment Setup
            logger.info("🔧 Phase 2: Setting up test environment...")
            if not self.setup_test_environment():
                raise RuntimeError("Failed to setup test environment")

            # Phase 3: Test Execution
            logger.info("🧪 Phase 3: Executing test suites...")
            test_results = self.run_parallel_test_execution(execution_plan)

            # Store results in framework for coverage analysis
            self.testing_framework.test_results = test_results

            # Phase 4: Coverage Analysis
            logger.info("📊 Phase 4: Generating coverage analysis...")
            coverage_report = self.testing_framework._generate_coverage_report()
            self.testing_framework.coverage_report = coverage_report

            # Phase 5: Report Generation
            if generate_reports:
                logger.info("📄 Phase 5: Generating comprehensive reports...")
                self.testing_framework._generate_test_reports()

            # Phase 6: Validation
            logger.info("✅ Phase 6: Validating results...")
            try:
                self.testing_framework._validate_test_results(fail_on_coverage)
                validation_passed = True
            except RuntimeError as e:
                logger.warning(f"Validation failed: {e}")
                validation_passed = False

            # Compile final results
            workflow_duration = time.time() - workflow_start_time

            # Calculate summary metrics
            total_tests = len(test_results)
            passed_tests = sum(1 for result in test_results.values() if result.passed)
            failed_tests = total_tests - passed_tests
            total_test_duration = sum(result.duration for result in test_results.values())

            automation_results = {
                "workflow_status": "SUCCESS" if validation_passed and failed_tests == 0 else "FAILED",
                "execution_plan": [suite.value for suite in execution_plan],
                "summary": {
                    "total_suites": total_tests,
                    "passed_suites": passed_tests,
                    "failed_suites": failed_tests,
                    "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
                    "total_test_duration": total_test_duration,
                    "workflow_duration": workflow_duration,
                    "automation_efficiency": (total_test_duration / workflow_duration) if workflow_duration > 0 else 0,
                },
                "coverage": {
                    "total_coverage": coverage_report.total_coverage,
                    "meets_threshold": coverage_report.meets_threshold,
                    "threshold": self.testing_framework.coverage_threshold,
                }
                if coverage_report
                else None,
                "test_results": {
                    suite.value: {
                        "passed": result.passed,
                        "duration": result.duration,
                        "failed_tests": len(result.failed_tests),
                        "skipped_tests": len(result.skipped_tests),
                        "error_message": result.error_message,
                    }
                    for suite, result in test_results.items()
                },
                "automation_metrics": self.execution_metrics,
                "timestamp": datetime.now().isoformat(),
            }

            # Store results
            self.automation_results = automation_results

            # Log summary
            logger.info("🎯 Comprehensive automated testing completed:")
            logger.info(f"   Status: {automation_results['workflow_status']}")
            logger.info(f"   Suites: {passed_tests}/{total_tests} passed")
            logger.info(
                f"   Coverage: {coverage_report.total_coverage:.2f}%"
                if coverage_report
                else "   Coverage: Not available"
            )
            logger.info(f"   Duration: {workflow_duration:.2f}s")

            return automation_results

        except Exception as e:
            logger.error(f"❌ Comprehensive automated testing failed: {e}", exc_info=True)
            workflow_duration = time.time() - workflow_start_time

            error_results = {
                "workflow_status": "ERROR",
                "error_message": str(e),
                "duration": workflow_duration,
                "timestamp": datetime.now().isoformat(),
            }

            self.automation_results = error_results
            return error_results

        finally:
            # Cleanup
            logger.info("🧹 Cleaning up test environment...")
            try:
                if TestSuiteType.END_TO_END in getattr(self, "execution_plan", []):
                    self.e2e_runner.teardown_environment()
                self.data_manager.cleanup_data()
            except Exception as e:
                logger.warning(f"Cleanup warning: {e}")

    def get_automation_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the last automation run.

        Returns:
            Dictionary containing automation summary and metrics
        """
        if not self.automation_results:
            return {"status": "No automation run completed"}

        return {
            "last_run": self.automation_results,
            "execution_metrics": self.execution_metrics,
            "framework_capabilities": {
                "parallel_execution": self.enable_parallel_execution,
                "max_workers": self.max_parallel_workers,
                "coverage_threshold": self.testing_framework.coverage_threshold,
                "performance_testing": self.testing_framework.enable_performance_testing,
                "security_testing": self.testing_framework.enable_security_testing,
            },
        }

    def save_automation_report(self, output_path: Optional[str] = None) -> str:
        """
        Save comprehensive automation report to file.

        Args:
            output_path: Optional path to save report (if None, generates default path)

        Returns:
            Path to saved report file
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(self.project_root / "test_reports" / f"automation_report_{timestamp}.json")

        # Ensure directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        report_data = {
            "automation_summary": self.get_automation_summary(),
            "project_root": str(self.project_root),
            "generated_at": datetime.now().isoformat(),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        logger.info(f"Automation report saved to: {output_path}")
        return output_path


def main():
    """
    Main entry point for the test automation CLI.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Advanced Test Automation Orchestrator")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--coverage-threshold", type=float, default=95.0, help="Coverage threshold percentage")
    parser.add_argument("--max-workers", type=int, default=4, help="Maximum parallel workers")
    parser.add_argument("--no-parallel", action="store_true", help="Disable parallel execution")
    parser.add_argument("--optimize-speed", action="store_true", help="Optimize execution for speed")
    parser.add_argument(
        "--include-suites", nargs="+", choices=[s.value for s in TestSuiteType], help="Suites to include"
    )
    parser.add_argument(
        "--exclude-suites", nargs="+", choices=[s.value for s in TestSuiteType], help="Suites to exclude"
    )
    parser.add_argument("--ignore-coverage", action="store_true", help="Don't fail on coverage threshold")
    parser.add_argument("--no-reports", action="store_true", help="Skip report generation")
    parser.add_argument("--report-output", help="Output path for automation report")

    args = parser.parse_args()

    try:
        # Initialize orchestrator
        orchestrator = TestAutomationOrchestrator(
            project_root=args.project_root,
            coverage_threshold=args.coverage_threshold,
            enable_parallel_execution=not args.no_parallel,
            max_parallel_workers=args.max_workers,
        )

        # Convert suite arguments
        include_suites = [TestSuiteType(s) for s in args.include_suites] if args.include_suites else None
        exclude_suites = [TestSuiteType(s) for s in args.exclude_suites] if args.exclude_suites else None

        # Run comprehensive automated testing
        results = orchestrator.run_comprehensive_automated_testing(
            include_suites=include_suites,
            exclude_suites=exclude_suites,
            optimize_for_speed=args.optimize_speed,
            fail_on_coverage=not args.ignore_coverage,
            generate_reports=not args.no_reports,
        )

        # Save report if requested
        if args.report_output:
            orchestrator.save_automation_report(args.report_output)

        # Exit with appropriate code
        if results["workflow_status"] in ["SUCCESS"]:
            return 0
        else:
            return 1

    except KeyboardInterrupt:
        logger.error("❌ Automation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"❌ Automation failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
