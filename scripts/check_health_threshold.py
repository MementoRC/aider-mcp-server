#!/usr/bin/env python3
"""
Health Threshold Checker for Systematic Maintenance Framework.

This script checks health assessment results against configured thresholds
and sets GitHub Actions outputs for workflow decision making.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict

import yaml


class HealthThresholdChecker:
    """Checks health assessment results against configured thresholds."""

    def __init__(self, config_path: str = "maintenance.yml"):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load maintenance configuration."""
        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
            print(f"✅ Loaded configuration from {self.config_path}")
            return config
        except FileNotFoundError:
            print(f"⚠️ Configuration file {self.config_path} not found, using defaults")
            return self._get_default_config()
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            "health_thresholds": {
                "overall_score": 80,
                "dependency_health": 70,
                "code_quality": 75,
                "security": 90,
                "performance": 70,
                "system_health": 70,
                "maintenance_threshold": 80,
                "critical_threshold": 50,
            },
            "maintenance_automation": {
                "auto_create_issues": True,
                "auto_assign_reviewers": False,
                "urgency_escalation": True,
            },
        }

    def check_health_report(self, report_path: str) -> Dict[str, Any]:
        """Check health report against thresholds."""
        try:
            with open(report_path, "r") as f:
                health_data = json.load(f)
            print(f"✅ Loaded health report from {report_path}")
        except FileNotFoundError:
            print(f"❌ Health report not found: {report_path}")
            return self._get_failure_result("Health report file not found")
        except Exception as e:
            print(f"❌ Error reading health report: {e}")
            return self._get_failure_result(f"Error reading report: {e}")

        return self._analyze_health_data(health_data)

    def _analyze_health_data(self, health_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze health data against thresholds."""
        thresholds = self.config.get("health_thresholds", {})

        # Get scores (handle both 0-1 and 0-100 scales)
        composite_score = health_data.get("composite_score", 0)
        if composite_score <= 1.0:
            composite_score *= 100  # Convert to percentage

        component_scores = health_data.get("component_scores", {})

        # Convert component scores to percentage if needed
        normalized_components = {}
        for component, score in component_scores.items():
            if score <= 1.0:
                score *= 100
            normalized_components[component] = score

        # Check overall threshold
        maintenance_threshold = thresholds.get("maintenance_threshold", 80)
        critical_threshold = thresholds.get("critical_threshold", 50)

        needs_maintenance = composite_score < maintenance_threshold
        is_critical = composite_score < critical_threshold

        # Determine urgency level
        if is_critical:
            urgency = "critical"
        elif composite_score < 60:
            urgency = "high"
        elif composite_score < maintenance_threshold:
            urgency = "medium"
        else:
            urgency = "low"

        # Check individual component thresholds
        component_issues = []
        for component, score in normalized_components.items():
            threshold_key = component.replace("_health", "").replace("_", "_")
            threshold = thresholds.get(threshold_key, 70)

            if score < threshold:
                component_issues.append(
                    {
                        "component": component,
                        "score": score,
                        "threshold": threshold,
                        "severity": "critical" if score < threshold * 0.7 else "warning",
                    }
                )

        # Get recommendations
        recommendations = health_data.get("recommendations", [])

        result = {
            "needs_maintenance": needs_maintenance,
            "is_critical": is_critical,
            "urgency_level": urgency,
            "overall_score": composite_score,
            "maintenance_threshold": maintenance_threshold,
            "component_issues": component_issues,
            "recommendations": recommendations,
            "assessment_summary": {
                "total_components": len(normalized_components),
                "failing_components": len(component_issues),
                "critical_components": len([c for c in component_issues if c["severity"] == "critical"]),
                "recommendation_count": len(recommendations),
            },
        }

        print("🎯 Health Analysis Results:")
        print(f"   Overall Score: {composite_score:.1f}/{maintenance_threshold}")
        print(f"   Maintenance Needed: {needs_maintenance}")
        print(f"   Urgency Level: {urgency}")
        print(f"   Component Issues: {len(component_issues)}")

        return result

    def _get_failure_result(self, reason: str) -> Dict[str, Any]:
        """Get result structure for failure cases."""
        return {
            "needs_maintenance": True,
            "is_critical": True,
            "urgency_level": "critical",
            "overall_score": 0,
            "maintenance_threshold": 80,
            "component_issues": [],
            "recommendations": [f"Health check failed: {reason}"],
            "assessment_summary": {
                "total_components": 0,
                "failing_components": 0,
                "critical_components": 0,
                "recommendation_count": 1,
            },
            "error": reason,
        }

    def set_github_outputs(self, result: Dict[str, Any]) -> None:
        """Set GitHub Actions outputs for workflow decisions."""
        # GitHub Actions outputs
        outputs = {
            "needs_maintenance": str(result["needs_maintenance"]).lower(),
            "is_critical": str(result["is_critical"]).lower(),
            "urgency_level": result["urgency_level"],
            "overall_score": str(int(result["overall_score"])),
            "component_issues_count": str(len(result["component_issues"])),
            "critical_components_count": str(result["assessment_summary"]["critical_components"]),
        }

        # Set outputs for GitHub Actions
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            try:
                with open(github_output, "a") as f:
                    for key, value in outputs.items():
                        f.write(f"{key}={value}\n")
                print("✅ Set GitHub Actions outputs")
            except Exception as e:
                print(f"⚠️ Could not set GitHub outputs: {e}")

        # Also set as environment variables for local testing
        for key, value in outputs.items():
            os.environ[f"HEALTH_CHECK_{key.upper()}"] = value

        # Print outputs for verification
        print("\n📋 Workflow Outputs:")
        for key, value in outputs.items():
            print(f"   {key}: {value}")


def main():
    """Main entry point for threshold checking."""
    parser = argparse.ArgumentParser(description="Check health assessment results against configured thresholds")
    parser.add_argument("--report", required=True, help="Path to health assessment report JSON file")
    parser.add_argument("--config", default="maintenance.yml", help="Path to maintenance configuration file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    if args.verbose:
        print("🔍 Starting Health Threshold Checker")
        print(f"Report: {args.report}")
        print(f"Config: {args.config}")

    try:
        # Initialize checker and run analysis
        checker = HealthThresholdChecker(config_path=args.config)
        result = checker.check_health_report(args.report)

        # Set GitHub Actions outputs
        checker.set_github_outputs(result)

        # Print final summary
        if result.get("error"):
            print(f"\n❌ Check failed: {result['error']}")
            sys.exit(3)
        elif result["is_critical"]:
            print(f"\n🚨 CRITICAL: Immediate maintenance required (Score: {result['overall_score']:.1f})")
            sys.exit(2)
        elif result["needs_maintenance"]:
            print(f"\n⚠️ Maintenance recommended (Score: {result['overall_score']:.1f})")
            sys.exit(1)
        else:
            print(f"\n✅ Health check passed (Score: {result['overall_score']:.1f})")
            sys.exit(0)

    except Exception as e:
        print(f"❌ Threshold check failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    main()
