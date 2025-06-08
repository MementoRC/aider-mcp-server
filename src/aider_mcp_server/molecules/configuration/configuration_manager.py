"""
Configuration manager for centralized configuration management.

This module provides advanced configuration management capabilities including
multi-source configuration aggregation, validation, hot-reload, and hierarchical
configuration with environment-specific overrides.
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union, cast

from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol

T = TypeVar("T")


class ConfigurationSource(Enum):
    """Types of configuration sources."""

    ENVIRONMENT = auto()
    FILE = auto()
    COMMAND_LINE = auto()
    DEFAULT = auto()
    REMOTE = auto()
    OVERRIDE = auto()


class ConfigurationFormat(Enum):
    """Supported configuration file formats."""

    JSON = auto()
    YAML = auto()
    TOML = auto()
    INI = auto()
    PROPERTIES = auto()


@dataclass
class ConfigurationEntry:
    """Represents a configuration entry with metadata."""

    key: str
    value: Any
    source: ConfigurationSource
    source_path: Optional[str] = None
    priority: int = 0
    last_modified: Optional[datetime] = None
    is_sensitive: bool = False
    validator: Optional[Callable[[Any], bool]] = None
    description: Optional[str] = None
    default_value: Optional[Any] = None


@dataclass
class ConfigurationSchema:
    """Schema definition for configuration validation."""

    key: str
    required: bool = False
    data_type: type = str
    default_value: Optional[Any] = None
    validator: Optional[Callable[[Any], bool]] = None
    description: Optional[str] = None
    sensitive: bool = False
    choices: Optional[List[Any]] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None


class ConfigurationValidator:
    """Validates configuration values against schemas."""

    def __init__(self) -> None:
        self.schemas: Dict[str, ConfigurationSchema] = {}

    def register_schema(self, schema: ConfigurationSchema) -> None:
        """Register a configuration schema."""
        self.schemas[schema.key] = schema

    def _validate_type_conversion(self, key: str, value: Any, schema: ConfigurationSchema) -> tuple[Any, List[str]]:
        """Validate and convert value type."""
        errors: List[str] = []

        if isinstance(value, schema.data_type):
            return value, errors

        try:
            # Try to convert
            if schema.data_type is bool:
                if isinstance(value, str):
                    value = value.lower() in ("true", "yes", "1", "on")
                else:
                    value = bool(value)
            elif schema.data_type is int:
                value = int(value)
            elif schema.data_type is float:
                value = float(value)
            elif schema.data_type is str:
                value = str(value)
        except (ValueError, TypeError):
            errors.append(f"Value for '{key}' must be of type {schema.data_type.__name__}")

        return value, errors

    def _validate_constraints(self, key: str, value: Any, schema: ConfigurationSchema) -> List[str]:
        """Validate value constraints (choices, range, custom)."""
        errors = []

        # Choices validation
        if schema.choices and value not in schema.choices:
            errors.append(f"Value for '{key}' must be one of {schema.choices}")

        # Range validation
        if schema.min_value is not None and value < schema.min_value:
            errors.append(f"Value for '{key}' must be >= {schema.min_value}")

        if schema.max_value is not None and value > schema.max_value:
            errors.append(f"Value for '{key}' must be <= {schema.max_value}")

        # Custom validator
        if schema.validator and not schema.validator(value):
            errors.append(f"Custom validation failed for '{key}'")

        return errors

    def validate_entry(self, key: str, value: Any) -> List[str]:
        """
        Validate a configuration entry.

        Args:
            key: Configuration key
            value: Value to validate

        Returns:
            List of validation error messages
        """
        if key not in self.schemas:
            return []  # No schema, no validation

        schema = self.schemas[key]

        # Type validation and conversion
        value, type_errors = self._validate_type_conversion(key, value, schema)
        if type_errors:
            return type_errors

        # Constraint validation
        return self._validate_constraints(key, value, schema)

    def validate_all(self, configuration: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Validate entire configuration.

        Args:
            configuration: Configuration dictionary

        Returns:
            Dictionary mapping keys to validation errors
        """
        all_errors = {}

        # Check required keys
        for key, schema in self.schemas.items():
            if schema.required and key not in configuration:
                all_errors[key] = [f"Required configuration key '{key}' is missing"]

        # Validate existing keys
        for key, value in configuration.items():
            errors = self.validate_entry(key, value)
            if errors:
                all_errors[key] = errors

        return all_errors


