"""
Legacy configuration system bridge.

This module provides a compatibility layer between the legacy template ConfigurationSystem
and the new atomic design ConfigurationManager, allowing for gradual migration.

This bridge was created during Task 19 - Redistribute Template Directory Content
to preserve functionality while deprecating the templates directory.
"""

import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from aider_mcp_server.atoms.logging.logger import get_logger

from .configuration_manager import ConfigurationManager


class LegacyConfigurationSystem:
    """
    Legacy configuration system compatibility bridge.

    This class provides the same interface as the original template ConfigurationSystem
    but delegates to the new atomic design ConfigurationManager internally.

    .. deprecated::
        This class is deprecated. Use ConfigurationManager directly.
    """

    _instance: Optional["LegacyConfigurationSystem"] = None
    _initialized: bool = False

    def __new__(cls) -> "LegacyConfigurationSystem":
        warnings.warn(
            "LegacyConfigurationSystem is deprecated. Use ConfigurationManager directly.",
            DeprecationWarning,
            stacklevel=2,
        )

        if cls._instance is None:
            cls._instance = super(LegacyConfigurationSystem, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._logger = get_logger("legacy_configuration_system")
        self._config_manager = ConfigurationManager(logger=self._logger)

        # Load default configuration to match legacy behavior
        self._load_legacy_defaults()

        # Load from environment by default
        self.load_from_env()

        self._initialized = True
        self._logger.info("Legacy configuration system initialized (compatibility mode)")

    def _load_legacy_defaults(self) -> None:
        """Load default configuration values that match the legacy system."""
        defaults = {
            "logging.level": "INFO",
            "logging.directory": "logs",
            "logging.format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "logging.verbose": False,
            "transports.sse.enabled": True,
            "transports.sse.host": "localhost",
            "transports.sse.port": 8000,
            "transports.sse.heartbeat_interval": 30,
            "transports.stdio.enabled": True,
            "transports.http_streamable.enabled": True,
            "transports.http_streamable.host": "localhost",
            "transports.http_streamable.port": 8001,
            "application.name": "Aider MCP Server",
            "application.version": "0.1.0",
            "application.max_concurrent_requests": 100,
            "application.request_timeout": 30.0,
            "handlers.max_retries": 3,
            "handlers.retry_delay": 1.0,
        }

        for key, value in defaults.items():
            if not self._config_manager.has(key):
                self._config_manager.set(key, value, priority=0)  # Low priority for defaults

    def load_from_env(self, prefix: str = "AIDER_MCP_") -> None:
        """
        Load configuration from environment variables.

        This method provides the same interface as the legacy system.
        """
        self._config_manager.load_from_environment(prefix)

    def load_from_file(self, file_path: Union[str, Path]) -> None:
        """
        Load configuration from a file.

        This method provides the same interface as the legacy system.
        """
        self._config_manager.load_from_file(file_path, environment_specific=True)

    def get(self, *path: str, default: Any = None) -> Any:
        """
        Get a configuration value at the specified path.

        This method provides the same interface as the legacy system.
        """
        if not path:
            return default

        # Convert path to dot notation
        key = ".".join(path)
        return self._config_manager.get(key, default)

    def set(self, value: Any, *path: str) -> None:
        """
        Set a configuration value at the specified path.

        This method provides the same interface as the legacy system.
        """
        if not path:
            return

        # Convert path to dot notation
        key = ".".join(path)
        self._config_manager.set(key, value, priority=1000)  # High priority for programmatic sets

    def get_all(self) -> Dict[str, Any]:
        """
        Get the complete configuration.

        This method provides the same interface as the legacy system.
        """
        config = self._config_manager.get_all()

        # Convert flat keys back to nested structure for legacy compatibility
        return self._flatten_to_nested(config)

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get an entire configuration section.

        This method provides the same interface as the legacy system.
        """
        return self._config_manager.get_section(section)

    def has(self, *path: str) -> bool:
        """
        Check if a configuration path exists.

        This method provides the same interface as the legacy system.
        """
        if not path:
            return False

        key = ".".join(path)
        return self._config_manager.has(key)

    def reload(self) -> None:
        """
        Reload configuration from environment variables.

        This method provides the same interface as the legacy system.
        """
        # Clear and reload - this is a simplified version
        self._config_manager.load_from_environment("AIDER_MCP_")
        self._logger.info("Configuration reloaded from environment")

    def validate(self) -> List[str]:
        """
        Validate the current configuration.

        This method provides the same interface as the legacy system.
        """
        errors: List[str] = []

        # Validate logging configuration
        log_level = self.get("logging", "level")
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if log_level not in valid_levels:
            errors.append(f"Invalid logging level: {log_level}. Must be one of {valid_levels}")

        # Validate transport ports
        for transport in ["sse", "http_streamable"]:
            if self.get("transports", transport, "enabled"):
                port = self.get("transports", transport, "port")
                if not isinstance(port, int) or port < 1 or port > 65535:
                    errors.append(f"Invalid port for {transport}: {port}. Must be 1-65535")

        # Validate application settings
        timeout = self.get("application", "request_timeout")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            errors.append(f"Invalid request timeout: {timeout}. Must be a positive number")

        max_requests = self.get("application", "max_concurrent_requests")
        if not isinstance(max_requests, int) or max_requests < 1:
            errors.append(f"Invalid max concurrent requests: {max_requests}. Must be positive integer")

        if errors:
            self._logger.warning(f"Configuration validation found {len(errors)} errors")
            for error in errors:
                self._logger.warning(f"Validation error: {error}")
        else:
            self._logger.info("Configuration validation passed")

        return errors

    def get_transport_config(self, transport_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific transport.

        This method provides the same interface as the legacy system.
        """
        return self.get_section(f"transports.{transport_name}")

    def is_transport_enabled(self, transport_name: str) -> bool:
        """
        Check if a specific transport is enabled.

        This method provides the same interface as the legacy system.
        """
        return bool(self.get("transports", transport_name, "enabled", default=False))

    def _flatten_to_nested(self, flat_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Convert flat dot-notation keys to nested dictionary structure."""
        result = {}

        for key, value in flat_dict.items():
            parts = key.split(".")
            current = result

            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            current[parts[-1]] = value

        return result


# Legacy compatibility function
def get_config() -> LegacyConfigurationSystem:
    """
    Get the global configuration instance.

    .. deprecated::
        This function is deprecated. Use ConfigurationManager directly.
    """
    warnings.warn("get_config() is deprecated. Use ConfigurationManager directly.", DeprecationWarning, stacklevel=2)
    return LegacyConfigurationSystem()
