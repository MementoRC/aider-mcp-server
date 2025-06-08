"""
Tests for the configuration manager module.
"""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from aider_mcp_server.molecules.configuration.configuration_manager import (
    ConfigurationEntry,
    ConfigurationFormat,
    ConfigurationManager,
    ConfigurationSchema,
    ConfigurationSource,
    ConfigurationValidator,
    ConfigurationWatcher,
)


class MockLogger:
    """Mock logger for testing."""

    def __init__(self):
        self.messages = []

    def verbose(self, message: str):
        self.messages.append(f"VERBOSE: {message}")

    def info(self, message: str):
        self.messages.append(f"INFO: {message}")

    def warning(self, message: str):
        self.messages.append(f"WARNING: {message}")

    def error(self, message: str):
        self.messages.append(f"ERROR: {message}")


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return MockLogger()


@pytest.fixture
def config_manager(mock_logger):
    """Create a configuration manager with mock logger."""
    return ConfigurationManager(logger=mock_logger)


@pytest.fixture
def temp_config_file():
    """Create a temporary configuration file."""
    config_data = {
        "database": {"host": "localhost", "port": 5432, "name": "testdb"},
        "logging": {"level": "DEBUG", "verbose": True},
        "features": {"feature1": True, "feature2": False},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    os.unlink(temp_path)


class TestConfigurationValidator:
    """Test the ConfigurationValidator class."""

    def test_register_schema(self):
        """Test registering configuration schema."""
        validator = ConfigurationValidator()
        schema = ConfigurationSchema(key="test.key", required=True, data_type=str, default_value="default")

        validator.register_schema(schema)
        assert "test.key" in validator.schemas
        assert validator.schemas["test.key"] == schema

    def test_validate_entry_valid(self):
        """Test validating valid entry."""
        validator = ConfigurationValidator()
        schema = ConfigurationSchema(key="test.string", data_type=str, choices=["a", "b", "c"])
        validator.register_schema(schema)

        errors = validator.validate_entry("test.string", "a")
        assert len(errors) == 0

    def test_validate_entry_invalid_type(self):
        """Test validating entry with invalid type."""
        validator = ConfigurationValidator()
        schema = ConfigurationSchema(key="test.int", data_type=int)
        validator.register_schema(schema)

        # Should try to convert string to int
        errors = validator.validate_entry("test.int", "123")
        assert len(errors) == 0

        # Should fail for non-convertible string
        errors = validator.validate_entry("test.int", "not_a_number")
        assert len(errors) > 0
        assert "must be of type int" in errors[0]

    def test_validate_entry_invalid_choice(self):
        """Test validating entry with invalid choice."""
        validator = ConfigurationValidator()
        schema = ConfigurationSchema(key="test.choice", data_type=str, choices=["a", "b", "c"])
        validator.register_schema(schema)

        errors = validator.validate_entry("test.choice", "d")
        assert len(errors) > 0
        assert "must be one of" in errors[0]

    def test_validate_entry_range_validation(self):
        """Test range validation."""
        validator = ConfigurationValidator()
        schema = ConfigurationSchema(key="test.range", data_type=int, min_value=1, max_value=10)
        validator.register_schema(schema)

        # Valid range
        errors = validator.validate_entry("test.range", 5)
        assert len(errors) == 0

        # Below minimum
        errors = validator.validate_entry("test.range", 0)
        assert len(errors) > 0
        assert ">=" in errors[0]

        # Above maximum
        errors = validator.validate_entry("test.range", 11)
        assert len(errors) > 0
        assert "<=" in errors[0]

    def test_validate_entry_custom_validator(self):
        """Test custom validator function."""

        def even_validator(value):
            return value % 2 == 0

        validator = ConfigurationValidator()
        schema = ConfigurationSchema(key="test.even", data_type=int, validator=even_validator)
        validator.register_schema(schema)

        # Valid even number
        errors = validator.validate_entry("test.even", 4)
        assert len(errors) == 0

        # Invalid odd number
        errors = validator.validate_entry("test.even", 3)
        assert len(errors) > 0
        assert "Custom validation failed" in errors[0]

    def test_validate_all_missing_required(self):
        """Test validating configuration with missing required keys."""
        validator = ConfigurationValidator()

        # Register required schema
        schema = ConfigurationSchema(key="required.key", required=True)
        validator.register_schema(schema)

        # Validate empty configuration
        errors = validator.validate_all({})

        assert "required.key" in errors
        assert "Required configuration key" in errors["required.key"][0]

    def test_validate_all_with_errors(self):
        """Test validating configuration with multiple errors."""
        validator = ConfigurationValidator()

        # Register schemas
        validator.register_schema(ConfigurationSchema(key="required.key", required=True))
        validator.register_schema(ConfigurationSchema(key="int.key", data_type=int))

        # Configuration with errors
        config = {"int.key": "not_a_number"}

        errors = validator.validate_all(config)

        # Should have errors for both missing required and invalid type
        assert "required.key" in errors
        assert "int.key" in errors


class TestConfigurationManager:
    """Test the ConfigurationManager class."""

    def test_default_configuration(self, config_manager):
        """Test that default configuration is loaded."""
        # Should have default logging level
        assert config_manager.get("logging.level") == "INFO"
        assert config_manager.get("application.name") == "Aider MCP Server"

    def test_get_nonexistent_key(self, config_manager):
        """Test getting non-existent key returns default."""
        assert config_manager.get("nonexistent.key") is None
        assert config_manager.get("nonexistent.key", "default") == "default"

    def test_set_and_get(self, config_manager):
        """Test setting and getting configuration values."""
        config_manager.set("test.key", "test_value")
        assert config_manager.get("test.key") == "test_value"

    def test_has(self, config_manager):
        """Test checking if key exists."""
        assert config_manager.has("logging.level")  # Default key
        assert not config_manager.has("nonexistent.key")

        config_manager.set("new.key", "value")
        assert config_manager.has("new.key")

    def test_remove(self, config_manager):
        """Test removing configuration keys."""
        config_manager.set("test.key", "value")
        assert config_manager.has("test.key")

        removed = config_manager.remove("test.key")
        assert removed
        assert not config_manager.has("test.key")

        # Try to remove non-existent key
        removed = config_manager.remove("nonexistent.key")
        assert not removed

    def test_get_typed(self, config_manager):
        """Test getting typed configuration values."""
        config_manager.set("string.key", "test")
        config_manager.set("int.key", "123")
        config_manager.set("bool.key", "true")
        config_manager.set("float.key", "12.34")

        assert config_manager.get_typed("string.key", str) == "test"
        assert config_manager.get_typed("int.key", int) == 123
        assert config_manager.get_typed("bool.key", bool) is True
        assert config_manager.get_typed("float.key", float) == 12.34

    def test_get_typed_with_default(self, config_manager):
        """Test getting typed values with defaults."""
        # Non-existent key should return default
        assert config_manager.get_typed("nonexistent", int, 42) == 42

        # Invalid conversion should return default
        config_manager.set("invalid.int", "not_a_number")
        assert config_manager.get_typed("invalid.int", int, 42) == 42

    def test_get_all(self, config_manager):
        """Test getting all configuration."""
        config_manager.set("test.key1", "value1")
        config_manager.set("test.key2", "value2")

        all_config = config_manager.get_all()

        assert "test.key1" in all_config
        assert "test.key2" in all_config
        assert all_config["test.key1"] == "value1"
        assert all_config["test.key2"] == "value2"

    def test_get_section(self, config_manager):
        """Test getting configuration section."""
        config_manager.set("section.key1", "value1")
        config_manager.set("section.key2", "value2")
        config_manager.set("other.key", "other_value")

        section = config_manager.get_section("section")

        assert len(section) == 2
        assert section["key1"] == "value1"
        assert section["key2"] == "value2"
        assert "key" not in section  # Should not include other.key

    def test_load_from_environment(self, config_manager):
        """Test loading from environment variables."""
        # Mock environment variables
        env_vars = {
            "AIDER_MCP_TEST_KEY": "test_value",
            "AIDER_MCP_NESTED_KEY": "nested_value",
            "OTHER_PREFIX_KEY": "should_not_load",
        }

        with patch.dict(os.environ, env_vars):
            config_manager.load_from_environment()

        assert config_manager.get("test.key") == "test_value"
        assert config_manager.get("nested.key") == "nested_value"
        assert config_manager.get("key") is None  # Should not load OTHER_PREFIX

    def test_load_from_file_json(self, config_manager, temp_config_file):
        """Test loading from JSON file."""
        config_manager.load_from_file(temp_config_file)

        assert config_manager.get("database.host") == "localhost"
        assert config_manager.get("database.port") == 5432
        assert config_manager.get("logging.level") == "DEBUG"  # Should override default
        assert config_manager.get("features.feature1") is True

    def test_load_from_nonexistent_file(self, config_manager):
        """Test loading from non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            config_manager.load_from_file("/nonexistent/file.json")

    def test_set_environment(self, config_manager):
        """Test setting environment."""
        assert config_manager._current_environment == "development"

        config_manager.set_environment("production")
        assert config_manager._current_environment == "production"

    def test_add_environment(self, config_manager):
        """Test adding new environment."""
        config_manager.add_environment("testing")
        assert "testing" in config_manager._environments

    def test_freeze_unfreeze(self, config_manager):
        """Test freezing and unfreezing configuration."""
        # Initially not frozen
        config_manager.set("test.key", "value")
        assert config_manager.get("test.key") == "value"

        # Freeze configuration
        config_manager.freeze()

        # Should not allow changes
        with pytest.raises(RuntimeError, match="frozen"):
            config_manager.set("new.key", "value")

        with pytest.raises(RuntimeError, match="frozen"):
            config_manager.load_from_environment()

        # Unfreeze
        config_manager.unfreeze()
        config_manager.set("new.key", "value")
        assert config_manager.get("new.key") == "value"

    def test_register_schema(self, config_manager):
        """Test registering configuration schema."""
        schema = ConfigurationSchema(key="test.validated", required=True, data_type=int, min_value=1, max_value=100)

        config_manager.register_schema(schema)

        # Valid value should work
        config_manager.set("test.validated", 50)
        assert config_manager.get("test.validated") == 50

    def test_validate(self, config_manager):
        """Test configuration validation."""
        # Register schema
        schema = ConfigurationSchema(key="required.test", required=True, data_type=str)
        config_manager.register_schema(schema)

        # Validation should show missing required key
        errors = config_manager.validate()
        assert "required.test" in errors

        # Add the required key
        config_manager.set("required.test", "value")
        errors = config_manager.validate()
        assert "required.test" not in errors

    def test_change_callbacks(self, config_manager):
        """Test configuration change callbacks."""
        changes = []

        def on_change(key, old_value, new_value):
            changes.append((key, old_value, new_value))

        config_manager.add_change_callback(on_change)

        # Make changes
        config_manager.set("test.key", "value1")
        config_manager.set("test.key", "value2")  # Change existing value

        assert len(changes) >= 2

        # Check that changes were recorded
        change_keys = [change[0] for change in changes]
        assert "test.key" in change_keys

        # Remove callback
        config_manager.remove_change_callback(on_change)
        config_manager.set("test.key", "value3")

        # Should not add more changes after removal
        assert len([c for c in changes if c[2] == "value3"]) == 0

    @pytest.mark.asyncio
    async def test_hot_reload_enable_disable(self, config_manager):
        """Test enabling and disabling hot reload."""
        # Enable hot reload
        await config_manager.enable_hot_reload(interval=0.1)
        assert config_manager._watcher is not None
        assert config_manager._watcher._running

        # Disable hot reload
        await config_manager.disable_hot_reload()
        assert not config_manager._watcher._running

    def test_configuration_summary(self, config_manager):
        """Test getting configuration summary."""
        # Add some configuration
        config_manager.set("test.key1", "value1")
        config_manager.set("test.key2", "value2")

        summary = config_manager.get_configuration_summary()

        assert summary["total_entries"] > 0
        assert summary["current_environment"] == "development"
        assert "development" in summary["available_environments"]
        assert "DEFAULT" in summary["source_counts"]
        assert "OVERRIDE" in summary["source_counts"]
        assert summary["is_frozen"] is False

    def test_priority_override(self, config_manager):
        """Test that higher priority values override lower ones."""
        # Set low priority value
        config_manager._set_entry("test.priority", "low", ConfigurationSource.DEFAULT, priority=1)

        # Set high priority value
        config_manager._set_entry("test.priority", "high", ConfigurationSource.OVERRIDE, priority=100)

        assert config_manager.get("test.priority") == "high"

        # Try to set lower priority - should not override
        config_manager._set_entry("test.priority", "lower", ConfigurationSource.ENVIRONMENT, priority=50)

        assert config_manager.get("test.priority") == "high"  # Should still be high priority value


class TestConfigurationWatcher:
    """Test the ConfigurationWatcher class."""

    @pytest.mark.asyncio
    async def test_watcher_basic_functionality(self, temp_config_file):
        """Test basic file watching functionality."""
        changes = []

        def on_change(file_path):
            changes.append(file_path)

        watcher = ConfigurationWatcher(on_change)
        watcher.add_file(temp_config_file)

        # Start watching
        await watcher.start_watching(interval=0.1)

        # Wait a bit to ensure watcher is running
        import asyncio

        await asyncio.sleep(0.15)

        # Modify the file
        with open(temp_config_file, "w") as f:
            json.dump({"modified": True}, f)

        # Wait a bit for the watcher to detect the change
        await asyncio.sleep(0.25)

        # Stop watching
        await watcher.stop_watching()

        # Should have detected the change
        assert temp_config_file in changes

    def test_watcher_add_remove_files(self):
        """Test adding and removing files from watcher."""

        def dummy_callback(file_path):
            pass

        watcher = ConfigurationWatcher(dummy_callback)

        # Create a temporary file for testing
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"test": true}')
            temp_file = f.name

        try:
            # Add file
            watcher.add_file(temp_file)
            assert temp_file in watcher._watched_files

            # Remove file
            watcher.remove_file(temp_file)
            assert temp_file not in watcher._watched_files
        finally:
            # Cleanup
            os.unlink(temp_file)


class TestConfigurationEntry:
    """Test the ConfigurationEntry dataclass."""

    def test_configuration_entry_creation(self):
        """Test creating configuration entry."""
        entry = ConfigurationEntry(
            key="test.key",
            value="test_value",
            source=ConfigurationSource.FILE,
            source_path="/path/to/config.json",
            priority=100,
            is_sensitive=True,
            description="Test configuration entry",
        )

        assert entry.key == "test.key"
        assert entry.value == "test_value"
        assert entry.source == ConfigurationSource.FILE
        assert entry.source_path == "/path/to/config.json"
        assert entry.priority == 100
        assert entry.is_sensitive is True
        assert entry.description == "Test configuration entry"


class TestConfigurationEnums:
    """Test configuration enums."""

    def test_configuration_source_enum(self):
        """Test ConfigurationSource enum."""
        assert ConfigurationSource.ENVIRONMENT
        assert ConfigurationSource.FILE
        assert ConfigurationSource.COMMAND_LINE
        assert ConfigurationSource.DEFAULT
        assert ConfigurationSource.REMOTE
        assert ConfigurationSource.OVERRIDE

    def test_configuration_format_enum(self):
        """Test ConfigurationFormat enum."""
        assert ConfigurationFormat.JSON
        assert ConfigurationFormat.YAML
        assert ConfigurationFormat.TOML
        assert ConfigurationFormat.INI
        assert ConfigurationFormat.PROPERTIES
