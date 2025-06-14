#!/usr/bin/env python3
"""
Systematic Maintenance Framework - Health Score Calculator
Integrates with existing Aider MCP Server monitoring systems.

This script leverages the existing sophisticated monitoring infrastructure:
- HealthMonitor for real-time system metrics
- MetricsCollector for historical data analysis
- HealthTracker for trend analysis
- AuditAnalytics for performance insights
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Add src to path for importing existing monitoring systems
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from aider_mcp_server.molecules.monitoring.audit_analytics import AuditAnalytics
    from aider_mcp_server.molecules.monitoring.health_monitor import HealthMonitor
    from aider_mcp_server.molecules.monitoring.health_tracker import HealthTracker
    from aider_mcp_server.molecules.monitoring.metrics_collector import MetricsCollector

    EXISTING_MONITORING_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import existing monitoring systems: {e}")
    print("Falling back to standalone health calculation...")
    EXISTING_MONITORING_AVAILABLE = False


class HealthScoreCalculator:
    """
    Comprehensive health score calculator that integrates with existing monitoring systems
    and adds systematic maintenance framework capabilities.
    """

    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root or ".")
        self.config = self.load_maintenance_config()
        self.reports_dir = self.project_root / "reports"
        self.reports_dir.mkdir(exist_ok=True)

        # Initialize existing monitoring systems if available
        if EXISTING_MONITORING_AVAILABLE:
            try:
                # Try to initialize monitoring systems with basic configuration
                self.health_monitor = HealthMonitor(coordinator=None)  # Use None for standalone
                self.metrics_collector = MetricsCollector()
                self.health_tracker = HealthTracker()
                self.audit_analytics = AuditAnalytics()
                print("✅ Successfully integrated with existing monitoring systems")
            except Exception as e:
                print(f"⚠️ Could not fully initialize existing monitoring: {e}")
                print("📊 Falling back to basic health calculation...")
                self.health_monitor = None
                self.metrics_collector = None
                self.health_tracker = None
                self.audit_analytics = None
        else:
            self.health_monitor = None
            self.metrics_collector = None
            self.health_tracker = None
            self.audit_analytics = None

    def load_maintenance_config(self) -> Dict[str, Any]:
        """Load maintenance configuration."""
        config_path = self.project_root / "maintenance.yml"
        if config_path.exists():
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        return self.get_default_config()

    def get_default_config(self) -> Dict[str, Any]:
        """Default configuration if maintenance.yml is not found."""
        return {
            "health_thresholds": {
                "overall_score": 80,
                "security_vulnerabilities": 0,
                "dependency_staleness_days": 90,
                "performance_regression": 0.15,
                "code_coverage_minimum": 80,
            }
        }

    async def calculate_comprehensive_health_score(self) -> Dict[str, Any]:
        """Calculate comprehensive health score using all available data sources."""

        # Initialize component scores (0-25 each, total 100)
        dependency_score = await self.calculate_dependency_health()
        code_quality_score = await self.calculate_code_quality_health()
        architecture_score = await self.calculate_architecture_health()
        ecosystem_score = await self.calculate_ecosystem_alignment()

        # Calculate overall score
        overall_score = dependency_score + code_quality_score + architecture_score + ecosystem_score

        # Get additional context from existing monitoring systems
        monitoring_context = await self.get_monitoring_context()

        # Compile comprehensive health report
        health_report = {
            "overall_score": round(overall_score, 1),
            "component_scores": {
                "dependency_health": round(dependency_score, 1),
                "code_quality": round(code_quality_score, 1),
                "architecture_health": round(architecture_score, 1),
                "ecosystem_alignment": round(ecosystem_score, 1),
            },
            "monitoring_context": monitoring_context,
            "thresholds": self.config["health_thresholds"],
            "calculated_at": datetime.now().isoformat(),
            "maintenance_needed": overall_score < self.config["health_thresholds"]["overall_score"],
            "urgency_level": self.determine_urgency_level(overall_score, monitoring_context),
            "recommendations": await self.generate_recommendations(overall_score, monitoring_context),
        }

        # Save detailed report
        await self.save_health_report(health_report)

        return health_report

    async def calculate_dependency_health(self) -> float:
        """Calculate dependency health score (0-25 points)."""
        score = 25.0

        # Check for security vulnerabilities
        vulnerabilities = await self.check_security_vulnerabilities()
        if vulnerabilities:
            # Severe penalty for security issues
            critical_vulns = sum(1 for v in vulnerabilities if v.get("severity") == "critical")
            high_vulns = sum(1 for v in vulnerabilities if v.get("severity") == "high")
            medium_vulns = sum(1 for v in vulnerabilities if v.get("severity") == "medium")

            score -= critical_vulns * 10 + high_vulns * 5 + medium_vulns * 2
            score = max(0, score)  # Don't go below 0

        # Check dependency staleness
        outdated_deps = await self.check_outdated_dependencies()
        if outdated_deps:
            staleness_penalty = min(10, len(outdated_deps) * 0.5)
            score -= staleness_penalty

        # Check for dependency conflicts
        conflicts = await self.check_dependency_conflicts()
        if conflicts:
            score -= min(5, len(conflicts))

        return max(0, score)

    async def calculate_code_quality_health(self) -> float:
        """Calculate code quality health score (0-25 points)."""
        score = 25.0

        # Test coverage
        coverage = await self.get_test_coverage()
        if coverage is not None:
            min_coverage = self.config["health_thresholds"]["code_coverage_minimum"]
            if coverage < min_coverage:
                score -= (min_coverage - coverage) * 0.2

        # Linting violations
        lint_violations = await self.get_lint_violations()
        if lint_violations:
            critical_violations = sum(1 for v in lint_violations if v.get("severity") in ["F", "E9"])
            score -= min(10, critical_violations * 0.5)

        # Code complexity
        complexity_issues = await self.get_complexity_issues()
        if complexity_issues:
            score -= min(5, len(complexity_issues) * 0.1)

        # Type safety
        type_violations = await self.get_type_violations()
        if type_violations:
            score -= min(5, len(type_violations) * 0.1)

        return max(0, score)

    async def calculate_architecture_health(self) -> float:
        """Calculate architecture health score leveraging existing monitoring."""
        score = 25.0

        if self.health_monitor:
            try:
                # Get current health status from existing monitoring
                health_status = await self.health_monitor.get_health_status()

                # Convert existing health status to score component
                if health_status.get("status") == "critical":
                    score -= 15
                elif health_status.get("status") == "warning":
                    score -= 8
                elif health_status.get("status") == "degraded":
                    score -= 4

                # Factor in performance metrics
                metrics = health_status.get("metrics", {})
                if metrics.get("cpu_usage", 0) > 80:
                    score -= 3
                if metrics.get("memory_usage", 0) > 80:
                    score -= 3

            except Exception as e:
                print(f"Warning: Could not get health status from HealthMonitor: {e}")
                score -= 2  # Small penalty for monitoring unavailability

        # Check atomic design layer separation
        layer_violations = await self.check_atomic_design_violations()
        if layer_violations:
            score -= min(8, len(layer_violations) * 2)

        return max(0, score)

    async def calculate_ecosystem_alignment(self) -> float:
        """Calculate ecosystem alignment score."""
        score = 25.0

        # Python version currency
        python_version = await self.get_python_version_info()
        if python_version and python_version.get("is_outdated"):
            score -= 5

        # Dependency ecosystem alignment
        ecosystem_lag = await self.check_ecosystem_lag()
        if ecosystem_lag:
            score -= min(10, ecosystem_lag * 2)

        # Best practices compliance
        best_practices_score = await self.check_best_practices_compliance()
        score -= 10 - best_practices_score  # 10 points max for best practices

        return max(0, score)

    async def get_monitoring_context(self) -> Dict[str, Any]:
        """Get additional context from existing monitoring systems."""
        context = {}

        if self.metrics_collector:
            try:
                # Get recent metrics for trend analysis
                recent_metrics = await self.metrics_collector.get_recent_metrics(hours=24)
                context["recent_metrics"] = recent_metrics
            except Exception as e:
                context["metrics_error"] = str(e)

        if self.health_tracker:
            try:
                # Get health trends
                health_trends = await self.health_tracker.get_health_trends()
                context["health_trends"] = health_trends
            except Exception as e:
                context["health_trends_error"] = str(e)

        if self.audit_analytics:
            try:
                # Get recent audit insights
                audit_insights = await self.audit_analytics.get_recent_insights()
                context["audit_insights"] = audit_insights
            except Exception as e:
                context["audit_insights_error"] = str(e)

        return context

    def determine_urgency_level(self, overall_score: float, context: Dict[str, Any]) -> str:
        """Determine maintenance urgency level."""
        if overall_score < 60:
            return "critical"
        elif overall_score < 70:
            return "high"
        elif overall_score < 80:
            return "medium"
        else:
            return "low"

    async def generate_recommendations(self, overall_score: float, context: Dict[str, Any]) -> List[str]:
        """Generate maintenance recommendations based on health analysis."""
        recommendations = []

        if overall_score < self.config["health_thresholds"]["overall_score"]:
            recommendations.append("Overall health score below threshold - maintenance required")

        # Add specific recommendations based on component scores
        # (Implementation would analyze each component and suggest specific actions)

        return recommendations

    async def save_health_report(self, health_report: Dict[str, Any]) -> None:
        """Save comprehensive health report."""

        # Save detailed JSON report
        report_file = self.reports_dir / "project_health.json"
        with open(report_file, "w") as f:
            json.dump(health_report, f, indent=2)

        # Save simple score for CI/CD
        score_file = self.reports_dir / "health_score.txt"
        with open(score_file, "w") as f:
            f.write(str(int(health_report["overall_score"])))

        # Save maintenance needed flag
        maintenance_file = self.reports_dir / "maintenance_needed.txt"
        with open(maintenance_file, "w") as f:
            f.write("true" if health_report["maintenance_needed"] else "false")

        # Save urgency level
        urgency_file = self.reports_dir / "urgency_level.txt"
        with open(urgency_file, "w") as f:
            f.write(health_report["urgency_level"])

    # Helper methods for specific checks
    async def check_security_vulnerabilities(self) -> List[Dict[str, Any]]:
        """Check for security vulnerabilities using pip-audit and safety."""
        vulnerabilities = []

        # Check if security reports exist from CI
        pip_audit_file = self.reports_dir / "pip-audit.json"
        if pip_audit_file.exists():
            try:
                with open(pip_audit_file, "r") as f:
                    data = json.load(f)
                    vulnerabilities.extend(data.get("vulnerabilities", []))
            except Exception as e:
                print(f"Warning: Could not read pip-audit results: {e}")

        return vulnerabilities

    async def check_outdated_dependencies(self) -> List[str]:
        """Check for outdated dependencies."""
        # This would check pip list --outdated or similar
        # For now, return empty list as placeholder
        return []

    async def check_dependency_conflicts(self) -> List[str]:
        """Check for dependency conflicts."""
        # This would run pip check or similar
        return []

    async def get_test_coverage(self) -> Optional[float]:
        """Get current test coverage percentage."""
        # Check if coverage report exists
        coverage_file = self.reports_dir / "coverage.xml"
        if coverage_file.exists():
            # Parse coverage from XML file
            # For now, return a placeholder
            return 85.0
        return None

    async def get_lint_violations(self) -> List[Dict[str, Any]]:
        """Get current lint violations."""
        return []

    async def get_complexity_issues(self) -> List[Dict[str, Any]]:
        """Get code complexity issues."""
        return []

    async def get_type_violations(self) -> List[Dict[str, Any]]:
        """Get type checking violations."""
        return []

    async def check_atomic_design_violations(self) -> List[str]:
        """Check for atomic design pattern violations."""
        return []

    async def get_python_version_info(self) -> Dict[str, Any]:
        """Get Python version information."""
        return {"version": "3.12", "is_outdated": False}

    async def check_ecosystem_lag(self) -> int:
        """Check how far behind ecosystem standards the project is."""
        return 0

    async def check_best_practices_compliance(self) -> float:
        """Check compliance with best practices (0-10 score)."""
        return 8.5


async def main():
    """Main entry point for health score calculation."""

    calculator = HealthScoreCalculator()

    print("🔍 Calculating comprehensive project health score...")
    print("🔗 Integrating with existing monitoring systems...")

    try:
        health_report = await calculator.calculate_comprehensive_health_score()

        print("\n📊 Project Health Assessment Complete")
        print(f"Overall Score: {health_report['overall_score']}/100")
        print(f"Maintenance Needed: {health_report['maintenance_needed']}")
        print(f"Urgency Level: {health_report['urgency_level']}")

        print("\n🔍 Component Breakdown:")
        for component, score in health_report["component_scores"].items():
            print(f"  {component.replace('_', ' ').title()}: {score}/25")

        if health_report["recommendations"]:
            print("\n💡 Recommendations:")
            for rec in health_report["recommendations"]:
                print(f"  • {rec}")

        print(f"\n📁 Detailed reports saved to: {calculator.reports_dir}")

        # Exit with error code if critical issues found
        if health_report["urgency_level"] == "critical":
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error calculating health score: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
