import dataclasses
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Union

from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)


def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert a dataclass object to a dictionary, handling enums."""
    if dataclasses.is_dataclass(obj):
        result = []
        for f in dataclasses.fields(obj):
            value = _dataclass_to_dict(getattr(obj, f.name))
            result.append((f.name, value))
        return dict(result)
    elif isinstance(obj, tuple) and hasattr(obj, "_fields"):  # namedtuple
        return type(obj)(*[_dataclass_to_dict(v) for v in obj])
    elif isinstance(obj, (list, tuple)):
        return type(obj)(_dataclass_to_dict(v) for v in obj)
    elif isinstance(obj, dict):
        return type(obj)((_dataclass_to_dict(k), _dataclass_to_dict(v)) for k, v in obj.items())
    elif isinstance(obj, Enum):
        return obj.value
    else:
        return obj


class AuditLogger:
    """
    Logs detailed audit trails for safety-critical operations.
    """

    def __init__(self, log_dir: Union[str, Path] = "./logs/audit", privacy_preserving: bool = True) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.privacy_preserving = privacy_preserving
        self.log_file_path = self.log_dir / "safety_audit.log"
        logger.info(f"Audit logger initialized. Logging to: {self.log_file_path}")

    def _sanitize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitizes data to remove potentially sensitive information."""
        if not self.privacy_preserving:
            return data

        sanitized = data.copy()
        if "context" in sanitized and "prompt" in sanitized.get("context", {}):
            sanitized["context"]["prompt"] = f"<{len(sanitized['context']['prompt'])} chars>"
        if "file_content" in sanitized:
            sanitized["file_content"] = f"<{len(sanitized['file_content'])} bytes>"
        if "diff" in sanitized:
            sanitized["diff"] = f"<{len(sanitized['diff'])} chars>"

        if "target_files" in sanitized and isinstance(sanitized.get("target_files"), list):
            sanitized["target_files"] = f"<{len(sanitized['target_files'])} files>"

        return sanitized

    def _write_log(self, event_type: str, data: Dict[str, Any]) -> None:
        """Writes a structured log entry to the audit log file."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "data": self._sanitize_data(data),
        }
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except IOError as e:
            logger.error(f"Failed to write to audit log {self.log_file_path}: {e}")

    def log_operation_start(
        self,
        operation_id: str,
        operation_context: Dict[str, Any],
        target_files: List[str],
    ) -> None:
        """Logs the start of a safety-monitored operation."""
        data = {
            "operation_id": operation_id,
            "context": operation_context,
            "target_files": target_files,
        }
        self._write_log("operation_start", data)

    def log_pre_execution_check(self, operation_id: str, result: Any) -> None:
        """Logs the result of a pre-execution safety check."""
        from aider_mcp_server.atoms.utils.safety_system_manager import PreExecutionResult

        if isinstance(result, PreExecutionResult):
            data = {
                "operation_id": operation_id,
                "is_safe": result.is_safe,
                "reason": result.reason,
                "details": result.details,
                "risk_assessment": _dataclass_to_dict(result.risk_assessment),
            }
            self._write_log("pre_execution_check", data)

    def log_checkpoint_creation(self, operation_id: str, result: Any) -> None:
        """Logs the creation of a safety checkpoint."""
        from aider_mcp_server.atoms.utils.safety_system_manager import CheckpointResult

        if isinstance(result, CheckpointResult):
            data = {
                "operation_id": operation_id,
                "success": result.success,
                "checkpoint_id": result.checkpoint_id,
                "error_message": result.error_message,
            }
            self._write_log("checkpoint_creation", data)

    def log_failure_detection(self, operation_id: str, result: Any) -> None:
        """Logs the result of failure detection."""
        if result:
            data = {
                "operation_id": operation_id,
                "has_failures": getattr(result, "has_failures", False),
                "requires_rollback": getattr(result, "requires_rollback", False),
                "failure_summary": getattr(result, "failure_summary", None),
                "details": getattr(result, "details", {}),
            }
            self._write_log("failure_detection", data)

    def log_rollback(self, operation_id: str, result: Any) -> None:
        """Logs a rollback action."""
        if result:
            data = {
                "operation_id": operation_id,
                "success": getattr(result, "success", False),
                "rollback_type": getattr(result, "rollback_type", None),
                "checkpoint_id": getattr(result, "checkpoint_id", None),
                "error_message": getattr(result, "error_message", None),
            }
            self._write_log("rollback", data)

    def log_recovery_guidance(self, operation_id: str, result: Any) -> None:
        """Logs the generation of recovery guidance."""
        if result:
            data = {
                "operation_id": operation_id,
                "has_guidance": getattr(result, "has_guidance", False),
                "recommendations_count": getattr(result, "total_recommendations", 0),
                "summary": getattr(result, "detection_summary", None),
            }
            self._write_log("recovery_guidance", data)

    def log_operation_complete(self, operation_id: str, result: Any) -> None:
        """Logs the completion of a safety-monitored operation."""
        from aider_mcp_server.atoms.utils.safety_system_manager import SafetyOperationResult

        if isinstance(result, SafetyOperationResult):
            data = {
                "operation_id": operation_id,
                "success": result.success,
                "checkpoint_id": result.checkpoint_id,
                "error_message": result.error_message,
                "performance_metrics": result.performance_metrics,
            }
            self._write_log("operation_complete", data)
