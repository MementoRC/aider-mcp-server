"""
Performance Benchmarking system for comprehensive performance monitoring and regression detection.

This module provides advanced performance benchmarking capabilities that establish baselines,
track performance metrics over time, and detect regressions in critical system operations.
"""

import asyncio
import json
import tempfile
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol


class BenchmarkType(Enum):
    """Types of performance benchmarks."""

    API_REQUEST = "api_request_processing"
    DATABASE_QUERY = "database_query"
    MODEL_INFERENCE = "model_inference"
    MEMORY_USAGE = "memory_usage"
    THREAD_POOL = "thread_pool_performance"
    FILE_IO = "file_io_operations"


class RegressionSeverity(Enum):
    """Severity levels for performance regressions."""

    MINOR = "minor"  # 5-15% regression
    MODERATE = "moderate"  # 15-30% regression
    MAJOR = "major"  # 30-50% regression
    CRITICAL = "critical"  # >50% regression


@dataclass
class BenchmarkResult:
    """Represents a single benchmark execution result."""

    benchmark_type: BenchmarkType
    operation_name: str
    iterations: int
    start_time: float
    end_time: float
    mean_time: float
    median_time: float
    min_time: float
    max_time: float
    p95_time: float
    p99_time: float
    std_dev: float
    throughput: float  # operations per second
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Total benchmark duration."""
        return self.end_time - self.start_time


@dataclass
class PerformanceBaseline:
    """Performance baseline data for a specific operation."""

    operation_name: str
    benchmark_type: BenchmarkType
    established_at: float
    iterations: int
    mean_time: float
    median_time: float
    p95_time: float
    p99_time: float
    std_dev: float
    throughput: float
    environment_info: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"


@dataclass
class RegressionReport:
    """Report of detected performance regression."""

    operation_name: str
    benchmark_type: BenchmarkType
    severity: RegressionSeverity
    baseline_time: float
    current_time: float
    regression_percent: float
    threshold_percent: float
    detected_at: float
    details: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class BenchmarkMetrics:
    """Aggregated benchmark metrics."""

    total_benchmarks: int
    successful_benchmarks: int
    failed_benchmarks: int
    total_operations: int
    average_performance: Dict[str, float] = field(default_factory=dict)
    regression_count: int = 0
    last_benchmark_time: Optional[float] = None


class PerformanceBenchmarking:
    """
    Comprehensive performance benchmarking system that establishes baselines,
    tracks performance metrics over time, and detects regressions in critical
    system operations.
    """

    def __init__(
        self,
        application_coordinator: Any,
        baseline_path: str = "data/performance_baseline.json",
        history_retention_hours: int = 168,  # 1 week
    ) -> None:
        """
        Initialize the performance benchmarking system.

        Args:
            application_coordinator: Reference to the main application coordinator
            baseline_path: Path to store performance baseline data
            history_retention_hours: Hours to retain benchmark history
        """
        self._logger: LoggerProtocol = get_logger(__name__)
        self._application_coordinator = application_coordinator
        self._baseline_path = Path(baseline_path).resolve()
        self._history_retention_hours = history_retention_hours

        # Performance data storage
        self._baselines: Dict[str, PerformanceBaseline] = {}
        self._benchmark_history: deque[BenchmarkResult] = deque(maxlen=10000)
        self._regression_reports: List[RegressionReport] = []

        # Configuration
        self._default_iterations = 50
        self._regression_thresholds = {
            RegressionSeverity.MINOR: 0.05,  # 5%
            RegressionSeverity.MODERATE: 0.15,  # 15%
            RegressionSeverity.MAJOR: 0.30,  # 30%
            RegressionSeverity.CRITICAL: 0.50,  # 50%
        }

        # Background tasks
        self._benchmarking_task: Optional[asyncio.Task[None]] = None
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._benchmarking_active = False
        self._benchmarking_interval = 300.0  # 5 minutes

        # Thread pool for CPU-intensive benchmarks
        self._thread_pool_size = 4

        self._lock = asyncio.Lock()

        # Load existing baselines
        self._load_baselines()

        self._logger.info(f"PerformanceBenchmarking initialized with baseline path: {self._baseline_path}")

    async def start_benchmarking(self) -> None:
        """Start the continuous performance benchmarking system."""
        async with self._lock:
            if self._benchmarking_active:
                self._logger.warning("Performance benchmarking is already active")
                return

            self._benchmarking_active = True

            # Start background benchmarking and cleanup tasks
            self._benchmarking_task = asyncio.create_task(self._benchmarking_loop())
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            self._logger.info(f"Performance benchmarking started with {self._benchmarking_interval:.1f}s interval")

    async def stop_benchmarking(self) -> None:
        """Stop the continuous performance benchmarking system."""
        async with self._lock:
            self._benchmarking_active = False

            # Cancel background tasks
            if self._benchmarking_task:
                self._benchmarking_task.cancel()
                try:
                    await self._benchmarking_task
                except asyncio.CancelledError:
                    pass
                self._benchmarking_task = None

            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
                self._cleanup_task = None

            self._logger.info("Performance benchmarking stopped")

    async def run_benchmark(self, benchmark_type: BenchmarkType, iterations: Optional[int] = None) -> BenchmarkResult:
        """
        Run a specific benchmark.

        Args:
            benchmark_type: Type of benchmark to run
            iterations: Number of iterations (uses default if None)

        Returns:
            BenchmarkResult containing performance metrics
        """
        if iterations is None:
            iterations = self._default_iterations

        self._logger.debug(f"Running {benchmark_type.value} benchmark with {iterations} iterations")

        try:
            if benchmark_type == BenchmarkType.API_REQUEST:
                return await self._benchmark_api_request_processing(iterations)
            elif benchmark_type == BenchmarkType.DATABASE_QUERY:
                return await self._benchmark_database_query(iterations)
            elif benchmark_type == BenchmarkType.MODEL_INFERENCE:
                return await self._benchmark_model_inference(iterations)
            elif benchmark_type == BenchmarkType.MEMORY_USAGE:
                return await self._benchmark_memory_usage(iterations)
            elif benchmark_type == BenchmarkType.THREAD_POOL:
                return await self._benchmark_thread_pool_performance(iterations)
            elif benchmark_type == BenchmarkType.FILE_IO:
                return await self._benchmark_file_io_operations(iterations)
            else:
                raise ValueError(f"Unknown benchmark type: {benchmark_type}")

        except Exception as e:
            self._logger.error(f"Error running benchmark {benchmark_type.value}: {str(e)}")
            raise

    async def run_all_benchmarks(self) -> Dict[BenchmarkType, BenchmarkResult]:
        """
        Run all available benchmarks.

        Returns:
            Dictionary mapping benchmark types to their results
        """
        results = {}

        for benchmark_type in BenchmarkType:
            try:
                result = await self.run_benchmark(benchmark_type)
                results[benchmark_type] = result
                self._benchmark_history.append(result)

                self._logger.debug(
                    f"Completed benchmark {benchmark_type.value}: "
                    f"{result.mean_time:.4f}s mean, {result.throughput:.2f} ops/s"
                )

            except Exception as e:
                self._logger.error(f"Failed to run benchmark {benchmark_type.value}: {str(e)}")

        return results

    def establish_baseline(self, benchmark_results: Dict[BenchmarkType, BenchmarkResult]) -> None:
        """
        Establish performance baselines from benchmark results.

        Args:
            benchmark_results: Results from running benchmarks
        """
        for benchmark_type, result in benchmark_results.items():
            baseline = PerformanceBaseline(
                operation_name=result.operation_name,
                benchmark_type=benchmark_type,
                established_at=time.time(),
                iterations=result.iterations,
                mean_time=result.mean_time,
                median_time=result.median_time,
                p95_time=result.p95_time,
                p99_time=result.p99_time,
                std_dev=result.std_dev,
                throughput=result.throughput,
                environment_info={
                    "timestamp": time.time(),
                    "iterations": result.iterations,
                },
            )

            self._baselines[result.operation_name] = baseline
            self._logger.info(f"Established baseline for {result.operation_name}")

        self._save_baselines()

    def detect_regressions(
        self, benchmark_results: Dict[BenchmarkType, BenchmarkResult], custom_threshold: Optional[float] = None
    ) -> List[RegressionReport]:
        """
        Detect performance regressions against established baselines.

        Args:
            benchmark_results: Current benchmark results
            custom_threshold: Custom regression threshold (0.0-1.0)

        Returns:
            List of detected regressions
        """
        regressions = []

        for benchmark_type, result in benchmark_results.items():
            baseline = self._baselines.get(result.operation_name)
            if not baseline:
                self._logger.warning(f"No baseline found for {result.operation_name}, skipping regression detection")
                continue

            # Calculate regression percentage
            baseline_time = baseline.mean_time
            current_time = result.mean_time

            if baseline_time > 0:
                regression_pct = (current_time - baseline_time) / baseline_time

                # Determine severity and threshold
                severity = self._determine_regression_severity(regression_pct)
                threshold = custom_threshold or self._regression_thresholds[RegressionSeverity.MINOR]

                # Check if regression exceeds threshold
                if regression_pct > threshold:
                    regression = RegressionReport(
                        operation_name=result.operation_name,
                        benchmark_type=benchmark_type,
                        severity=severity,
                        baseline_time=baseline_time,
                        current_time=current_time,
                        regression_percent=regression_pct,
                        threshold_percent=threshold,
                        detected_at=time.time(),
                        details={
                            "baseline_throughput": baseline.throughput,
                            "current_throughput": result.throughput,
                            "baseline_p95": baseline.p95_time,
                            "current_p95": result.p95_time,
                            "iterations": result.iterations,
                        },
                        recommendations=self._generate_regression_recommendations(benchmark_type, regression_pct),
                    )

                    regressions.append(regression)
                    self._logger.warning(
                        f"Performance regression detected in {result.operation_name}: "
                        f"{regression_pct:.1%} slower than baseline"
                    )

        # Store regression reports
        self._regression_reports.extend(regressions)

        return regressions

    def get_performance_summary(self) -> BenchmarkMetrics:
        """
        Get a summary of performance benchmarking metrics.

        Returns:
            BenchmarkMetrics with aggregated performance data
        """
        total_benchmarks = len(self._benchmark_history)
        successful_benchmarks = sum(1 for result in self._benchmark_history if result.iterations > 0)
        failed_benchmarks = total_benchmarks - successful_benchmarks

        # Calculate average performance by operation
        performance_by_operation: defaultdict[str, List[float]] = defaultdict(list)
        for result in self._benchmark_history:
            performance_by_operation[result.operation_name].append(result.mean_time)

        average_performance = {operation: mean(times) for operation, times in performance_by_operation.items()}

        last_benchmark_time = None
        if self._benchmark_history:
            last_benchmark_time = self._benchmark_history[-1].end_time

        return BenchmarkMetrics(
            total_benchmarks=total_benchmarks,
            successful_benchmarks=successful_benchmarks,
            failed_benchmarks=failed_benchmarks,
            total_operations=sum(result.iterations for result in self._benchmark_history),
            average_performance=average_performance,
            regression_count=len(self._regression_reports),
            last_benchmark_time=last_benchmark_time,
        )

    def export_benchmark_data(self, format_type: str = "json") -> bytes:
        """
        Export benchmark data in specified format.

        Args:
            format_type: Export format ("json", "csv")

        Returns:
            Exported data as bytes
        """
        if format_type == "json":
            return self._export_json()
        elif format_type == "csv":
            return self._export_csv()
        else:
            raise ValueError(f"Unsupported export format: {format_type}")

    # Benchmark implementation methods

    async def _benchmark_api_request_processing(self, iterations: int) -> BenchmarkResult:
        """Benchmark API request processing performance."""
        operation_name = "api_request_processing"
        times = []

        start_time = time.time()

        for _ in range(iterations):
            iteration_start = time.perf_counter()

            # Simulate API request processing
            await asyncio.sleep(0.001)  # Simulated async work

            # Add some CPU work
            _ = sum(i * i for i in range(100))

            iteration_end = time.perf_counter()
            times.append(iteration_end - iteration_start)

        end_time = time.time()

        return self._create_benchmark_result(
            BenchmarkType.API_REQUEST, operation_name, iterations, start_time, end_time, times
        )

    async def _benchmark_database_query(self, iterations: int) -> BenchmarkResult:
        """Benchmark database query performance."""
        operation_name = "database_query"
        times = []

        start_time = time.time()

        for _ in range(iterations):
            iteration_start = time.perf_counter()

            # Simulate database query
            await asyncio.sleep(0.005)  # Simulated DB latency

            # Simulate data processing
            _ = list(range(1000))

            iteration_end = time.perf_counter()
            times.append(iteration_end - iteration_start)

        end_time = time.time()

        return self._create_benchmark_result(
            BenchmarkType.DATABASE_QUERY, operation_name, iterations, start_time, end_time, times
        )

    async def _benchmark_model_inference(self, iterations: int) -> BenchmarkResult:
        """Benchmark model inference performance."""
        operation_name = "model_inference"
        times = []

        start_time = time.time()

        for _ in range(iterations):
            iteration_start = time.perf_counter()

            # Simulate model inference computation
            await asyncio.sleep(0.010)  # Simulated inference time

            # CPU-intensive work to simulate model computation
            _ = sum(i**2 for i in range(500))

            iteration_end = time.perf_counter()
            times.append(iteration_end - iteration_start)

        end_time = time.time()

        return self._create_benchmark_result(
            BenchmarkType.MODEL_INFERENCE, operation_name, iterations, start_time, end_time, times
        )

    async def _benchmark_memory_usage(self, iterations: int) -> BenchmarkResult:
        """Benchmark memory allocation and usage patterns."""
        operation_name = "memory_usage"
        times = []

        start_time = time.time()

        for _ in range(iterations):
            iteration_start = time.perf_counter()

            # Simulate memory-intensive operations
            large_list = [i * 2 for i in range(10000)]
            large_dict = {i: str(i) for i in range(1000)}

            # Cleanup
            del large_list
            del large_dict

            iteration_end = time.perf_counter()
            times.append(iteration_end - iteration_start)

        end_time = time.time()

        return self._create_benchmark_result(
            BenchmarkType.MEMORY_USAGE, operation_name, iterations, start_time, end_time, times
        )

    async def _benchmark_thread_pool_performance(self, iterations: int) -> BenchmarkResult:
        """Benchmark thread pool performance."""
        operation_name = "thread_pool_performance"
        times = []

        start_time = time.time()

        for _ in range(iterations):
            iteration_start = time.perf_counter()

            # Simulate thread pool work
            tasks = []
            for _ in range(self._thread_pool_size):
                task = asyncio.create_task(asyncio.sleep(0.001))
                tasks.append(task)

            await asyncio.gather(*tasks)

            iteration_end = time.perf_counter()
            times.append(iteration_end - iteration_start)

        end_time = time.time()

        return self._create_benchmark_result(
            BenchmarkType.THREAD_POOL, operation_name, iterations, start_time, end_time, times
        )

    async def _benchmark_file_io_operations(self, iterations: int) -> BenchmarkResult:
        """Benchmark file I/O operations."""
        operation_name = "file_io_operations"
        times = []

        start_time = time.time()

        # Create temporary directory for benchmarking
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)

            for i in range(iterations):
                iteration_start = time.perf_counter()

                # Simulate file operations
                test_file = temp_dir / f"test_{i}.txt"
                test_data = f"Benchmark data for iteration {i} " * 100

                # Write operation
                test_file.write_text(test_data, encoding="utf-8")

                # Read operation
                _ = test_file.read_text(encoding="utf-8")

                # Cleanup
                test_file.unlink()

                iteration_end = time.perf_counter()
                times.append(iteration_end - iteration_start)

        end_time = time.time()

        return self._create_benchmark_result(
            BenchmarkType.FILE_IO, operation_name, iterations, start_time, end_time, times
        )

    # Utility methods

    def _create_benchmark_result(
        self,
        benchmark_type: BenchmarkType,
        operation_name: str,
        iterations: int,
        start_time: float,
        end_time: float,
        times: List[float],
    ) -> BenchmarkResult:
        """Create a BenchmarkResult from timing data."""
        if not times:
            raise ValueError("No timing data available")

        sorted_times = sorted(times)
        n = len(sorted_times)

        mean_time = mean(times)
        median_time = median(times)
        min_time = min(times)
        max_time = max(times)
        p95_time = sorted_times[int(n * 0.95)] if n > 0 else 0
        p99_time = sorted_times[int(n * 0.99)] if n > 0 else 0
        std_dev = stdev(times) if len(times) > 1 else 0

        total_duration = end_time - start_time
        throughput = iterations / total_duration if total_duration > 0 else 0

        return BenchmarkResult(
            benchmark_type=benchmark_type,
            operation_name=operation_name,
            iterations=iterations,
            start_time=start_time,
            end_time=end_time,
            mean_time=mean_time,
            median_time=median_time,
            min_time=min_time,
            max_time=max_time,
            p95_time=p95_time,
            p99_time=p99_time,
            std_dev=std_dev,
            throughput=throughput,
            metadata={
                "total_duration": total_duration,
                "sample_count": len(times),
            },
        )

    def _determine_regression_severity(self, regression_pct: float) -> RegressionSeverity:
        """Determine the severity of a performance regression."""
        if regression_pct >= self._regression_thresholds[RegressionSeverity.CRITICAL]:
            return RegressionSeverity.CRITICAL
        elif regression_pct >= self._regression_thresholds[RegressionSeverity.MAJOR]:
            return RegressionSeverity.MAJOR
        elif regression_pct >= self._regression_thresholds[RegressionSeverity.MODERATE]:
            return RegressionSeverity.MODERATE
        else:
            return RegressionSeverity.MINOR

    def _generate_regression_recommendations(self, benchmark_type: BenchmarkType, regression_pct: float) -> List[str]:
        """Generate recommendations for addressing performance regressions."""
        recommendations = []

        if regression_pct > 0.30:  # Major regression
            recommendations.append("Immediate investigation required")
            recommendations.append("Consider rolling back recent changes")

        if benchmark_type == BenchmarkType.API_REQUEST:
            recommendations.extend(
                ["Check API endpoint performance", "Review request processing logic", "Monitor network latency"]
            )
        elif benchmark_type == BenchmarkType.DATABASE_QUERY:
            recommendations.extend(
                [
                    "Analyze database query performance",
                    "Check for missing indexes",
                    "Review database connection pooling",
                ]
            )
        elif benchmark_type == BenchmarkType.MODEL_INFERENCE:
            recommendations.extend(
                ["Review model optimization settings", "Check GPU/CPU utilization", "Consider model quantization"]
            )
        elif benchmark_type == BenchmarkType.MEMORY_USAGE:
            recommendations.extend(
                ["Check for memory leaks", "Review garbage collection settings", "Monitor memory allocation patterns"]
            )

        recommendations.append("Run detailed profiling")
        recommendations.append("Compare with previous baselines")

        return recommendations

    def _load_baselines(self) -> None:
        """Load performance baselines from storage."""
        try:
            if self._baseline_path.exists():
                with open(self._baseline_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for operation_name, baseline_data in data.items():
                    baseline = PerformanceBaseline(
                        operation_name=baseline_data["operation_name"],
                        benchmark_type=BenchmarkType(baseline_data["benchmark_type"]),
                        established_at=baseline_data["established_at"],
                        iterations=baseline_data["iterations"],
                        mean_time=baseline_data["mean_time"],
                        median_time=baseline_data["median_time"],
                        p95_time=baseline_data["p95_time"],
                        p99_time=baseline_data["p99_time"],
                        std_dev=baseline_data["std_dev"],
                        throughput=baseline_data["throughput"],
                        environment_info=baseline_data.get("environment_info", {}),
                        version=baseline_data.get("version", "1.0"),
                    )
                    self._baselines[operation_name] = baseline

                self._logger.info(f"Loaded {len(self._baselines)} performance baselines")
            else:
                self._logger.info("No existing baselines found")

        except Exception as e:
            self._logger.error(f"Error loading baselines: {str(e)}")

    def _save_baselines(self) -> None:
        """Save performance baselines to storage."""
        try:
            # Ensure directory exists
            self._baseline_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert baselines to serializable format
            data = {}
            for operation_name, baseline in self._baselines.items():
                data[operation_name] = {
                    "operation_name": baseline.operation_name,
                    "benchmark_type": baseline.benchmark_type.value,
                    "established_at": baseline.established_at,
                    "iterations": baseline.iterations,
                    "mean_time": baseline.mean_time,
                    "median_time": baseline.median_time,
                    "p95_time": baseline.p95_time,
                    "p99_time": baseline.p99_time,
                    "std_dev": baseline.std_dev,
                    "throughput": baseline.throughput,
                    "environment_info": baseline.environment_info,
                    "version": baseline.version,
                }

            with open(self._baseline_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            self._logger.info(f"Saved {len(self._baselines)} performance baselines")

        except Exception as e:
            self._logger.error(f"Error saving baselines: {str(e)}")

    def _export_json(self) -> bytes:
        """Export benchmark data as JSON."""
        export_data: Dict[str, Any] = {
            "timestamp": time.time(),
            "baselines": {},
            "recent_results": [],
            "regressions": [],
            "summary": asdict(self.get_performance_summary()),
        }

        # Export baselines
        for operation_name, baseline in self._baselines.items():
            baseline_dict = asdict(baseline)
            baseline_dict["benchmark_type"] = baseline.benchmark_type.value
            export_data["baselines"][operation_name] = baseline_dict

        # Export recent results (last 100)
        recent_results = list(self._benchmark_history)[-100:]
        for result in recent_results:
            result_dict = asdict(result)
            result_dict["benchmark_type"] = result.benchmark_type.value
            export_data["recent_results"].append(result_dict)

        # Export regressions
        for regression in self._regression_reports[-50:]:  # Last 50 regressions
            regression_dict = asdict(regression)
            regression_dict["benchmark_type"] = regression.benchmark_type.value
            regression_dict["severity"] = regression.severity.value
            export_data["regressions"].append(regression_dict)

        return json.dumps(export_data, indent=2).encode("utf-8")

    def _export_csv(self) -> bytes:
        """Export benchmark data as CSV."""
        lines = ["timestamp,benchmark_type,operation_name,mean_time,throughput,iterations,p95_time"]

        for result in self._benchmark_history:
            lines.append(
                f"{result.end_time},{result.benchmark_type.value},{result.operation_name},"
                f"{result.mean_time},{result.throughput},{result.iterations},{result.p95_time}"
            )

        return "\n".join(lines).encode("utf-8")

    async def _benchmarking_loop(self) -> None:
        """Background task for continuous benchmarking."""
        while self._benchmarking_active:
            try:
                # Run all benchmarks
                results = await self.run_all_benchmarks()

                # Check for regressions
                regressions = self.detect_regressions(results)

                # Log any detected regressions
                if regressions:
                    self._logger.warning(f"Detected {len(regressions)} performance regressions")

                await asyncio.sleep(self._benchmarking_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in benchmarking loop: {str(e)}")
                await asyncio.sleep(30.0)  # Brief pause before retry

    async def _cleanup_loop(self) -> None:
        """Background task for data cleanup."""
        while self._benchmarking_active:
            try:
                await self._cleanup_old_data()
                await asyncio.sleep(3600.0)  # Cleanup every hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in cleanup loop: {str(e)}")
                await asyncio.sleep(300.0)  # Brief pause before retry

    async def _cleanup_old_data(self) -> None:
        """Clean up old benchmark data based on retention policy."""
        cutoff_time = time.time() - (self._history_retention_hours * 3600)

        # Clean up old benchmark results
        original_count = len(self._benchmark_history)
        filtered_results = [result for result in self._benchmark_history if result.end_time >= cutoff_time]

        # Update the deque
        self._benchmark_history.clear()
        self._benchmark_history.extend(filtered_results)

        # Clean up old regression reports
        self._regression_reports = [
            regression for regression in self._regression_reports if regression.detected_at >= cutoff_time
        ]

        cleaned_count = original_count - len(self._benchmark_history)
        if cleaned_count > 0:
            self._logger.debug(f"Cleaned up {cleaned_count} old benchmark results")

    @property
    def is_benchmarking_active(self) -> bool:
        """Check if continuous benchmarking is active."""
        return self._benchmarking_active

    @property
    def baseline_count(self) -> int:
        """Get the number of established baselines."""
        return len(self._baselines)

    @property
    def total_benchmarks_run(self) -> int:
        """Get the total number of benchmarks run."""
        return len(self._benchmark_history)
