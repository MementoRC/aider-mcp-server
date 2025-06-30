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
    # Import the existing health score calculator
    sys.path.append(str(Path(__file__).parent))
    from calculate_health_score import HealthScoreCalculator
except ImportError as e:
    print(f"Warning: Could not import health score calculator: {e}")
    print("Health assessment cannot run without HealthScoreCalculator")
    sys.exit(1)


class HealthAssessmentRunner:
    """Health assessment runner that coordinates all health monitoring components."""

    def __init__(self, config_path: str = "maintenance.yml"):
        self.config_path = config_path
        self.health_score_calculator: Optional[HealthScoreCalculator] = None

    async def initialize_components(self) -> None:
        """Initialize health monitoring components."""
        try:
            # Initialize the comprehensive health score calculator
            project_root = Path(__file__).parent.parent  # Go up from scripts/ to project root
            self.health_score_calculator = HealthScoreCalculator(str(project_root))
            print("✅ Initialized HealthScoreCalculator system")

        except Exception as e:
            print(f"❌ Error initializing components: {e}")
            raise

    async def run_assessment(self) -> Dict[str, Any]:
        """Run comprehensive health assessment."""
        if not self.health_score_calculator:
            raise RuntimeError("Health score calculator not initialized")

        print("🔍 Running comprehensive health assessment...")

        try:
            # Calculate comprehensive health scores
            health_result = await self.health_score_calculator.calculate_comprehensive_health_score()
            print(f"✅ Health assessment completed - Score: {health_result['overall_score']}")

            # Transform the result to match expected format
            assessment_result = {
                "timestamp": health_result.get("calculated_at", "N/A"),
                "overall_score": health_result["overall_score"],
                "status": "healthy" if health_result["overall_score"] >= 80 else "needs_maintenance",
                "component_scores": health_result["component_scores"],
                "recommendations": health_result.get("recommendations", []),
                "assessment_metadata": {
                    "config_path": self.config_path,
                    "urgency_level": health_result.get("urgency_level", "unknown"),
                    "maintenance_needed": health_result.get("maintenance_needed", False),
                    "monitoring_context": health_result.get("monitoring_context", {}),
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
                f.write(str(int(assessment_result["overall_score"])))

            # Maintenance needed flag
            needs_maintenance = assessment_result["assessment_metadata"]["maintenance_needed"]
            with open(reports_dir / "maintenance_needed.txt", "w") as f:
                f.write("true" if needs_maintenance else "false")

            # Urgency level
            urgency = assessment_result["assessment_metadata"]["urgency_level"]
            with open(reports_dir / "urgency_level.txt", "w") as f:
                f.write(urgency)

            # Project health JSON for detailed analysis
            project_health = {
                "overall_score": assessment_result["overall_score"],
                "status": assessment_result["status"],
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
        score = result["overall_score"]
        print("\n🎯 Health Assessment Summary:")
        print(f"   Overall Score: {score:.1f}/100")
        print(f"   Status: {result['status']}")
        print(f"   Recommendations: {len(result['recommendations'])} items")

        # Exit with appropriate code
        if score < 50:
            print("❌ Critical health issues detected")
            sys.exit(2)
        elif score < 80:
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
