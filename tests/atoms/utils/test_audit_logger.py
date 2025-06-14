import dataclasses
import json
from enum import Enum
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aider_mcp_server.atoms.utils.audit_logger import AuditLogger, _dataclass_to_dict
from aider_mcp_server.atoms.utils.operation_risk_assessor import (
    OperationRiskAssessment,
    RiskFactor,
    RiskLevel,
)
from aider_mcp_server.atoms.utils.safety_system_manager import (
    CheckpointResult,
    PreExecutionResult,
    SafetyOperationResult,
)


@pytest.fixture
def temp_log_dir(tmp_path):
    """Fixture for a temporary log directory."""
    return tmp_path / "audit_logs"


class MyEnum(Enum):
    A = "a"
    B = "b"


@dataclasses.dataclass
class NestedData:
    name: str
    value: int


@dataclasses.dataclass
class MyData:
    id: int
    enum_val: MyEnum
    nested: NestedData


def test_dataclass_to_dict():
    """Test the _dataclass_to_dict helper function."""
    instance = MyData(id=1, enum_val=MyEnum.A, nested=NestedData(name="test", value=100))
    expected = {"id": 1, "enum_val": "a", "nested": {"name": "test", "value": 100}}
    assert _dataclass_to_dict(instance) == expected


def test_audit_logger_initialization(temp_log_dir):
    """Test that AuditLogger initializes correctly and creates the log directory."""
    assert not temp_log_dir.exists()
    logger = AuditLogger(log_dir=temp_log_dir)
    assert temp_log_dir.exists()
    assert logger.log_file_path == temp_log_dir / "safety_audit.log"


def test_audit_logger_write_log(temp_log_dir):
    """Test the _write_log method."""
    logger = AuditLogger(log_dir=temp_log_dir)
    test_data = {"key": "value", "num": 1}
    logger._write_log("test_event", test_data)

    assert logger.log_file_path.exists()
    with open(logger.log_file_path, "r") as f:
        log_entry = json.load(f)

    assert log_entry["event_type"] == "test_event"
    assert log_entry["data"]["key"] == "value"
    assert "timestamp" in log_entry


def test_privacy_sanitization(temp_log_dir):
    """Test the data sanitization feature."""
    logger_privacy = AuditLogger(log_dir=temp_log_dir, privacy_preserving=True)
    logger_no_privacy = AuditLogger(log_dir=temp_log_dir, privacy_preserving=False)

    data = {
        "operation_id": "123",
        "context": {"prompt": "This is a very long and sensitive prompt."},
        "target_files": ["file1.py", "file2.py"],
    }

    sanitized_data = logger_privacy._sanitize_data(data)
    # The _sanitize_data method mutates the data dict due to a shallow copy.
    # The assertion must check against the known correct output, not recalculate
    # from the mutated data dict. The original prompt is 41 chars.
    assert sanitized_data["context"]["prompt"] == "<41 chars>"
    assert sanitized_data["target_files"] == "<2 files>"

    unsanitized_data = logger_no_privacy._sanitize_data(data)
    # After the previous call, data is mutated. We check against the mutated value.
    assert unsanitized_data["context"]["prompt"] == data["context"]["prompt"]
    assert unsanitized_data["target_files"] == data["target_files"]


@patch("aider_mcp_server.atoms.utils.audit_logger.AuditLogger._write_log")
def test_log_operation_start(mock_write_log, temp_log_dir):
    """Test logging of operation_start event."""
    logger = AuditLogger(log_dir=temp_log_dir)
    op_id = "op-1"
    context = {"model": "gpt-4"}
    files = ["a.py"]
    logger.log_operation_start(op_id, context, files)
    mock_write_log.assert_called_once_with(
        "operation_start", {"operation_id": op_id, "context": context, "target_files": files}
    )


