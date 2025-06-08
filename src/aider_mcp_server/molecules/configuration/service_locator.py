"""
Service locator patterns for the aider-mcp-server.

This module implements the Service Locator pattern with support for lazy loading,
scope management, and service registration with various lifecycle options.
"""

import asyncio
import weakref
from contextlib import AsyncExitStack
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Protocol, Type, TypeVar, cast

from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol

T = TypeVar("T")


class ServiceLifecycle(Enum):
    """Lifecycle management options for services."""

    SINGLETON = auto()  # One instance for the entire application
    TRANSIENT = auto()  # New instance every time
    SCOPED = auto()  # One instance per scope
    LAZY_SINGLETON = auto()  # Singleton created on first access
    WEAK_SINGLETON = auto()  # Singleton with weak reference (can be garbage collected)


@dataclass
class ServiceRegistration:
    """Registration information for a service."""

    service_type: Type[Any]
    implementation_type: Optional[Type[Any]] = None
    factory: Optional[Callable[..., Any]] = None
    instance: Optional[Any] = None
    lifecycle: ServiceLifecycle = ServiceLifecycle.SINGLETON
    scope_id: Optional[str] = None
    tags: Optional[List[str]] = None
    priority: int = 0


class IServiceFactory(Protocol):
    """Protocol for service factories."""

    def create(self, service_type: Type[T]) -> T:
        """Create an instance of the service."""
        ...

    async def create_async(self, service_type: Type[T]) -> T:
        """Create an instance of the service asynchronously."""
        ...


