"""
Health Tracker for real-time health state aggregation and predictive analysis.

This module provides advanced health tracking capabilities that complement the existing
HealthMonitor by offering real-time health state aggregation, predictive analysis,
and intelligent health event correlation.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from statistics import mean, stdev
from typing import Any, Callable, Dict, List, Optional, Protocol

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.event_types import EventTypes
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol


class HealthState(Enum):
    """Enumeration of possible health states with increasing severity."""

    HEALTHY = "healthy"
    WARNING = "warning"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class TrendDirection(Enum):
    """Direction of health trend analysis."""

    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    VOLATILE = "volatile"


@dataclass
class HealthMetric:
    """Represents a single health metric data point."""

    component: str
    metric_name: str
    value: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthEvent:
    """Represents a health-related event."""

    event_id: str
    component: str
    event_type: str
    state: HealthState
    timestamp: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None


@dataclass
class HealthPrediction:
    """Represents predicted health trends and early warnings."""

    component: str
    predicted_state: HealthState
    confidence: float  # 0.0 to 1.0
    time_to_state: Optional[float]  # seconds until predicted state
    trend_direction: TrendDirection
    risk_factors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class ComponentHealth:
    """Comprehensive health information for a component."""

    component: str
    current_state: HealthState
    last_updated: float
    metrics: Dict[str, float] = field(default_factory=dict)
    events: List[HealthEvent] = field(default_factory=list)
    predictions: List[HealthPrediction] = field(default_factory=list)
    trend_direction: TrendDirection = TrendDirection.STABLE


class HealthSource(Protocol):
    """Protocol for health data sources."""

    async def get_health_metrics(self) -> List[HealthMetric]:
        """Retrieve current health metrics from this source."""
        ...

    async def get_health_state(self) -> HealthState:
        """Get the current health state of this source."""
        ...


class HealthTracker:
    """
    Advanced health tracking system that aggregates health data from multiple sources,
    performs predictive analysis, and provides intelligent health event correlation.
    """

    def __init__(self, application_coordinator: Any, retention_hours: int = 24) -> None:
        """
        Initialize the health tracker.

        Args:
            application_coordinator: Reference to the main application coordinator
            retention_hours: Hours to retain health data for analysis
        """
        self._logger: LoggerProtocol = get_logger(__name__)
        self._application_coordinator = application_coordinator
        self._retention_hours = retention_hours

        # Health data storage
        self._component_health: Dict[str, ComponentHealth] = {}
        self._health_sources: Dict[str, HealthSource] = {}
        self._health_metrics: deque[HealthMetric] = deque(maxlen=10000)  # Recent metrics
        self._health_events: deque[HealthEvent] = deque(maxlen=5000)  # Recent events

        # Prediction and analysis
        self._threshold_configs: Dict[str, Dict[str, float]] = {}
        self._correlation_patterns: Dict[str, List[str]] = {}
        self._prediction_models: Dict[str, Callable[[], Any]] = {}

        # Background tasks
        self._analysis_task: Optional[asyncio.Task[None]] = None
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._monitoring_active = False

        # Configuration
        self._analysis_interval = 30.0  # seconds
        self._prediction_window = 300.0  # 5 minutes prediction window

        self._lock = asyncio.Lock()
        self._logger.info(f"HealthTracker initialized with {retention_hours} hour retention")

    async def start_tracking(self) -> None:
        """Start the health tracking system."""
        async with self._lock:
            if self._monitoring_active:
                self._logger.warning("Health tracking is already active")
                return

            self._monitoring_active = True

            # Start background analysis task
            self._analysis_task = asyncio.create_task(self._analysis_loop())
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            self._logger.info("Health tracking started")

    async def stop_tracking(self) -> None:
        """Stop the health tracking system."""
        async with self._lock:
            self._monitoring_active = False

            # Cancel background tasks
            if self._analysis_task:
                self._analysis_task.cancel()
                try:
                    await self._analysis_task
                except asyncio.CancelledError:
                    pass
                self._analysis_task = None

            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
                self._cleanup_task = None

            self._logger.info("Health tracking stopped")

    async def register_health_source(self, source_name: str, source: HealthSource) -> None:
        """
        Register a health data source.

        Args:
            source_name: Unique name for the health source
            source: Health source implementation
        """
        self._health_sources[source_name] = source
        self._logger.info(f"Registered health source: {source_name}")

    async def unregister_health_source(self, source_name: str) -> None:
        """
        Unregister a health data source.

        Args:
            source_name: Name of the health source to remove
        """
        if source_name in self._health_sources:
            del self._health_sources[source_name]
            self._logger.info(f"Unregistered health source: {source_name}")

    async def configure_thresholds(self, component: str, thresholds: Dict[str, float]) -> None:
        """
        Configure health thresholds for a component.

        Args:
            component: Component name
            thresholds: Dictionary of metric_name -> threshold_value
        """
        self._threshold_configs[component] = thresholds
        self._logger.info(f"Configured thresholds for component: {component}")

    async def add_correlation_pattern(self, pattern_name: str, components: List[str]) -> None:
        """
        Add a correlation pattern between components.

        Args:
            pattern_name: Name of the correlation pattern
            components: List of component names that are correlated
        """
        self._correlation_patterns[pattern_name] = components
        self._logger.info(f"Added correlation pattern '{pattern_name}' for components: {components}")

    async def record_health_event(self, event: HealthEvent) -> None:
        """
        Record a health event.

        Args:
            event: Health event to record
        """
        self._health_events.append(event)

        # Update component health
        if event.component not in self._component_health:
            self._component_health[event.component] = ComponentHealth(
                component=event.component, current_state=event.state, last_updated=event.timestamp
            )

        # Always update the component health with new event
        component_health = self._component_health[event.component]
        component_health.current_state = event.state
        component_health.last_updated = event.timestamp
        component_health.events.append(event)

        # Keep only recent events per component
        if len(component_health.events) > 100:
            component_health.events = component_health.events[-50:]

        # Broadcast health event if significant
        if event.state in [HealthState.CRITICAL, HealthState.DEGRADED]:
            await self._broadcast_health_event(event)

        self._logger.debug(f"Recorded health event for component {event.component}: {event.state.value}")

    async def get_component_health(self, component: str) -> Optional[ComponentHealth]:
        """
        Get comprehensive health information for a component.

        Args:
            component: Component name

        Returns:
            ComponentHealth object or None if component not found
        """
        return self._component_health.get(component)

    async def get_aggregate_health_state(self) -> HealthState:
        """
        Get the aggregate health state across all components.

        Returns:
            Overall system health state
        """
        if not self._component_health:
            return HealthState.UNKNOWN

        states = [comp.current_state for comp in self._component_health.values()]

        # Priority: CRITICAL > DEGRADED > WARNING > HEALTHY
        if any(state == HealthState.CRITICAL for state in states):
            return HealthState.CRITICAL
        elif any(state == HealthState.DEGRADED for state in states):
            return HealthState.DEGRADED
        elif any(state == HealthState.WARNING for state in states):
            return HealthState.WARNING
        elif any(state == HealthState.HEALTHY for state in states):
            return HealthState.HEALTHY
        else:
            return HealthState.UNKNOWN

    async def get_health_predictions(self, component: Optional[str] = None) -> List[HealthPrediction]:
        """
        Get health predictions for components.

        Args:
            component: Specific component name, or None for all components

        Returns:
            List of health predictions
        """
        predictions = []

        if component:
            comp_health = self._component_health.get(component)
            if comp_health:
                predictions.extend(comp_health.predictions)
        else:
            for comp_health in self._component_health.values():
                predictions.extend(comp_health.predictions)

        return predictions

    async def get_health_timeline(self, duration_hours: int = 1) -> List[HealthEvent]:
        """
        Get health events within a time window.

        Args:
            duration_hours: Number of hours to look back

        Returns:
            List of health events within the time window
        """
        cutoff_time = time.time() - (duration_hours * 3600)
        return [event for event in self._health_events if event.timestamp >= cutoff_time]

    async def analyze_health_trends(self, component: str) -> TrendDirection:
        """
        Analyze health trends for a component.

        Args:
            component: Component name

        Returns:
            Trend direction based on recent health data
        """
        comp_health = self._component_health.get(component)
        if not comp_health or len(comp_health.events) < 3:
            return TrendDirection.STABLE

        # Analyze recent events (last 10 events)
        recent_events = comp_health.events[-10:]
        state_scores = {
            HealthState.HEALTHY: 4,
            HealthState.WARNING: 3,
            HealthState.DEGRADED: 2,
            HealthState.CRITICAL: 1,
            HealthState.UNKNOWN: 0,
        }

        scores = [state_scores.get(event.state, 0) for event in recent_events]

        if len(scores) < 3:
            return TrendDirection.STABLE

        # Calculate trend
        first_half = mean(scores[: len(scores) // 2])
        second_half = mean(scores[len(scores) // 2 :])

        diff = second_half - first_half

        # Check volatility
        if len(scores) >= 5:
            try:
                volatility = stdev(scores)
                if volatility > 1.5:  # High volatility threshold
                    return TrendDirection.VOLATILE
            except (ValueError, TypeError, ZeroDivisionError):
                pass  # Handle single value case

        if diff > 0.5:
            return TrendDirection.IMPROVING
        elif diff < -0.5:
            return TrendDirection.DEGRADING
        else:
            return TrendDirection.STABLE

    async def _analysis_loop(self) -> None:
        """Background task for continuous health analysis."""
        while self._monitoring_active:
            try:
                await self._perform_health_analysis()
                await asyncio.sleep(self._analysis_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in health analysis loop: {str(e)}")
                await asyncio.sleep(5.0)  # Brief pause before retry

    async def _cleanup_loop(self) -> None:
        """Background task for data cleanup."""
        while self._monitoring_active:
            try:
                await self._cleanup_old_data()
                await asyncio.sleep(3600.0)  # Cleanup every hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in cleanup loop: {str(e)}")
                await asyncio.sleep(300.0)  # Brief pause before retry

    async def _perform_health_analysis(self) -> None:
        """Perform comprehensive health analysis."""
        try:
            # Collect metrics from all sources
            await self._collect_metrics_from_sources()

            # Update trend analysis for all components
            for component in self._component_health.keys():
                trend = await self.analyze_health_trends(component)
                self._component_health[component].trend_direction = trend

            # Generate predictions
            await self._generate_health_predictions()

            # Check correlation patterns
            await self._analyze_correlations()

        except Exception as e:
            self._logger.error(f"Error during health analysis: {str(e)}")

    async def _collect_metrics_from_sources(self) -> None:
        """Collect health metrics from all registered sources."""
        for source_name, source in self._health_sources.items():
            try:
                metrics = await source.get_health_metrics()
                for metric in metrics:
                    self._health_metrics.append(metric)

                    # Update component metrics
                    component = metric.component
                    if component not in self._component_health:
                        self._component_health[component] = ComponentHealth(
                            component=component, current_state=HealthState.UNKNOWN, last_updated=metric.timestamp
                        )

                    self._component_health[component].metrics[metric.metric_name] = metric.value
                    self._component_health[component].last_updated = metric.timestamp

            except Exception as e:
                self._logger.error(f"Error collecting metrics from source {source_name}: {str(e)}")

    async def _generate_health_predictions(self) -> None:
        """Generate health predictions for all components."""
        for component, comp_health in self._component_health.items():
            try:
                # Simple trend-based prediction
                trend = comp_health.trend_direction
                current_state = comp_health.current_state

                # Generate prediction based on trend
                if trend == TrendDirection.DEGRADING:
                    if current_state == HealthState.HEALTHY:
                        predicted_state = HealthState.WARNING
                        confidence = 0.7
                    elif current_state == HealthState.WARNING:
                        predicted_state = HealthState.DEGRADED
                        confidence = 0.8
                    elif current_state == HealthState.DEGRADED:
                        predicted_state = HealthState.CRITICAL
                        confidence = 0.9
                    else:
                        continue

                    prediction = HealthPrediction(
                        component=component,
                        predicted_state=predicted_state,
                        confidence=confidence,
                        time_to_state=self._prediction_window,
                        trend_direction=trend,
                        risk_factors=["Degrading health trend detected"],
                        recommendations=["Monitor component closely", "Check for resource constraints"],
                    )

                    # Clear old predictions and add new one
                    comp_health.predictions = [prediction]

            except Exception as e:
                self._logger.error(f"Error generating predictions for component {component}: {str(e)}")

    async def _analyze_correlations(self) -> None:
        """Analyze correlation patterns between components."""
        for pattern_name, components in self._correlation_patterns.items():
            try:
                # Check if multiple components in pattern are unhealthy
                unhealthy_components = []
                for component in components:
                    comp_health = self._component_health.get(component)
                    if comp_health and comp_health.current_state in [
                        HealthState.WARNING,
                        HealthState.DEGRADED,
                        HealthState.CRITICAL,
                    ]:
                        unhealthy_components.append(component)

                # If correlation detected, generate correlation event
                if len(unhealthy_components) >= 2:
                    correlation_event = HealthEvent(
                        event_id=f"correlation_{pattern_name}_{int(time.time())}",
                        component="system",
                        event_type="correlation_detected",
                        state=HealthState.WARNING,
                        timestamp=time.time(),
                        message=f"Health correlation detected in pattern '{pattern_name}'",
                        details={
                            "pattern": pattern_name,
                            "affected_components": unhealthy_components,
                            "correlation_strength": len(unhealthy_components) / len(components),
                        },
                    )
                    await self.record_health_event(correlation_event)

            except Exception as e:
                self._logger.error(f"Error analyzing correlation pattern {pattern_name}: {str(e)}")

    async def _cleanup_old_data(self) -> None:
        """Clean up old health data based on retention policy."""
        cutoff_time = time.time() - (self._retention_hours * 3600)

        # Clean up old events in component health
        for comp_health in self._component_health.values():
            comp_health.events = [event for event in comp_health.events if event.timestamp >= cutoff_time]

        self._logger.debug(f"Cleaned up health data older than {self._retention_hours} hours")

    async def _broadcast_health_event(self, event: HealthEvent) -> None:
        """
        Broadcast significant health events through the application coordinator.

        Args:
            event: Health event to broadcast
        """
        try:
            if self._application_coordinator and hasattr(self._application_coordinator, "broadcast_event"):
                event_data = {
                    "event_id": event.event_id,
                    "component": event.component,
                    "state": event.state.value,
                    "message": event.message,
                    "timestamp": event.timestamp,
                    "details": event.details,
                }

                await self._application_coordinator.broadcast_event(EventTypes.STATUS, event_data)

        except Exception as e:
            self._logger.error(f"Error broadcasting health event: {str(e)}")

    @property
    def is_tracking_active(self) -> bool:
        """Check if health tracking is currently active."""
        return self._monitoring_active

    @property
    def component_count(self) -> int:
        """Get the number of tracked components."""
        return len(self._component_health)

    @property
    def health_source_count(self) -> int:
        """Get the number of registered health sources."""
        return len(self._health_sources)
