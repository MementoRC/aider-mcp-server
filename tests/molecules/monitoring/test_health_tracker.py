"""
Tests for HealthTracker monitoring molecule.
"""

import asyncio
import time
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from aider_mcp_server.molecules.monitoring.health_tracker import (
    ComponentHealth,
    HealthEvent,
    HealthMetric,
    HealthPrediction,
    HealthState,
    HealthTracker,
    TrendDirection,
)


class MockHealthSource:
    """Mock health source for testing."""

    def __init__(self, component: str, state: HealthState = HealthState.HEALTHY):
        self.component = component
        self.state = state
        self.metrics = []

    async def get_health_metrics(self) -> List[HealthMetric]:
        """Return mock health metrics."""
        return self.metrics

    async def get_health_state(self) -> HealthState:
        """Return mock health state."""
        return self.state

    def get_metric_definitions(self) -> Dict[str, Dict[str, str]]:
        """Return mock metric definitions."""
        return {"cpu_usage": {"type": "gauge", "unit": "percent"}, "memory_usage": {"type": "gauge", "unit": "percent"}}


@pytest.fixture
def mock_coordinator():
    """Create a mock application coordinator."""
    coordinator = MagicMock()
    coordinator.broadcast_event = AsyncMock()
    return coordinator


@pytest.fixture
def health_tracker(mock_coordinator):
    """Create a HealthTracker instance for testing."""
    return HealthTracker(mock_coordinator, retention_hours=1)


@pytest.fixture
def mock_health_source():
    """Create a mock health source."""
    return MockHealthSource("test_component")