class ConfigurationWatcher:
    """Watches configuration files for changes and triggers reloads."""

    def __init__(self, callback: Callable[[str], None], logger: Optional[LoggerProtocol] = None):
        self.callback = callback
        self.logger = logger
        self._watched_files: Set[str] = set()
        self._file_mtimes: Dict[str, float] = {}
        self._watch_task: Optional[asyncio.Task[None]] = None
        self._running = False

    def add_file(self, file_path: str) -> None:
        """Add a file to watch."""
        if os.path.exists(file_path):
            self._watched_files.add(file_path)
            self._file_mtimes[file_path] = os.path.getmtime(file_path)

            if self.logger:
                self.logger.verbose(f"Watching configuration file: {file_path}")

    def remove_file(self, file_path: str) -> None:
        """Remove a file from watching."""
        self._watched_files.discard(file_path)
        self._file_mtimes.pop(file_path, None)

    async def start_watching(self, interval: float = 1.0) -> None:
        """Start watching for file changes."""
        if self._running:
            return

        self._running = True
        self._watch_task = asyncio.create_task(self._watch_loop(interval))

        if self.logger:
            self.logger.verbose(f"Started configuration file watching (interval: {interval}s)")

    async def stop_watching(self) -> None:
        """Stop watching for file changes."""
        self._running = False
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        if self.logger:
            self.logger.verbose("Stopped configuration file watching")

    async def _check_file_changes(self, file_path: str) -> None:
        """Check if a file has changed and handle the change."""
        if os.path.exists(file_path):
            current_mtime = os.path.getmtime(file_path)
            last_mtime = self._file_mtimes.get(file_path, 0)

            if current_mtime > last_mtime:
                self._file_mtimes[file_path] = current_mtime

                if self.logger:
                    self.logger.info(f"Configuration file changed: {file_path}")

                try:
                    self.callback(file_path)
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"Error in configuration change callback: {e}")
        else:
            # File was deleted
            if self.logger:
                self.logger.warning(f"Watched configuration file deleted: {file_path}")
            self.remove_file(file_path)

    async def _watch_loop(self, interval: float) -> None:
        """Main watching loop."""
        while self._running:
            try:
                for file_path in list(self._watched_files):
                    await self._check_file_changes(file_path)

                await asyncio.sleep(interval)

            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error in configuration watcher: {e}")
                await asyncio.sleep(interval)


