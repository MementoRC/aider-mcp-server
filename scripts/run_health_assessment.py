#!/usr/bin/env python3
"""
Health Assessment Script for Systematic Maintenance Framework.

This script integrates the HealthScoring system with existing monitoring components
to generate comprehensive health reports for the daily health check workflow.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from aider_mcp_server.molecules.monitoring.health_monitor import HealthMonitor
    from aider_mcp_server.molecules.monitoring.health_scoring import HealthScoring
    from aider_mcp_server.molecules.monitoring.metrics_collector import MetricsCollector
except ImportError as e:
    print(f"Warning: Could not import monitoring components: {e}")
    print("Running in standalone mode with mock components")


class MockHealthMonitor:
    """Mock health monitor for standalone operation."""

    def __init__(self):
        self._metrics_summary = {
            "performance_regression": 0.05,
            "requests_per_minute": 100,
            "success_rate": 0.98,
        }

    async def get_metrics_summary(self, minutes_back=30):
        return self._metrics_summary

    async def get_health_status(self):
        class MockStatus:
            status = "healthy"
            error_rate = 0.02

            class MockSys:
                cpu_percent = 50
                memory_percent = 40

            system_metrics = MockSys()

        return MockStatus()


class MockMetricsCollector:
    """Mock metrics collector for standalone operation."""

    def __init__(self):
        self._summary = {
            "dependency_staleness_days": 30,
            "code_coverage": 85,
            "max_cyclomatic_complexity": 8,
            "technical_debt_ratio": 0.05,
            "security_vulnerabilities": 0,
            "security_patches_applied": True,
        }

    async def get_metrics_summary(self):
        return self._summary


class HealthAssessmentRunner:
    """Health assessment runner that coordinates all health monitoring components."""

    def __init__(self, config_path: str = "maintenance.yml"):
        self.config_path = config_path
        self.health_monitor: Optional[Any] = None
        self.metrics_collector: Optional[Any] = None
        self.health_scoring: Optional[HealthScoring] = None

    async def initialize_components(self) -> None:
        """Initialize health monitoring components."""
        try:
            # Try to use real components first
            try:
                self.health_monitor = HealthMonitor(
                    coordinator=None,  # For assessment purposes, we don't need full coordinator
                    metrics_retention_minutes=60,
                    health_check_interval=30.0,
                )
                print("✅ Initialized HealthMonitor")
            except Exception:
                self.health_monitor = MockHealthMonitor()
                print("⚠️ Using MockHealthMonitor")

            try:
                self.metrics_collector = MetricsCollector(
                    application_coordinator=None,  # For assessment purposes
                    retention_hours=24,
                    collection_interval=30.0,
                )
                print("✅ Initialized MetricsCollector")
            except Exception:
                self.metrics_collector = MockMetricsCollector()
                print("⚠️ Using MockMetricsCollector")

            # Initialize health scoring system
            self.health_scoring = HealthScoring(
                health_monitor=self.health_monitor,
                metrics_collector=self.metrics_collector,
                config_path=self.config_path,
            )
            print("✅ Initialized HealthScoring system")

        except Exception as e:
            print(f"❌ Error initializing components: {e}")
            raise

    async def run_assessment(self) -> Dict[str, Any]:
        """Run comprehensive health assessment."""
        if not self.health_scoring:
            raise RuntimeError("Health scoring system not initialized")

        print("🔍 Running comprehensive health assessment...")

        try:
            # Calculate health scores
            health_result = await self.health_scoring.calculate_health_score()
            print(f"✅ Health assessment completed - Score: {health_result['composite_score']}")

            # Add metadata
            assessment_result = {
                "timestamp": health_result.get("timestamp") or "N/A",
                "composite_score": health_result["composite_score"],
                "component_scores": {
                    "dependency_health": health_result["dependency_score"],
                    "code_quality": health_result["code_quality_score"],
                    "security": health_result["security_score"],
                    "performance": health_result["performance_score"],
                    "system_health": health_result["system_score"],
                },
                "recommendations": health_result["recommendations"],
                "assessment_metadata": {
                    "config_path": self.config_path,
                    "components_used": {
                        "health_monitor": type(self.health_monitor).__name__,
                        "metrics_collector": type(self.metrics_collector).__name__,
                        "health_scoring": "HealthScoring",
                    },
                },
            }

            return assessment_result

        except Exception as e:
            print(f"❌ Error during health assessment: {e}")
            raise

    async def save_reports(self, assessment_result: Dict[str, Any], output_path: str) -> None:
        """Save assessment results to files for workflow consumption."""
        try:
            # Ensure output directory exists
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)

            # Save main assessment report
            with open(output_path, "w") as f:
                json.dump(assessment_result, f, indent=2)
            print(f"✅ Saved assessment report to {output_path}")

            # Save individual component files for easy workflow consumption
            reports_dir = output_dir

            # Health score for easy reading
            with open(reports_dir / "health_score.txt", "w") as f:
                f.write(str(int(assessment_result["composite_score"] * 100)))

            # Maintenance needed flag
            needs_maintenance = assessment_result["composite_score"] < 0.8
            with open(reports_dir / "maintenance_needed.txt", "w") as f:
                f.write("true" if needs_maintenance else "false")

            # Urgency level
            score = assessment_result["composite_score"]
            if score < 0.5:
                urgency = "critical"
            elif score < 0.7:
                urgency = "high"
            elif score < 0.8:
                urgency = "medium"
            else:
                urgency = "low"

            with open(reports_dir / "urgency_level.txt", "w") as f:
                f.write(urgency)

            # Project health JSON for detailed analysis
            project_health = {
                "overall_score": assessment_result["composite_score"],
                "component_scores": assessment_result["component_scores"],
                "recommendations": assessment_result["recommendations"],
                "assessment_date": assessment_result["timestamp"],
                "needs_maintenance": needs_maintenance,
                "urgency_level": urgency,
            }

            with open(reports_dir / "project_health.json", "w") as f:
                json.dump(project_health, f, indent=2)

            print(f"✅ Saved workflow reports to {reports_dir}")

        except Exception as e:
            print(f"❌ Error saving reports: {e}")
            raise


async def main():
    """Main entry point for health assessment."""
    parser = argparse.ArgumentParser(description="Run comprehensive health assessment for systematic maintenance")
    parser.add_argument(
        "--output", default="reports/health_assessment.json", help="Output file path for assessment results"
    )
    parser.add_argument("--config", default="maintenance.yml", help="Path to maintenance configuration file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    if args.verbose:
        print("🚀 Starting Health Assessment Runner")
        print(f"Configuration: {args.config}")
        print(f"Output: {args.output}")

    try:
        # Initialize and run assessment
        runner = HealthAssessmentRunner(config_path=args.config)
        await runner.initialize_components()

        # Run the assessment
        result = await runner.run_assessment()

        # Save results
        await runner.save_reports(result, args.output)

        # Print summary
        score = result["composite_score"]
        print("\n🎯 Health Assessment Summary:")
        print(f"   Overall Score: {score:.2f}")
        print(f"   Recommendations: {len(result['recommendations'])} items")

        # Exit with appropriate code
        if score < 0.5:
            print("❌ Critical health issues detected")
            sys.exit(2)
        elif score < 0.8:
            print("⚠️ Maintenance recommended")
            sys.exit(1)
        else:
            print("✅ System health is good")
            sys.exit(0)

    except Exception as e:
        print(f"❌ Health assessment failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    asyncio.run(main())