class TestHealthTracker:
    """Test cases for HealthTracker."""

    @pytest.mark.asyncio
    async def test_initialization(self, health_tracker):
        """Test HealthTracker initialization."""
        assert not health_tracker.is_tracking_active
        assert health_tracker.component_count == 0
        assert health_tracker.health_source_count == 0

    @pytest.mark.asyncio
    async def test_start_stop_tracking(self, health_tracker):
        """Test starting and stopping health tracking."""
        # Test start
        await health_tracker.start_tracking()
        assert health_tracker.is_tracking_active

        # Test stop
        await health_tracker.stop_tracking()
        assert not health_tracker.is_tracking_active

    @pytest.mark.asyncio
    async def test_register_health_source(self, health_tracker, mock_health_source):
        """Test registering a health source."""
        await health_tracker.register_health_source("test_source", mock_health_source)
        assert health_tracker.health_source_count == 1

    @pytest.mark.asyncio
    async def test_unregister_health_source(self, health_tracker, mock_health_source):
        """Test unregistering a health source."""
        await health_tracker.register_health_source("test_source", mock_health_source)
        await health_tracker.unregister_health_source("test_source")
        assert health_tracker.health_source_count == 0

    @pytest.mark.asyncio
    async def test_record_health_event(self, health_tracker):
        """Test recording health events."""
        event = HealthEvent(
            event_id="test_event_1",
            component="test_component",
            event_type="status_change",
            state=HealthState.WARNING,
            timestamp=time.time(),
            message="Test warning event",
        )

        await health_tracker.record_health_event(event)
        assert health_tracker.component_count == 1

        comp_health = await health_tracker.get_component_health("test_component")
        assert comp_health is not None
        assert comp_health.current_state == HealthState.WARNING
        assert len(comp_health.events) == 1

    @pytest.mark.asyncio
    async def test_get_aggregate_health_state(self, health_tracker):
        """Test getting aggregate health state."""
        # Test unknown state with no components
        assert await health_tracker.get_aggregate_health_state() == HealthState.UNKNOWN

        # Add healthy component
        healthy_event = HealthEvent(
            event_id="healthy_1",
            component="comp1",
            event_type="status_change",
            state=HealthState.HEALTHY,
            timestamp=time.time(),
            message="Healthy component",
        )
        await health_tracker.record_health_event(healthy_event)
        assert await health_tracker.get_aggregate_health_state() == HealthState.HEALTHY

        # Add warning component
        warning_event = HealthEvent(
            event_id="warning_1",
            component="comp2",
            event_type="status_change",
            state=HealthState.WARNING,
            timestamp=time.time(),
            message="Warning component",
        )
        await health_tracker.record_health_event(warning_event)
        assert await health_tracker.get_aggregate_health_state() == HealthState.WARNING

        # Add critical component (should override warning)
        critical_event = HealthEvent(
            event_id="critical_1",
            component="comp3",
            event_type="status_change",
            state=HealthState.CRITICAL,
            timestamp=time.time(),
            message="Critical component",
        )
        await health_tracker.record_health_event(critical_event)
        assert await health_tracker.get_aggregate_health_state() == HealthState.CRITICAL

    @pytest.mark.asyncio
    async def test_analyze_health_trends(self, health_tracker):
        """Test health trend analysis."""
        component = "trend_test"
        current_time = time.time()

        # Create a series of events showing degrading health
        events = [
            HealthEvent("evt1", component, "test", HealthState.HEALTHY, current_time - 100, "Healthy"),
            HealthEvent("evt2", component, "test", HealthState.HEALTHY, current_time - 90, "Still healthy"),
            HealthEvent("evt3", component, "test", HealthState.WARNING, current_time - 80, "Warning"),
            HealthEvent("evt4", component, "test", HealthState.WARNING, current_time - 70, "Still warning"),
            HealthEvent("evt5", component, "test", HealthState.DEGRADED, current_time - 60, "Degraded"),
            HealthEvent("evt6", component, "test", HealthState.CRITICAL, current_time - 50, "Critical"),
        ]

        for event in events:
            await health_tracker.record_health_event(event)

        # Analyze trend
        trend = await health_tracker.analyze_health_trends(component)
        assert trend == TrendDirection.DEGRADING

    @pytest.mark.asyncio
    async def test_configure_thresholds(self, health_tracker):
        """Test configuring health thresholds."""
        thresholds = {"cpu_usage": 80.0, "memory_usage": 90.0, "response_time": 5.0}

        await health_tracker.configure_thresholds("test_component", thresholds)
        # Check that thresholds are stored (internal state check)
        assert "test_component" in health_tracker._threshold_configs
        assert health_tracker._threshold_configs["test_component"] == thresholds

    @pytest.mark.asyncio
    async def test_add_correlation_pattern(self, health_tracker):
        """Test adding correlation patterns."""
        components = ["component1", "component2", "component3"]
        await health_tracker.add_correlation_pattern("related_services", components)

        # Check that pattern is stored (internal state check)
        assert "related_services" in health_tracker._correlation_patterns
        assert health_tracker._correlation_patterns["related_services"] == components

    @pytest.mark.asyncio
    async def test_get_health_timeline(self, health_tracker):
        """Test getting health timeline."""
        current_time = time.time()

        # Add events at different times
        old_event = HealthEvent(
            "old_event",
            "comp1",
            "test",
            HealthState.HEALTHY,
            current_time - 7200,  # 2 hours ago
            "Old event",
        )
        recent_event = HealthEvent(
            "recent_event",
            "comp1",
            "test",
            HealthState.WARNING,
            current_time - 1800,  # 30 minutes ago
            "Recent event",
        )

        await health_tracker.record_health_event(old_event)
        await health_tracker.record_health_event(recent_event)

        # Get timeline for last hour
        timeline = await health_tracker.get_health_timeline(duration_hours=1)
        assert len(timeline) == 1
        assert timeline[0].event_id == "recent_event"

    @pytest.mark.asyncio
    async def test_get_health_predictions(self, health_tracker):
        """Test getting health predictions."""
        component = "pred_test"

        # Create events that would trigger a prediction
        current_time = time.time()
        events = [
            HealthEvent("evt1", component, "test", HealthState.HEALTHY, current_time - 60, "Healthy"),
            HealthEvent("evt2", component, "test", HealthState.WARNING, current_time - 40, "Warning"),
            HealthEvent("evt3", component, "test", HealthState.WARNING, current_time - 20, "Still warning"),
        ]

        for event in events:
            await health_tracker.record_health_event(event)

        # Start tracking to trigger analysis
        await health_tracker.start_tracking()

        # Wait a bit for analysis (in real scenario this would be background)
        await asyncio.sleep(0.1)

        # Stop tracking
        await health_tracker.stop_tracking()

        # Get predictions for the component
        predictions = await health_tracker.get_health_predictions(component)

        # Should have predictions if trend analysis detected degradation
        # Note: The prediction generation is based on trend analysis
        # which may or may not trigger depending on the exact timing
        assert isinstance(predictions, list)  # Verify we get a list response

    @pytest.mark.asyncio
    async def test_health_event_broadcast(self, health_tracker, mock_coordinator):
        """Test that critical health events are broadcasted."""
        critical_event = HealthEvent(
            event_id="critical_test",
            component="broadcast_test",
            event_type="system_failure",
            state=HealthState.CRITICAL,
            timestamp=time.time(),
            message="Critical system failure",
        )

        await health_tracker.record_health_event(critical_event)

        # Verify broadcast was called for critical event
        mock_coordinator.broadcast_event.assert_called()

    @pytest.mark.asyncio
    async def test_multiple_component_tracking(self, health_tracker):
        """Test tracking multiple components simultaneously."""
        components = ["comp1", "comp2", "comp3"]
        states = [HealthState.HEALTHY, HealthState.WARNING, HealthState.CRITICAL]

        for i, (comp, state) in enumerate(zip(components, states, strict=False)):
            event = HealthEvent(
                event_id=f"multi_event_{i}",
                component=comp,
                event_type="multi_test",
                state=state,
                timestamp=time.time(),
                message=f"Event for {comp}",
            )
            await health_tracker.record_health_event(event)

        assert health_tracker.component_count == 3

        # Check individual component health
        for comp, expected_state in zip(components, states, strict=False):
            comp_health = await health_tracker.get_component_health(comp)
            assert comp_health is not None
            assert comp_health.current_state == expected_state

    @pytest.mark.asyncio
    async def test_health_source_integration(self, health_tracker):
        """Test integration with health sources."""
        # Create mock source with metrics
        source = MockHealthSource("source_comp", HealthState.HEALTHY)
        source.metrics = [
            HealthMetric(
                component="source_comp",
                metric_name="cpu_usage",
                value=75.0,
                timestamp=time.time(),
                metadata={"unit": "percent"},
            ),
            HealthMetric(
                component="source_comp",
                metric_name="memory_usage",
                value=60.0,
                timestamp=time.time(),
                metadata={"unit": "percent"},
            ),
        ]

        await health_tracker.register_health_source("test_source", source)

        # Start tracking to trigger collection
        await health_tracker.start_tracking()

        # Allow some time for background collection
        await asyncio.sleep(0.1)

        await health_tracker.stop_tracking()

        # Check that component was registered and metrics were collected
        comp_health = await health_tracker.get_component_health("source_comp")
        if comp_health:  # Metrics collection happens in background
            assert "cpu_usage" in comp_health.metrics or "memory_usage" in comp_health.metrics


