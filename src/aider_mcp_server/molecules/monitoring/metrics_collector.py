"""
Metrics Collector for centralized metrics aggregation and time-series data management.

This module provides comprehensive metrics collection capabilities that aggregate
metrics from multiple sources, store time-series data efficiently, and provide
export interfaces for external monitoring systems.
"""

import asyncio
import json
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from statistics import mean
from typing import Any, Dict, List, Optional, Protocol, Union

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol


class MetricType(Enum):
    """Types of metrics that can be collected."""

    COUNTER = "counter"  # Monotonically increasing values
    GAUGE = "gauge"  # Point-in-time values
    HISTOGRAM = "histogram"  # Distribution of values
    SUMMARY = "summary"  # Statistical summary


class MetricsFormat(Enum):
    """Supported metrics export formats."""

    JSON = "json"
    PROMETHEUS = "prometheus"
    CSV = "csv"
    INFLUXDB = "influxdb"


@dataclass
class MetricValue:
    """Represents a single metric value with metadata."""

    name: str
    value: Union[float, int]
    metric_type: MetricType
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricSeries:
    """Time series of metric values."""

    name: str
    metric_type: MetricType
    values: List[MetricValue] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)

    def add_value(self, value: Union[float, int], timestamp: Optional[float] = None, **kwargs: Any) -> None:
        """Add a new value to the series."""
        if timestamp is None:
            timestamp = time.time()

        metric_value = MetricValue(
            name=self.name,
            value=value,
            metric_type=self.metric_type,
            timestamp=timestamp,
            labels=self.labels,
            metadata=kwargs,
        )
        self.values.append(metric_value)


@dataclass
class MetricsSnapshot:
    """Complete snapshot of all metrics at a point in time."""

    timestamp: float
    metrics: Dict[str, MetricSeries] = field(default_factory=dict)
    system_info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            "timestamp": self.timestamp,
            "system_info": self.system_info,
            "metrics": {
                name: {
                    "name": series.name,
                    "type": series.metric_type.value,
                    "labels": series.labels,
                    "values": [asdict(val) for val in series.values],
                }
                for name, series in self.metrics.items()
            },
        }


@dataclass
class MetricsQuery:
    """Query parameters for metrics retrieval."""

    metric_names: Optional[List[str]] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    labels: Optional[Dict[str, str]] = None
    aggregation: Optional[str] = None  # "avg", "sum", "max", "min", "count"
    interval: Optional[float] = None  # Aggregation interval in seconds


@dataclass
class MetricsResult:
    """Result of a metrics query."""

    metrics: Dict[str, MetricSeries]
    query: MetricsQuery
    result_count: int
    execution_time: float


class MetricsSource(Protocol):
    """Protocol for metrics data sources."""

    async def collect_metrics(self) -> List[MetricValue]:
        """Collect current metrics from this source."""
        ...

    def get_metric_definitions(self) -> Dict[str, Dict[str, Any]]:
        """Get definitions of metrics provided by this source."""
        ...


