import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.molecules.monitoring.metrics_collector import (
    MetricType,
    MetricsCollector,
)

logger = get_logger(__name__)


class AuditAnalytics:
    """
    Processes audit logs to generate analytics and insights.
    """

    def __init__(
        self,
        log_dir: Union[str, Path] = "./logs/audit",
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        self.log_dir = Path(log_dir)
        self.log_file_path = self.log_dir / "safety_audit.log"
        self.metrics_collector = metrics_collector
        self.audit_data: List[Dict[str, Any]] = []

    def load_audit_data(self) -> bool:
        """Loads audit data from the log file."""
        if not self.log_file_path.exists():
            logger.warning(f"Audit log file not found: {self.log_file_path}")
            return False

        try:
            with open(self.log_file_path, "r", encoding="utf-8") as f:
                self.audit_data = [json.loads(line) for line in f if line.strip()]
            logger.info(f"Loaded {len(self.audit_data)} audit log entries.")
            return True
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load or parse audit log file {self.log_file_path}: {e}")
            self.audit_data = []
            return False

    def analyze_failure_patterns(self) -> Dict[str, Any]:
        """Analyzes failure patterns from the audit data."""
        if not self.audit_data:
            self.load_audit_data()
        if not self.audit_data:
            return {"total_failures": 0, "failure_reasons": {}}

        failures = [
            e["data"]
            for e in self.audit_data
            if e.get("event_type") == "failure_detection" and e.get("data", {}).get("has_failures")
        ]

        total_failures = len(failures)
        failure_reasons = defaultdict(int)

        for failure_data in failures:
            summary = failure_data.get("failure_summary")
            if summary:
                reasons = [r.strip() for r in summary.split(";") if r.strip()]
                for reason in reasons:
                    failure_reasons[reason] += 1

        return {
            "total_failures": total_failures,
            "failure_reasons": dict(failure_reasons),
        }

    def analyze_model_safety(self) -> Dict[str, Any]:
        """Compares safety metrics across different models."""
        if not self.audit_data:
            self.load_audit_data()
        if not self.audit_data:
            return {}

        ops = {
            e["data"]["operation_id"]: e["data"]
            for e in self.audit_data
            if e.get("event_type") == "operation_start" and "operation_id" in e.get("data", {})
        }
        failures = {
            e["data"]["operation_id"]
            for e in self.audit_data
            if e.get("event_type") == "failure_detection"
            and e.get("data", {}).get("has_failures")
            and "operation_id" in e.get("data", {})
        }
        risks = {
            e["data"]["operation_id"]: e["data"]
            for e in self.audit_data
            if e.get("event_type") == "pre_execution_check" and "operation_id" in e.get("data", {})
        }

        model_safety = defaultdict(lambda: {"operations": 0, "failures": 0, "risk_scores": []})

        for op_id, op_data in ops.items():
            model = op_data.get("context", {}).get("model", "unknown")
            model_safety[model]["operations"] += 1

            if op_id in failures:
                model_safety[model]["failures"] += 1

            risk_data = risks.get(op_id)
            if risk_data:
                risk_assessment = risk_data.get("risk_assessment")
                if isinstance(risk_assessment, dict):
                    risk_score = risk_assessment.get("total_score")
                    if risk_score is not None:
                        model_safety[model]["risk_scores"].append(risk_score)

        report = {}
        for model, data in model_safety.items():
            report[model] = {
                "total_operations": data["operations"],
                "total_failures": data["failures"],
                "failure_rate": (data["failures"] / data["operations"]) if data["operations"] > 0 else 0,
                "average_risk_score": (
                    statistics.mean(data["risk_scores"]) if data["risk_scores"] else None
                ),
            }

        return report

    def analyze_performance(self) -> Dict[str, Any]:
        """Analyzes performance metrics from operation completion logs."""
        if not self.audit_data:
            self.load_audit_data()
        if not self.audit_data:
            return {}

        perf_events = [
            e["data"]
            for e in self.audit_data
            if e.get("event_type") == "operation_complete"
            and "performance_metrics" in e.get("data", {})
        ]

        durations = [
            p["performance_metrics"]["total_duration"]
            for p in perf_events
            if p.get("performance_metrics") and "total_duration" in p.get("performance_metrics", {})
        ]

        if not durations:
            return {}

        return {
            "average_duration": statistics.mean(durations),
            "median_duration": statistics.median(durations),
            "max_duration": max(durations),
            "min_duration": min(durations),
            "total_operations": len(durations),
        }

    async def publish_metrics(self):
        """Publishes key analytics to the MetricsCollector."""
        if not self.metrics_collector:
            logger.warning("MetricsCollector not configured, skipping metric publication.")
            return

        failure_analysis = self.analyze_failure_patterns()
        await self.metrics_collector.record_metric(
            name="safety.failures.total",
            value=failure_analysis.get("total_failures", 0),
            metric_type=MetricType.GAUGE,
        )

        model_safety = self.analyze_model_safety()
        for model, data in model_safety.items():
            labels = {"model": model}
            await self.metrics_collector.record_metric(
                name="safety.operations.total",
                value=data.get("total_operations", 0),
                metric_type=MetricType.GAUGE,
                labels=labels,
            )
            await self.metrics_collector.record_metric(
                name="safety.model.failure_rate",
                value=data.get("failure_rate", 0),
                metric_type=MetricType.GAUGE,
                labels=labels,
            )
            if data.get("average_risk_score") is not None:
                await self.metrics_collector.record_metric(
                    name="safety.model.avg_risk_score",
                    value=data.get("average_risk_score"),
                    metric_type=MetricType.GAUGE,
                    labels=labels,
                )

        performance = self.analyze_performance()
        if performance:
            await self.metrics_collector.record_metric(
                name="safety.performance.avg_duration_seconds",
                value=performance.get("average_duration", 0),
                metric_type=MetricType.GAUGE,
            )

        logger.info("Published audit analytics to MetricsCollector.")

    def generate_report(self, format: str = "dict") -> Union[str, Dict[str, Any]]:
        """Generates a comprehensive analytics report."""
        self.load_audit_data()

        report_data = {
            "summary": {
                "total_log_entries": len(self.audit_data),
                "log_file": str(self.log_file_path),
            },
            "failure_patterns": self.analyze_failure_patterns(),
            "model_safety_comparison": self.analyze_model_safety(),
            "performance_analytics": self.analyze_performance(),
        }

        if format == "json":
            return json.dumps(report_data, indent=2)
        elif format == "text":
            text_report = "Safety Audit Analytics Report\n"
            text_report += "=============================\n\n"
            text_report += f"Log Entries: {report_data['summary']['total_log_entries']}\n"
            text_report += f"Log File: {report_data['summary']['log_file']}\n\n"

            text_report += "Performance:\n"
            perf = report_data["performance_analytics"]
            if perf:
                text_report += f"  - Average Duration: {perf.get('average_duration', 0):.2f}s\n"
                text_report += f"  - Total Operations: {perf.get('total_operations', 0)}\n\n"
            else:
                text_report += "  - No performance data.\n\n"

            text_report += "Failures:\n"
            fails = report_data["failure_patterns"]
            text_report += f"  - Total Failures: {fails.get('total_failures', 0)}\n\n"

            text_report += "Model Safety:\n"
            model_safety = report_data["model_safety_comparison"]
            if model_safety:
                for model, data in model_safety.items():
                    text_report += f"  - Model: {model}\n"
                    text_report += f"    - Operations: {data['total_operations']}\n"
                    text_report += f"    - Failures: {data['total_failures']}\n"
                    text_report += f"    - Failure Rate: {data['failure_rate']:.2%}\n"
                    if data["average_risk_score"] is not None:
                        text_report += f"    - Avg Risk Score: {data['average_risk_score']:.2f}\n"
            else:
                text_report += "  - No model safety data.\n\n"

            return text_report
        else:
            return report_data
