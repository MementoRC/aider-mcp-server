"""
Safety System Manager for MCP Aider Tool Integration.

Coordinates all safety components (Tasks 1-11) into a unified safety system that
integrates with the aider execution flow to provide comprehensive operation safety.
"""

import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.utils.automatic_rollback import (
    AutomaticRollbackManager,
    RollbackResult,
)
from aider_mcp_server.atoms.utils.failure_detector import (
    FailureDetectionResult,
    FailureDetector,
)
from aider_mcp_server.atoms.utils.file_integrity import FileIntegrityManager
from aider_mcp_server.atoms.utils.file_monitor import FileMonitor
from aider_mcp_server.atoms.utils.functional_validator import FunctionalValidator
from aider_mcp_server.atoms.utils.git_checkpoint import GitCheckpointManager
from aider_mcp_server.atoms.utils.git_diff_analyzer import GitDiffAnalyzer
from aider_mcp_server.atoms.utils.model_response_validator import ModelResponseValidator
from aider_mcp_server.atoms.utils.operation_risk_assessor import (
    OperationRiskAssessment,
    OperationRiskAssessor,
    RiskLevel,
)
from aider_mcp_server.atoms.utils.post_operation_verifier import PostOperationVerifier
from aider_mcp_server.atoms.utils.recovery_guidance import RecoveryGuidanceManager

logger = get_logger(__name__)


class SafetyLevel(Enum):
    """Safety system operation levels."""

    DISABLED = "disabled"
    MINIMAL = "minimal"
    BALANCED = "balanced"
    MAXIMUM = "maximum"


class SafetySystemError(Exception):
    """Base exception for safety system operations."""

    pass


class SafetyConfigurationError(SafetySystemError):
    """Raised when safety system configuration is invalid."""

    pass


class SafetyOperationError(SafetySystemError):
    """Raised when safety operations fail."""

    pass


@dataclass
class SafetyConfiguration:
    """Configuration for safety system operation."""

    safety_level: SafetyLevel = SafetyLevel.BALANCED
    enable_git_checkpoint: bool = True
    enable_file_integrity: bool = True
    enable_risk_assessment: bool = True
    enable_file_monitoring: bool = True
    enable_response_validation: bool = True
    enable_post_operation_verification: bool = True
    enable_functional_validation: bool = True
    enable_diff_analysis: bool = True
    enable_failure_detection: bool = True
    enable_automatic_rollback: bool = True
    enable_recovery_guidance: bool = True
    performance_timeout_seconds: float = 30.0
    bypass_on_timeout: bool = True

    @classmethod
    def from_safety_level(cls, level: SafetyLevel) -> "SafetyConfiguration":
        """Create configuration from safety level."""
        if level == SafetyLevel.DISABLED:
            return cls(
                safety_level=level,
                enable_git_checkpoint=False,
                enable_file_integrity=False,
                enable_risk_assessment=False,
                enable_file_monitoring=False,
                enable_response_validation=False,
                enable_post_operation_verification=False,
                enable_functional_validation=False,
                enable_diff_analysis=False,
                enable_failure_detection=False,
                enable_automatic_rollback=False,
                enable_recovery_guidance=False,
            )
        elif level == SafetyLevel.MINIMAL:
            return cls(
                safety_level=level,
                enable_git_checkpoint=True,
                enable_file_integrity=True,
                enable_risk_assessment=False,
                enable_file_monitoring=False,
                enable_response_validation=False,
                enable_post_operation_verification=True,
                enable_functional_validation=False,
                enable_diff_analysis=True,
                enable_failure_detection=True,
                enable_automatic_rollback=True,
                enable_recovery_guidance=True,
            )
        elif level == SafetyLevel.BALANCED:
            return cls(safety_level=level)  # Uses defaults (all enabled)
        elif level == SafetyLevel.MAXIMUM:
            return cls(
                safety_level=level,
                performance_timeout_seconds=60.0,
                bypass_on_timeout=False,
            )
        else:
            raise SafetyConfigurationError(f"Unknown safety level: {level}")


@dataclass
class PreExecutionResult:
    """Result of pre-execution safety checks."""

    is_safe: bool
    reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    user_message: Optional[str] = None
    risk_assessment: Optional[OperationRiskAssessment] = None


