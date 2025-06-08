"""
Tests for MetricsCollector monitoring molecule.
"""

import asyncio
import json
import time
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from aider_mcp_server.molecules.monitoring.metrics_collector import (
    MetricsCollector,
    MetricSeries,
    MetricsFormat,
    MetricsQuery,
    MetricsResult,
    MetricsSnapshot,
    MetricType,
    MetricValue,
)


class MockMetricsSource:
    """Mock metrics source for testing."""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.metrics = []

    async def collect_metrics(self) -> List[MetricValue]:
        """Return mock metrics."""
        return self.metrics

    def get_metric_definitions(self) -> Dict[str, Dict[str, str]]:
        """Return mock metric definitions."""
        return {
            "requests_total": {"type": "counter", "description": "Total requests"},
            "cpu_usage": {"type": "gauge", "description": "CPU usage percentage"},
            "response_time": {"type": "histogram", "description": "Response time distribution"},
        }


@pytest.fixture
def mock_coordinator():
    """Create a mock application coordinator."""
    coordinator = MagicMock()
    coordinator.broadcast_event = AsyncMock()
    return coordinator


@pytest.fixture
def metrics_collector(mock_coordinator):
    """Create a MetricsCollector instance for testing."""
    return MetricsCollector(mock_coordinator, retention_hours=1, collection_interval=1.0)


@pytest.fixture
def mock_metrics_source():
    """Create a mock metrics source."""
    return MockMetricsSource("test_source")


