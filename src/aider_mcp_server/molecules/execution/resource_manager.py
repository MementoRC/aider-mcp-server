"""
Resource Manager module for resource allocation and cleanup management.
Provides comprehensive resource lifecycle management with monitoring and constraints.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol

T = TypeVar("T")


class ResourceType(Enum):
    """Enumeration of resource types for classification."""

    MEMORY = "memory"
    FILE = "file"
    NETWORK = "network"
    PROCESS = "process"
    TEMPORARY = "temporary"
    DATABASE = "database"
    LOCK = "lock"
    CUSTOM = "custom"


class ResourceState(Enum):
    """Enumeration of resource states."""

    ALLOCATED = "allocated"
    IN_USE = "in_use"
    IDLE = "idle"
    RELEASING = "releasing"
    RELEASED = "released"
    ERROR = "error"


class Resource:
    """Represents a managed resource with lifecycle tracking."""

    def __init__(
        self,
        resource_id: str,
        resource_type: ResourceType,
        resource_object: Any,
        cleanup_func: Optional[Callable[[Any], None]] = None,
        async_cleanup_func: Optional[Callable[[Any], Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.resource_id = resource_id
        self.resource_type = resource_type
        self.resource_object = resource_object
        self.cleanup_func = cleanup_func
        self.async_cleanup_func = async_cleanup_func
        self.metadata = metadata or {}

        self.state = ResourceState.ALLOCATED
        self.allocated_at = time.time()
        self.last_accessed = time.time()
        self.access_count = 0
        self.cleanup_attempts = 0
        self.max_cleanup_attempts = 3

    def access(self) -> Any:
        """Access the resource and update access tracking."""
        self.last_accessed = time.time()
        self.access_count += 1
        if self.state in (ResourceState.ALLOCATED, ResourceState.IDLE):
            self.state = ResourceState.IN_USE
        return self.resource_object

    def mark_idle(self) -> None:
        """Mark the resource as idle."""
        if self.state == ResourceState.IN_USE:
            self.state = ResourceState.IDLE

    def get_age(self) -> float:
        """Get the age of the resource in seconds."""
        return time.time() - self.allocated_at

    def get_idle_time(self) -> float:
        """Get the time since last access in seconds."""
        return time.time() - self.last_accessed

    def to_dict(self) -> Dict[str, Any]:
        """Convert resource to dictionary representation."""
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type.value,
            "state": self.state.value,
            "allocated_at": self.allocated_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "age": self.get_age(),
            "idle_time": self.get_idle_time(),
            "cleanup_attempts": self.cleanup_attempts,
            "metadata": self.metadata.copy(),
        }


class ResourceConstraints:
    """Defines constraints for resource allocation."""

    def __init__(
        self,
        max_resources: Optional[int] = None,
        max_memory_mb: Optional[float] = None,
        max_idle_time: Optional[float] = None,
        max_age: Optional[float] = None,
        max_access_count: Optional[int] = None,
    ) -> None:
        self.max_resources = max_resources
        self.max_memory_mb = max_memory_mb
        self.max_idle_time = max_idle_time
        self.max_age = max_age
        self.max_access_count = max_access_count


class ResourceAllocator(ABC):
    """Abstract base class for resource allocation strategies."""

    @abstractmethod
    def allocate(self, resource_id: str, *args: Any, **kwargs: Any) -> Any:
        """Allocate a new resource."""
        pass

    @abstractmethod
    def can_allocate(self, resources: Dict[str, Resource], constraints: ResourceConstraints) -> bool:
        """Check if a new resource can be allocated."""
        pass


class SimpleResourceAllocator(ResourceAllocator):
    """Simple resource allocator that creates objects directly."""

    def __init__(self, factory_func: Callable[..., Any]) -> None:
        self.factory_func = factory_func

    def allocate(self, resource_id: str, *args: Any, **kwargs: Any) -> Any:
        """Allocate a resource using the factory function."""
        return self.factory_func(*args, **kwargs)

    def can_allocate(self, resources: Dict[str, Resource], constraints: ResourceConstraints) -> bool:
        """Check allocation constraints."""
        if constraints.max_resources is not None:
            if len(resources) >= constraints.max_resources:
                return False
        return True


class PooledResourceAllocator(ResourceAllocator):
    """Resource allocator that maintains a pool of reusable resources."""

    def __init__(
        self,
        factory_func: Callable[..., Any],
        reset_func: Optional[Callable[[Any], None]] = None,
        pool_size: int = 10,
    ) -> None:
        self.factory_func = factory_func
        self.reset_func = reset_func
        self.pool_size = pool_size
        self._pool: List[Any] = []

    def allocate(self, resource_id: str, *args: Any, **kwargs: Any) -> Any:
        """Allocate a resource from the pool or create a new one."""
        if self._pool:
            resource_object = self._pool.pop()
            if self.reset_func:
                self.reset_func(resource_object)
            return resource_object
        else:
            return self.factory_func(*args, **kwargs)

    def can_allocate(self, resources: Dict[str, Resource], constraints: ResourceConstraints) -> bool:
        """Check allocation constraints."""
        if constraints.max_resources is not None:
            if len(resources) >= constraints.max_resources:
                return False
        return True

    def return_to_pool(self, resource_object: Any) -> None:
        """Return a resource to the pool for reuse."""
        if len(self._pool) < self.pool_size:
            self._pool.append(resource_object)


class ResourceManager:
    """
    Manages resource allocation, tracking, and cleanup with comprehensive monitoring.

    Provides resource lifecycle management with constraints, cleanup automation,
    and detailed metrics collection.
    """

    def __init__(
        self,
        name: str = "default",
        constraints: Optional[ResourceConstraints] = None,
        cleanup_interval: float = 60.0,
        logger_name: Optional[str] = None,
    ) -> None:
        """
        Initialize the ResourceManager.

        Args:
            name: Name identifier for this resource manager
            constraints: Resource allocation constraints
            cleanup_interval: Interval for automatic cleanup in seconds
            logger_name: Custom logger name
        """
        self.name = name
        self.constraints = constraints or ResourceConstraints()
        self.cleanup_interval = cleanup_interval
        self._logger: LoggerProtocol = get_logger(logger_name or __name__)

        # Resource tracking
        self._resources: Dict[str, Resource] = {}
        self._allocators: Dict[ResourceType, ResourceAllocator] = {}
        self._cleanup_callbacks: List[Callable[[Resource], None]] = []

        # Cleanup automation
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._cleanup_running = False

        # Metrics
        self._allocation_count = 0
        self._cleanup_count = 0
        self._failed_allocations = 0
        self._failed_cleanups = 0

        self._logger.info(f"ResourceManager '{name}' initialized")

    def register_allocator(self, resource_type: ResourceType, allocator: ResourceAllocator) -> None:
        """Register a resource allocator for a specific resource type."""
        self._allocators[resource_type] = allocator
        self._logger.debug(f"Registered allocator for {resource_type.value} resources")

    def add_cleanup_callback(self, callback: Callable[[Resource], None]) -> None:
        """Add a callback to be called during resource cleanup."""
        self._cleanup_callbacks.append(callback)

    def remove_cleanup_callback(self, callback: Callable[[Resource], None]) -> None:
        """Remove a cleanup callback."""
        if callback in self._cleanup_callbacks:
            self._cleanup_callbacks.remove(callback)

    def allocate_resource(
        self,
        resource_id: str,
        resource_type: ResourceType,
        factory_func: Optional[Callable[..., Any]] = None,
        cleanup_func: Optional[Callable[[Any], None]] = None,
        async_cleanup_func: Optional[Callable[[Any], Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Optional[Any]:
        """
        Allocate a new resource.

        Args:
            resource_id: Unique identifier for the resource
            resource_type: Type of resource being allocated
            factory_func: Function to create the resource (optional if allocator registered)
            cleanup_func: Function to clean up the resource
            async_cleanup_func: Async function to clean up the resource
            metadata: Additional metadata for the resource
            *args: Arguments to pass to the factory function
            **kwargs: Keyword arguments to pass to the factory function

        Returns:
            The allocated resource object, or None if allocation failed
        """
        if resource_id in self._resources:
            self._logger.warning(f"Resource '{resource_id}' already exists")
            return self._resources[resource_id].access()

        # Check constraints
        if not self._can_allocate():
            self._logger.warning("Resource allocation denied by constraints")
            self._failed_allocations += 1
            return None

        try:
            # Determine how to create the resource
            if resource_type in self._allocators:
                resource_object = self._allocators[resource_type].allocate(resource_id, *args, **kwargs)
            elif factory_func:
                resource_object = factory_func(*args, **kwargs)
            else:
                raise ValueError(f"No allocator or factory function for {resource_type.value}")

            # Create resource wrapper
            resource = Resource(
                resource_id=resource_id,
                resource_type=resource_type,
                resource_object=resource_object,
                cleanup_func=cleanup_func,
                async_cleanup_func=async_cleanup_func,
                metadata=metadata,
            )

            self._resources[resource_id] = resource
            self._allocation_count += 1

            self._logger.info(f"Allocated {resource_type.value} resource: {resource_id}")
            return resource_object

        except Exception as e:
            self._logger.error(f"Failed to allocate resource '{resource_id}': {e}")
            self._failed_allocations += 1
            return None

    def get_resource(self, resource_id: str) -> Optional[Any]:
        """Get an existing resource by ID."""
        if resource_id in self._resources:
            return self._resources[resource_id].access()
        return None

    def release_resource(self, resource_id: str) -> bool:
        """Release a specific resource."""
        if resource_id not in self._resources:
            self._logger.warning(f"Cannot release unknown resource: {resource_id}")
            return False

        resource = self._resources[resource_id]
        return self._cleanup_resource(resource)

    def mark_resource_idle(self, resource_id: str) -> None:
        """Mark a resource as idle (not actively in use)."""
        if resource_id in self._resources:
            self._resources[resource_id].mark_idle()

    async def start_cleanup_automation(self) -> None:
        """Start the automatic cleanup task."""
        if self._cleanup_task is not None:
            self._logger.warning("Cleanup automation already running")
            return

        self._cleanup_running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._logger.info("Started automatic resource cleanup")

    async def stop_cleanup_automation(self) -> None:
        """Stop the automatic cleanup task."""
        self._cleanup_running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        self._logger.info("Stopped automatic resource cleanup")

    async def cleanup_idle_resources(self) -> int:
        """Clean up idle resources based on constraints."""
        cleaned_count = 0
        resources_to_cleanup = []

        current_time = time.time()

        for resource in self._resources.values():
            should_cleanup = False

            # Check idle time constraint
            if (
                self.constraints.max_idle_time is not None
                and resource.state == ResourceState.IDLE
                and current_time - resource.last_accessed > self.constraints.max_idle_time
            ):
                should_cleanup = True

            # Check age constraint
            if self.constraints.max_age is not None and current_time - resource.allocated_at > self.constraints.max_age:
                should_cleanup = True

            # Check access count constraint
            if (
                self.constraints.max_access_count is not None
                and resource.access_count > self.constraints.max_access_count
            ):
                should_cleanup = True

            if should_cleanup:
                resources_to_cleanup.append(resource)

        # Clean up identified resources
        for resource in resources_to_cleanup:
            if self._cleanup_resource(resource):
                cleaned_count += 1

        if cleaned_count > 0:
            self._logger.info(f"Cleaned up {cleaned_count} idle resources")

        return cleaned_count

    async def cleanup_all_resources(self) -> int:
        """Clean up all managed resources."""
        cleaned_count = 0
        resources_to_cleanup = list(self._resources.values())

        for resource in resources_to_cleanup:
            if self._cleanup_resource(resource):
                cleaned_count += 1

        self._logger.info(f"Cleaned up {cleaned_count} resources during shutdown")
        return cleaned_count

    def _can_allocate(self) -> bool:
        """Check if a new resource can be allocated based on constraints."""
        # Check resource count constraint
        if self.constraints.max_resources is not None and len(self._resources) >= self.constraints.max_resources:
            return False

        # Check allocator-specific constraints
        for _resource_type, allocator in self._allocators.items():
            if not allocator.can_allocate(self._resources, self.constraints):
                return False

        return True

    def _cleanup_resource(self, resource: Resource) -> bool:
        """Clean up a single resource."""
        if resource.state == ResourceState.RELEASING:
            return False  # Already being cleaned up

        resource.state = ResourceState.RELEASING

        try:
            # Call cleanup callbacks
            for callback in self._cleanup_callbacks:
                try:
                    callback(resource)
                except Exception as e:
                    self._logger.error(f"Cleanup callback error for {resource.resource_id}: {e}")

            # Call resource-specific cleanup
            if resource.async_cleanup_func:
                # Schedule async cleanup
                asyncio.create_task(self._async_cleanup_resource(resource))
                return True
            elif resource.cleanup_func:
                resource.cleanup_func(resource.resource_object)

            # Remove from tracking
            if resource.resource_id in self._resources:
                del self._resources[resource.resource_id]

            resource.state = ResourceState.RELEASED
            self._cleanup_count += 1

            self._logger.debug(f"Cleaned up resource: {resource.resource_id}")
            return True

        except Exception as e:
            resource.state = ResourceState.ERROR
            resource.cleanup_attempts += 1
            self._failed_cleanups += 1

            self._logger.error(f"Failed to clean up resource '{resource.resource_id}': {e}")

            # Remove from tracking if max attempts reached
            if resource.cleanup_attempts >= resource.max_cleanup_attempts:
                if resource.resource_id in self._resources:
                    del self._resources[resource.resource_id]
                self._logger.warning(f"Removed problematic resource after {resource.cleanup_attempts} attempts")

            return False

    async def _async_cleanup_resource(self, resource: Resource) -> None:
        """Perform async cleanup of a resource."""
        try:
            if resource.async_cleanup_func:
                await resource.async_cleanup_func(resource.resource_object)

            # Remove from tracking
            if resource.resource_id in self._resources:
                del self._resources[resource.resource_id]

            resource.state = ResourceState.RELEASED
            self._cleanup_count += 1

            self._logger.debug(f"Async cleaned up resource: {resource.resource_id}")

        except Exception as e:
            resource.state = ResourceState.ERROR
            resource.cleanup_attempts += 1
            self._failed_cleanups += 1

            self._logger.error(f"Failed to async clean up resource '{resource.resource_id}': {e}")

            # Remove from tracking if max attempts reached
            if resource.cleanup_attempts >= resource.max_cleanup_attempts:
                if resource.resource_id in self._resources:
                    del self._resources[resource.resource_id]

    async def _cleanup_loop(self) -> None:
        """Main cleanup loop for automatic resource management."""
        while self._cleanup_running:
            try:
                await self.cleanup_idle_resources()
                await asyncio.sleep(self.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(self.cleanup_interval)

    def get_resource_stats(self) -> Dict[str, Any]:
        """Get comprehensive resource statistics."""
        stats_by_type = {}
        stats_by_state = {}

        for resource in self._resources.values():
            # Count by type
            type_name = resource.resource_type.value
            if type_name not in stats_by_type:
                stats_by_type[type_name] = 0
            stats_by_type[type_name] += 1

            # Count by state
            state_name = resource.state.value
            if state_name not in stats_by_state:
                stats_by_state[state_name] = 0
            stats_by_state[state_name] += 1

        return {
            "manager_name": self.name,
            "total_resources": len(self._resources),
            "resources_by_type": stats_by_type,
            "resources_by_state": stats_by_state,
            "allocation_count": self._allocation_count,
            "cleanup_count": self._cleanup_count,
            "failed_allocations": self._failed_allocations,
            "failed_cleanups": self._failed_cleanups,
            "cleanup_automation_running": self._cleanup_running,
            "constraints": {
                "max_resources": self.constraints.max_resources,
                "max_memory_mb": self.constraints.max_memory_mb,
                "max_idle_time": self.constraints.max_idle_time,
                "max_age": self.constraints.max_age,
                "max_access_count": self.constraints.max_access_count,
            },
        }

    def get_resource_details(self) -> List[Dict[str, Any]]:
        """Get detailed information about all managed resources."""
        return [resource.to_dict() for resource in self._resources.values()]

    async def __aenter__(self) -> "ResourceManager":
        """Async context manager entry."""
        await self.start_cleanup_automation()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop_cleanup_automation()
        await self.cleanup_all_resources()


# Global resource manager registry
_resource_managers: Dict[str, ResourceManager] = {}


def get_resource_manager(name: str = "default") -> ResourceManager:
    """Get or create a resource manager by name."""
    if name not in _resource_managers:
        _resource_managers[name] = ResourceManager(name)
    return _resource_managers[name]


def register_resource_manager(name: str, manager: ResourceManager) -> None:
    """Register a resource manager globally."""
    _resource_managers[name] = manager


async def cleanup_all_managers() -> None:
    """Clean up all registered resource managers."""
    for manager in _resource_managers.values():
        await manager.cleanup_all_resources()
        await manager.stop_cleanup_automation()


# Convenience decorators and functions
def managed_resource(
    resource_type: ResourceType,
    cleanup_func: Optional[Callable[[Any], None]] = None,
    manager_name: str = "default",
) -> Callable[[Callable[..., T]], Callable[..., Optional[T]]]:
    """Decorator to automatically manage resource lifecycle."""

    def decorator(factory_func: Callable[..., T]) -> Callable[..., Optional[T]]:
        def wrapper(*args: Any, **kwargs: Any) -> Optional[T]:
            manager = get_resource_manager(manager_name)
            resource_id = f"{factory_func.__name__}_{id(args)}_{id(kwargs)}"
            return manager.allocate_resource(
                resource_id=resource_id,
                resource_type=resource_type,
                factory_func=lambda: factory_func(*args, **kwargs),
                cleanup_func=cleanup_func,
            )

        return wrapper

    return decorator
