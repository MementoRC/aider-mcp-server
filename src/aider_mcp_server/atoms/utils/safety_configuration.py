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
from typing import Any, Dict, Optional, Union

import toml  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

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

    def __post_init__(self) -> None:
        """Apply profile defaults and validate the configuration."""
        if self.profile != SafetyProfile.CUSTOM:
            self.apply_profile(self.profile)
        self.validate()

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
        """Convert configuration to a dictionary."""
        data = asdict(self)
        data["profile"] = self.profile.value
        data["validation_level"] = self.validation_level.value
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
        2. A configuration object is created from this base profile.
        3. Settings from the config file are layered on top.
        4. Settings from CLI overrides are layered on top of that.
        5. If any customizations are applied, the profile is marked as 'custom'.

        Args:
            cli_overrides: A dictionary of settings to override file configuration.

        Returns:
            A validated SafetyConfiguration instance.
        """
        file_config = self._load_from_file()
        merged_config = {**file_config, **(cli_overrides or {})}

        profile_name = merged_config.get("profile", "balanced")
        try:
            profile = SafetyProfile(profile_name.lower())
        except (ValueError, AttributeError) as e:
            raise SafetyConfigurationError(f"Invalid profile name: {profile_name}") from e

        config = SafetyConfiguration(profile=profile)

        if "validation_level" in merged_config and isinstance(merged_config["validation_level"], str):
            try:
                merged_config["validation_level"] = ValidationLevel(merged_config["validation_level"].lower())
            except ValueError as e:
                raise SafetyConfigurationError(f"Invalid validation_level: {merged_config['validation_level']}") from e

        for key, value in merged_config.items():
            if hasattr(config, key) and key != "profile":
                setattr(config, key, value)

        if file_config or cli_overrides:
            config.profile = SafetyProfile.CUSTOM

        config.validate()

        logger.info(f"Loaded safety configuration with effective profile: {config.profile.value}")
        return config

    def _load_from_file(self) -> Dict[str, Any]:
        """Find and parse a configuration file."""
        config_file = self._find_config_file()
        if not config_file:
            logger.debug("No safety configuration file found. Using default settings.")
            return {}

        logger.info(f"Loading safety configuration from: {config_file}")
        return self._parse_config_file(config_file)

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
                    return yaml.safe_load(f) or {}
                elif file_path.name == "pyproject.toml":
                    data = toml.load(f)
                    return data.get("tool", {}).get("aider", {}).get("safety", {})  # type: ignore[no-any-return]
            return {}
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
            with path.open("w", encoding="utf-8") as f:
                yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)
        except IOError as e:
            raise SafetyConfigurationError(f"Error saving configuration file {path}: {e}") from e