class ConfigurationManager:
    """
    Advanced configuration manager with multi-source support and hot-reload.

    Supports loading configuration from multiple sources with proper precedence,
    validation, hot-reload capabilities, and environment-specific overrides.
    """

    def __init__(self, logger: Optional[LoggerProtocol] = None):
        self.logger = logger
        self._entries: Dict[str, ConfigurationEntry] = {}
        self._sources: List[str] = []
        self._validator = ConfigurationValidator()
        self._watcher: Optional[ConfigurationWatcher] = None
        self._change_callbacks: List[Callable[[str, Any, Any], None]] = []
        self._environments: Set[str] = {"development", "staging", "production"}
        self._current_environment = "development"
        self._frozen = False

        # Default configuration
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Load default configuration values."""
        defaults = {
            "logging.level": "INFO",
            "logging.directory": "logs",
            "logging.format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "logging.verbose": False,
            "application.name": "Aider MCP Server",
            "application.version": "1.0.0",
            "application.max_concurrent_requests": 100,
            "application.request_timeout": 30.0,
            "transports.sse.enabled": True,
            "transports.sse.host": "localhost",
            "transports.sse.port": 8000,
            "transports.stdio.enabled": True,
            "transports.http_streamable.enabled": True,
            "transports.http_streamable.host": "localhost",
            "transports.http_streamable.port": 8001,
            "handlers.max_retries": 3,
            "handlers.retry_delay": 1.0,
        }

        for key, value in defaults.items():
            self._set_entry(key, value, ConfigurationSource.DEFAULT, description=f"Default value for {key}")

    def set_environment(self, environment: str) -> None:
        """
        Set the current environment.

        Args:
            environment: Environment name (development, staging, production, etc.)
        """
        if environment not in self._environments:
            self._environments.add(environment)

        old_env = self._current_environment
        self._current_environment = environment

        if self.logger:
            self.logger.info(f"Changed environment from {old_env} to {environment}")

        # Reload configuration for new environment
        self._reload_environment_specific()

    def add_environment(self, environment: str) -> None:
        """Add a new environment."""
        self._environments.add(environment)

    def freeze(self) -> None:
        """Freeze configuration to prevent further changes."""
        self._frozen = True
        if self.logger:
            self.logger.info("Configuration frozen - no further changes allowed")

    def unfreeze(self) -> None:
        """Unfreeze configuration to allow changes."""
        self._frozen = False
        if self.logger:
            self.logger.info("Configuration unfrozen - changes allowed")

    def load_from_environment(self, prefix: str = "AIDER_MCP_") -> None:
        """
        Load configuration from environment variables.

        Args:
            prefix: Prefix for environment variables
        """
        if self._frozen:
            raise RuntimeError("Configuration is frozen")

        loaded_count = 0

        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix) :].lower().replace("_", ".")
                self._set_entry(
                    config_key, value, ConfigurationSource.ENVIRONMENT, source_path=f"env:{key}", priority=100
                )
                loaded_count += 1

        if self.logger:
            self.logger.info(f"Loaded {loaded_count} configuration entries from environment")

    def load_from_file(
        self,
        file_path: Union[str, Path],
        format_type: Optional[ConfigurationFormat] = None,
        environment_specific: bool = False,
    ) -> None:
        """
        Load configuration from a file.

        Args:
            file_path: Path to configuration file
            format_type: File format (auto-detected if None)
            environment_specific: Whether to load environment-specific overrides
        """
        if self._frozen:
            raise RuntimeError("Configuration is frozen")

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        # Auto-detect format
        if format_type is None:
            format_type = self._detect_format(file_path)

        # Load the configuration
        config_data = self._load_file_content(file_path, format_type)

        # Flatten and store configuration
        flattened = self._flatten_dict(config_data)
        source_path = str(file_path)

        for key, value in flattened.items():
            self._set_entry(key, value, ConfigurationSource.FILE, source_path=source_path, priority=200)

        # Add to watched files if watcher is active
        if self._watcher:
            self._watcher.add_file(source_path)

        # Load environment-specific overrides
        if environment_specific:
            self._load_environment_specific_file(file_path, format_type)

        if self.logger:
            self.logger.info(f"Loaded configuration from file: {file_path}")

    def _load_environment_specific_file(self, base_path: Path, format_type: ConfigurationFormat) -> None:
        """Load environment-specific configuration overrides."""
        env_file = base_path.parent / f"{base_path.stem}.{self._current_environment}{base_path.suffix}"

        if env_file.exists():
            self.load_from_file(env_file, format_type, environment_specific=False)
            if self.logger:
                self.logger.info(f"Loaded environment-specific config: {env_file}")

    def _reload_environment_specific(self) -> None:
        """Reload all environment-specific configurations."""
        # This would typically reload all previously loaded files with environment-specific logic
        pass

    def _detect_format(self, file_path: Path) -> ConfigurationFormat:
        """Auto-detect configuration file format."""
        suffix = file_path.suffix.lower()

        if suffix in [".json"]:
            return ConfigurationFormat.JSON
        elif suffix in [".yaml", ".yml"]:
            return ConfigurationFormat.YAML
        elif suffix in [".toml"]:
            return ConfigurationFormat.TOML
        elif suffix in [".ini", ".cfg"]:
            return ConfigurationFormat.INI
        elif suffix in [".properties"]:
            return ConfigurationFormat.PROPERTIES
        else:
            # Default to JSON
            return ConfigurationFormat.JSON

    def _load_json_content(self, f: Any) -> Dict[str, Any]:
        """Load JSON configuration content."""
        return cast(Dict[str, Any], json.load(f))

    def _load_yaml_content(self, f: Any) -> Dict[str, Any]:
        """Load YAML configuration content."""
        try:
            import yaml  # type: ignore[import-untyped]

            return cast(Dict[str, Any], yaml.safe_load(f))
        except ImportError as e:
            raise ImportError("PyYAML is required for YAML configuration files") from e

    def _load_toml_content(self, file_path: Path) -> Dict[str, Any]:
        """Load TOML configuration content."""
        try:
            import tomllib

            with open(file_path, "rb") as bf:
                return tomllib.load(bf)
        except ImportError:
            try:
                import toml  # type: ignore[import-untyped]

                with open(file_path, "r", encoding="utf-8") as tf:
                    return cast(Dict[str, Any], toml.load(tf))
            except ImportError as e:
                raise ImportError("tomllib or toml is required for TOML configuration files") from e

    def _load_ini_content(self, f: Any) -> Dict[str, Any]:
        """Load INI configuration content."""
        import configparser

        config = configparser.ConfigParser()
        config.read_file(f)
        result = {}
        for section_name in config.sections():
            for key, value in config.items(section_name):
                result[f"{section_name}.{key}"] = value
        return result

    def _load_properties_content(self, f: Any) -> Dict[str, Any]:
        """Load properties configuration content."""
        result = {}
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    result[key.strip()] = value.strip()
        return result

    def _load_file_content(self, file_path: Path, format_type: ConfigurationFormat) -> Dict[str, Any]:
        """Load content from a configuration file."""
        if format_type == ConfigurationFormat.TOML:
            return self._load_toml_content(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            if format_type == ConfigurationFormat.JSON:
                return self._load_json_content(f)
            elif format_type == ConfigurationFormat.YAML:
                return self._load_yaml_content(f)
            elif format_type == ConfigurationFormat.INI:
                return self._load_ini_content(f)
            elif format_type == ConfigurationFormat.PROPERTIES:
                return self._load_properties_content(f)
            else:
                raise ValueError(f"Unsupported configuration format: {format_type}")

    def _flatten_dict(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """Flatten a nested dictionary using dot notation."""
        result = {}

        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                result.update(self._flatten_dict(value, full_key))
            else:
                result[full_key] = value

        return result

    def _set_entry(
        self,
        key: str,
        value: Any,
        source: ConfigurationSource,
        source_path: Optional[str] = None,
        priority: int = 0,
        is_sensitive: bool = False,
        description: Optional[str] = None,
    ) -> None:
        """Set a configuration entry."""
        # Check if we should override existing entry
        if key in self._entries:
            existing = self._entries[key]
            if existing.priority > priority:
                # Existing entry has higher priority, don't override
                return

        # Validate the entry
        validation_errors = self._validator.validate_entry(key, value)
        if validation_errors:
            if self.logger:
                for error in validation_errors:
                    self.logger.warning(f"Configuration validation warning: {error}")

        # Store old value for change callback
        old_value = self._entries[key].value if key in self._entries else None

        # Create and store the entry
        entry = ConfigurationEntry(
            key=key,
            value=value,
            source=source,
            source_path=source_path,
            priority=priority,
            last_modified=datetime.now(),
            is_sensitive=is_sensitive,
            description=description,
        )

        self._entries[key] = entry

        # Trigger change callbacks
        if old_value != value:
            self._trigger_change_callbacks(key, old_value, value)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.

        Args:
            key: Configuration key (dot notation supported)
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if key in self._entries:
            return self._entries[key].value
        return default

    def get_typed(self, key: str, value_type: type, default: Optional[T] = None) -> T:
        """
        Get a configuration value with type conversion.

        Args:
            key: Configuration key
            value_type: Expected type
            default: Default value

        Returns:
            Typed configuration value
        """
        value = self.get(key, default)

        if value is None:
            return cast(T, default)

        if isinstance(value, value_type):
            return cast(T, value)

        # Try to convert
        try:
            if value_type is bool:
                if isinstance(value, str):
                    return cast(T, value.lower() in ("true", "yes", "1", "on"))
                return cast(T, bool(value))
            elif value_type in (int, float, str):
                return cast(T, value_type(value))
        except (ValueError, TypeError):
            if self.logger:
                self.logger.warning(f"Failed to convert {key} to {value_type.__name__}, using default")

        return cast(T, default)

    def set(self, key: str, value: Any, priority: int = 1000) -> None:
        """
        Set a configuration value programmatically.

        Args:
            key: Configuration key
            value: Value to set
            priority: Priority level (higher values override lower)
        """
        if self._frozen:
            raise RuntimeError("Configuration is frozen")

        self._set_entry(
            key, value, ConfigurationSource.OVERRIDE, priority=priority, description="Programmatically set value"
        )

    def has(self, key: str) -> bool:
        """Check if a configuration key exists."""
        return key in self._entries

    def remove(self, key: str) -> bool:
        """
        Remove a configuration entry.

        Args:
            key: Configuration key to remove

        Returns:
            True if the key was removed
        """
        if self._frozen:
            raise RuntimeError("Configuration is frozen")

        if key in self._entries:
            del self._entries[key]
            if self.logger:
                self.logger.verbose(f"Removed configuration key: {key}")
            return True
        return False

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration as a flat dictionary."""
        return {key: entry.value for key, entry in self._entries.items()}

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get all configuration entries for a section.

        Args:
            section: Section name (e.g., 'logging', 'transports')

        Returns:
            Dictionary of section configuration
        """
        result = {}
        prefix = f"{section}."

        for key, entry in self._entries.items():
            if key.startswith(prefix):
                subkey = key[len(prefix) :]
                result[subkey] = entry.value

        return result

    def register_schema(self, schema: ConfigurationSchema) -> None:
        """Register a configuration schema for validation."""
        self._validator.register_schema(schema)

    def validate(self) -> Dict[str, List[str]]:
        """
        Validate all configuration entries.

        Returns:
            Dictionary mapping keys to validation errors
        """
        config_dict = self.get_all()
        return self._validator.validate_all(config_dict)

    def add_change_callback(self, callback: Callable[[str, Any, Any], None]) -> None:
        """
        Add a callback for configuration changes.

        Args:
            callback: Function to call when configuration changes (key, old_value, new_value)
        """
        self._change_callbacks.append(callback)

    def remove_change_callback(self, callback: Callable[[str, Any, Any], None]) -> None:
        """Remove a configuration change callback."""
        if callback in self._change_callbacks:
            self._change_callbacks.remove(callback)

    def _trigger_change_callbacks(self, key: str, old_value: Any, new_value: Any) -> None:
        """Trigger configuration change callbacks."""
        for callback in self._change_callbacks:
            try:
                callback(key, old_value, new_value)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error in configuration change callback: {e}")

    async def enable_hot_reload(self, interval: float = 1.0) -> None:
        """
        Enable hot reloading of configuration files.

        Args:
            interval: File check interval in seconds
        """
        if self._watcher is None:
            self._watcher = ConfigurationWatcher(callback=self._handle_file_change, logger=self.logger)

        await self._watcher.start_watching(interval)

    async def disable_hot_reload(self) -> None:
        """Disable hot reloading."""
        if self._watcher:
            await self._watcher.stop_watching()

    def _handle_file_change(self, file_path: str) -> None:
        """Handle configuration file changes."""
        try:
            # Reload the file
            self.load_from_file(file_path)

            if self.logger:
                self.logger.info(f"Reloaded configuration from changed file: {file_path}")

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to reload configuration file {file_path}: {e}")

    def get_configuration_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the configuration manager state.

        Returns:
            Dictionary containing configuration summary
        """
        source_counts = {}
        sensitive_count = 0

        for entry in self._entries.values():
            source_name = entry.source.name
            if source_name not in source_counts:
                source_counts[source_name] = 0
            source_counts[source_name] += 1

            if entry.is_sensitive:
                sensitive_count += 1

        return {
            "total_entries": len(self._entries),
            "current_environment": self._current_environment,
            "available_environments": list(self._environments),
            "source_counts": source_counts,
            "sensitive_entries": sensitive_count,
            "is_frozen": self._frozen,
            "hot_reload_enabled": self._watcher is not None and self._watcher._running,
            "change_callbacks": len(self._change_callbacks),
            "validation_schemas": len(self._validator.schemas),
        }