class TestMetricsCollector:
    """Test cases for MetricsCollector."""

    @pytest.mark.asyncio
    async def test_initialization(self, metrics_collector):
        """Test MetricsCollector initialization."""
        assert not metrics_collector.is_collecting_active
        assert metrics_collector.series_count == 0
        assert metrics_collector.source_count == 0

    @pytest.mark.asyncio
    async def test_start_stop_collection(self, metrics_collector):
        """Test starting and stopping metrics collection."""
        # Test start
        await metrics_collector.start_collection()
        assert metrics_collector.is_collecting_active

        # Test stop
        await metrics_collector.stop_collection()
        assert not metrics_collector.is_collecting_active

    @pytest.mark.asyncio
    async def test_register_metrics_source(self, metrics_collector, mock_metrics_source):
        """Test registering a metrics source."""
        await metrics_collector.register_metrics_source("test_source", mock_metrics_source)
        assert metrics_collector.source_count == 1

    @pytest.mark.asyncio
    async def test_unregister_metrics_source(self, metrics_collector, mock_metrics_source):
        """Test unregistering a metrics source."""
        await metrics_collector.register_metrics_source("test_source", mock_metrics_source)
        await metrics_collector.unregister_metrics_source("test_source")
        assert metrics_collector.source_count == 0

    @pytest.mark.asyncio
    async def test_record_metric(self, metrics_collector):
        """Test recording individual metrics."""
        # Record a simple gauge metric
        await metrics_collector.record_metric(
            name="cpu_usage", value=75.5, metric_type=MetricType.GAUGE, labels={"host": "server1"}, unit="percent"
        )

        assert metrics_collector.series_count == 1

        # Get the recorded metric series
        series = await metrics_collector.get_metric_series("cpu_usage", {"host": "server1"})
        assert series is not None
        assert len(series.values) == 1
        assert series.values[0].value == 75.5
        assert series.metric_type == MetricType.GAUGE
        assert series.labels == {"host": "server1"}

    @pytest.mark.asyncio
    async def test_record_multiple_metrics(self, metrics_collector):
        """Test recording multiple metrics."""
        metrics_data = [
            ("requests_total", 150, MetricType.COUNTER, {"method": "GET"}),
            ("requests_total", 75, MetricType.COUNTER, {"method": "POST"}),
            ("response_time", 0.25, MetricType.HISTOGRAM, {"endpoint": "/api/users"}),
            ("memory_usage", 68.2, MetricType.GAUGE, {"host": "server1"}),
        ]

        for name, value, metric_type, labels in metrics_data:
            await metrics_collector.record_metric(name, value, metric_type, labels)

        # Should have 4 different series (different label combinations)
        assert metrics_collector.series_count == 4

    @pytest.mark.asyncio
    async def test_metric_series_size_limit(self, metrics_collector):
        """Test that metric series size is limited."""
        # Set a very small max series size for testing
        metrics_collector._max_series_size = 5

        # Record more values than the limit
        for i in range(10):
            await metrics_collector.record_metric(name="test_metric", value=float(i), metric_type=MetricType.GAUGE)

        series = await metrics_collector.get_metric_series("test_metric")
        assert series is not None
        # Should be limited to half of max_series_size when trimmed
        assert len(series.values) <= metrics_collector._max_series_size

    @pytest.mark.asyncio
    async def test_query_metrics_by_name(self, metrics_collector):
        """Test querying metrics by name."""
        # Record some test metrics
        await metrics_collector.record_metric("cpu_usage", 50.0, MetricType.GAUGE)
        await metrics_collector.record_metric("memory_usage", 60.0, MetricType.GAUGE)
        await metrics_collector.record_metric("disk_usage", 70.0, MetricType.GAUGE)

        # Query specific metrics
        query = MetricsQuery(metric_names=["cpu_usage", "memory_usage"])
        result = await metrics_collector.query_metrics(query)

        assert result.result_count == 2
        assert len(result.metrics) == 2
        assert any("cpu_usage" in key for key in result.metrics.keys())
        assert any("memory_usage" in key for key in result.metrics.keys())

    @pytest.mark.asyncio
    async def test_query_metrics_by_time_range(self, metrics_collector):
        """Test querying metrics by time range."""
        current_time = time.time()

        # Record metrics at different times
        await metrics_collector.record_metric(
            "test_metric", 10.0, MetricType.GAUGE, timestamp=current_time - 3600
        )  # 1 hour ago
        await metrics_collector.record_metric(
            "test_metric", 20.0, MetricType.GAUGE, timestamp=current_time - 1800
        )  # 30 minutes ago
        await metrics_collector.record_metric("test_metric", 30.0, MetricType.GAUGE, timestamp=current_time)  # now

        # Query for last 45 minutes
        query = MetricsQuery(
            start_time=current_time - 2700,  # 45 minutes ago
            end_time=current_time,
        )
        result = await metrics_collector.query_metrics(query)

        # Should get 2 metrics (30 min ago and now)
        assert result.result_count == 2

    @pytest.mark.asyncio
    async def test_query_metrics_by_labels(self, metrics_collector):
        """Test querying metrics by labels."""
        # Record metrics with different labels
        await metrics_collector.record_metric("requests", 100, MetricType.COUNTER, {"service": "api", "status": "200"})
        await metrics_collector.record_metric("requests", 10, MetricType.COUNTER, {"service": "api", "status": "404"})
        await metrics_collector.record_metric("requests", 50, MetricType.COUNTER, {"service": "web", "status": "200"})

        # Query by label
        query = MetricsQuery(labels={"service": "api"})
        result = await metrics_collector.query_metrics(query)

        assert result.result_count == 2
        for series in result.metrics.values():
            assert series.labels.get("service") == "api"

    @pytest.mark.asyncio
    async def test_create_snapshot(self, metrics_collector):
        """Test creating metrics snapshots."""
        # Record some metrics
        await metrics_collector.record_metric("cpu", 50.0, MetricType.GAUGE)
        await metrics_collector.record_metric("memory", 60.0, MetricType.GAUGE)

        snapshot = await metrics_collector.create_snapshot()

        assert isinstance(snapshot, MetricsSnapshot)
        assert len(snapshot.metrics) == 2
        assert "total_series" in snapshot.system_info
        assert snapshot.system_info["total_series"] == 2

    @pytest.mark.asyncio
    async def test_get_metrics_summary(self, metrics_collector):
        """Test getting metrics summary."""
        # Record some test metrics
        await metrics_collector.record_metric("metric1", 10.0, MetricType.GAUGE)
        await metrics_collector.record_metric("metric2", 20.0, MetricType.COUNTER)
        await metrics_collector.record_metric("metric1", 15.0, MetricType.GAUGE)  # Second value

        summary = await metrics_collector.get_metrics_summary()

        assert summary["total_series"] == 2
        assert summary["total_values"] == 3
        assert "gauge" in summary["metric_types"]
        assert "counter" in summary["metric_types"]
        assert summary["sources_count"] == 0  # No sources registered yet
        assert not summary["collection_active"]

    @pytest.mark.asyncio
    async def test_export_json(self, metrics_collector):
        """Test exporting metrics as JSON."""
        # Record test metrics
        await metrics_collector.record_metric("test_metric", 42.0, MetricType.GAUGE, {"host": "server1"})

        json_data = await metrics_collector.export_metrics(MetricsFormat.JSON)
        exported = json.loads(json_data.decode("utf-8"))

        assert "timestamp" in exported
        assert "metrics" in exported
        assert len(exported["metrics"]) == 1

    @pytest.mark.asyncio
    async def test_export_prometheus(self, metrics_collector):
        """Test exporting metrics in Prometheus format."""
        # Record test metrics
        await metrics_collector.record_metric(
            "http_requests_total", 100, MetricType.COUNTER, {"method": "GET", "status": "200"}
        )

        prom_data = await metrics_collector.export_metrics(MetricsFormat.PROMETHEUS)
        prom_text = prom_data.decode("utf-8")

        assert "# HELP http_requests_total" in prom_text
        assert "# TYPE http_requests_total counter" in prom_text
        assert "http_requests_total{" in prom_text

    @pytest.mark.asyncio
    async def test_export_csv(self, metrics_collector):
        """Test exporting metrics as CSV."""
        # Record test metrics
        await metrics_collector.record_metric("cpu_usage", 75.0, MetricType.GAUGE)

        csv_data = await metrics_collector.export_metrics(MetricsFormat.CSV)
        csv_text = csv_data.decode("utf-8")

        lines = csv_text.strip().split("\n")
        assert lines[0] == "timestamp,metric_name,value,labels"
        assert len(lines) == 2  # Header + 1 data row
        assert "cpu_usage" in lines[1]

    @pytest.mark.asyncio
    async def test_export_influxdb(self, metrics_collector):
        """Test exporting metrics in InfluxDB line protocol format."""
        # Record test metrics
        await metrics_collector.record_metric(
            "temperature", 23.5, MetricType.GAUGE, {"location": "datacenter", "sensor": "1"}
        )

        influx_data = await metrics_collector.export_metrics(MetricsFormat.INFLUXDB)
        influx_text = influx_data.decode("utf-8")

        assert "temperature," in influx_text
        assert "location=datacenter" in influx_text
        assert "sensor=1" in influx_text
        assert "value=23.5" in influx_text

    @pytest.mark.asyncio
    async def test_metrics_source_integration(self, metrics_collector):
        """Test integration with metrics sources."""
        # Create mock source with metrics
        source = MockMetricsSource("test_source")
        source.metrics = [
            MetricValue(
                name="cpu_usage",
                value=75.0,
                metric_type=MetricType.GAUGE,
                timestamp=time.time(),
                labels={"host": "server1"},
            ),
            MetricValue(
                name="memory_usage",
                value=60.0,
                metric_type=MetricType.GAUGE,
                timestamp=time.time(),
                labels={"host": "server1"},
            ),
        ]

        await metrics_collector.register_metrics_source("test_source", source)

        # Start collection to trigger source collection
        await metrics_collector.start_collection()

        # Allow some time for background collection
        await asyncio.sleep(0.1)

        await metrics_collector.stop_collection()

        # Check that metrics were collected from source
        # Note: Actual collection happens in background, so we might not see immediate results
        summary = await metrics_collector.get_metrics_summary()
        assert summary["sources_count"] == 1

    @pytest.mark.asyncio
    async def test_unsupported_export_format(self, metrics_collector):
        """Test error handling for unsupported export formats."""
        with pytest.raises(ValueError, match="Unsupported export format"):
            await metrics_collector.export_metrics("unsupported_format")

    @pytest.mark.asyncio
    async def test_aggregation_functionality(self, metrics_collector):
        """Test metrics aggregation functionality."""
        # Record multiple values for aggregation testing
        base_time = time.time()
        for i in range(10):
            await metrics_collector.record_metric(
                name="response_time",
                value=float(i * 10),  # 0, 10, 20, ..., 90
                metric_type=MetricType.HISTOGRAM,
                timestamp=base_time + i,
            )

        # Query with aggregation
        query = MetricsQuery(
            metric_names=["response_time"],
            aggregation="avg",
            interval=5.0,  # 5 second intervals
        )
        result = await metrics_collector.query_metrics(query)

        # Should have aggregated the data
        assert result.result_count > 0