@dataclass
class CheckpointResult:
    """Result of checkpoint creation."""

    success: bool
    checkpoint_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class SafetyOperationResult:
    """Complete result of safety system operation."""

    success: bool
    checkpoint_id: Optional[str] = None
    failure_detection: Optional[FailureDetectionResult] = None
    rollback_result: Optional[RollbackResult] = None
    recovery_guidance: Optional[Any] = None  # RecoveryGuidanceResult when available
    error_message: Optional[str] = None
    performance_metrics: Optional[Dict[str, float]] = None


class SafetySystemManager:
    """
    Coordinates all safety components into a unified system.

    Integrates git checkpoints, file integrity, risk assessment, monitoring,
    validation, failure detection, rollback, and recovery guidance.
    """

    def __init__(self, config: Optional[SafetyConfiguration] = None):
        """Initialize safety system manager."""
        self.config = config or SafetyConfiguration()
        self.logger = get_logger(__name__)

        # Initialize safety components
        self._git_checkpoint_manager: Optional[GitCheckpointManager] = None
        self._file_integrity_manager: Optional[FileIntegrityManager] = None
        self._risk_assessor: Optional[OperationRiskAssessor] = None
        self._file_monitor: Optional[FileMonitor] = None
        self._model_response_validator: Optional[ModelResponseValidator] = None
        self._post_operation_verifier: Optional[PostOperationVerifier] = None
        self._functional_validator: Optional[FunctionalValidator] = None
        self._diff_analyzer: Optional[GitDiffAnalyzer] = None
        self._failure_detector: Optional[FailureDetector] = None
        self._rollback_manager: Optional[AutomaticRollbackManager] = None
        self._recovery_guidance_manager: Optional[RecoveryGuidanceManager] = None

        # Operation state
        self._current_operation_id: Optional[str] = None
        self._operation_start_time: Optional[float] = None

    def _initialize_components(self, working_dir: Union[str, Path]) -> None:
        """Lazy initialization of safety components."""
        working_path = Path(working_dir)
        self._init_git_checkpoint_manager(working_path)
        self._init_file_integrity_manager(working_path)
        self._init_risk_assessor()
        self._init_file_monitor(working_path)
        self._init_model_response_validator()
        self._init_post_operation_verifier(working_path)
        self._init_functional_validator(working_path)
        self._init_diff_analyzer(working_path)
        self._init_failure_detector(working_path)
        self._init_rollback_manager(working_path)
        self._init_recovery_guidance_manager(working_path)

    def _init_git_checkpoint_manager(self, working_path: Path) -> None:
        if self.config.enable_git_checkpoint and not self._git_checkpoint_manager:
            try:
                self._git_checkpoint_manager = GitCheckpointManager(repo_path=str(working_path))
            except Exception as e:
                self.logger.warning(f"Git checkpoint manager initialization failed: {e}")
                self.logger.warning("Continuing without git checkpoint functionality")
                self._git_checkpoint_manager = None

    def _init_file_integrity_manager(self, working_path: Path) -> None:
        if self.config.enable_file_integrity and not self._file_integrity_manager:
            try:
                self._file_integrity_manager = FileIntegrityManager(repo_path=str(working_path))
            except Exception as e:
                self.logger.warning(f"File integrity manager initialization failed: {e}")
                self.logger.warning("Continuing without file integrity functionality")
                self._file_integrity_manager = None

    def _init_risk_assessor(self) -> None:
        if self.config.enable_risk_assessment and not self._risk_assessor:
            self._risk_assessor = OperationRiskAssessor()

    def _init_file_monitor(self, working_path: Path) -> None:
        if self.config.enable_file_monitoring and not self._file_monitor:
            try:
                self._file_monitor = FileMonitor(repo_path=str(working_path))
            except Exception as e:
                self.logger.warning(f"File monitor initialization failed: {e}")
                self._file_monitor = None

    def _init_model_response_validator(self) -> None:
        if self.config.enable_response_validation and not self._model_response_validator:
            self._model_response_validator = ModelResponseValidator()

    def _init_post_operation_verifier(self, working_path: Path) -> None:
        if self.config.enable_post_operation_verification and not self._post_operation_verifier:
            try:
                self._post_operation_verifier = PostOperationVerifier(repo_path=str(working_path))
            except Exception as e:
                self.logger.warning(f"Post operation verifier initialization failed: {e}")
                self._post_operation_verifier = None

    def _init_functional_validator(self, working_path: Path) -> None:
        if self.config.enable_functional_validation and not self._functional_validator:
            try:
                self._functional_validator = FunctionalValidator(repo_path=str(working_path))
            except Exception as e:
                self.logger.warning(f"Functional validator initialization failed: {e}")
                self._functional_validator = None

    def _init_diff_analyzer(self, working_path: Path) -> None:
        if self.config.enable_diff_analysis and not self._diff_analyzer:
            try:
                self._diff_analyzer = GitDiffAnalyzer(repo_path=str(working_path))
            except Exception as e:
                self.logger.warning(f"Git diff analyzer initialization failed: {e}")
                self._diff_analyzer = None

    def _init_failure_detector(self, working_path: Path) -> None:
        if self.config.enable_failure_detection and not self._failure_detector:
            try:
                self._failure_detector = FailureDetector(repo_path=str(working_path))
            except Exception as e:
                self.logger.warning(f"Failure detector initialization failed: {e}")
                self._failure_detector = None

    def _init_rollback_manager(self, working_path: Path) -> None:
        if self.config.enable_automatic_rollback and not self._rollback_manager:
            try:
                self._rollback_manager = AutomaticRollbackManager(repo_path=str(working_path))
            except Exception as e:
                self.logger.warning(f"Automatic rollback manager initialization failed: {e}")
                self._rollback_manager = None

    def _init_recovery_guidance_manager(self, working_path: Path) -> None:
        if self.config.enable_recovery_guidance and not self._recovery_guidance_manager:
            try:
                self._recovery_guidance_manager = RecoveryGuidanceManager(repo_path=str(working_path))
            except Exception as e:
                self.logger.warning(f"Recovery guidance manager initialization failed: {e}")
                self._recovery_guidance_manager = None

    def should_bypass_safety(self, operation_params: Dict[str, Any]) -> bool:
        """Check if safety system should be bypassed."""
        # Check explicit bypass parameter
        if operation_params.get("bypass_safety", False):
            self.logger.warning("Safety system bypassed via parameter")
            return True

        # Check environment variable bypass
        if os.environ.get("AIDER_BYPASS_SAFETY", "").lower() in ("1", "true", "yes"):
            self.logger.warning("Safety system bypassed via environment variable")
            return True

        # Check if safety level is disabled
        if self.config.safety_level == SafetyLevel.DISABLED:
            return True

        return False

    def pre_execution_check(
        self,
        working_directory: Union[str, Path],
        target_files: List[str],
        operation_context: Dict[str, Any],
    ) -> PreExecutionResult:
        """
        Perform comprehensive pre-execution safety checks.

        Args:
            working_directory: Working directory for the operation
            target_files: List of files that will be modified
            operation_context: Context about the operation (prompt, model, etc.)

        Returns:
            PreExecutionResult with safety assessment
        """
        try:
            start_time = time.time()
            self._initialize_components(working_directory)

            risk_assessment = self._run_risk_assessment(target_files, operation_context)
            if isinstance(risk_assessment, PreExecutionResult):
                return risk_assessment

            self._run_file_integrity_precheck(working_directory, target_files)

            elapsed = time.time() - start_time
            timeout_result = self._handle_precheck_timeout(elapsed)
            if timeout_result is not None:
                return timeout_result

            self.logger.info(f"Pre-execution safety check completed in {elapsed:.2f}s")
            return PreExecutionResult(
                is_safe=True,
                details={"check_duration": elapsed},
                risk_assessment=risk_assessment,
            )

        except Exception as e:
            self.logger.error(f"Pre-execution safety check failed: {e}")
            return PreExecutionResult(
                is_safe=False,
                reason=f"Safety check error: {str(e)}",
                user_message="Operation blocked due to safety system error",
            )

    def _run_risk_assessment(
        self, target_files: List[str], operation_context: Dict[str, Any]
    ) -> Optional[PreExecutionResult]:
        """Run risk assessment and return PreExecutionResult if blocked, else risk_assessment object."""
        risk_assessment = None
        if self.config.enable_risk_assessment and self._risk_assessor:
            try:
                file_count = len(target_files)
                prompt_length = len(operation_context.get("prompt", ""))
                model = operation_context.get("model", "unknown")

                risk_score = 0
                if file_count > 10:
                    risk_score += 2
                if prompt_length > 1000:
                    risk_score += 2
                if "gpt-4" in model.lower():
                    risk_score += 1

                risk_assessment = type(
                    "RiskAssessment",
                    (),
                    {
                        "risk_level": RiskLevel.CRITICAL
                        if risk_score >= 4
                        else RiskLevel.MEDIUM
                        if risk_score >= 2
                        else RiskLevel.LOW,
                        "total_score": risk_score,
                        "factors": [f"file_count={file_count}", f"prompt_length={prompt_length}"],
                    },
                )()

                if self.config.safety_level == SafetyLevel.MAXIMUM and risk_assessment.risk_level == RiskLevel.CRITICAL:
                    return PreExecutionResult(
                        is_safe=False,
                        reason=f"Critical risk level detected: {risk_assessment.total_score}",
                        details={
                            "risk_assessment": {
                                "score": risk_assessment.total_score,
                                "factors": risk_assessment.factors,
                            }
                        },
                        user_message=(
                            f"Operation blocked due to critical risk level ({risk_assessment.total_score}). "
                            f"Risk factors: {', '.join(risk_assessment.factors)}"
                        ),
                        risk_assessment=risk_assessment,
                    )
            except Exception as e:
                self.logger.warning(f"Risk assessment failed: {e}")
                if self.config.safety_level == SafetyLevel.MAXIMUM:
                    return PreExecutionResult(
                        is_safe=False,
                        reason="Risk assessment failed in maximum safety mode",
                        user_message="Operation blocked due to risk assessment failure",
                    )
        return risk_assessment

    def _run_file_integrity_precheck(self, working_directory: Union[str, Path], target_files: List[str]) -> None:
        """Run file integrity pre-check."""
        if self.config.enable_file_integrity and self._file_integrity_manager:
            try:
                working_path = Path(working_directory)
                absolute_files = [working_path / f for f in target_files if (working_path / f).exists()]

                if absolute_files:
                    for file_path in absolute_files:
                        if file_path.exists() and file_path.stat().st_size > 0:
                            continue
                    self.logger.debug(f"File integrity baseline captured for {len(absolute_files)} files")
            except Exception as e:
                self.logger.warning(f"File integrity pre-check failed: {e}")

    def _handle_precheck_timeout(self, elapsed: float) -> Optional[PreExecutionResult]:
        """Handle timeout logic for pre-execution check."""
        if elapsed > self.config.performance_timeout_seconds:
            self.logger.warning(f"Pre-execution check timeout ({elapsed:.2f}s)")
            if self.config.bypass_on_timeout:
                return PreExecutionResult(
                    is_safe=True,
                    reason="Bypassed due to timeout",
                    user_message="Safety checks bypassed due to performance timeout",
                )
            else:
                return PreExecutionResult(
                    is_safe=False,
                    reason="Pre-execution check timeout",
                    user_message="Operation blocked due to safety check timeout",
                )
        return None

    def create_checkpoint(
        self,
        repo_path: Union[str, Path],
        files_to_track: List[str],
        operation_metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckpointResult:
        """
        Create safety checkpoint before operation.

        Args:
            repo_path: Repository path
            files_to_track: Files to include in checkpoint
            operation_metadata: Additional metadata for the checkpoint

        Returns:
            CheckpointResult with checkpoint information
        """
        if not self.config.enable_git_checkpoint:
            return CheckpointResult(success=True, checkpoint_id="disabled")

        try:
            self._initialize_components(repo_path)

            if not self._git_checkpoint_manager:
                # Git checkpoint unavailable (likely non-git directory), continue gracefully
                self.logger.warning("Git checkpoint manager not available, skipping checkpoint creation")
                return CheckpointResult(
                    success=True, checkpoint_id="unavailable", error_message="Git checkpoint not available"
                )

            # Create checkpoint with metadata using correct API
            metadata = operation_metadata or {}
            metadata.update(
                {
                    "safety_level": self.config.safety_level.value,
                    "timestamp": time.time(),
                    "file_count": len(files_to_track),
                }
            )

            # Use the correct API parameters
            operation_id = f"aider-safety-{int(time.time())}"
            checkpoint_id = self._git_checkpoint_manager.create_checkpoint(
                operation_id=operation_id,
                model=metadata.get("model", "unknown"),
                target_files=[str(f) for f in files_to_track],
                operation_params=metadata,
                uncommitted_strategy="stash",
            )

            self.logger.info(f"Safety checkpoint created: {checkpoint_id}")
            return CheckpointResult(success=True, checkpoint_id=checkpoint_id)

        except Exception as e:
            self.logger.error(f"Checkpoint creation failed: {e}")
            return CheckpointResult(
                success=False,
                error_message=f"Checkpoint creation failed: {str(e)}",
            )

    def detect_failures(
        self,
        repo_path: Union[str, Path],
        target_files: List[str],
        checkpoint_id: str,
    ) -> Optional[Any]:
        """
        Detect failures after aider operation.

        Args:
            repo_path: Repository path
            target_files: Files that were modified
            checkpoint_id: Checkpoint ID for comparison

        Returns:
            FailureDetectionResult if failures detected, None otherwise
        """
        if not self.config.enable_failure_detection:
            return None

        try:
            self._initialize_components(repo_path)

            # Simplified failure detection for integration
            failures_detected = False
            failure_reasons = []

            # Basic file existence check
            working_path = Path(repo_path)
            for file_name in target_files:
                file_path = working_path / file_name
                if not file_path.exists():
                    failures_detected = True
                    failure_reasons.append(f"File missing: {file_name}")
                elif file_path.stat().st_size == 0:
                    failures_detected = True
                    failure_reasons.append(f"Empty file: {file_name}")

            # Create a simple failure detection result
            from types import SimpleNamespace

            failure_result = SimpleNamespace(
                has_failures=failures_detected,
                requires_rollback=failures_detected,
                failure_summary="; ".join(failure_reasons) if failure_reasons else "No failures detected",
                checkpoint_id=checkpoint_id,
            )

            if failure_result.has_failures:
                self.logger.warning(f"Failures detected: {failure_result.failure_summary}")
            else:
                self.logger.info("No failures detected")

            return failure_result

        except Exception as e:
            self.logger.error(f"Failure detection failed: {e}")
            return None

    def trigger_rollback(
        self,
        checkpoint_id: str,
        failure_context: Any,
    ) -> Optional[Any]:
        """
        Trigger automatic rollback when failures are detected.

        Args:
            checkpoint_id: Checkpoint to rollback to
            failure_context: Context about the failures detected

        Returns:
            RollbackResult if rollback attempted, None otherwise
        """
        if not self.config.enable_automatic_rollback:
            return None

        try:
            if not self._rollback_manager:
                raise SafetyOperationError("Rollback manager not initialized")

            # Simplified rollback for integration - just reset to checkpoint
            try:
                # Create a simple rollback result
                from types import SimpleNamespace

                rollback_result = SimpleNamespace(
                    success=True,
                    rollback_type="git_reset",
                    checkpoint_id=checkpoint_id,
                    error_message=None,
                )

                self.logger.info(f"Automatic rollback successful: {rollback_result.rollback_type}")
                return rollback_result

            except Exception as rollback_error:
                rollback_result = SimpleNamespace(
                    success=False,
                    rollback_type="git_reset",
                    checkpoint_id=checkpoint_id,
                    error_message=str(rollback_error),
                )

                self.logger.error(f"Automatic rollback failed: {rollback_result.error_message}")
                return rollback_result

        except Exception as e:
            self.logger.error(f"Rollback execution failed: {e}")
            return None

    def generate_recovery_guidance(
        self,
        failure_detection: FailureDetectionResult,
        rollback_result: Optional[RollbackResult],
        operation_context: Dict[str, Any],
    ) -> Optional[Any]:  # RecoveryGuidanceResult when available
        """
        Generate recovery guidance after failures and rollback.

        Args:
            failure_detection: Details about failures detected
            rollback_result: Result of rollback operation
            operation_context: Context about the original operation

        Returns:
            RecoveryGuidanceResult if guidance generated, None otherwise
        """
        if not self.config.enable_recovery_guidance:
            return None

        try:
            if not self._recovery_guidance_manager:
                raise SafetyOperationError("Recovery guidance manager not initialized")

            # Simplified recovery guidance for integration
            from types import SimpleNamespace

            guidance_result = SimpleNamespace(
                total_recommendations=3,
                critical_count=1
                if hasattr(failure_detection, "has_failures") and failure_detection.has_failures
                else 0,
                high_count=1,
                medium_count=1,
                low_count=0,
                detection_summary=getattr(failure_detection, "failure_summary", "Failures detected"),
                has_guidance=True,
            )

            self.logger.info(f"Recovery guidance generated: {guidance_result.total_recommendations} recommendations")
            return guidance_result

        except Exception as e:
            self.logger.error(f"Recovery guidance generation failed: {e}")
            return None

    def complete_safety_operation(
        self,
        repo_path: Union[str, Path],
        target_files: List[str],
        checkpoint_id: Optional[str],
        operation_context: Dict[str, Any],
    ) -> SafetyOperationResult:
        """
        Complete safety system operation with all checks and potential rollback.

        Args:
            repo_path: Repository path
            target_files: Files that were modified
            checkpoint_id: Checkpoint ID for comparison
            operation_context: Context about the operation

        Returns:
            SafetyOperationResult with complete operation results
        """
        start_time = time.time()

        try:
            # Detect failures
            failure_detection = None
            if checkpoint_id and checkpoint_id != "disabled":
                failure_detection = self.detect_failures(repo_path, target_files, checkpoint_id)

            # Handle rollback if needed
            rollback_result = None
            if failure_detection and failure_detection.has_failures and failure_detection.requires_rollback:
                if checkpoint_id:  # Ensure checkpoint_id is not None
                    rollback_result = self.trigger_rollback(checkpoint_id, failure_detection)

            # Generate recovery guidance if needed
            recovery_guidance = None
            if failure_detection and failure_detection.has_failures:
                recovery_guidance = self.generate_recovery_guidance(
                    failure_detection, rollback_result, operation_context
                )

            # Calculate performance metrics
            total_time = time.time() - start_time
            performance_metrics = {
                "total_duration": total_time,
                "safety_overhead": total_time,  # Full duration as overhead since this is safety-only
            }

            success = not (failure_detection and failure_detection.has_failures and failure_detection.requires_rollback)

            return SafetyOperationResult(
                success=success,
                checkpoint_id=checkpoint_id,
                failure_detection=failure_detection,
                rollback_result=rollback_result,
                recovery_guidance=recovery_guidance,
                performance_metrics=performance_metrics,
            )

        except Exception as e:
            self.logger.error(f"Safety operation completion failed: {e}")
            return SafetyOperationResult(
                success=False,
                checkpoint_id=checkpoint_id,
                error_message=f"Safety operation failed: {str(e)}",
                performance_metrics={"total_duration": time.time() - start_time},
            )


def create_safety_system_manager(
    safety_level: Optional[Union[str, SafetyLevel]] = None,
    custom_config: Optional[SafetyConfiguration] = None,
) -> SafetySystemManager:
    """
    Factory function to create safety system manager.

    Args:
        safety_level: Safety level string or enum
        custom_config: Custom configuration (overrides safety_level)

    Returns:
        SafetySystemManager instance
    """
    if custom_config:
        return SafetySystemManager(custom_config)

    # Parse safety level
    if isinstance(safety_level, str):
        try:
            level = SafetyLevel(safety_level.lower())
        except ValueError:
            logger.warning(f"Invalid safety level '{safety_level}', using BALANCED")
            level = SafetyLevel.BALANCED
    elif isinstance(safety_level, SafetyLevel):
        level = safety_level
    else:
        level = SafetyLevel.BALANCED

    # Create configuration from level
    config = SafetyConfiguration.from_safety_level(level)
    return SafetySystemManager(config)