class MetricsCollector:
    """
    Centralized metrics collection system that aggregates metrics from multiple sources,
    stores time-series data efficiently, and provides export capabilities for external
    monitoring systems.
    """

    def __init__(
        self, application_coordinator: Any, retention_hours: int = 24, collection_interval: float = 30.0
    ) -> None:
        """
        Initialize the metrics collector.

        Args:
            application_coordinator: Reference to the main application coordinator
            retention_hours: Hours to retain metrics data
            collection_interval: Interval between metric collections in seconds
        """
        self._logger: LoggerProtocol = get_logger(__name__)
        self._application_coordinator = application_coordinator
        self._retention_hours = retention_hours
        self._collection_interval = collection_interval

        # Metrics storage
        self._metric_series: Dict[str, MetricSeries] = {}
        self._metrics_sources: Dict[str, MetricsSource] = {}
        self._snapshots: deque[MetricsSnapshot] = deque(maxlen=1000)  # Recent snapshots

        # Metric definitions and metadata
        self._metric_definitions: Dict[str, Dict[str, Any]] = {}
        self._custom_metrics: Dict[str, MetricSeries] = {}

        # Background tasks
        self._collection_task: Optional[asyncio.Task[None]] = None
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._collecting_active = False

        # Configuration
        self._max_series_size = 10000  # Max values per series

        self._lock = asyncio.Lock()
        self._logger.info(f"MetricsCollector initialized with {retention_hours} hour retention")

    async def start_collection(self) -> None:
        """Start the metrics collection system."""
        async with self._lock:
            if self._collecting_active:
                self._logger.warning("Metrics collection is already active")
                return

            self._collecting_active = True

            # Start background collection and cleanup tasks
            self._collection_task = asyncio.create_task(self._collection_loop())
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            self._logger.info(f"Metrics collection started with {self._collection_interval:.1f}s interval")

    async def stop_collection(self) -> None:
        """Stop the metrics collection system."""
        async with self._lock:
            self._collecting_active = False

            # Cancel background tasks
            if self._collection_task:
                self._collection_task.cancel()
                try:
                    await self._collection_task
                except asyncio.CancelledError:
                    pass
                self._collection_task = None

            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
                self._cleanup_task = None

            self._logger.info("Metrics collection stopped")

    async def register_metrics_source(self, source_name: str, source: MetricsSource) -> None:
        """
        Register a metrics data source.

        Args:
            source_name: Unique name for the metrics source
            source: Metrics source implementation
        """
        self._metrics_sources[source_name] = source

        # Register metric definitions from the source
        definitions = source.get_metric_definitions()
        for metric_name, definition in definitions.items():
            self._metric_definitions[f"{source_name}.{metric_name}"] = definition

        self._logger.info(f"Registered metrics source: {source_name} with {len(definitions)} metrics")

    async def unregister_metrics_source(self, source_name: str) -> None:
        """
        Unregister a metrics data source.

        Args:
            source_name: Name of the metrics source to remove
        """
        if source_name in self._metrics_sources:
            del self._metrics_sources[source_name]

            # Remove metric definitions from this source
            keys_to_remove = [key for key in self._metric_definitions.keys() if key.startswith(f"{source_name}.")]
            for key in keys_to_remove:
                del self._metric_definitions[key]

            self._logger.info(f"Unregistered metrics source: {source_name}")

    async def record_metric(
        self,
        name: str,
        value: Union[float, int],
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[Dict[str, str]] = None,
        timestamp: Optional[float] = None,
        **metadata: Any,
    ) -> None:
        """
        Record a custom metric value.

        Args:
            name: Metric name
            value: Metric value
            metric_type: Type of metric
            labels: Optional labels for the metric
            timestamp: Optional timestamp (defaults to current time)
            **metadata: Additional metadata
        """
        if timestamp is None:
            timestamp = time.time()

        if labels is None:
            labels = {}

        # Create metric key including labels for uniqueness
        label_key = "_".join(f"{k}={v}" for k, v in sorted(labels.items()))
        series_key = f"{name}_{label_key}" if label_key else name

        # Get or create metric series
        if series_key not in self._metric_series:
            self._metric_series[series_key] = MetricSeries(name=name, metric_type=metric_type, labels=labels)

        # Add value to series
        self._metric_series[series_key].add_value(value, timestamp, **metadata)

        # Limit series size
        series = self._metric_series[series_key]
        if len(series.values) > self._max_series_size:
            series.values = series.values[-self._max_series_size // 2 :]  # Keep newer half

        self._logger.debug(f"Recorded metric {name} = {value}")

    async def get_metric_series(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[MetricSeries]:
        """
        Get a metric series by name and labels.

        Args:
            name: Metric name
            labels: Optional labels to match

        Returns:
            MetricSeries if found, None otherwise
        """
        if labels is None:
            labels = {}

        label_key = "_".join(f"{k}={v}" for k, v in sorted(labels.items()))
        series_key = f"{name}_{label_key}" if label_key else name

        return self._metric_series.get(series_key)

    async def query_metrics(self, query: MetricsQuery) -> MetricsResult:
        """
        Query metrics based on specified criteria.

        Args:
            query: Query parameters

        Returns:
            MetricsResult containing matching metrics
        """
        start_time = time.time()
        matching_series = {}

        # Filter metrics by name
        series_to_check = self._metric_series
        if query.metric_names:
            series_to_check = {
                key: series
                for key, series in self._metric_series.items()
                if any(series.name == name for name in query.metric_names)
            }

        # Apply filters
        for series_key, series in series_to_check.items():
            # Filter by labels
            if query.labels:
                if not all(series.labels.get(k) == v for k, v in query.labels.items()):
                    continue

            # Filter by time range
            filtered_values = series.values
            if query.start_time or query.end_time:
                filtered_values = [
                    val
                    for val in series.values
                    if (query.start_time is None or val.timestamp >= query.start_time)
                    and (query.end_time is None or val.timestamp <= query.end_time)
                ]

            if filtered_values:
                # Create filtered series
                filtered_series = MetricSeries(name=series.name, metric_type=series.metric_type, labels=series.labels)
                filtered_series.values = filtered_values

                # Apply aggregation if specified
                if query.aggregation and query.interval:
                    filtered_series = await self._aggregate_series(filtered_series, query.aggregation, query.interval)

                matching_series[series_key] = filtered_series

        execution_time = time.time() - start_time
        result_count = sum(len(series.values) for series in matching_series.values())

        return MetricsResult(
            metrics=matching_series, query=query, result_count=result_count, execution_time=execution_time
        )

    async def create_snapshot(self) -> MetricsSnapshot:
        """
        Create a snapshot of all current metrics.

        Returns:
            MetricsSnapshot containing all current metrics
        """
        snapshot = MetricsSnapshot(
            timestamp=time.time(),
            system_info={
                "collector_version": "1.0.0",
                "retention_hours": self._retention_hours,
                "collection_interval": self._collection_interval,
                "total_series": len(self._metric_series),
                "total_sources": len(self._metrics_sources),
            },
        )

        # Copy all metric series
        snapshot.metrics = dict(self._metric_series)

        # Store snapshot
        self._snapshots.append(snapshot)

        return snapshot

    async def export_metrics(self, format_type: MetricsFormat, query: Optional[MetricsQuery] = None) -> bytes:
        """
        Export metrics in the specified format.

        Args:
            format_type: Export format
            query: Optional query to filter metrics

        Returns:
            Exported metrics as bytes
        """
        # Get metrics to export
        if query:
            result = await self.query_metrics(query)
            metrics_to_export = result.metrics
        else:
            metrics_to_export = self._metric_series

        if format_type == MetricsFormat.JSON:
            return await self._export_json(metrics_to_export)
        elif format_type == MetricsFormat.PROMETHEUS:
            return await self._export_prometheus(metrics_to_export)
        elif format_type == MetricsFormat.CSV:
            return await self._export_csv(metrics_to_export)
        elif format_type == MetricsFormat.INFLUXDB:
            return await self._export_influxdb(metrics_to_export)
        else:
            raise ValueError(f"Unsupported export format: {format_type}")

    async def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get a summary of collected metrics.

        Returns:
            Summary statistics about collected metrics
        """
        total_values = sum(len(series.values) for series in self._metric_series.values())

        metric_types: defaultdict[str, int] = defaultdict(int)
        for series in self._metric_series.values():
            metric_types[series.metric_type.value] += 1

        latest_values = {}
        for name, series in self._metric_series.items():
            if series.values:
                latest_values[name] = series.values[-1].value

        return {
            "total_series": len(self._metric_series),
            "total_values": total_values,
            "metric_types": dict(metric_types),
            "sources_count": len(self._metrics_sources),
            "latest_values": latest_values,
            "retention_hours": self._retention_hours,
            "collection_active": self._collecting_active,
        }

    async def _collection_loop(self) -> None:
        """Background task for periodic metrics collection."""
        while self._collecting_active:
            try:
                await self._collect_from_all_sources()
                await asyncio.sleep(self._collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in metrics collection loop: {str(e)}")
                await asyncio.sleep(5.0)  # Brief pause before retry

    async def _cleanup_loop(self) -> None:
        """Background task for data cleanup."""
        while self._collecting_active:
            try:
                await self._cleanup_old_data()
                await asyncio.sleep(3600.0)  # Cleanup every hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in cleanup loop: {str(e)}")
                await asyncio.sleep(300.0)  # Brief pause before retry

    async def _collect_from_all_sources(self) -> None:
        """Collect metrics from all registered sources."""
        for source_name, source in self._metrics_sources.items():
            try:
                metrics = await source.collect_metrics()
                for metric in metrics:
                    await self.record_metric(
                        name=f"{source_name}.{metric.name}",
                        value=metric.value,
                        metric_type=metric.metric_type,
                        labels=metric.labels,
                        timestamp=metric.timestamp,
                        **metric.metadata,
                    )
            except Exception as e:
                self._logger.error(f"Error collecting metrics from source {source_name}: {str(e)}")

    async def _cleanup_old_data(self) -> None:
        """Clean up old metrics data based on retention policy."""
        cutoff_time = time.time() - (self._retention_hours * 3600)

        # Clean up old values in metric series
        for series in self._metric_series.values():
            original_count = len(series.values)
            series.values = [val for val in series.values if val.timestamp >= cutoff_time]
            cleaned_count = original_count - len(series.values)

            if cleaned_count > 0:
                self._logger.debug(f"Cleaned {cleaned_count} old values from series {series.name}")

    async def _aggregate_series(self, series: MetricSeries, aggregation: str, interval: float) -> MetricSeries:
        """
        Aggregate a metric series over time intervals.

        Args:
            series: Original metric series
            aggregation: Aggregation method ("avg", "sum", "max", "min", "count")
            interval: Aggregation interval in seconds

        Returns:
            Aggregated metric series
        """
        if not series.values:
            return series

        # Group values by interval
        intervals = defaultdict(list)
        start_time = series.values[0].timestamp

        for value in series.values:
            interval_key = int((value.timestamp - start_time) // interval)
            intervals[interval_key].append(value)

        # Aggregate each interval
        aggregated_series = MetricSeries(
            name=f"{series.name}_{aggregation}_{interval}s", metric_type=series.metric_type, labels=series.labels
        )

        for interval_key, values in intervals.items():
            interval_timestamp = start_time + (interval_key * interval)
            numeric_values = [val.value for val in values]

            if aggregation == "avg":
                aggregated_value = mean(numeric_values)
            elif aggregation == "sum":
                aggregated_value = sum(numeric_values)
            elif aggregation == "max":
                aggregated_value = max(numeric_values)
            elif aggregation == "min":
                aggregated_value = min(numeric_values)
            elif aggregation == "count":
                aggregated_value = len(numeric_values)
            else:
                raise ValueError(f"Unsupported aggregation: {aggregation}")

            aggregated_series.add_value(aggregated_value, interval_timestamp)

        return aggregated_series

    async def _export_json(self, metrics: Dict[str, MetricSeries]) -> bytes:
        """Export metrics as JSON."""
        export_data: Dict[str, Any] = {"timestamp": time.time(), "metrics": {}}

        for series_key, series in metrics.items():
            export_data["metrics"][series_key] = {
                "name": series.name,
                "type": series.metric_type.value,
                "labels": series.labels,
                "values": [
                    {"timestamp": val.timestamp, "value": val.value, "metadata": val.metadata} for val in series.values
                ],
            }

        return json.dumps(export_data, indent=2).encode("utf-8")

    async def _export_prometheus(self, metrics: Dict[str, MetricSeries]) -> bytes:
        """Export metrics in Prometheus format."""
        lines = []

        for _, series in metrics.items():
            # Prometheus metric name (replace dots with underscores)
            prom_name = series.name.replace(".", "_").replace("-", "_")

            # Add help and type comments
            lines.append(f"# HELP {prom_name} {series.name}")
            lines.append(f"# TYPE {prom_name} {series.metric_type.value}")

            # Add values
            for value in series.values:
                labels_str = ""
                if series.labels:
                    label_pairs = [f'{k}="{v}"' for k, v in series.labels.items()]
                    labels_str = "{" + ",".join(label_pairs) + "}"

                timestamp_ms = int(value.timestamp * 1000)
                lines.append(f"{prom_name}{labels_str} {value.value} {timestamp_ms}")

        return "\n".join(lines).encode("utf-8")

    async def _export_csv(self, metrics: Dict[str, MetricSeries]) -> bytes:
        """Export metrics as CSV."""
        lines = ["timestamp,metric_name,value,labels"]

        for _, series in metrics.items():
            for value in series.values:
                labels_str = json.dumps(series.labels) if series.labels else "{}"
                lines.append(f'{value.timestamp},{series.name},{value.value},"{labels_str}"')

        return "\n".join(lines).encode("utf-8")

    async def _export_influxdb(self, metrics: Dict[str, MetricSeries]) -> bytes:
        """Export metrics in InfluxDB line protocol format."""
        lines = []

        for _, series in metrics.items():
            for value in series.values:
                # InfluxDB line protocol: measurement,tag1=value1,tag2=value2 field1=value1,field2=value2 timestamp
                measurement = series.name.replace(" ", "_")

                tags = ""
                if series.labels:
                    tag_pairs = [f"{k}={v}" for k, v in series.labels.items()]
                    tags = "," + ",".join(tag_pairs)

                timestamp_ns = int(value.timestamp * 1_000_000_000)
                lines.append(f"{measurement}{tags} value={value.value} {timestamp_ns}")

        return "\n".join(lines).encode("utf-8")

    @property
    def is_collecting_active(self) -> bool:
        """Check if metrics collection is currently active."""
        return self._collecting_active

    @property
    def series_count(self) -> int:
        """Get the number of metric series."""
        return len(self._metric_series)

    @property
    def source_count(self) -> int:
        """Get the number of registered metrics sources."""
        return len(self._metrics_sources)
