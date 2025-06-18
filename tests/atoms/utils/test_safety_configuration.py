"""
Test suite for the Safety Configuration System.

Tests the functionality of SafetyConfiguration and SafetyConfigurationSystem,
including profile application, validation, file loading, and overrides.
"""

import tempfile
from pathlib import Path

import pytest
import toml
import yaml

from aider_mcp_server.atoms.utils.safety_configuration import (
    ModelSpecificConfiguration,
    SafetyConfiguration,
    SafetyConfigurationError,
    SafetyConfigurationSystem,
    SafetyProfile,
    ValidationLevel,
)


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory to act as a project root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestSafetyConfiguration:
    """Tests the SafetyConfiguration dataclass."""

    def test_maximum_profile(self):
        """Test that the 'maximum' profile applies the correct settings."""
        config = SafetyConfiguration(profile=SafetyProfile.MAXIMUM)
        assert config.enable_automatic_rollback is True
        assert config.rollback_on_high_failures is True
        assert config.validation_level == ValidationLevel.STRICT
        assert config.performance_timeout_seconds == 60.0
        assert config.bypass_on_timeout is False

    def test_balanced_profile(self):
        """Test that the 'balanced' profile applies the correct settings."""
        config = SafetyConfiguration(profile=SafetyProfile.BALANCED)
        assert config.enable_automatic_rollback is True
        assert config.rollback_on_high_failures is False
        assert config.validation_level == ValidationLevel.NORMAL
        assert config.performance_timeout_seconds == 30.0
        assert config.bypass_on_timeout is True

    def test_minimal_profile(self):
        """Test that the 'minimal' profile applies the correct settings."""
        config = SafetyConfiguration(profile=SafetyProfile.MINIMAL)
        assert config.enable_git_checkpoint is True
        assert config.enable_risk_assessment is False
        assert config.enable_functional_validation is False
        assert config.validation_level == ValidationLevel.BASIC

    def test_custom_profile_does_not_override(self):
        """Test that the 'custom' profile uses dataclass defaults unless specified."""
        config = SafetyConfiguration(profile=SafetyProfile.CUSTOM, enable_git_checkpoint=False)
        assert config.enable_git_checkpoint is False
        assert config.enable_file_integrity is True  # Should be the default from the field

    def test_validation_error_on_inconsistent_settings(self):
        """Test that validation raises an error for logically inconsistent settings."""
        with pytest.raises(SafetyConfigurationError):
            SafetyConfiguration(
                profile=SafetyProfile.CUSTOM, enable_automatic_rollback=True, enable_failure_detection=False
            )

    def test_validation_warning_on_risky_settings(self):
        """Test that validation accepts risky but valid settings."""
        # This should not raise an exception, but should log a warning
        config = SafetyConfiguration(
            profile=SafetyProfile.CUSTOM, enable_automatic_rollback=True, enable_git_checkpoint=False
        )
        assert config.enable_automatic_rollback is True
        assert config.enable_git_checkpoint is False

    def test_to_dict_conversion(self):
        """Test conversion of the configuration to a dictionary."""
        config = SafetyConfiguration(profile=SafetyProfile.MAXIMUM)
        d = config.to_dict()
        assert d["profile"] == "maximum"
        assert d["validation_level"] == "strict"
        assert d["enable_git_checkpoint"] is True
        assert "gpt-4*" in d["model_specific"]

    def test_default_model_configs(self):
        """Test that default model configurations are loaded."""
        config = SafetyConfiguration()
        assert "gemini*" in config.model_specific_configs
        assert config.model_specific_configs["gemini*"].risk_multiplier == 1.4


