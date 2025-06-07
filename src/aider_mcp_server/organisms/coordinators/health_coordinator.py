"""
Health Coordinator for managing system health monitoring and metrics.
Provides centralized health tracking, request monitoring, and client management.
"""

import asyncio
from typing import Any, Dict, Optional

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol
from aider_mcp_server.molecules.monitoring.health_monitor import HealthMonitor, HealthStatus


class HealthCoordinator:
    """
    Manages system health monitoring and metrics collection.
    Provides centralized health tracking for requests, clients, and system status.
    """

    def __init__(self, application_coordinator: Any) -> None:
        """
        Initialize the health coordinator.
        
        Args:
            application_coordinator: Reference to the main application coordinator
        """
        self._logger: LoggerProtocol = get_logger(__name__)
        self._application_coordinator = application_coordinator
        self._health_monitor: Optional[HealthMonitor] = None
        self._lock = asyncio.Lock()
        self._logger.info("HealthCoordinator initialized.")

    async def initialize(self) -> None:
        """Initialize the health monitoring system."""
        async with self._lock:
            self._logger.info("Initializing HealthCoordinator...")
            
            # Initialize health monitoring with default configuration
            self._health_monitor = HealthMonitor(
                self._application_coordinator, 
                metrics_retention_minutes=60, 
                health_check_interval=30.0
            )
            await self._health_monitor.start_monitoring()
            self._logger.info("Health monitoring started.")

    async def get_health_status(self) -> Optional[HealthStatus]:
        """Get comprehensive system health status."""
        if self._health_monitor:
            return await self._health_monitor.get_health_status()
        return None

    async def get_health_metrics_summary(self, minutes_back: int = 30) -> Optional[Dict[str, Any]]:
        """Get health metrics summary for the specified time period."""
        if self._health_monitor:
            return await self._health_monitor.get_metrics_summary(minutes_back)
        return None

    async def record_request_start(self, request_id: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Record the start of a request for health monitoring."""
        if self._health_monitor:
            await self._health_monitor.record_request_start(request_id, context)

    async def record_request_completion(
        self, request_id: str, success: bool, error_type: Optional[str] = None
    ) -> None:
        """Record the completion of a request for health monitoring."""
        if self._health_monitor:
            await self._health_monitor.record_request_completion(request_id, success, error_type)

    async def record_throttling_event(self, request_id: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Record a throttling event for health monitoring."""
        if self._health_monitor:
            await self._health_monitor.record_throttling_event(request_id, context)

    async def register_streaming_client(self, client_id: str, client_info: Dict[str, Any]) -> None:
        """Register a streaming client for health monitoring."""
        if self._health_monitor:
            await self._health_monitor.register_streaming_client(client_id, client_info)

    async def unregister_streaming_client(self, client_id: str) -> None:
        """Unregister a streaming client from health monitoring."""
        if self._health_monitor:
            await self._health_monitor.unregister_streaming_client(client_id)

    async def start_request(
        self,
        request_id: str,
        transport_id: Optional[str] = None,
        operation_name: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Start tracking a request."""
        # Build context from all provided data
        full_context = context or {}
        if transport_id:
            full_context["transport_id"] = transport_id
        if operation_name:
            full_context["operation_name"] = operation_name
        if request_data:
            full_context["request_data"] = request_data
        await self.record_request_start(request_id, full_context)

    async def fail_request(
        self,
        request_id: str,
        operation_name: Optional[str] = None,
        error: Optional[str] = None,
        error_details: Optional[str] = None,
        originating_transport_id: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> None:
        """Mark a request as failed."""
        # Use error or error_type as the error type for health monitoring
        final_error_type = error_type or error or "unknown_error"
        await self.record_request_completion(request_id, success=False, error_type=final_error_type)

    async def shutdown(self) -> None:
        """Shut down the health monitoring system."""
        async with self._lock:
            self._logger.info("Shutting down HealthCoordinator...")
            
            if self._health_monitor:
                await self._health_monitor.stop_monitoring()
                self._health_monitor = None
                self._logger.info("Health monitoring stopped.")
            
            self._logger.info("HealthCoordinator shutdown complete.")

    @property
    def is_monitoring_active(self) -> bool:
        """Check if health monitoring is currently active."""
        return self._health_monitor is not None