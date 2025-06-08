"""
Configuration molecules for advanced dependency management and configuration handling.

This package provides sophisticated dependency management capabilities including:
- Advanced dependency resolution with graph analysis
- Service locator patterns with multiple lifecycle options
- Centralized configuration management with multi-source support

The modules work together to provide a comprehensive configuration and dependency
management system for the aider-mcp-server.
"""

from typing import Any, Optional

from .configuration_manager import (
    ConfigurationEntry,
    ConfigurationFormat,
    ConfigurationManager,
    ConfigurationSchema,
    ConfigurationSource,
    ConfigurationValidator,
    ConfigurationWatcher,
)
from .dependency_resolver import (
    DependencyGraph,
    DependencyInfo,
    DependencyResolver,
    DependencyType,
)
from .service_locator import (
    IServiceFactory,
    ServiceLifecycle,
    ServiceLocator,
    ServiceRegistration,
    ServiceScope,
)

__all__ = [
    # Dependency Resolution
    "DependencyResolver",
    "DependencyGraph",
    "DependencyInfo",
    "DependencyType",
    # Service Location
    "ServiceLocator",
    "ServiceScope",
    "ServiceLifecycle",
    "ServiceRegistration",
    "IServiceFactory",
    # Configuration Management
    "ConfigurationManager",
    "ConfigurationEntry",
    "ConfigurationSchema",
    "ConfigurationValidator",
    "ConfigurationWatcher",
    "ConfigurationSource",
    "ConfigurationFormat",
]


def create_dependency_resolver(logger: Optional[Any] = None) -> DependencyResolver:
    """
    Create a dependency resolver instance with optional logging.

    Args:
        logger: Optional logger instance

    Returns:
        Configured DependencyResolver instance
    """
    return DependencyResolver(logger=logger)


def create_service_locator(logger: Optional[Any] = None) -> ServiceLocator:
    """
    Create a service locator instance with optional logging.

    Args:
        logger: Optional logger instance

    Returns:
        Configured ServiceLocator instance
    """
    return ServiceLocator(logger=logger)


def create_configuration_manager(logger: Optional[Any] = None) -> ConfigurationManager:
    """
    Create a configuration manager instance with optional logging.

    Args:
        logger: Optional logger instance

    Returns:
        Configured ConfigurationManager instance
    """
    return ConfigurationManager(logger=logger)


def create_complete_configuration_system(
    logger: Optional[Any] = None,
) -> tuple[DependencyResolver, ServiceLocator, ConfigurationManager]:
    """
    Create a complete configuration system with all components.

    Args:
        logger: Optional logger instance

    Returns:
        Tuple of (DependencyResolver, ServiceLocator, ConfigurationManager)
    """
    resolver = create_dependency_resolver(logger)
    locator = create_service_locator(logger)
    manager = create_configuration_manager(logger)

    return resolver, locator, manager