class ServiceScope:
    """Represents a service scope with its own service instances."""

    def __init__(self, scope_id: str, parent: Optional["ServiceScope"] = None):
        self.scope_id = scope_id
        self.parent = parent
        self.instances: Dict[Type[Any], Any] = {}
        self.exit_stack = AsyncExitStack()
        self._is_disposed = False

    async def __aenter__(self) -> "ServiceScope":
        """Enter the async context."""
        await self.exit_stack.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the async context."""
        await self.dispose()

    async def dispose(self) -> None:
        """Dispose of the scope and clean up resources."""
        if self._is_disposed:
            return

        self._is_disposed = True

        # Dispose of all instances in this scope
        for instance in self.instances.values():
            if hasattr(instance, "__aexit__"):
                await self.exit_stack.aclose()
                break

        self.instances.clear()

    def is_disposed(self) -> bool:
        """Check if the scope has been disposed."""
        return self._is_disposed


class ServiceLocator:
    """
    Service locator implementation with advanced features.

    Provides service registration, location, and lifecycle management with support
    for various service scopes, lazy loading, and weak references.
    """

    def __init__(self, logger: Optional[LoggerProtocol] = None):
        self.logger = logger
        self._registrations: Dict[Type[Any], ServiceRegistration] = {}
        self._singletons: Dict[Type[Any], Any] = {}
        self._weak_singletons: weakref.WeakValueDictionary[Type[Any], Any] = weakref.WeakValueDictionary()
        self._scopes: Dict[str, ServiceScope] = {}
        self._current_scope: Optional[ServiceScope] = None
        self._factories: Dict[Type[Any], IServiceFactory] = {}
        self._tags_index: Dict[str, List[Type[Any]]] = {}

    def register_singleton(
        self,
        service_type: Type[T],
        implementation_type: Optional[Type[T]] = None,
        factory: Optional[Callable[..., T]] = None,
        instance: Optional[T] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Register a singleton service.

        Args:
            service_type: The service interface type
            implementation_type: Concrete implementation type
            factory: Factory function to create the service
            instance: Pre-created instance
            tags: Tags for service categorization
        """
        self._register_service(
            service_type, implementation_type, factory, instance, ServiceLifecycle.SINGLETON, tags=tags
        )

    def register_transient(
        self,
        service_type: Type[T],
        implementation_type: Optional[Type[T]] = None,
        factory: Optional[Callable[..., T]] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Register a transient service (new instance each time).

        Args:
            service_type: The service interface type
            implementation_type: Concrete implementation type
            factory: Factory function to create the service
            tags: Tags for service categorization
        """
        self._register_service(service_type, implementation_type, factory, None, ServiceLifecycle.TRANSIENT, tags=tags)

    def register_scoped(
        self,
        service_type: Type[T],
        implementation_type: Optional[Type[T]] = None,
        factory: Optional[Callable[..., T]] = None,
        scope_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Register a scoped service (one instance per scope).

        Args:
            service_type: The service interface type
            implementation_type: Concrete implementation type
            factory: Factory function to create the service
            scope_id: Specific scope ID (uses current scope if None)
            tags: Tags for service categorization
        """
        self._register_service(
            service_type, implementation_type, factory, None, ServiceLifecycle.SCOPED, scope_id=scope_id, tags=tags
        )

    def register_lazy_singleton(
        self,
        service_type: Type[T],
        implementation_type: Optional[Type[T]] = None,
        factory: Optional[Callable[..., T]] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Register a lazy singleton (created on first access).

        Args:
            service_type: The service interface type
            implementation_type: Concrete implementation type
            factory: Factory function to create the service
            tags: Tags for service categorization
        """
        self._register_service(
            service_type, implementation_type, factory, None, ServiceLifecycle.LAZY_SINGLETON, tags=tags
        )

    def register_weak_singleton(
        self,
        service_type: Type[T],
        implementation_type: Optional[Type[T]] = None,
        factory: Optional[Callable[..., T]] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Register a weak singleton (can be garbage collected).

        Args:
            service_type: The service interface type
            implementation_type: Concrete implementation type
            factory: Factory function to create the service
            tags: Tags for service categorization
        """
        self._register_service(
            service_type, implementation_type, factory, None, ServiceLifecycle.WEAK_SINGLETON, tags=tags
        )

    def _register_service(
        self,
        service_type: Type[Any],
        implementation_type: Optional[Type[Any]],
        factory: Optional[Callable[..., Any]],
        instance: Optional[Any],
        lifecycle: ServiceLifecycle,
        scope_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        priority: int = 0,
    ) -> None:
        """Internal method to register a service."""
        # Validate registration parameters
        provided_count = sum(1 for x in [implementation_type, factory, instance] if x is not None)
        if provided_count == 0:
            # Default to using the service_type as implementation_type
            implementation_type = service_type
        elif provided_count > 1:
            raise ValueError("Exactly one of implementation_type, factory, or instance must be provided")

        registration = ServiceRegistration(
            service_type=service_type,
            implementation_type=implementation_type,
            factory=factory,
            instance=instance,
            lifecycle=lifecycle,
            scope_id=scope_id,
            tags=tags or [],
            priority=priority,
        )

        self._registrations[service_type] = registration

        # Update tags index
        if tags:
            for tag in tags:
                if tag not in self._tags_index:
                    self._tags_index[tag] = []
                if service_type not in self._tags_index[tag]:
                    self._tags_index[tag].append(service_type)

        if self.logger:
            self.logger.verbose(f"Registered {lifecycle.name} service: {service_type.__name__}")

    def get_service(self, service_type: Type[T]) -> T:
        """
        Get a service instance.

        Args:
            service_type: The service type to resolve

        Returns:
            Service instance

        Raises:
            ValueError: If the service is not registered or cannot be created
        """
        if service_type not in self._registrations:
            raise ValueError(f"Service type {service_type.__name__} is not registered")

        registration = self._registrations[service_type]

        # Handle different lifecycle patterns
        if registration.lifecycle == ServiceLifecycle.SINGLETON:
            return self._get_singleton(service_type, registration)

        elif registration.lifecycle == ServiceLifecycle.LAZY_SINGLETON:
            return self._get_lazy_singleton(service_type, registration)

        elif registration.lifecycle == ServiceLifecycle.WEAK_SINGLETON:
            return self._get_weak_singleton(service_type, registration)

        elif registration.lifecycle == ServiceLifecycle.TRANSIENT:
            return cast(T, self._create_instance(registration))

        elif registration.lifecycle == ServiceLifecycle.SCOPED:
            return self._get_scoped_instance(service_type, registration)

        else:
            raise ValueError(f"Unsupported lifecycle: {registration.lifecycle}")

    def _get_singleton(self, service_type: Type[T], registration: ServiceRegistration) -> T:
        """Get or create a singleton instance."""
        if service_type in self._singletons:
            return cast(T, self._singletons[service_type])

        instance = self._create_instance(registration)
        self._singletons[service_type] = instance
        return cast(T, instance)

    def _get_lazy_singleton(self, service_type: Type[T], registration: ServiceRegistration) -> T:
        """Get or create a lazy singleton instance."""
        if service_type in self._singletons:
            return cast(T, self._singletons[service_type])

        if self.logger:
            self.logger.verbose(f"Creating lazy singleton: {service_type.__name__}")

        instance = self._create_instance(registration)
        self._singletons[service_type] = instance
        return cast(T, instance)

    def _get_weak_singleton(self, service_type: Type[T], registration: ServiceRegistration) -> T:
        """Get or create a weak singleton instance."""
        if service_type in self._weak_singletons:
            return cast(T, self._weak_singletons[service_type])

        instance = self._create_instance(registration)
        self._weak_singletons[service_type] = instance
        return cast(T, instance)

    def _get_scoped_instance(self, service_type: Type[T], registration: ServiceRegistration) -> T:
        """Get or create a scoped instance."""
        scope = self._get_current_scope(registration.scope_id)

        if service_type in scope.instances:
            return cast(T, scope.instances[service_type])

        instance = self._create_instance(registration)
        scope.instances[service_type] = instance
        return cast(T, instance)

    def _create_instance(self, registration: ServiceRegistration) -> Any:
        """Create a new instance based on registration."""
        if registration.instance is not None:
            return registration.instance

        if registration.factory is not None:
            if asyncio.iscoroutinefunction(registration.factory):
                # Handle async factories
                try:
                    # Check if we're in an event loop
                    asyncio.get_running_loop()
                    # We're in an event loop - need to schedule and wait for the coroutine
                    # This is tricky in a sync context, so we'll use a workaround for testing
                    import concurrent.futures

                    def run_in_thread() -> Any:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            if registration.factory is None:
                                raise ValueError("Factory cannot be None")
                            return new_loop.run_until_complete(registration.factory())
                        finally:
                            new_loop.close()

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_in_thread)
                        return future.result()

                except RuntimeError as e:
                    if "no running event loop" in str(e):
                        # No event loop running, create one
                        return asyncio.run(registration.factory())
                    else:
                        # Re-raise other RuntimeErrors
                        raise
            else:
                return registration.factory()

        if registration.implementation_type is not None:
            # Use registered factory if available
            if registration.service_type in self._factories:
                factory = self._factories[registration.service_type]
                return factory.create(registration.implementation_type)
            else:
                # Create instance directly
                return registration.implementation_type()

        raise ValueError(f"Cannot create instance for {registration.service_type.__name__}")

    def _get_current_scope(self, scope_id: Optional[str] = None) -> ServiceScope:
        """Get the current service scope."""
        if scope_id:
            if scope_id not in self._scopes:
                self._scopes[scope_id] = ServiceScope(scope_id)
            return self._scopes[scope_id]

        if self._current_scope is None:
            # Create default scope
            self._current_scope = ServiceScope("default")
            self._scopes["default"] = self._current_scope

        return self._current_scope

    def create_scope(self, scope_id: str) -> ServiceScope:
        """
        Create a new service scope.

        Args:
            scope_id: Unique identifier for the scope

        Returns:
            New service scope
        """
        if scope_id in self._scopes:
            raise ValueError(f"Scope {scope_id} already exists")

        scope = ServiceScope(scope_id, parent=self._current_scope)
        self._scopes[scope_id] = scope

        if self.logger:
            self.logger.verbose(f"Created service scope: {scope_id}")

        return scope

    def enter_scope(self, scope_id: str) -> ServiceScope:
        """
        Enter a service scope.

        Args:
            scope_id: Scope to enter

        Returns:
            The entered scope
        """
        if scope_id not in self._scopes:
            scope = self.create_scope(scope_id)
        else:
            scope = self._scopes[scope_id]

        self._current_scope = scope

        if self.logger:
            self.logger.verbose(f"Entered service scope: {scope_id}")

        return scope

    def exit_scope(self) -> Optional[ServiceScope]:
        """
        Exit the current scope and return to parent.

        Returns:
            The parent scope, if any
        """
        if self._current_scope and self._current_scope.parent:
            parent = self._current_scope.parent
            self._current_scope = parent

            if self.logger:
                self.logger.verbose(f"Exited to parent scope: {parent.scope_id}")

            return parent

        return None

    def register_factory(self, service_type: Type[T], factory: IServiceFactory) -> None:
        """
        Register a service factory.

        Args:
            service_type: Service type to create
            factory: Factory implementation
        """
        self._factories[service_type] = factory

        if self.logger:
            self.logger.verbose(f"Registered factory for: {service_type.__name__}")

    def is_registered(self, service_type: Type[Any]) -> bool:
        """
        Check if a service type is registered.

        Args:
            service_type: Service type to check

        Returns:
            True if registered
        """
        return service_type in self._registrations

    def get_services_by_tag(self, tag: str) -> List[Any]:
        """
        Get all services with a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of service instances
        """
        if tag not in self._tags_index:
            return []

        services = []
        for service_type in self._tags_index[tag]:
            try:
                service = self.get_service(service_type)
                services.append(service)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to get service {service_type.__name__}: {e}")

        return services

    def get_registration_info(self, service_type: Type[Any]) -> Optional[ServiceRegistration]:
        """
        Get registration information for a service type.

        Args:
            service_type: Service type to query

        Returns:
            Registration information or None if not registered
        """
        return self._registrations.get(service_type)

    def clear_cache(self) -> None:
        """Clear all cached service instances."""
        self._singletons.clear()
        self._weak_singletons.clear()

        for scope in self._scopes.values():
            scope.instances.clear()

        if self.logger:
            self.logger.verbose("Cleared service locator cache")

    async def dispose_all_scopes(self) -> None:
        """Dispose of all service scopes."""
        for scope in self._scopes.values():
            await scope.dispose()

        self._scopes.clear()
        self._current_scope = None

        if self.logger:
            self.logger.verbose("Disposed all service scopes")

    def get_service_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all registered services.

        Returns:
            Dictionary containing service registration summary
        """
        lifecycle_counts: Dict[str, int] = {}
        services_by_lifecycle: Dict[str, List[str]] = {}

        summary = {
            "total_registrations": len(self._registrations),
            "lifecycle_counts": lifecycle_counts,
            "scope_counts": len(self._scopes),
            "tag_counts": len(self._tags_index),
            "services_by_lifecycle": services_by_lifecycle,
            "services_by_tag": dict(self._tags_index),
        }

        # Count by lifecycle
        for registration in self._registrations.values():
            lifecycle_name = registration.lifecycle.name
            if lifecycle_name not in lifecycle_counts:
                lifecycle_counts[lifecycle_name] = 0
                services_by_lifecycle[lifecycle_name] = []

            lifecycle_counts[lifecycle_name] += 1
            services_by_lifecycle[lifecycle_name].append(registration.service_type.__name__)

        return summary
