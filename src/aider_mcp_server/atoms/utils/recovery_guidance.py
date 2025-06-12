"""
Recovery Guidance System for Aider Safety Operations.

Provides comprehensive recovery guidance after failures, including failure analysis,
alternative approach suggestions, manual override options, and support escalation information.
Integrates with existing safety infrastructure to help users understand and recover from issues.

Features:
- Root cause failure analysis
- Alternative approach recommendations
- Manual override instructions for experienced users
- Support escalation information and debugging details
- Integration with FailureDetector and AutomaticRollbackManager
- Human-readable guidance messages

Author: Aider MCP Server Team
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.utils.automatic_rollback import RollbackResult
from aider_mcp_server.atoms.utils.failure_detector import FailureDetectionResult, FailureType

logger = get_logger(__name__)


class RecoveryGuidanceError(Exception):
    """Base exception for recovery guidance operations."""

    pass


class GuidanceType(Enum):
    """Types of recovery guidance that can be provided."""

    FAILURE_ANALYSIS = "failure_analysis"
    ALTERNATIVE_APPROACHES = "alternative_approaches"
    MANUAL_OVERRIDE = "manual_override"
    SUPPORT_ESCALATION = "support_escalation"


class GuidancePriority(Enum):
    """Priority levels for guidance recommendations."""

    CRITICAL = "critical"  # Must be addressed immediately
    HIGH = "high"  # Should be addressed soon
    MEDIUM = "medium"  # Important but not urgent
    LOW = "low"  # Optional or informational


@dataclass
class GuidanceItem:
    """Represents a single guidance recommendation."""

    guidance_type: GuidanceType
    priority: GuidancePriority
    title: str
    description: str
    action_steps: List[str]
    related_files: List[str]
    details: Dict[str, Any]
    warning_level: Optional[str] = None


@dataclass
class RecoveryGuidanceResult:
    """Complete result of recovery guidance generation."""

    has_guidance: bool
    failure_summary: str
    rollback_summary: str
    guidance_items: List[GuidanceItem]
    formatted_message: str
    total_recommendations: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    next_steps_summary: str

    def __post_init__(self) -> None:
        """Calculate statistics after initialization."""
        self.critical_count = sum(1 for g in self.guidance_items if g.priority == GuidancePriority.CRITICAL)
        self.high_count = sum(1 for g in self.guidance_items if g.priority == GuidancePriority.HIGH)
        self.medium_count = sum(1 for g in self.guidance_items if g.priority == GuidancePriority.MEDIUM)
        self.low_count = sum(1 for g in self.guidance_items if g.priority == GuidancePriority.LOW)
        self.total_recommendations = len(self.guidance_items)
        self.has_guidance = self.total_recommendations > 0


class RecoveryGuidanceManager:
    """
    Manages recovery guidance generation for Aider safety operations.

    Provides comprehensive recovery guidance after failures, helping users understand
    what went wrong and how to proceed safely. Integrates with existing safety systems
    to provide contextual, actionable recommendations.

    Usage:
        manager = RecoveryGuidanceManager(repo_path)
        guidance = manager.generate_recovery_guidance(
            failure_detection=failure_result,
            rollback_result=rollback_result,
            operation_params={"model": "gpt-4", "files": ["src/test.py"]}
        )
        print(guidance.formatted_message)
    """

    def __init__(
        self,
        repo_path: str,
        enable_manual_overrides: bool = True,
        include_debug_info: bool = True,
        max_alternative_suggestions: int = 5,
    ):
        """
        Initialize the recovery guidance manager.

        Args:
            repo_path: Path to the git repository
            enable_manual_overrides: Enable manual override options
            include_debug_info: Include detailed debugging information
            max_alternative_suggestions: Maximum number of alternative suggestions
        """
        self.repo_path = os.path.abspath(repo_path)
        self.enable_manual_overrides = enable_manual_overrides
        self.include_debug_info = include_debug_info
        self.max_alternative_suggestions = max_alternative_suggestions

        logger.info(
            f"Initialized RecoveryGuidanceManager for {repo_path} "
            f"(overrides={enable_manual_overrides}, debug={include_debug_info})"
        )

    def generate_recovery_guidance(
        self,
        failure_detection: FailureDetectionResult,
        rollback_result: Optional[RollbackResult] = None,
        operation_params: Optional[Dict[str, Any]] = None,
        operation_context: Optional[str] = None,
    ) -> RecoveryGuidanceResult:
        """
        Generate comprehensive recovery guidance.

        Args:
            failure_detection: Results from FailureDetector
            rollback_result: Optional results from AutomaticRollbackManager
            operation_params: Optional parameters of the failed operation
            operation_context: Optional context about what was being attempted

        Returns:
            Complete recovery guidance results
        """
        logger.info("Generating recovery guidance for detected failures")

        guidance_items: List[GuidanceItem] = []

        # Generate failure analysis
        failure_analysis_items = self.analyze_failures(failure_detection, operation_params)
        guidance_items.extend(failure_analysis_items)

        # Generate alternative approaches
        alternative_items = self.suggest_alternatives(failure_detection, operation_params)
        guidance_items.extend(alternative_items)

        # Generate manual override options (if enabled)
        if self.enable_manual_overrides:
            override_items = self.provide_override_options(failure_detection, rollback_result)
            guidance_items.extend(override_items)

        # Generate support escalation information
        support_items = self.generate_support_info(failure_detection, rollback_result, operation_params)
        guidance_items.extend(support_items)

        # Create summary strings
        failure_summary = self._create_failure_summary(failure_detection)
        rollback_summary = self._create_rollback_summary(rollback_result)
        next_steps_summary = self._create_next_steps_summary(guidance_items)

        # Format the complete message
        formatted_message = self._format_guidance_message(
            failure_summary, rollback_summary, guidance_items, next_steps_summary
        )

        result = RecoveryGuidanceResult(
            has_guidance=False,  # Will be calculated in __post_init__
            failure_summary=failure_summary,
            rollback_summary=rollback_summary,
            guidance_items=guidance_items,
            formatted_message=formatted_message,
            total_recommendations=0,  # Will be calculated in __post_init__
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            next_steps_summary=next_steps_summary,
        )

        logger.info(f"Recovery guidance generated: {result.total_recommendations} recommendations")
        if result.critical_count > 0:
            logger.warning(f"Critical guidance items: {result.critical_count}")

        return result

    def analyze_failures(
        self, failure_detection: FailureDetectionResult, operation_params: Optional[Dict[str, Any]] = None
    ) -> List[GuidanceItem]:
        """
        Analyze failures to explain what went wrong and why.

        Args:
            failure_detection: Results from FailureDetector
            operation_params: Optional parameters of the failed operation

        Returns:
            List of failure analysis guidance items
        """
        analysis_items = []

        for trigger in failure_detection.triggers:
            # Determine priority based on severity
            if trigger.severity.value == "critical":
                priority = GuidancePriority.CRITICAL
            elif trigger.severity.value == "high":
                priority = GuidancePriority.HIGH
            elif trigger.severity.value == "medium":
                priority = GuidancePriority.MEDIUM
            else:
                priority = GuidancePriority.LOW

            # Generate analysis based on failure type
            if trigger.failure_type == FailureType.EMPTY_FILES:
                analysis_items.append(
                    GuidanceItem(
                        guidance_type=GuidanceType.FAILURE_ANALYSIS,
                        priority=priority,
                        title="File Content Loss Detected",
                        description=f"Files became empty during operation: {', '.join(trigger.affected_files)}",
                        action_steps=[
                            "Verify if this was intentional file deletion",
                            "Check if backup content exists in git history",
                            "Review the operation prompt for file deletion instructions",
                        ],
                        related_files=trigger.affected_files,
                        details={"root_cause": "File processing resulted in empty files"},
                        warning_level="critical",
                    )
                )

        logger.debug(f"Generated {len(analysis_items)} failure analysis items")
        return analysis_items

    def suggest_alternatives(
        self, failure_detection: FailureDetectionResult, operation_params: Optional[Dict[str, Any]] = None
    ) -> List[GuidanceItem]:
        """
        Suggest alternative approaches to achieve the same goals safely.

        Args:
            failure_detection: Results from FailureDetector
            operation_params: Optional parameters of the failed operation

        Returns:
            List of alternative approach guidance items
        """
        alternative_items = []

        # General alternative suggestions based on failure patterns
        failure_types = {t.failure_type for t in failure_detection.triggers}

        if FailureType.EMPTY_FILES in failure_types or FailureType.CONTENT_LOSS in failure_types:
            alternative_items.append(
                GuidanceItem(
                    guidance_type=GuidanceType.ALTERNATIVE_APPROACHES,
                    priority=GuidancePriority.HIGH,
                    title="Use More Conservative File Operations",
                    description="Consider smaller, incremental changes to reduce the risk of content loss.",
                    action_steps=[
                        "Break the operation into smaller, focused tasks",
                        "Modify one file at a time instead of batch operations",
                        "Use explicit backup instructions in prompts",
                    ],
                    related_files=[],
                    details={"strategy": "Incremental changes with explicit preservation"},
                )
            )

        logger.debug(f"Generated {len(alternative_items)} alternative approach items")
        return alternative_items

    def provide_override_options(
        self, failure_detection: FailureDetectionResult, rollback_result: Optional[RollbackResult] = None
    ) -> List[GuidanceItem]:
        """
        Provide manual override options for experienced users.

        Args:
            failure_detection: Results from FailureDetector
            rollback_result: Optional results from AutomaticRollbackManager

        Returns:
            List of manual override guidance items
        """
        override_items = []

        # Only provide overrides if rollback was successful
        if rollback_result and rollback_result.success:
            override_items.append(
                GuidanceItem(
                    guidance_type=GuidanceType.MANUAL_OVERRIDE,
                    priority=GuidancePriority.LOW,
                    title="Manual Safety Override Options",
                    description="For experienced users who understand the risks and want to proceed despite failures.",
                    action_steps=[
                        "Review all failure details thoroughly",
                        "Ensure you understand the specific risks involved",
                        "Create manual backup before proceeding",
                    ],
                    related_files=[],
                    details={"warning": "Manual overrides bypass safety systems - use with extreme caution"},
                    warning_level="caution",
                )
            )

        logger.debug(f"Generated {len(override_items)} manual override items")
        return override_items

    def generate_support_info(
        self,
        failure_detection: FailureDetectionResult,
        rollback_result: Optional[RollbackResult] = None,
        operation_params: Optional[Dict[str, Any]] = None,
    ) -> List[GuidanceItem]:
        """
        Generate support escalation information for complex failures.

        Args:
            failure_detection: Results from FailureDetector
            rollback_result: Optional results from AutomaticRollbackManager
            operation_params: Optional parameters of the failed operation

        Returns:
            List of support escalation guidance items
        """
        support_items = []

        if self.include_debug_info:
            support_items.append(
                GuidanceItem(
                    guidance_type=GuidanceType.SUPPORT_ESCALATION,
                    priority=GuidancePriority.MEDIUM,
                    title="Debugging Information Collection",
                    description="Collect comprehensive debugging information for support or issue reporting.",
                    action_steps=[
                        "Document the original operation that failed",
                        "Save the complete failure detection results",
                        "Record rollback operation details",
                    ],
                    related_files=[],
                    details={"useful_for": "Support tickets, bug reports, system analysis"},
                )
            )

        logger.debug(f"Generated {len(support_items)} support escalation items")
        return support_items

    def _create_failure_summary(self, failure_detection: FailureDetectionResult) -> str:
        """Create a concise summary of detected failures."""
        if not failure_detection.has_failures:
            return "No failures detected"

        summary_parts = [
            f"Detected {len(failure_detection.triggers)} failure(s):",
            f"Critical: {failure_detection.critical_count}",
            f"High: {failure_detection.high_count}",
        ]

        if failure_detection.requires_rollback:
            summary_parts.append("(Rollback required)")

        return " ".join(summary_parts)

    def _create_rollback_summary(self, rollback_result: Optional[RollbackResult]) -> str:
        """Create a concise summary of rollback operation."""
        if not rollback_result:
            return "No rollback attempted"

        if rollback_result.success:
            return (
                f"Rollback successful: {rollback_result.rollback_type} rollback to {rollback_result.checkpoint_id[:8]}"
            )
        else:
            return f"Rollback failed: {rollback_result.rollback_type} rollback attempt failed"

    def _create_next_steps_summary(self, guidance_items: List[GuidanceItem]) -> str:
        """Create a summary of recommended next steps."""
        if not guidance_items:
            return "No specific recommendations available"

        critical_items = [g for g in guidance_items if g.priority == GuidancePriority.CRITICAL]
        if critical_items:
            return f"CRITICAL: Address {len(critical_items)} critical issues immediately"
        else:
            return f"Review {len(guidance_items)} recommendations for safer future operations"

    def _format_guidance_message(
        self,
        failure_summary: str,
        rollback_summary: str,
        guidance_items: List[GuidanceItem],
        next_steps_summary: str,
    ) -> str:
        """
        Format the complete guidance message for user display.

        Args:
            failure_summary: Summary of detected failures
            rollback_summary: Summary of rollback operation
            guidance_items: List of all guidance items
            next_steps_summary: Summary of next steps

        Returns:
            Formatted guidance message
        """
        message_lines = [
            "RECOVERY GUIDANCE",
            "=" * 50,
            "",
            "SITUATION SUMMARY:",
            f"   Failures: {failure_summary}",
            f"   Rollback: {rollback_summary}",
            f"   Guidance: {len(guidance_items)} recommendations available",
            "",
        ]

        # Group guidance items by type
        by_type: Dict[str, List[GuidanceItem]] = {}
        for item in guidance_items:
            type_name = item.guidance_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(item)

        # Add sections for each guidance type
        type_order = [
            GuidanceType.FAILURE_ANALYSIS.value,
            GuidanceType.ALTERNATIVE_APPROACHES.value,
            GuidanceType.MANUAL_OVERRIDE.value,
            GuidanceType.SUPPORT_ESCALATION.value,
        ]

        for guidance_type in type_order:
            if guidance_type in by_type:
                items = by_type[guidance_type]
                type_title = guidance_type.replace("_", " ").title()
                message_lines.append(f"{type_title.upper()}:")

                for item in items:
                    message_lines.append(f"   [{item.priority.value.upper()}] {item.title}")
                    message_lines.append(f"      {item.description}")
                    message_lines.append("")

        # Add next steps summary
        message_lines.extend(
            [
                "NEXT STEPS:",
                f"   {next_steps_summary}",
                "",
                "Remember: Review all guidance carefully before proceeding.",
            ]
        )

        return "\n".join(message_lines)

    def get_guidance_summary(self, result: RecoveryGuidanceResult) -> str:
        """
        Get a brief summary of guidance results.

        Args:
            result: Recovery guidance results

        Returns:
            Brief summary string
        """
        if not result.has_guidance:
            return "No specific guidance needed - basic troubleshooting should suffice"

        summary_parts = [
            f"{result.total_recommendations} recommendations:",
            f"Critical: {result.critical_count}",
            f"High: {result.high_count}",
        ]

        if result.critical_count > 0:
            summary_parts.append("IMMEDIATE ATTENTION REQUIRED")

        return " ".join(summary_parts)
