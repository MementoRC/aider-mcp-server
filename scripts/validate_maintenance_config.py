#!/usr/bin/env python3
"""
Validation script for maintenance.yml configuration file.

This script validates the maintenance.yml configuration file to ensure
all required fields are present and values are within acceptable ranges.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml


class MaintenanceConfigValidator:
    """Validates maintenance.yml configuration."""

    def __init__(self, config_path: str = "maintenance.yml"):
        self.config_path = Path(config_path)
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def load_config(self) -> Dict[str, Any]:
        """Load and parse the maintenance configuration."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file {self.config_path} not found")

        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML syntax: {e}") from e

    def validate_project_section(self, config: Dict[str, Any]) -> None:
        """Validate project metadata section."""
        if "project" not in config:
            self.errors.append("Missing required 'project' section")
            return

        project = config["project"]
        required_fields = ["name", "type", "criticality"]

        for field in required_fields:
            if field not in project:
                self.errors.append(f"Missing required field 'project.{field}'")

        # Validate criticality level
        if "criticality" in project and project["criticality"] not in ["low", "medium", "high", "critical"]:
            self.errors.append(f"Invalid criticality level: {project['criticality']}")

    def validate_health_thresholds(self, config: Dict[str, Any]) -> None:
        """Validate health threshold values."""
        if "health_thresholds" not in config:
            self.errors.append("Missing required 'health_thresholds' section")
            return

        thresholds = config["health_thresholds"]
        required_thresholds = ["overall_score", "security_vulnerabilities", "dependency_staleness_days"]

        for threshold in required_thresholds:
            if threshold not in thresholds:
                self.errors.append(f"Missing required threshold 'health_thresholds.{threshold}'")

        # Validate threshold ranges
        if "overall_score" in thresholds:
            score = thresholds["overall_score"]
            if not isinstance(score, (int, float)) or score < 0 or score > 100:
                self.errors.append("overall_score must be between 0 and 100")

        if "security_vulnerabilities" in thresholds:
            vulns = thresholds["security_vulnerabilities"]
            if not isinstance(vulns, int) or vulns < 0:
                self.errors.append("security_vulnerabilities must be a non-negative integer")

        if "dependency_staleness_days" in thresholds:
            days = thresholds["dependency_staleness_days"]
            if not isinstance(days, int) or days < 1:
                self.errors.append("dependency_staleness_days must be a positive integer")

    def validate_automation_levels(self, config: Dict[str, Any]) -> None:
        """Validate automation level configurations."""
        if "automation_levels" not in config:
            self.errors.append("Missing required 'automation_levels' section")
            return

        automation = config["automation_levels"]
        valid_levels = ["auto", "semi-auto", "manual"]

        # Check that all automation values are valid
        def check_automation_values(section: Dict[str, Any], prefix: str = "") -> None:
            for key, value in section.items():
                if isinstance(value, dict):
                    check_automation_values(value, f"{prefix}.{key}" if prefix else key)
                elif isinstance(value, str):
                    if value not in valid_levels:
                        self.errors.append(f"Invalid automation level '{value}' for {prefix}.{key}")

        check_automation_values(automation, "automation_levels")

    def validate_maintenance_schedule(self, config: Dict[str, Any]) -> None:
        """Validate maintenance scheduling configuration."""
        if "maintenance_schedule" not in config:
            self.warnings.append("Missing 'maintenance_schedule' section - using defaults")
            return

        schedule = config["maintenance_schedule"]

        # Validate frequency values
        valid_frequencies = ["hourly", "daily", "weekly", "monthly"]
        frequency_fields = ["health_check_frequency", "full_maintenance_review"]

        for field in frequency_fields:
            if field in schedule:
                freq = schedule[field]
                if freq not in valid_frequencies:
                    self.warnings.append(f"Unusual frequency '{freq}' for {field}")

    def validate_quality_gates(self, config: Dict[str, Any]) -> None:
        """Validate quality gate configurations."""
        if "quality_gates" in config:
            gates = config["quality_gates"]

            if "required_checks" in gates and not isinstance(gates["required_checks"], list):
                self.errors.append("quality_gates.required_checks must be a list")

            if "blocking_conditions" in gates and not isinstance(gates["blocking_conditions"], list):
                self.errors.append("quality_gates.blocking_conditions must be a list")

    def validate_existing_systems(self, config: Dict[str, Any]) -> None:
        """Validate references to existing monitoring systems."""
        if "existing_systems" not in config:
            self.warnings.append("No existing_systems configuration - integration may be limited")
            return

        systems = config["existing_systems"]

        # Check if referenced files exist
        for system_name, file_path in systems.items():
            if isinstance(file_path, str):
                full_path = Path(file_path)
                if not full_path.exists():
                    self.warnings.append(f"Referenced file for {system_name} does not exist: {file_path}")

    def validate_config(self) -> bool:
        """Run full configuration validation."""
        try:
            config = self.load_config()
        except (FileNotFoundError, ValueError) as e:
            self.errors.append(str(e))
            return False

        # Run all validation checks
        self.validate_project_section(config)
        self.validate_health_thresholds(config)
        self.validate_automation_levels(config)
        self.validate_maintenance_schedule(config)
        self.validate_quality_gates(config)
        self.validate_existing_systems(config)

        return len(self.errors) == 0

    def print_results(self) -> None:
        """Print validation results."""
        if not self.errors and not self.warnings:
            print("✅ Configuration validation passed - all checks successful")
            return

        if self.errors:
            print(f"❌ Configuration validation failed with {len(self.errors)} errors:")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")

        if self.warnings:
            print(f"⚠️  Found {len(self.warnings)} warnings:")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")

        if not self.errors:
            print("✅ Configuration is valid despite warnings")


def main():
    """Main entry point."""
    validator = MaintenanceConfigValidator()

    try:
        is_valid = validator.validate_config()
        validator.print_results()

        # Exit with appropriate code
        sys.exit(0 if is_valid else 1)

    except Exception as e:
        print(f"❌ Validation failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
