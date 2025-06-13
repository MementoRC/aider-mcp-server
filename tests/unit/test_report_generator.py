import pytest
from strategy_sandbox.reporting.report_generator import ReportGenerator

class DummyGitHubReporter:
    def __init__(self):
        self.published = None
    def publish_report(self, html):
        self.published = html

class DummyTemplateEngine:
    def render(self, template_name, context):
        # Simple rendering for test
        return (
            f"{context['coverage_summary']}\n"
            f"{context['performance_trends']}\n"
            f"{context['build_dashboard']}\n"
            f"Timestamp: {context['timestamp']}"
        )

class DummyArtifactManager:
    def __init__(self):
        self.saved = {}
    def save_artifact(self, name, content):
        self.saved[name] = content

@pytest.fixture
def generator():
    return ReportGenerator(
        github_reporter=DummyGitHubReporter(),
        template_engine=DummyTemplateEngine(),
        artifact_manager=DummyArtifactManager(),
    )

def test_aggregate_data(generator):
    coverage = {"percent": 85.5, "trend": "improving"}
    perf = [{"value": 1.0}, {"value": 0.9}, {"value": 0.8}]
    build = {"status": "success", "failed_tests": []}
    agg = generator.aggregate_data(coverage, perf, build)
    assert agg["coverage"] == coverage
    assert agg["performance"] == perf
    assert agg["build_status"] == build
    assert "timestamp" in agg

def test_generate_coverage_summary(generator):
    summary = generator.generate_coverage_summary({"percent": 90.0, "trend": "stable"})
    assert "90.0%" in summary
    assert "stable" in summary

def test_generate_performance_trends_improving(generator):
    perf = [{"value": 2.0}, {"value": 1.8}, {"value": 1.5}, {"value": 1.2}, {"value": 1.0}]
    summary = generator.generate_performance_trends(perf)
    assert "improving" in summary
    assert "1.00" in summary

def test_generate_performance_trends_regressing(generator):
    perf = [{"value": 1.0}, {"value": 1.2}, {"value": 1.5}, {"value": 1.8}, {"value": 2.0}]
    summary = generator.generate_performance_trends(perf)
    assert "regressing" in summary
    assert "2.00" in summary

def test_generate_performance_trends_stable(generator):
    perf = [{"value": 1.0}, {"value": 1.0}, {"value": 1.0}, {"value": 1.0}, {"value": 1.0}]
    summary = generator.generate_performance_trends(perf)
    assert "stable" in summary

def test_generate_build_dashboard_success(generator):
    build = {"status": "success", "failed_tests": []}
    dashboard = generator.generate_build_dashboard(build)
    assert "SUCCESS" in dashboard
    assert "All checks passed" in dashboard

def test_generate_build_dashboard_failure(generator):
    build = {"status": "failure", "failed_tests": ["test_a", "test_b"]}
    dashboard = generator.generate_build_dashboard(build)
    assert "FAILURE" in dashboard
    assert "2 test(s) failed" in dashboard

def test_render_report(generator):
    coverage = {"percent": 88.0, "trend": "improving"}
    perf = [{"value": 1.0}, {"value": 0.9}, {"value": 0.8}, {"value": 0.7}, {"value": 0.6}]
    build = {"status": "success", "failed_tests": []}
    agg = generator.aggregate_data(coverage, perf, build)
    report = generator.render_report(agg)
    assert "Test Coverage" in report
    assert "Performance Trend" in report
    assert "Build Status" in report

def test_generate_and_publish_report(generator):
    coverage = {"percent": 75.0, "trend": "regressing"}
    perf = [{"value": 1.0}, {"value": 1.1}, {"value": 1.2}, {"value": 1.3}, {"value": 1.4}]
    build = {"status": "failure", "failed_tests": ["test_x"]}
    generator.generate_and_publish_report(
        coverage, perf, build, publish_to_github=True, artifact_name="test_report.html"
    )
    # Check artifact saved
    assert "Test Coverage" in generator.artifact_manager.saved["test_report.html"]
    # Check published to GitHub
    assert "Test Coverage" in generator.github_reporter.published
