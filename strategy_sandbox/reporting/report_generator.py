import datetime
from typing import Any, Dict, List, Optional

from .artifact_manager import ArtifactManager
from .github_reporter import GitHubReporter
from .template_engine import TemplateEngine


class ReportGenerator:
    """
    Orchestrates dynamic report generation for CI pipelines, integrating
    test coverage, performance trends, and build status dashboards.
    """

    def __init__(
        self,
        github_reporter: Optional[GitHubReporter] = None,
        template_engine: Optional[TemplateEngine] = None,
        artifact_manager: Optional[ArtifactManager] = None,
    ):
        self.github_reporter = github_reporter or GitHubReporter()
        self.template_engine = template_engine or TemplateEngine()
        self.artifact_manager = artifact_manager or ArtifactManager()

    def aggregate_data(
        self,
        coverage_data: Dict[str, Any],
        performance_data: List[Dict[str, Any]],
        build_status_data: Dict[str, Any],
        additional_sources: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate data from multiple sources for comprehensive reporting.
        """
        aggregated = {
            "coverage": coverage_data,
            "performance": performance_data,
            "build_status": build_status_data,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }
        if additional_sources:
            aggregated.update(additional_sources)
        return aggregated

    def generate_coverage_summary(self, coverage_data: Dict[str, Any]) -> str:
        """
        Generate a visual summary (e.g., badge, chart) for test coverage.
        """
        percent = coverage_data.get("percent", 0)
        trend = coverage_data.get("trend", "stable")
        # Simple text-based visualization; can be replaced with SVG/chart
        summary = f"Test Coverage: {percent:.1f}% ({trend})"
        return summary

    def generate_performance_trends(self, performance_data: List[Dict[str, Any]]) -> str:
        """
        Generate performance trend visualization and regression detection.
        """
        if not performance_data:
            return "No performance data available."
        # Example: show last 5 runs and detect regression
        last_runs = performance_data[-5:]
        values = [run["value"] for run in last_runs]
        trend = "improving" if values[-1] < values[0] else "regressing" if values[-1] > values[0] else "stable"
        chart = " → ".join(f"{v:.2f}" for v in values)
        return f"Performance Trend: {chart} ({trend})"

    def generate_build_dashboard(self, build_status_data: Dict[str, Any]) -> str:
        """
        Generate a build status dashboard with actionable insights.
        """
        status = build_status_data.get("status", "unknown")
        failed_tests = build_status_data.get("failed_tests", [])
        actionable = (
            f"Action Required: {len(failed_tests)} test(s) failed." if status != "success" else "All checks passed."
        )
        return f"Build Status: {status.upper()}\n{actionable}"

    def render_report(self, aggregated_data: Dict[str, Any]) -> str:
        """
        Render the final report using the templating engine.
        """
        context = {
            "coverage_summary": self.generate_coverage_summary(aggregated_data["coverage"]),
            "performance_trends": self.generate_performance_trends(aggregated_data["performance"]),
            "build_dashboard": self.generate_build_dashboard(aggregated_data["build_status"]),
            "timestamp": aggregated_data["timestamp"],
        }
        # Use a named template for consistent formatting
        return self.template_engine.render("ci_report.html", context)

    def generate_and_publish_report(
        self,
        coverage_data: Dict[str, Any],
        performance_data: List[Dict[str, Any]],
        build_status_data: Dict[str, Any],
        additional_sources: Optional[Dict[str, Any]] = None,
        publish_to_github: bool = True,
        artifact_name: str = "ci_report.html",
    ) -> str:
        """
        High-level orchestration: aggregate data, render report, publish artifacts.
        """
        aggregated = self.aggregate_data(coverage_data, performance_data, build_status_data, additional_sources)
        report_html = self.render_report(aggregated)
        self.artifact_manager.save_artifact(artifact_name, report_html)
        if publish_to_github:
            self.github_reporter.publish_report(report_html)
        return report_html
