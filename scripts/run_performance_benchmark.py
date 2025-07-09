#!/usr/bin/env python3
"""
Script to run performance benchmarks, establish baselines, and detect regressions.
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add src to path for importing existing monitoring systems
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from aider_mcp_server.atoms.logging.logger import get_logger
    from aider_mcp_server.molecules.monitoring.performance_benchmarking import (
        BenchmarkResult,
        BenchmarkType,
        PerformanceBenchmarking,
        RegressionReport,
    )

    MONITORING_SYSTEM_AVAILABLE = True
except ImportError as e:
    print(f"Error: Could not import performance benchmarking system: {e}", file=sys.stderr)
    print("Please ensure 'src' is in your Python path and dependencies are installed.", file=sys.stderr)
    MONITORING_SYSTEM_AVAILABLE = False


def setup_logging_and_directories(args: argparse.Namespace) -> None:
    """Setup logging configuration and create necessary directories."""
    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)
    else:
        import logging

        logging.getLogger().setLevel(logging.INFO)

    # Ensure the output directory exists
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.baseline_path.parent.mkdir(parents=True, exist_ok=True)


async def run_benchmarks(
    args: argparse.Namespace,
) -> Tuple[Dict[BenchmarkType, BenchmarkResult], List[RegressionReport], Any]:
    """Run performance benchmarks and detect regressions."""
    logger = get_logger(__name__)

    # PerformanceBenchmarking expects an application_coordinator,
    # for standalone script, we can pass None or a mock object.
    benchmarking_system = PerformanceBenchmarking(
        application_coordinator=None,
        baseline_path=str(args.baseline_path),
    )

    all_benchmark_results: Dict[BenchmarkType, BenchmarkResult] = {}
    detected_regressions: List[RegressionReport] = []

    logger.info("Running all performance benchmarks...")
    # Run all benchmarks with specified iterations
    for benchmark_type in BenchmarkType:
        try:
            result = await benchmarking_system.run_benchmark(benchmark_type, iterations=args.iterations)
            all_benchmark_results[benchmark_type] = result
            logger.info(
                f"  {result.operation_name}: Mean={result.mean_time:.4f}s, Throughput={result.throughput:.2f} ops/s"
            )
        except Exception as e:
            logger.error(f"Failed to run benchmark {benchmark_type.value}: {e}")
            continue

    # Handle baseline establishment or regression detection
    if args.establish_baseline:
        logger.info("Establishing new performance baselines...")
        benchmarking_system.establish_baseline(all_benchmark_results)
        logger.info(f"Successfully established baselines. Saved to {args.baseline_path}")
    else:
        logger.info("Detecting performance regressions...")
        detected_regressions = benchmarking_system.detect_regressions(all_benchmark_results)

        if detected_regressions:
            logger.warning(f"Detected {len(detected_regressions)} performance regressions.")
            for reg in detected_regressions:
                logger.warning(
                    f"  Regression: {reg.operation_name} ({reg.benchmark_type.value}) "
                    f"Severity: {reg.severity.value.upper()} ({reg.regression_percent:.1%} slower)"
                )

    # Get overall summary
    overall_summary_obj = benchmarking_system.get_performance_summary()

    return all_benchmark_results, detected_regressions, overall_summary_obj


def process_results(
    all_benchmark_results: Dict[BenchmarkType, BenchmarkResult],
    detected_regressions: List[RegressionReport],
    overall_summary_obj: Any,
) -> Dict[str, Any]:
    """Process benchmark results into JSON-serializable format."""
    # Prepare results for JSON output with enum handling
    output_data: Dict[str, Any] = {
        "benchmark_results": {},
        "regression_reports": [],
        "summary": asdict(overall_summary_obj) if overall_summary_obj else {},
    }

    # Convert benchmark results with enum handling
    for bt, result in all_benchmark_results.items():
        result_dict = asdict(result)
        result_dict["benchmark_type"] = result.benchmark_type.value  # Convert enum to string
        output_data["benchmark_results"][bt.value] = result_dict

    # Convert regression reports with enum handling
    for reg in detected_regressions:
        reg_dict = asdict(reg)
        reg_dict["benchmark_type"] = reg.benchmark_type.value  # Convert enum to string
        reg_dict["severity"] = reg.severity.value  # Convert enum to string
        output_data["regression_reports"].append(reg_dict)

    return output_data


def save_results_and_output(
    args: argparse.Namespace, output_data: Dict[str, Any], detected_regressions: List[RegressionReport]
) -> None:
    """Save results to file and set GitHub Actions output."""
    logger = get_logger(__name__)

    # Save results to output file
    try:
        with open(args.output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"Benchmark results and regression reports saved to {args.output_file}")
    except Exception as e:
        logger.error(f"Failed to save output to {args.output_file}: {e}")
        sys.exit(1)

    # Indicate if regressions were detected for workflow output
    with open(os.environ.get("GITHUB_OUTPUT", "output.txt"), "a", encoding="utf-8") as gh_output:
        gh_output.write(f"regressions_detected={'true' if detected_regressions else 'false'}\n")


async def main():
    """Main function with reduced complexity."""
    parser = argparse.ArgumentParser(
        description="Run performance benchmarks, establish baselines, or detect regressions."
    )
    parser.add_argument(
        "--establish-baseline",
        action="store_true",
        help="Run benchmarks and establish a new performance baseline.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default="reports/performance_results.json",
        help="Path to output the benchmark results and regression reports.",
    )
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default="data/performance_baseline.json",
        help="Path to the performance baseline JSON file.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=50,
        help="Number of iterations for each benchmark (default: 50).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output.")

    args = parser.parse_args()

    if not MONITORING_SYSTEM_AVAILABLE:
        print("Exiting due to missing monitoring system dependencies.", file=sys.stderr)
        sys.exit(1)

    try:
        setup_logging_and_directories(args)
        all_benchmark_results, detected_regressions, overall_summary_obj = await run_benchmarks(args)
        output_data = process_results(all_benchmark_results, detected_regressions, overall_summary_obj)
        save_results_and_output(args, output_data, detected_regressions)
    except Exception as e:
        logger = get_logger(__name__)
        logger.critical(f"An unhandled error occurred during benchmarking: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