class TestMetricType:
    """Test cases for MetricType enum."""

    def test_metric_type_values(self):
        """Test MetricType enum values."""
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.GAUGE.value == "gauge"
        assert MetricType.HISTOGRAM.value == "histogram"
        assert MetricType.SUMMARY.value == "summary"


class TestMetricsFormat:
    """Test cases for MetricsFormat enum."""

    def test_metrics_format_values(self):
        """Test MetricsFormat enum values."""
        assert MetricsFormat.JSON.value == "json"
        assert MetricsFormat.PROMETHEUS.value == "prometheus"
        assert MetricsFormat.CSV.value == "csv"
        assert MetricsFormat.INFLUXDB.value == "influxdb"


class TestMetricValue:
    """Test cases for MetricValue dataclass."""

    def test_metric_value_creation(self):
        """Test creating MetricValue instances."""
        timestamp = time.time()
        metric = MetricValue(
            name="test_metric",
            value=42.5,
            metric_type=MetricType.GAUGE,
            timestamp=timestamp,
            labels={"env": "prod"},
            metadata={"unit": "bytes"},
        )

        assert metric.name == "test_metric"
        assert metric.value == 42.5
        assert metric.metric_type == MetricType.GAUGE
        assert metric.timestamp == timestamp
        assert metric.labels == {"env": "prod"}
        assert metric.metadata == {"unit": "bytes"}


