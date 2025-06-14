"""
Safety Configuration System for Aider.

Provides a comprehensive system for managing safety configurations, including:
- Predefined safety profiles (maximum, balanced, minimal)
- Custom profiles with fine-grained control
- Loading from project-specific files (.aider-safety.yaml, pyproject.toml)
- Command-line override support
- Configuration validation to prevent unsafe settings
- Persistence and loading of configurations
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import toml
import yaml

from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)


class SafetyProfile(Enum):
    """Predefined safety profiles."""

    MAXIMUM = "maximum"
    BALANCED = "balanced"
    MINIMAL = "minimal"
    CUSTOM = "custom"


class ValidationLevel(Enum):
    """Levels for functional validation."""

    STRICT = "strict"
    NORMAL = "normal"
    BASIC = "basic"


class SafetyConfigurationError(Exception):
    """Base exception for configuration errors."""

    pass


@dataclass
class ModelSpecificConfiguration:
    """
    Configuration specific to a model pattern.

    Attributes:
        risk_multiplier: Multiplier for the assessed operation risk score.
        timeout_multiplier: Multiplier for performance timeouts.
        validation_level_override: Specific validation level for this model.
        architect_risk_multiplier: Additional risk multiplier for architect mode.
        fallback_model_suggestion: Suggested fallback model for high-risk operations.
        monitoring_flags: List of special flags for monitoring systems.
    """

    risk_multiplier: float = 1.0
    timeout_multiplier: float = 1.0
    validation_level_override: Optional[ValidationLevel] = None
    architect_risk_multiplier: float = 1.0
    fallback_model_suggestion: Optional[str] = None
    monitoring_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling enums."""
        data = asdict(self)
        if self.validation_level_override:
            data["validation_level_override"] = self.validation_level_override.value
        return data


@dataclass
class SafetyConfiguration:
    """
    Represents the safety configuration for Aider operations.

    Attributes:
        profile: The active safety profile.
        enable_*: Fine-grained toggles for individual safety components.
        rollback_on_*: Conditions for triggering automatic rollbacks.
        validation_level: The strictness of functional validations.
        performance_timeout_seconds: Timeout for safety checks.
        bypass_on_timeout: Whether to bypass checks on timeout.
        model_specific_configs: Dictionary of model-specific settings.
    """

    profile: SafetyProfile = SafetyProfile.BALANCED

    # Component toggles
    enable_git_checkpoint: bool = field(default=True, metadata={"description": "Enable git safety checkpoints."})
    enable_file_integrity: bool = field(default=True, metadata={"description": "Enable file integrity checks."})
    enable_risk_assessment: bool = field(
        default=True, metadata={"description": "Enable pre-operation risk assessment."}
    )
    enable_file_monitoring: bool = field(
        default=True, metadata={"description": "Enable file monitoring during operations."}
    )
    enable_response_validation: bool = field(
        default=True, metadata={"description": "Enable validation of model responses."}
    )
    enable_post_operation_verification: bool = field(
        default=True, metadata={"description": "Enable post-operation verification."}
    )
    enable_functional_validation: bool = field(
        default=True, metadata={"description": "Enable functional validation (linting, tests)."}
    )
    enable_diff_analysis: bool = field(
        default=True, metadata={"description": "Enable git diff analysis for suspicious patterns."}
    )
    enable_failure_detection: bool = field(default=True, metadata={"description": "Enable failure detection system."})
    enable_automatic_rollback: bool = field(
        default=True, metadata={"description": "Enable automatic rollback on critical failures."}
    )
    enable_recovery_guidance: bool = field(
        default=True, metadata={"description": "Enable recovery guidance generation."}
    )

    # Rollback triggers
    rollback_on_critical_failures: bool = field(
        default=True, metadata={"description": "Trigger rollback on CRITICAL failures."}
    )
    rollback_on_high_failures: bool = field(
        default=False, metadata={"description": "Trigger rollback on HIGH failures."}
    )

    # Validation and performance
    validation_level: ValidationLevel = field(
        default=ValidationLevel.NORMAL, metadata={"description": "Strictness of functional validation."}
    )
    performance_timeout_seconds: float = field(
        default=30.0, metadata={"description": "Timeout for safety checks in seconds."}
    )
    bypass_on_timeout: bool = field(default=True, metadata={"description": "Bypass safety checks if they time out."})

    # Model-specific settings
    model_specific_configs: Dict[str, "ModelSpecificConfiguration"] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Apply profile defaults and validate the configuration."""
        if not self.model_specific_configs:
            self._apply_default_model_configs()
        if self.profile != SafetyProfile.CUSTOM:
            self.apply_profile(self.profile)
        self.validate()

    def _apply_default_model_configs(self) -> None:
        """Apply predefined default configurations for known models."""
        self.model_specific_configs = {
            "gpt-4*": ModelSpecificConfiguration(
                risk_multiplier=1.2, architect_risk_multiplier=1.5, monitoring_flags=["high_complexity"]
            ),
            "claude-3*": ModelSpecificConfiguration(risk_multiplier=1.1, fallback_model_suggestion="gpt-4-turbo"),
            "gemini*": ModelSpecificConfiguration(
                risk_multiplier=1.4,
                architect_risk_multiplier=1.8,
                fallback_model_suggestion="claude-3-opus",
                monitoring_flags=["api_stability", "hallucination_risk"],
            ),
            "gpt-3.5*": ModelSpecificConfiguration(risk_multiplier=0.9),
        }

    def apply_profile(self, profile: SafetyProfile) -> None:
        """Apply settings from a predefined profile."""
        logger.debug(f"Applying safety profile: {profile.value}")
        if profile == SafetyProfile.MAXIMUM:
            self._set_all_components(True)
            self.rollback_on_high_failures = True
            self.validation_level = ValidationLevel.STRICT
            self.performance_timeout_seconds = 60.0
            self.bypass_on_timeout = False
        elif profile == SafetyProfile.BALANCED:
            self._set_all_components(True)
            self.rollback_on_high_failures = False
            self.validation_level = ValidationLevel.NORMAL
            self.performance_timeout_seconds = 30.0
            self.bypass_on_timeout = True
        elif profile == SafetyProfile.MINIMAL:
            self._set_all_components(False)
            self.enable_git_checkpoint = True
            self.enable_file_integrity = True
            self.enable_post_operation_verification = True
            self.enable_failure_detection = True
            self.enable_automatic_rollback = True
            self.rollback_on_high_failures = False
            self.validation_level = ValidationLevel.BASIC
            self.performance_timeout_seconds = 20.0
            self.bypass_on_timeout = True

    def _set_all_components(self, value: bool) -> None:
        """Helper to enable or disable all component toggles."""
        for f in self.__dataclass_fields__.values():
            if f.name.startswith("enable_"):
                setattr(self, f.name, value)

    def validate(self) -> None:
        """Validate the configuration for logical consistency."""
        if self.enable_automatic_rollback and not self.enable_failure_detection:
            raise SafetyConfigurationError("Automatic rollback cannot be enabled without failure detection.")
        if self.enable_automatic_rollback and not self.enable_git_checkpoint:
            logger.warning("Automatic rollback is enabled but git checkpoints are not. Rollback may not be possible.")
        if self.performance_timeout_seconds <= 0:
            raise SafetyConfigurationError("Performance timeout must be a positive number.")
        logger.debug("Safety configuration validated successfully.")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to a dictionary for serialization."""
        data = asdict(self)
        data["profile"] = self.profile.value
        data["validation_level"] = self.validation_level.value

        # Use 'model_specific' as the key for consistency with loading conventions
        model_specific_data = {pattern: config.to_dict() for pattern, config in self.model_specific_configs.items()}
        if model_specific_data:
            data["model_specific"] = model_specific_data

        del data["model_specific_configs"]
        return data


