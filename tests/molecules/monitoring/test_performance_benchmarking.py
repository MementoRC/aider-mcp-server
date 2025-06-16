"""
Tests for PerformanceBenchmarking monitoring molecule.
"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from aider_mcp_server.molecules.monitoring.performance_benchmarking import (
    BenchmarkMetrics,
    BenchmarkResult,
    BenchmarkType,
    PerformanceBenchmarking,
    RegressionReport,
    RegressionSeverity,
)


@pytest.fixture
def mock_coordinator():
    """Create a mock application coordinator."""
    coordinator = MagicMock()
    coordinator.broadcast_event = AsyncMock()
    return coordinator


@pytest.fixture
def temp_baseline_path():
    """Create a temporary path for baseline storage."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield str(Path(temp_dir) / "test_baseline.json")


@pytest.fixture
def performance_benchmarking(mock_coordinator, temp_baseline_path):
    """Create a PerformanceBenchmarking instance for testing."""
    return PerformanceBenchmarking(
        application_coordinator=mock_coordinator,
        baseline_path=temp_baseline_path,
        history_retention_hours=1,  # Short retention for testing
    )


@pytest.fixture
def sample_benchmark_results():
    """Create sample benchmark results for testing."""
    current_time = time.time()

    return {
        BenchmarkType.API_REQUEST: BenchmarkResult(
            benchmark_type=BenchmarkType.API_REQUEST,
            operation_name="api_request_processing",
            iterations=50,
            start_time=current_time - 10,
            end_time=current_time,
            mean_time=0.002,
            median_time=0.0018,
            min_time=0.001,
            max_time=0.005,
            p95_time=0.004,
            p99_time=0.0045,
            std_dev=0.0008,
            throughput=500.0,
            metadata={"test": True},
        ),
        BenchmarkType.DATABASE_QUERY: BenchmarkResult(
            benchmark_type=BenchmarkType.DATABASE_QUERY,
            operation_name="database_query",
            iterations=30,
            start_time=current_time - 5,
            end_time=current_time,
            mean_time=0.010,
            median_time=0.009,
            min_time=0.007,
            max_time=0.015,
            p95_time=0.014,
            p99_time=0.0148,
            std_dev=0.002,
            throughput=100.0,
            metadata={"test": True},
        ),
    }