class TestSafetyConfigurationSystem:
    """Tests the SafetyConfigurationSystem for loading and managing configs."""

    def test_load_no_config_file_defaults_to_balanced(self, temp_project_dir):
        """Test that loading with no config file results in a 'balanced' profile."""
        system = SafetyConfigurationSystem(project_root=temp_project_dir)
        config = system.load_config()
        assert config.profile == SafetyProfile.BALANCED
        assert "gpt-4*" in config.model_specific_configs

    def test_load_with_yaml_config(self, temp_project_dir):
        """Test loading configuration from a .aider-safety.yaml file."""
        yaml_content = {
            "safety": {
                "profile": "minimal",
                "performance_timeout_seconds": 45.0,
                "model_specific": {
                    "gemini*": {"risk_multiplier": 2.0},
                    "new-model*": {"risk_multiplier": 0.5},
                },
            }
        }
        config_file = temp_project_dir / ".aider-safety.yaml"
        with config_file.open("w") as f:
            yaml.dump(yaml_content, f)

        system = SafetyConfigurationSystem(project_root=temp_project_dir)
        config = system.load_config()

        assert config.profile == SafetyProfile.CUSTOM
        assert config.enable_risk_assessment is False  # From 'minimal' profile base
        assert config.performance_timeout_seconds == 45.0  # From file override
        assert config.model_specific_configs["gemini*"].risk_multiplier == 2.0  # Override
        assert "new-model*" in config.model_specific_configs  # New entry
        assert "gpt-4*" in config.model_specific_configs  # Default entry preserved

    def test_load_with_toml_config(self, temp_project_dir):
        """Test loading configuration from pyproject.toml."""
        toml_content = {
            "tool": {
                "aider": {
                    "safety": {
                        "profile": "maximum",
                        "enable_recovery_guidance": False,
                        "model_specific": {"gpt-4*": {"architect_risk_multiplier": 2.5}},
                    }
                }
            }
        }
        config_file = temp_project_dir / "pyproject.toml"
        with config_file.open("w") as f:
            toml.dump(toml_content, f)

        system = SafetyConfigurationSystem(project_root=temp_project_dir)
        config = system.load_config()

        assert config.profile == SafetyProfile.CUSTOM
        assert config.validation_level == ValidationLevel.STRICT  # From 'maximum' profile base
        assert config.enable_recovery_guidance is False  # From file override
        assert config.model_specific_configs["gpt-4*"].architect_risk_multiplier == 2.5

    def test_cli_overrides(self, temp_project_dir):
        """Test that CLI overrides take precedence over default settings."""
        system = SafetyConfigurationSystem(project_root=temp_project_dir)
        overrides = {"profile": "minimal", "enable_functional_validation": True}
        config = system.load_config(cli_overrides=overrides)

        assert config.profile == SafetyProfile.CUSTOM
        assert config.enable_risk_assessment is False  # From 'minimal' profile base
        assert config.enable_functional_validation is True  # From CLI override

    def test_cli_overrides_model_specific(self, temp_project_dir):
        """Test CLI overrides for model-specific settings."""
        system = SafetyConfigurationSystem(project_root=temp_project_dir)
        overrides = {
            "model_specific": {
                "gemini*": {"risk_multiplier": 5.0, "fallback_model_suggestion": "test"},
                "claude-3*": {"risk_multiplier": 0.1},
            }
        }
        config = system.load_config(cli_overrides=overrides)
        assert config.profile == SafetyProfile.CUSTOM
        assert config.model_specific_configs["gemini*"].risk_multiplier == 5.0
        assert config.model_specific_configs["gemini*"].fallback_model_suggestion == "test"
        assert config.model_specific_configs["claude-3*"].risk_multiplier == 0.1

    def test_cli_overrides_profile_over_file(self, temp_project_dir):
        """Test that a CLI profile override takes precedence over a file profile."""
        yaml_content = {"profile": "maximum"}
        config_file = temp_project_dir / ".aider-safety.yaml"
        with config_file.open("w") as f:
            yaml.dump(yaml_content, f)

        system = SafetyConfigurationSystem(project_root=temp_project_dir)
        overrides = {"profile": "minimal"}
        config = system.load_config(cli_overrides=overrides)

        assert config.profile == SafetyProfile.CUSTOM  # It's custom because an override was applied
        assert config.validation_level == ValidationLevel.BASIC  # From 'minimal' profile
        assert config.bypass_on_timeout is True  # From 'minimal' profile

    def test_find_config_file_in_parent_directory(self, temp_project_dir):
        """Test that the system can find a config file in a parent directory."""
        config_file = temp_project_dir / ".aider-safety.yml"
        config_file.touch()

        sub_dir = temp_project_dir / "subdir"
        sub_dir.mkdir()

        system = SafetyConfigurationSystem(project_root=sub_dir)
        found_file = system._find_config_file()
        assert found_file is not None
        assert found_file.resolve() == config_file.resolve()

    def test_save_and_load_config(self, temp_project_dir):
        """Test saving a configuration and then loading it back."""
        system = SafetyConfigurationSystem(project_root=temp_project_dir)
        config_to_save = SafetyConfiguration(
            profile=SafetyProfile.CUSTOM, enable_diff_analysis=False, performance_timeout_seconds=99.0
        )
        config_to_save.model_specific_configs["test*"] = ModelSpecificConfiguration(risk_multiplier=10.0)

        system.save_config(config_to_save, ".aider-safety.yaml")
        loaded_config = system.load_config()

        assert loaded_config.profile == SafetyProfile.CUSTOM
        assert loaded_config.enable_diff_analysis is False
        assert loaded_config.performance_timeout_seconds == 99.0
        assert loaded_config.model_specific_configs["test*"].risk_multiplier == 10.0

    def test_invalid_profile_in_file_raises_error(self, temp_project_dir):
        """Test that an invalid profile name in a config file raises an error."""
        yaml_content = {"profile": "invalid_profile"}
        config_file = temp_project_dir / ".aider-safety.yaml"
        with config_file.open("w") as f:
            yaml.dump(yaml_content, f)

        system = SafetyConfigurationSystem(project_root=temp_project_dir)
        with pytest.raises(SafetyConfigurationError):
            system.load_config()

    def test_invalid_profile_in_cli_raises_error(self, temp_project_dir):
        """Test that an invalid profile name in CLI overrides raises an error."""
        system = SafetyConfigurationSystem(project_root=temp_project_dir)
        with pytest.raises(SafetyConfigurationError):
            system.load_config(cli_overrides={"profile": "invalid_profile"})
