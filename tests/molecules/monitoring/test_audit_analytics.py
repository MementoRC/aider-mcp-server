import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from aider_mcp_server.molecules.monitoring.audit_analytics import AuditAnalytics
from aider_mcp_server.molecules.monitoring.metrics_collector import MetricType


@pytest.fixture
def temp_log_dir(tmp_path):
    """Fixture for a temporary log directory."""
    return tmp_path / "audit_analytics_logs"


@pytest.fixture
def mock_audit_log_file(temp_log_dir):
    """Fixture to create a mock audit log file with sample data."""
    log_dir = temp_log_dir
    log_dir.mkdir()
    log_file = log_dir / "safety_audit.log"

    log_data = [
        # Operation 1: gpt-4, success
        {
            "timestamp": "2023-01-01T10:00:00Z",
            "event_type": "operation_start",
            "data": {"operation_id": "op1", "context": {"model": "gpt-4"}},
        },
        {
            "timestamp": "2023-01-01T10:00:01Z",
            "event_type": "pre_execution_check",
            "data": {"operation_id": "op1", "is_safe": True, "risk_assessment": {"total_score": 5}},
        },
        {
            "timestamp": "2023-01-01T10:00:05Z",
            "event_type": "failure_detection",
            "data": {"operation_id": "op1", "has_failures": False},
        },
        {
            "timestamp": "2023-01-01T10:00:06Z",
            "event_type": "operation_complete",
            "data": {"operation_id": "op1", "success": True, "performance_metrics": {"total_duration": 6.0}},
        },
        # Operation 2: gpt-3.5, failure
        {
            "timestamp": "2023-01-01T11:00:00Z",
            "event_type": "operation_start",
            "data": {"operation_id": "op2", "context": {"model": "gpt-3.5-turbo"}},
        },
        {
            "timestamp": "2023-01-01T11:00:01Z",
            "event_type": "pre_execution_check",
            "data": {"operation_id": "op2", "is_safe": True, "risk_assessment": {"total_score": 3}},
        },
        {
            "timestamp": "2023-01-01T11:00:05Z",
            "event_type": "failure_detection",
            "data": {"operation_id": "op2", "has_failures": True, "failure_summary": "File missing; Test failed"},
        },
        {
            "timestamp": "2023-01-01T11:00:06Z",
            "event_type": "operation_complete",
            "data": {"operation_id": "op2", "success": False, "performance_metrics": {"total_duration": 6.0}},
        },
        # Operation 3: gpt-4, another success
        {
            "timestamp": "2023-01-01T12:00:00Z",
            "event_type": "operation_start",
            "data": {"operation_id": "op3", "context": {"model": "gpt-4"}},
        },
        {
            "timestamp": "2023-01-01T12:00:01Z",
            "event_type": "pre_execution_check",
            "data": {"operation_id": "op3", "is_safe": True, "risk_assessment": {"total_score": 6}},
        },
        {
            "timestamp": "2023-01-01T12:00:08Z",
            "event_type": "operation_complete",
            "data": {"operation_id": "op3", "success": True, "performance_metrics": {"total_duration": 8.0}},
        },
    ]

    with open(log_file, "w") as f:
        for entry in log_data:
            f.write(json.dumps(entry) + "\n")

    return log_file


def test_analytics_initialization(temp_log_dir):
    """Test AuditAnalytics initialization."""
    analytics = AuditAnalytics(log_dir=temp_log_dir)
    assert analytics.log_dir == temp_log_dir


def test_load_audit_data(mock_audit_log_file):
    """Test loading data from an audit log file."""
    analytics = AuditAnalytics(log_dir=mock_audit_log_file.parent)
    assert analytics.load_audit_data() is True
    assert len(analytics.audit_data) == 11
    assert analytics.audit_data[0]["event_type"] == "operation_start"


def test_analyze_failure_patterns(mock_audit_log_file):
    """Test the analysis of failure patterns."""
    analytics = AuditAnalytics(log_dir=mock_audit_log_file.parent)
    patterns = analytics.analyze_failure_patterns()
    assert patterns["total_failures"] == 1
    assert patterns["failure_reasons"] == {"File missing": 1, "Test failed": 1}


def test_analyze_model_safety(mock_audit_log_file):
    """Test the analysis of model safety metrics."""
    analytics = AuditAnalytics(log_dir=mock_audit_log_file.parent)
    safety_report = analytics.analyze_model_safety()

    assert "gpt-4" in safety_report
    assert "gpt-3.5-turbo" in safety_report

    assert safety_report["gpt-4"]["total_operations"] == 2
    assert safety_report["gpt-4"]["total_failures"] == 0
    assert safety_report["gpt-4"]["failure_rate"] == 0.0
    assert safety_report["gpt-4"]["average_risk_score"] == (5 + 6) / 2

    assert safety_report["gpt-3.5-turbo"]["total_operations"] == 1
    assert safety_report["gpt-3.5-turbo"]["total_failures"] == 1
    assert safety_report["gpt-3.5-turbo"]["failure_rate"] == 1.0
    assert safety_report["gpt-3.5-turbo"]["average_risk_score"] == 3


def test_analyze_performance(mock_audit_log_file):
    """Test the analysis of performance metrics."""
    analytics = AuditAnalytics(log_dir=mock_audit_log_file.parent)
    performance = analytics.analyze_performance()
    assert performance["total_operations"] == 3
    assert performance["average_duration"] == (6.0 + 6.0 + 8.0) / 3
    assert performance["median_duration"] == 6.0
    assert performance["max_duration"] == 8.0
    assert performance["min_duration"] == 6.0


def test_generate_report(mock_audit_log_file):
    """Test report generation in different formats."""
    analytics = AuditAnalytics(log_dir=mock_audit_log_file.parent)

    # Test dict format
    dict_report = analytics.generate_report(output_format="dict")
    assert isinstance(dict_report, dict)
    assert "summary" in dict_report
    assert "failure_patterns" in dict_report

    # Test json format
    json_report = analytics.generate_report(output_format="json")
    assert isinstance(json_report, str)
    assert json.loads(json_report)["summary"]["total_log_entries"] == 11

    # Test text format
    text_report = analytics.generate_report(output_format="text")
    assert isinstance(text_report, str)
    assert "Safety Audit Analytics Report" in text_report
    assert "Model: gpt-4" in text_report


@pytest.mark.asyncio
async def test_publish_metrics(mock_audit_log_file):
    """Test publishing analytics to the MetricsCollector."""
    mock_collector = MagicMock()
    mock_collector.record_metric = AsyncMock()

    analytics = AuditAnalytics(log_dir=mock_audit_log_file.parent, metrics_collector=mock_collector)
    await analytics.publish_metrics()

    assert mock_collector.record_metric.call_count > 0
    # Check one of the calls
    mock_collector.record_metric.assert_any_call(name="safety.failures.total", value=1, metric_type=MetricType.GAUGE)
    mock_collector.record_metric.assert_any_call(
        name="safety.model.failure_rate",
        value=1.0,
        metric_type=MetricType.GAUGE,
        labels={"model": "gpt-3.5-turbo"},
    )
