"""
Resource Coordinator for managing resource allocation and cleanup.
Handles session resources, memory cleanup, and resource lifecycle management.
"""

import asyncio
import time
from typing import Any, Dict, Optional, Set

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol


class ResourceCoordinator:
    """
    Manages resource allocation and cleanup across the system.
    Provides centralized resource tracking, session management, and cleanup coordination.
    """

    def __init__(self) -> None:
        """Initialize the resource coordinator."""
        self._logger: LoggerProtocol = get_logger(__name__)
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._active_resources: Dict[str, Any] = {}
        self._temp_files: Set[str] = set()
        self._cleanup_tasks: Dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_interval = 300.0  # 5 minutes
        self._session_timeout = 3600.0  # 1 hour
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._is_running = False
        self._logger.info("ResourceCoordinator initialized.")

    async def initialize(self) -> None:
        """Initialize the resource coordinator and start cleanup tasks."""
        async with self._lock:
            self._logger.info("Initializing ResourceCoordinator...")
            self._is_running = True

            # Start background cleanup task
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            self._logger.info("Resource cleanup task started.")

    async def register_session(self, session_id: str, session_data: Dict[str, Any]) -> None:
        """Register a new session for resource tracking."""
        async with self._lock:
            self._active_sessions[session_id] = {
                "data": session_data,
                "created_at": time.time(),
                "last_activity": time.time(),
                "resources": set(),
            }
            self._logger.debug(f"Session '{session_id}' registered for resource tracking.")

    async def update_session_activity(self, session_id: str) -> None:
        """Update the last activity time for a session."""
        async with self._lock:
            if session_id in self._active_sessions:
                self._active_sessions[session_id]["last_activity"] = time.time()
                self._logger.debug(f"Session '{session_id}' activity updated.")

    async def unregister_session(self, session_id: str) -> None:
        """Unregister a session and clean up its resources."""
        async with self._lock:
            if session_id in self._active_sessions:
                session_info = self._active_sessions[session_id]

                # Clean up session resources
                for resource_id in session_info.get("resources", set()):
                    await self._cleanup_resource(resource_id)

                del self._active_sessions[session_id]
                self._logger.info(f"Session '{session_id}' unregistered and resources cleaned up.")

    async def allocate_resource(
        self, resource_id: str, resource_type: str, resource_data: Any, session_id: Optional[str] = None
    ) -> bool:
        """Allocate a new resource and track it."""
        async with self._lock:
            if resource_id in self._active_resources:
                self._logger.warning(f"Resource '{resource_id}' already allocated.")
                return False

            self._active_resources[resource_id] = {
                "type": resource_type,
                "data": resource_data,
                "allocated_at": time.time(),
                "session_id": session_id,
            }

            # Associate with session if provided
            if session_id and session_id in self._active_sessions:
                self._active_sessions[session_id]["resources"].add(resource_id)

            self._logger.debug(f"Resource '{resource_id}' ({resource_type}) allocated.")
            return True

    async def deallocate_resource(self, resource_id: str) -> bool:
        """Deallocate a resource and clean it up."""
        async with self._lock:
            if resource_id not in self._active_resources:
                self._logger.warning(f"Resource '{resource_id}' not found for deallocation.")
                return False

            resource_info = self._active_resources[resource_id]
            session_id = resource_info.get("session_id")

            # Remove from session if associated
            if session_id and session_id in self._active_sessions:
                self._active_sessions[session_id]["resources"].discard(resource_id)

            # Clean up the resource
            await self._cleanup_resource(resource_id)
            del self._active_resources[resource_id]

            self._logger.debug(f"Resource '{resource_id}' deallocated.")
            return True

    async def track_temp_file(self, file_path: str) -> None:
        """Track a temporary file for cleanup."""
        async with self._lock:
            self._temp_files.add(file_path)
            self._logger.debug(f"Temporary file '{file_path}' tracked for cleanup.")

    async def cleanup_temp_file(self, file_path: str) -> None:
        """Clean up a specific temporary file."""
        async with self._lock:
            if file_path in self._temp_files:
                try:
                    import os

                    if os.path.exists(file_path):
                        os.remove(file_path)
                        self._logger.debug(f"Temporary file '{file_path}' removed.")
                except Exception as e:
                    self._logger.error(f"Error removing temporary file '{file_path}': {e}")
                finally:
                    self._temp_files.discard(file_path)

    async def schedule_cleanup(self, resource_id: str, delay_seconds: float) -> None:
        """Schedule delayed cleanup for a resource."""

        async def delayed_cleanup() -> None:
            await asyncio.sleep(delay_seconds)
            await self.deallocate_resource(resource_id)

        # Cancel existing cleanup task if present
        if resource_id in self._cleanup_tasks:
            self._cleanup_tasks[resource_id].cancel()

        # Schedule new cleanup
        self._cleanup_tasks[resource_id] = asyncio.create_task(delayed_cleanup())
        self._logger.debug(f"Scheduled cleanup for resource '{resource_id}' in {delay_seconds} seconds.")

    async def cancel_scheduled_cleanup(self, resource_id: str) -> None:
        """Cancel scheduled cleanup for a resource."""
        if resource_id in self._cleanup_tasks:
            self._cleanup_tasks[resource_id].cancel()
            del self._cleanup_tasks[resource_id]
            self._logger.debug(f"Cancelled scheduled cleanup for resource '{resource_id}'.")

    async def get_resource_stats(self) -> Dict[str, Any]:
        """Get comprehensive resource statistics."""
        async with self._lock:
            current_time = time.time()

            session_stats = {
                "total_sessions": len(self._active_sessions),
                "active_sessions": sum(
                    1
                    for session in self._active_sessions.values()
                    if current_time - session["last_activity"] < self._session_timeout
                ),
                "expired_sessions": sum(
                    1
                    for session in self._active_sessions.values()
                    if current_time - session["last_activity"] >= self._session_timeout
                ),
            }

            resource_stats: Dict[str, Any] = {
                "total_resources": len(self._active_resources),
                "resources_by_type": {},
                "temp_files": len(self._temp_files),
                "scheduled_cleanups": len(self._cleanup_tasks),
            }

            # Count resources by type
            resources_by_type: Dict[str, int] = {}
            for resource in self._active_resources.values():
                resource_type = resource["type"]
                resources_by_type[resource_type] = resources_by_type.get(resource_type, 0) + 1
            resource_stats["resources_by_type"] = resources_by_type

            return {
                "sessions": session_stats,
                "resources": resource_stats,
                "coordinator_status": {
                    "is_running": self._is_running,
                    "cleanup_interval": self._cleanup_interval,
                    "session_timeout": self._session_timeout,
                },
            }

    async def _cleanup_resource(self, resource_id: str) -> None:
        """Internal method to clean up a specific resource."""
        if resource_id not in self._active_resources:
            return

        resource_info = self._active_resources[resource_id]
        resource_type = resource_info["type"]
        resource_data = resource_info["data"]

        try:
            # Clean up based on resource type
            if resource_type == "file":
                if hasattr(resource_data, "close"):
                    resource_data.close()
            elif resource_type == "connection":
                if hasattr(resource_data, "close"):
                    await resource_data.close()
            elif resource_type == "temp_file":
                await self.cleanup_temp_file(str(resource_data))

            self._logger.debug(f"Resource '{resource_id}' ({resource_type}) cleaned up.")

        except Exception as e:
            self._logger.error(f"Error cleaning up resource '{resource_id}': {e}")

    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup task for expired sessions and resources."""
        while self._is_running:
            try:
                current_time = time.time()

                # Clean up expired sessions
                expired_sessions = []
                async with self._lock:
                    for session_id, session_info in self._active_sessions.items():
                        if current_time - session_info["last_activity"] >= self._session_timeout:
                            expired_sessions.append(session_id)

                for session_id in expired_sessions:
                    await self.unregister_session(session_id)
                    self._logger.info(f"Expired session '{session_id}' cleaned up.")

                # Clean up temporary files
                temp_files_to_cleanup = list(self._temp_files)
                for file_path in temp_files_to_cleanup:
                    await self.cleanup_temp_file(file_path)

                # Clean up completed cleanup tasks
                completed_tasks = [resource_id for resource_id, task in self._cleanup_tasks.items() if task.done()]
                for resource_id in completed_tasks:
                    del self._cleanup_tasks[resource_id]

                self._logger.debug("Periodic cleanup completed.")

            except Exception as e:
                self._logger.error(f"Error during periodic cleanup: {e}")

            await asyncio.sleep(self._cleanup_interval)

    async def shutdown(self) -> None:
        """Shut down the resource coordinator and clean up all resources."""
        async with self._lock:
            self._logger.info("Shutting down ResourceCoordinator...")
            self._is_running = False

            # Cancel cleanup task
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
                self._cleanup_task = None

            # Cancel all scheduled cleanup tasks
            for task in self._cleanup_tasks.values():
                task.cancel()
            self._cleanup_tasks.clear()

            # Clean up all active resources
            resource_ids = list(self._active_resources.keys())
            for resource_id in resource_ids:
                await self._cleanup_resource(resource_id)
            self._active_resources.clear()

            # Clean up all temporary files
            temp_files = list(self._temp_files)
            for file_path in temp_files:
                await self.cleanup_temp_file(file_path)

            # Clear all sessions
            self._active_sessions.clear()

            self._logger.info("ResourceCoordinator shutdown complete.")

    @property
    def is_running(self) -> bool:
        """Check if the resource coordinator is currently running."""
        return self._is_running

    @property
    def active_session_count(self) -> int:
        """Get the number of active sessions."""
        return len(self._active_sessions)

    @property
    def active_resource_count(self) -> int:
        """Get the number of active resources."""
        return len(self._active_resources)

    @property
    def temp_file_count(self) -> int:
        """Get the number of tracked temporary files."""
        return len(self._temp_files)