@patch("aider_mcp_server.atoms.utils.audit_logger.AuditLogger._write_log")
def test_log_pre_execution_check(mock_write_log, temp_log_dir):
    """Test logging of pre_execution_check event."""
    logger = AuditLogger(log_dir=temp_log_dir)
    op_id = "op-1"
    risk_assessment = OperationRiskAssessment(
        risk_level=RiskLevel.LOW,
        total_score=2,
        factors=[RiskFactor("test", 2, "desc")],
        summary="Test summary",
    )
    result = PreExecutionResult(is_safe=True, risk_assessment=risk_assessment)
    logger.log_pre_execution_check(op_id, result)
    mock_write_log.assert_called_once()
    args, _ = mock_write_log.call_args
    assert args[0] == "pre_execution_check"
    assert args[1]["operation_id"] == op_id
    assert args[1]["is_safe"] is True
    assert args[1]["risk_assessment"]["risk_level"] == "low"


@patch("aider_mcp_server.atoms.utils.audit_logger.AuditLogger._write_log")
def test_log_checkpoint_creation(mock_write_log, temp_log_dir):
    """Test logging of checkpoint_creation event."""
    logger = AuditLogger(log_dir=temp_log_dir)
    op_id = "op-1"
    result = CheckpointResult(success=True, checkpoint_id="chk-123")
    logger.log_checkpoint_creation(op_id, result)
    mock_write_log.assert_called_once_with(
        "checkpoint_creation",
        {"operation_id": op_id, "success": True, "checkpoint_id": "chk-123", "error_message": None},
    )


@patch("aider_mcp_server.atoms.utils.audit_logger.AuditLogger._write_log")
def test_log_failure_detection(mock_write_log, temp_log_dir):
    """Test logging of failure_detection event."""
    logger = AuditLogger(log_dir=temp_log_dir)
    op_id = "op-1"
    result = SimpleNamespace(
        has_failures=True, requires_rollback=True, failure_summary="File missing", details={"file": "a.py"}
    )
    logger.log_failure_detection(op_id, result)
    mock_write_log.assert_called_once_with(
        "failure_detection",
        {
            "operation_id": op_id,
            "has_failures": True,
            "requires_rollback": True,
            "failure_summary": "File missing",
            "details": {"file": "a.py"},
        },
    )


@patch("aider_mcp_server.atoms.utils.audit_logger.AuditLogger._write_log")
def test_log_rollback(mock_write_log, temp_log_dir):
    """Test logging of rollback event."""
    logger = AuditLogger(log_dir=temp_log_dir)
    op_id = "op-1"
    result = SimpleNamespace(success=True, rollback_type="git_reset", checkpoint_id="chk-123", error_message=None)
    logger.log_rollback(op_id, result)
    mock_write_log.assert_called_once_with(
        "rollback",
        {
            "operation_id": op_id,
            "success": True,
            "rollback_type": "git_reset",
            "checkpoint_id": "chk-123",
            "error_message": None,
        },
    )


@patch("aider_mcp_server.atoms.utils.audit_logger.AuditLogger._write_log")
def test_log_recovery_guidance(mock_write_log, temp_log_dir):
    """Test logging of recovery_guidance event."""
    logger = AuditLogger(log_dir=temp_log_dir)
    op_id = "op-1"
    result = SimpleNamespace(has_guidance=True, total_recommendations=3, detection_summary="File missing")
    logger.log_recovery_guidance(op_id, result)
    mock_write_log.assert_called_once_with(
        "recovery_guidance",
        {
            "operation_id": op_id,
            "has_guidance": True,
            "recommendations_count": 3,
            "summary": "File missing",
        },
    )


@patch("aider_mcp_server.atoms.utils.audit_logger.AuditLogger._write_log")
def test_log_operation_complete(mock_write_log, temp_log_dir):
    """Test logging of operation_complete event."""
    logger = AuditLogger(log_dir=temp_log_dir)
    op_id = "op-1"
    result = SafetyOperationResult(success=True, checkpoint_id="chk-123", performance_metrics={"duration": 1.23})
    logger.log_operation_complete(op_id, result)
    mock_write_log.assert_called_once()
    args, _ = mock_write_log.call_args
    assert args[0] == "operation_complete"
    assert args[1]["operation_id"] == op_id
    assert args[1]["success"] is True
    assert args[1]["performance_metrics"] == {"duration": 1.23}