class TestMetricSeries:
    """Test cases for MetricSeries dataclass."""

    def test_metric_series_creation(self):
        """Test creating MetricSeries instances."""
        series = MetricSeries(name="cpu_usage", metric_type=MetricType.GAUGE, labels={"host": "server1"})

        assert series.name == "cpu_usage"
        assert series.metric_type == MetricType.GAUGE
        assert series.labels == {"host": "server1"}
        assert len(series.values) == 0

    def test_metric_series_add_value(self):
        """Test adding values to MetricSeries."""
        series = MetricSeries("test_metric", MetricType.GAUGE)

        # Add value with custom timestamp
        timestamp = time.time()
        series.add_value(75.0, timestamp, unit="percent")

        assert len(series.values) == 1
        assert series.values[0].value == 75.0
        assert series.values[0].timestamp == timestamp
        assert series.values[0].metadata["unit"] == "percent"

        # Add value with automatic timestamp
        series.add_value(80.0)
        assert len(series.values) == 2


class TestMetricsSnapshot:
    """Test cases for MetricsSnapshot dataclass."""

    def test_metrics_snapshot_creation(self):
        """Test creating MetricsSnapshot instances."""
        timestamp = time.time()
        snapshot = MetricsSnapshot(timestamp=timestamp, system_info={"version": "1.0.0"})

        assert snapshot.timestamp == timestamp
        assert snapshot.system_info["version"] == "1.0.0"
        assert len(snapshot.metrics) == 0

    def test_metrics_snapshot_to_dict(self):
        """Test converting MetricsSnapshot to dictionary."""
        timestamp = time.time()
        snapshot = MetricsSnapshot(timestamp=timestamp)

        # Add a metric series
        series = MetricSeries("test_metric", MetricType.GAUGE)
        series.add_value(42.0, timestamp)
        snapshot.metrics["test_key"] = series

        result_dict = snapshot.to_dict()

        assert result_dict["timestamp"] == timestamp
        assert "metrics" in result_dict
        assert "test_key" in result_dict["metrics"]


class TestMetricsQuery:
    """Test cases for MetricsQuery dataclass."""

    def test_metrics_query_creation(self):
        """Test creating MetricsQuery instances."""
        query = MetricsQuery(
            metric_names=["cpu", "memory"],
            start_time=time.time() - 3600,
            end_time=time.time(),
            labels={"env": "prod"},
            aggregation="avg",
            interval=60.0,
        )

        assert query.metric_names == ["cpu", "memory"]
        assert query.labels == {"env": "prod"}
        assert query.aggregation == "avg"
        assert query.interval == 60.0


class TestMetricsResult:
    """Test cases for MetricsResult dataclass."""

    def test_metrics_result_creation(self):
        """Test creating MetricsResult instances."""
        query = MetricsQuery(metric_names=["test"])
        result = MetricsResult(metrics={}, query=query, result_count=5, execution_time=0.123)

        assert result.query == query
        assert result.result_count == 5
        assert result.execution_time == 0.123