class SafetyConfigurationSystem:
    """Manages loading, validation, and access to safety configurations."""

    CONFIG_FILES = [".aider-safety.yaml", ".aider-safety.yml", "pyproject.toml"]

    def __init__(self, project_root: Optional[Union[str, Path]] = None):
        """
        Initialize the configuration system.

        Args:
            project_root: The root directory of the project to search for config files.
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        logger.info(f"Initialized SafetyConfigurationSystem with project root: {self.project_root}")

    def load_config(self, cli_overrides: Optional[Dict[str, Any]] = None) -> SafetyConfiguration:
        """
        Load safety configuration from file and merge with overrides.

        The loading process is as follows:
        1. A base profile is determined (from CLI, then file, then default 'balanced').
        2. A configuration object is created from this base profile, which includes default model settings.
        3. Settings from the config file are layered on top, including model-specific settings.
        4. Settings from CLI overrides are layered on top of that.
        5. If any customizations are applied, the profile is marked as 'custom'.

        Args:
            cli_overrides: A dictionary of settings to override file configuration.

        Returns:
            A validated SafetyConfiguration instance.
        """
        cli_overrides = cli_overrides or {}
        file_config = self._load_from_file()

        file_model_specific = file_config.pop("model_specific", {})
        cli_model_specific = cli_overrides.pop("model_specific", {})

        merged_config = {**file_config, **cli_overrides}

        profile = self._determine_profile(merged_config)
        config = SafetyConfiguration(profile=profile)

        self._apply_model_specific_configs(config, file_model_specific, cli_model_specific)
        self._apply_general_configs(config, merged_config)

        if file_config or cli_overrides or file_model_specific or cli_model_specific:
            config.profile = SafetyProfile.CUSTOM

        config.validate()
        logger.info(f"Loaded safety configuration with effective profile: {config.profile.value}")
        return config

    def _determine_profile(self, merged_config: Dict[str, Any]) -> SafetyProfile:
        """Determine the safety profile from the merged configuration."""
        profile_name = merged_config.get("profile", "balanced")
        try:
            return SafetyProfile(str(profile_name).lower())
        except (ValueError, AttributeError) as e:
            raise SafetyConfigurationError(f"Invalid profile name: '{profile_name}'") from e

    def _apply_model_specific_configs(
        self, config: SafetyConfiguration, file_configs: Dict[str, Any], cli_configs: Dict[str, Any]
    ) -> None:
        """Apply model-specific configurations from file and CLI overrides."""
        all_overrides = {**file_configs, **cli_configs}
        for pattern, model_data in all_overrides.items():
            if not isinstance(model_data, dict):
                logger.warning(f"Skipping invalid model-specific config for '{pattern}': not a dictionary.")
                continue

            if "validation_level_override" in model_data and isinstance(model_data["validation_level_override"], str):
                try:
                    model_data["validation_level_override"] = ValidationLevel(
                        model_data["validation_level_override"].lower()
                    )
                except ValueError as e:
                    raise SafetyConfigurationError(
                        f"Invalid validation_level_override for model '{pattern}': '{model_data['validation_level_override']}'"
                    ) from e

            if pattern in config.model_specific_configs:
                for key, value in model_data.items():
                    if hasattr(config.model_specific_configs[pattern], key):
                        setattr(config.model_specific_configs[pattern], key, value)
            else:
                config.model_specific_configs[pattern] = ModelSpecificConfiguration(**model_data)

    def _apply_general_configs(self, config: SafetyConfiguration, merged_config: Dict[str, Any]) -> None:
        """Apply general configuration settings from file and CLI overrides."""
        if "validation_level" in merged_config and isinstance(merged_config["validation_level"], str):
            try:
                merged_config["validation_level"] = ValidationLevel(merged_config["validation_level"].lower())
            except ValueError as e:
                raise SafetyConfigurationError(
                    f"Invalid validation_level: '{merged_config['validation_level']}'"
                ) from e

        for key, value in merged_config.items():
            if hasattr(config, key) and key != "profile":
                setattr(config, key, value)

    def _load_from_file(self) -> Dict[str, Any]:
        """Find and parse a configuration file."""
        config_file = self._find_config_file()
        if not config_file:
            logger.debug("No safety configuration file found. Using default settings.")
            return {}

        logger.info(f"Loading safety configuration from: {config_file}")
        parsed_config = self._parse_config_file(config_file)

        if config_file.name == "pyproject.toml":
            safety_config = parsed_config.get("tool", {}).get("aider", {}).get("safety", {})
            if not isinstance(safety_config, dict):
                raise SafetyConfigurationError(f"[tool.aider.safety] section in {config_file} is not a table.")
            return safety_config

        if "safety" in parsed_config:
            safety_config = parsed_config["safety"]
            if not isinstance(safety_config, dict):
                raise SafetyConfigurationError(f"'safety' key in {config_file} does not contain a dictionary.")
            return safety_config

        return parsed_config

    def _find_config_file(self) -> Optional[Path]:
        """Search for a configuration file upwards from the project root."""
        current_dir = self.project_root.resolve()
        # Search up to the root directory
        while current_dir != current_dir.parent:
            for filename in self.CONFIG_FILES:
                file_path = current_dir / filename
                if file_path.exists():
                    return file_path
            current_dir = current_dir.parent
        return None

    def _parse_config_file(self, file_path: Path) -> Dict[str, Any]:
        """Parse a YAML or TOML configuration file."""
        try:
            with file_path.open("r", encoding="utf-8") as f:
                if file_path.name.endswith((".yaml", ".yml")):
                    data = yaml.safe_load(f) or {}
                    if not isinstance(data, dict):
                        raise SafetyConfigurationError(
                            f"YAML file {file_path} does not contain a dictionary-like structure at the top level."
                        )
                    return data
                elif file_path.name == "pyproject.toml":
                    return toml.load(f)
            return {}  # Should be unreachable
        except (yaml.YAMLError, toml.TomlDecodeError, IOError) as e:
            raise SafetyConfigurationError(f"Error parsing configuration file {file_path}: {e}") from e

    def save_config(self, config: SafetyConfiguration, file_path: str = ".aider-safety.yaml") -> None:
        """
        Save a SafetyConfiguration object to a YAML file.

        Args:
            config: The configuration object to save.
            file_path: The path to the YAML file.
        """
        path = self.project_root / file_path
        logger.info(f"Saving safety configuration to: {path}")
        try:
            config_dict = {"safety": config.to_dict()}
            with path.open("w", encoding="utf-8") as f:
                yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
        except IOError as e:
            raise SafetyConfigurationError(f"Error saving configuration file {path}: {e}") from e