class TestPerformanceBenchmarking:
    """Test cases for PerformanceBenchmarking class."""

    def test_initialization(self, performance_benchmarking, temp_baseline_path):
        """Test PerformanceBenchmarking initialization."""
        assert performance_benchmarking._baseline_path == Path(temp_baseline_path)
        assert performance_benchmarking._history_retention_hours == 1
        assert performance_benchmarking._default_iterations == 50
        assert not performance_benchmarking.is_benchmarking_active
        assert performance_benchmarking.baseline_count == 0
        assert performance_benchmarking.total_benchmarks_run == 0

    @pytest.mark.asyncio
    async def test_start_stop_benchmarking(self, performance_benchmarking):
        """Test starting and stopping benchmarking."""
        # Test start
        await performance_benchmarking.start_benchmarking()
        assert performance_benchmarking.is_benchmarking_active
        assert performance_benchmarking._benchmarking_task is not None
        assert performance_benchmarking._cleanup_task is not None

        # Test stop
        await performance_benchmarking.stop_benchmarking()
        assert not performance_benchmarking.is_benchmarking_active
        assert performance_benchmarking._benchmarking_task is None
        assert performance_benchmarking._cleanup_task is None

    @pytest.mark.asyncio
    async def test_start_benchmarking_already_active(self, performance_benchmarking):
        """Test starting benchmarking when already active."""
        await performance_benchmarking.start_benchmarking()

        # Try to start again - should not create new tasks
        original_task = performance_benchmarking._benchmarking_task
        await performance_benchmarking.start_benchmarking()
        assert performance_benchmarking._benchmarking_task is original_task

        await performance_benchmarking.stop_benchmarking()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("benchmark_type", list(BenchmarkType))
    async def test_run_benchmark(self, performance_benchmarking, benchmark_type):
        """Test running individual benchmarks."""
        iterations = 5  # Use small number for fast tests

        result = await performance_benchmarking.run_benchmark(benchmark_type, iterations)

        assert isinstance(result, BenchmarkResult)
        assert result.benchmark_type == benchmark_type
        assert result.iterations == iterations
        assert result.mean_time > 0
        assert result.throughput > 0
        assert result.end_time > result.start_time
        assert len(result.metadata) > 0

    @pytest.mark.asyncio
    async def test_run_all_benchmarks(self, performance_benchmarking):
        """Test running all available benchmarks."""
        # Override default iterations for faster tests
        performance_benchmarking._default_iterations = 3

        results = await performance_benchmarking.run_all_benchmarks()

        assert isinstance(results, dict)
        assert len(results) == len(BenchmarkType)

        for benchmark_type, result in results.items():
            assert isinstance(benchmark_type, BenchmarkType)
            assert isinstance(result, BenchmarkResult)
            assert result.benchmark_type == benchmark_type

    def test_establish_baseline(self, performance_benchmarking, sample_benchmark_results):
        """Test establishing performance baselines."""
        performance_benchmarking.establish_baseline(sample_benchmark_results)

        assert performance_benchmarking.baseline_count == len(sample_benchmark_results)

        for benchmark_type, result in sample_benchmark_results.items():
            baseline = performance_benchmarking._baselines.get(result.operation_name)
            assert baseline is not None
            assert baseline.benchmark_type == benchmark_type
            assert baseline.mean_time == result.mean_time
            assert baseline.throughput == result.throughput

    def test_detect_regressions_no_baseline(self, performance_benchmarking, sample_benchmark_results):
        """Test regression detection when no baseline exists."""
        regressions = performance_benchmarking.detect_regressions(sample_benchmark_results)
        assert len(regressions) == 0

    def test_detect_regressions_with_baseline(self, performance_benchmarking, sample_benchmark_results):
        """Test regression detection with established baseline."""
        # Establish baseline
        performance_benchmarking.establish_baseline(sample_benchmark_results)

        # Create worse results (regression)
        regression_results = {}
        for benchmark_type, result in sample_benchmark_results.items():
            # Create a result that's 20% slower
            regression_result = BenchmarkResult(
                benchmark_type=result.benchmark_type,
                operation_name=result.operation_name,
                iterations=result.iterations,
                start_time=result.start_time,
                end_time=result.end_time,
                mean_time=result.mean_time * 1.2,  # 20% slower
                median_time=result.median_time * 1.2,
                min_time=result.min_time,
                max_time=result.max_time * 1.2,
                p95_time=result.p95_time * 1.2,
                p99_time=result.p99_time * 1.2,
                std_dev=result.std_dev,
                throughput=result.throughput * 0.8,  # Lower throughput
                metadata=result.metadata,
            )
            regression_results[benchmark_type] = regression_result

        regressions = performance_benchmarking.detect_regressions(regression_results)

        # Should detect regressions for both operations (20% > 5% threshold)
        assert len(regressions) == 2

        for regression in regressions:
            assert isinstance(regression, RegressionReport)
            assert regression.regression_percent == pytest.approx(0.2, rel=0.01)
            assert regression.severity == RegressionSeverity.MODERATE  # 20% is moderate
            assert len(regression.recommendations) > 0

    def test_get_performance_summary_empty(self, performance_benchmarking):
        """Test getting performance summary with no data."""
        summary = performance_benchmarking.get_performance_summary()

        assert isinstance(summary, BenchmarkMetrics)
        assert summary.total_benchmarks == 0
        assert summary.successful_benchmarks == 0
        assert summary.failed_benchmarks == 0
        assert summary.total_operations == 0
        assert len(summary.average_performance) == 0
        assert summary.regression_count == 0
        assert summary.last_benchmark_time is None

    def test_export_benchmark_data_json(self, performance_benchmarking, sample_benchmark_results):
        """Test exporting benchmark data as JSON."""
        # Add some data
        performance_benchmarking.establish_baseline(sample_benchmark_results)
        for result in sample_benchmark_results.values():
            performance_benchmarking._benchmark_history.append(result)

        export_data = performance_benchmarking.export_benchmark_data("json")

        assert isinstance(export_data, bytes)

        # Parse JSON to verify structure
        data = json.loads(export_data.decode("utf-8"))
        assert "timestamp" in data
        assert "baselines" in data
        assert "recent_results" in data
        assert "regressions" in data
        assert "summary" in data

        assert len(data["baselines"]) == 2
        assert len(data["recent_results"]) == 2

    def test_export_benchmark_data_csv(self, performance_benchmarking, sample_benchmark_results):
        """Test exporting benchmark data as CSV."""
        # Add some data
        for result in sample_benchmark_results.values():
            performance_benchmarking._benchmark_history.append(result)

        export_data = performance_benchmarking.export_benchmark_data("csv")

        assert isinstance(export_data, bytes)

        # Parse CSV to verify structure
        csv_text = export_data.decode("utf-8")
        lines = csv_text.strip().split("\n")

        assert len(lines) == 3  # Header + 2 data rows
        assert lines[0] == "timestamp,benchmark_type,operation_name,mean_time,throughput,iterations,p95_time"

    def test_regression_severity_determination(self, performance_benchmarking):
        """Test regression severity determination."""
        # Test different regression percentages
        assert performance_benchmarking._determine_regression_severity(0.03) == RegressionSeverity.MINOR
        assert performance_benchmarking._determine_regression_severity(0.20) == RegressionSeverity.MODERATE
        assert performance_benchmarking._determine_regression_severity(0.40) == RegressionSeverity.MAJOR
        assert performance_benchmarking._determine_regression_severity(0.60) == RegressionSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_benchmark_api_request_processing(self, performance_benchmarking):
        """Test API request processing benchmark."""
        result = await performance_benchmarking._benchmark_api_request_processing(5)

        assert result.benchmark_type == BenchmarkType.API_REQUEST
        assert result.operation_name == "api_request_processing"
        assert result.iterations == 5
        assert result.mean_time > 0
        assert result.throughput > 0

    @pytest.mark.asyncio
    async def test_cleanup_old_data(self, performance_benchmarking):
        """Test cleanup of old benchmark data."""
        # Add some old and recent data
        old_time = time.time() - 7200  # 2 hours ago (exceeds 1 hour retention)
        recent_time = time.time() - 1800  # 30 minutes ago

        old_result = BenchmarkResult(
            benchmark_type=BenchmarkType.API_REQUEST,
            operation_name="api_request_processing",
            iterations=10,
            start_time=old_time - 10,
            end_time=old_time,
            mean_time=0.002,
            median_time=0.002,
            min_time=0.001,
            max_time=0.003,
            p95_time=0.0025,
            p99_time=0.0028,
            std_dev=0.0005,
            throughput=100.0,
        )

        recent_result = BenchmarkResult(
            benchmark_type=BenchmarkType.API_REQUEST,
            operation_name="api_request_processing",
            iterations=10,
            start_time=recent_time - 10,
            end_time=recent_time,
            mean_time=0.002,
            median_time=0.002,
            min_time=0.001,
            max_time=0.003,
            p95_time=0.0025,
            p99_time=0.0028,
            std_dev=0.0005,
            throughput=100.0,
        )

        performance_benchmarking._benchmark_history.extend([old_result, recent_result])

        # Run cleanup
        await performance_benchmarking._cleanup_old_data()

        # Verify old data was removed
        assert len(performance_benchmarking._benchmark_history) == 1
        assert performance_benchmarking._benchmark_history[0] == recent_result

    def test_create_benchmark_result(self, performance_benchmarking):
        """Test creating benchmark result from timing data."""
        times = [0.001, 0.002, 0.0015, 0.0025, 0.003]
        start_time = time.time()
        end_time = start_time + 1.0

        result = performance_benchmarking._create_benchmark_result(
            BenchmarkType.API_REQUEST, "test_operation", len(times), start_time, end_time, times
        )

        assert result.benchmark_type == BenchmarkType.API_REQUEST
        assert result.operation_name == "test_operation"
        assert result.iterations == len(times)
        assert result.mean_time == sum(times) / len(times)
        assert result.min_time == min(times)
        assert result.max_time == max(times)
        assert result.throughput > 0

    def test_benchmark_result_properties(self):
        """Test BenchmarkResult properties."""
        start_time = time.time()
        end_time = start_time + 5.0

        result = BenchmarkResult(
            benchmark_type=BenchmarkType.API_REQUEST,
            operation_name="test_operation",
            iterations=100,
            start_time=start_time,
            end_time=end_time,
            mean_time=0.002,
            median_time=0.0018,
            min_time=0.001,
            max_time=0.005,
            p95_time=0.004,
            p99_time=0.0045,
            std_dev=0.0008,
            throughput=500.0,
        )

        assert result.duration == 5.0