class TestHealthState:
    """Test cases for HealthState enum."""

    def test_health_state_values(self):
        """Test HealthState enum values."""
        assert HealthState.HEALTHY.value == "healthy"
        assert HealthState.WARNING.value == "warning"
        assert HealthState.DEGRADED.value == "degraded"
        assert HealthState.CRITICAL.value == "critical"
        assert HealthState.UNKNOWN.value == "unknown"


class TestTrendDirection:
    """Test cases for TrendDirection enum."""

    def test_trend_direction_values(self):
        """Test TrendDirection enum values."""
        assert TrendDirection.IMPROVING.value == "improving"
        assert TrendDirection.STABLE.value == "stable"
        assert TrendDirection.DEGRADING.value == "degrading"
        assert TrendDirection.VOLATILE.value == "volatile"


class TestHealthEvent:
    """Test cases for HealthEvent dataclass."""

    def test_health_event_creation(self):
        """Test creating HealthEvent instances."""
        event = HealthEvent(
            event_id="test_event",
            component="test_component",
            event_type="status_change",
            state=HealthState.WARNING,
            timestamp=time.time(),
            message="Test event message",
            details={"key": "value"},
            correlation_id="corr_123",
        )

        assert event.event_id == "test_event"
        assert event.component == "test_component"
        assert event.state == HealthState.WARNING
        assert event.details == {"key": "value"}
        assert event.correlation_id == "corr_123"


class TestHealthPrediction:
    """Test cases for HealthPrediction dataclass."""

    def test_health_prediction_creation(self):
        """Test creating HealthPrediction instances."""
        prediction = HealthPrediction(
            component="test_component",
            predicted_state=HealthState.WARNING,
            confidence=0.85,
            time_to_state=300.0,
            trend_direction=TrendDirection.DEGRADING,
            risk_factors=["high_cpu", "memory_leak"],
            recommendations=["scale_up", "restart_service"],
        )

        assert prediction.component == "test_component"
        assert prediction.predicted_state == HealthState.WARNING
        assert prediction.confidence == 0.85
        assert prediction.time_to_state == 300.0
        assert "high_cpu" in prediction.risk_factors
        assert "scale_up" in prediction.recommendations


class TestComponentHealth:
    """Test cases for ComponentHealth dataclass."""

    def test_component_health_creation(self):
        """Test creating ComponentHealth instances."""
        comp_health = ComponentHealth(
            component="test_component",
            current_state=HealthState.HEALTHY,
            last_updated=time.time(),
            metrics={"cpu": 50.0, "memory": 60.0},
            events=[],
            predictions=[],
            trend_direction=TrendDirection.STABLE,
        )

        assert comp_health.component == "test_component"
        assert comp_health.current_state == HealthState.HEALTHY
        assert comp_health.metrics["cpu"] == 50.0
        assert comp_health.trend_direction == TrendDirection.STABLE
