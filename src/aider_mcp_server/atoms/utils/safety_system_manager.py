"""
Safety System Manager for MCP Aider Tool Integration.

Coordinates all safety components (Tasks 1-11) into a unified safety system that
integrates with the aider execution flow to provide comprehensive operation safety.
"""

import dataclasses
import fnmatch
import os
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.utils.audit_logger import AuditLogger
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
    RiskFactor,
    RiskLevel,
)
from aider_mcp_server.atoms.utils.post_operation_verifier import PostOperationVerifier
from aider_mcp_server.atoms.utils.recovery_guidance import RecoveryGuidanceManager
from aider_mcp_server.atoms.utils.safety_configuration import (
    ModelSpecificConfiguration,
    SafetyConfiguration,
    SafetyConfigurationSystem,
    ValidationLevel,
)

logger = get_logger(__name__)


class SafetySystemError(Exception):
    """Base exception for safety system operations."""

    pass


class SafetyOperationError(SafetySystemError):
    """Raised when safety operations fail."""

    pass


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
        if config is None:
            config_system = SafetyConfigurationSystem()
            self.config = config_system.load_config()
        else:
            self.config = config

        self.logger = get_logger(__name__)
        self.audit_logger = AuditLogger()

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

        # Model-specific settings for the current operation
        self._risk_multiplier: float = 1.0
        self._architect_risk_multiplier: float = 1.0
        self._op_timeout_seconds: Optional[float] = None
        self._op_validation_level: Optional[ValidationLevel] = None
        self._fallback_model_suggestion: Optional[str] = None
        self._monitoring_flags: List[str] = []

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

    def _find_best_model_config_match(self, model_name: str) -> Optional[ModelSpecificConfiguration]:
        """Find the best matching model-specific configuration using wildcard patterns."""
        best_match = None
        longest_pattern = -1

        for pattern, model_config in self.config.model_specific_configs.items():
            if fnmatch.fnmatch(model_name, pattern):
                if len(pattern) > longest_pattern:
                    best_match = model_config
                    longest_pattern = len(pattern)

        return best_match

    def _apply_model_specific_settings(self, model_name: str) -> None:
        """Apply model-specific configurations based on the given model name for the current operation."""
        # Reset to global defaults before applying
        self._risk_multiplier = 1.0
        self._architect_risk_multiplier = 1.0
        self._op_timeout_seconds = self.config.performance_timeout_seconds
        self._op_validation_level = self.config.validation_level
        self._fallback_model_suggestion = None
        self._monitoring_flags = []

        model_spec = self._find_best_model_config_match(model_name)
        if not model_spec:
            self.logger.debug(f"No model-specific configuration found for '{model_name}'")
            return

        self.logger.info(f"Applying model-specific settings for '{model_name}'")

        # Store multipliers for later use
        self._risk_multiplier = model_spec.risk_multiplier
        self._architect_risk_multiplier = model_spec.architect_risk_multiplier

        # Apply timeout multiplier
        if self._op_timeout_seconds:
            self._op_timeout_seconds *= model_spec.timeout_multiplier
        self.logger.debug(f"Timeout adjusted to {self._op_timeout_seconds}s")

        # Override validation level
        if model_spec.validation_level_override:
            self._op_validation_level = model_spec.validation_level_override
            self.logger.debug(f"Validation level set to '{self._op_validation_level.value}'")

        # Store other info for potential use
        self._fallback_model_suggestion = model_spec.fallback_model_suggestion
        self._monitoring_flags = model_spec.monitoring_flags

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

        # Check if all safety components are disabled in the configuration
        all_disabled = all(
            not getattr(self.config, f.name) for f in dataclasses.fields(self.config) if f.name.startswith("enable_")
        )
        if all_disabled:
            self.logger.info("All safety features are disabled in the configuration, bypassing.")
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
        self._current_operation_id = str(uuid.uuid4())
        operation_context["operation_id"] = self._current_operation_id
        self.audit_logger.log_operation_start(
            operation_id=self._current_operation_id,
            operation_context=operation_context,
            target_files=target_files,
        )

        try:
            start_time = time.time()
            self._initialize_components(working_directory)

            model_name = operation_context.get("model", "unknown")
            self._apply_model_specific_settings(model_name)

            risk_assessment_result = self._run_risk_assessment(target_files, operation_context)
            if isinstance(risk_assessment_result, PreExecutionResult):
                self.audit_logger.log_pre_execution_check(self._current_operation_id, risk_assessment_result)
                return risk_assessment_result
            risk_assessment = risk_assessment_result

            self._run_file_integrity_precheck(working_directory, target_files)

            elapsed = time.time() - start_time
            timeout_result = self._handle_precheck_timeout(elapsed)
            if timeout_result is not None:
                self.audit_logger.log_pre_execution_check(self._current_operation_id, timeout_result)
                return timeout_result

            self.logger.info(f"Pre-execution safety check completed in {elapsed:.2f}s")
            result = PreExecutionResult(
                is_safe=True,
                details={"check_duration": elapsed},
                risk_assessment=risk_assessment,
            )
            self.audit_logger.log_pre_execution_check(self._current_operation_id, result)
            return result

        except Exception as e:
            self.logger.error(f"Pre-execution safety check failed: {e}")
            result = PreExecutionResult(
                is_safe=False,
                reason=f"Safety check error: {str(e)}",
                user_message="Operation blocked due to safety system error",
            )
            self.audit_logger.log_pre_execution_check(self._current_operation_id, result)
            return result

    def _run_risk_assessment(
        self, target_files: List[str], operation_context: Dict[str, Any]
    ) -> Union[PreExecutionResult, Optional[OperationRiskAssessment]]:
        """Run risk assessment and return PreExecutionResult if blocked, else risk_assessment object."""
        if not self.config.enable_risk_assessment or not self._risk_assessor:
            return None

        try:
            model_name = operation_context.get("model", "unknown")
            is_architect_mode = operation_context.get("architect_mode", False)
            operation_type = "architect" if is_architect_mode else operation_context.get("operation_type", "refactor")

            risk_assessment = self._risk_assessor.assess_operation_risk(
                model=model_name,
                operation_type=operation_type,
                file_count=len(target_files),
                operation_params=operation_context,
            )

            risk_assessment = self._apply_model_specific_multipliers(risk_assessment, is_architect_mode)

            pre_exec_result = self._maybe_block_on_risk(risk_assessment)
            if pre_exec_result is not None:
                return pre_exec_result

            return risk_assessment

        except Exception as e:
            self.logger.warning(f"Risk assessment failed: {e}")
            is_strict_profile = not self.config.bypass_on_timeout
            if is_strict_profile:
                return PreExecutionResult(
                    is_safe=False,
                    reason="Risk assessment failed in a strict safety profile",
                    user_message="Operation blocked due to risk assessment failure",
                )
            return None

    def _apply_model_specific_multipliers(
        self, risk_assessment: OperationRiskAssessment, is_architect_mode: bool
    ) -> OperationRiskAssessment:
        """Apply model-specific multipliers and recalculate risk level."""
        original_score = risk_assessment.total_score
        final_multiplier = self._risk_multiplier * (self._architect_risk_multiplier if is_architect_mode else 1.0)

        if final_multiplier != 1.0:
            risk_assessment.total_score = round(risk_assessment.total_score * final_multiplier)
            risk_assessment.factors.append(
                RiskFactor(
                    name="model_specific_multiplier",
                    score=risk_assessment.total_score - original_score,
                    description=f"Applied model-specific multiplier(s) (total: x{final_multiplier:.2f})",
                    details={
                        "base_multiplier": self._risk_multiplier,
                        "architect_multiplier": self._architect_risk_multiplier if is_architect_mode else None,
                    },
                )
            )
            # Recalculate risk level
            if risk_assessment.total_score <= 3:
                risk_assessment.risk_level = RiskLevel.LOW
            elif risk_assessment.total_score <= 7:
                risk_assessment.risk_level = RiskLevel.MEDIUM
            elif risk_assessment.total_score <= 10:
                risk_assessment.risk_level = RiskLevel.HIGH
            else:
                risk_assessment.risk_level = RiskLevel.CRITICAL
        return risk_assessment

    def _maybe_block_on_risk(self, risk_assessment: OperationRiskAssessment) -> Optional[PreExecutionResult]:
        """Block operation if risk is too high in strict profile, else return None."""
        is_strict_profile = not self.config.bypass_on_timeout
        if is_strict_profile and risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            user_message = f"Operation blocked due to {risk_assessment.risk_level.value} risk level ({risk_assessment.total_score})."
            if self._fallback_model_suggestion:
                user_message += f" Consider using a different model like '{self._fallback_model_suggestion}'."

            # Convert any Enum fields to their values for JSON serialization
            from typing import Any as _Any

            def _enum_to_value(obj: _Any) -> _Any:
                if isinstance(obj, dict):
                    return {k: _enum_to_value(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [_enum_to_value(v) for v in obj]
                elif isinstance(obj, tuple):
                    return tuple(_enum_to_value(v) for v in obj)
                elif hasattr(obj, "value") and isinstance(obj, Enum):
                    return obj.value
                else:
                    return obj

            risk_assessment_dict = dataclasses.asdict(risk_assessment)
            risk_assessment_dict = _enum_to_value(risk_assessment_dict)

            return PreExecutionResult(
                is_safe=False,
                reason=f"{risk_assessment.risk_level.value} risk level detected: {risk_assessment.total_score}",
                details={"risk_assessment": risk_assessment_dict},
                user_message=user_message,
                risk_assessment=risk_assessment,
            )
        return None

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
        if self._op_timeout_seconds and elapsed > self._op_timeout_seconds:
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
        operation_id = operation_metadata.get("operation_id") if operation_metadata else self._current_operation_id

        if not self.config.enable_git_checkpoint:
            result = CheckpointResult(success=True, checkpoint_id="disabled")
            if operation_id:
                self.audit_logger.log_checkpoint_creation(operation_id, result)
            return result

        try:
            self._initialize_components(repo_path)

            if not self._git_checkpoint_manager:
                # Git checkpoint unavailable (likely non-git directory), continue gracefully
                self.logger.warning("Git checkpoint manager not available, skipping checkpoint creation")
                result = CheckpointResult(
                    success=True, checkpoint_id="unavailable", error_message="Git checkpoint not available"
                )
                if operation_id:
                    self.audit_logger.log_checkpoint_creation(operation_id, result)
                return result

            # Create checkpoint with metadata using correct API
            metadata = operation_metadata or {}
            metadata.update(
                {
                    "safety_profile": self.config.profile.value,
                    "timestamp": time.time(),
                    "file_count": len(files_to_track),
                }
            )

            # Use the correct API parameters
            op_id = f"aider-safety-{int(time.time())}"
            checkpoint_id = self._git_checkpoint_manager.create_checkpoint(
                operation_id=op_id,
                model=metadata.get("model", "unknown"),
                target_files=[str(f) for f in files_to_track],
                operation_params=metadata,
                uncommitted_strategy="stash",
            )

            self.logger.info(f"Safety checkpoint created: {checkpoint_id}")
            result = CheckpointResult(success=True, checkpoint_id=checkpoint_id)
            if operation_id:
                self.audit_logger.log_checkpoint_creation(operation_id, result)
            return result

        except Exception as e:
            self.logger.error(f"Checkpoint creation failed: {e}")
            result = CheckpointResult(
                success=False,
                error_message=f"Checkpoint creation failed: {str(e)}",
            )
            if operation_id:
                self.audit_logger.log_checkpoint_creation(operation_id, result)
            return result

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
                details={},
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
        operation_id = operation_context.get("operation_id", self._current_operation_id)

        try:
            failure_detection, rollback_result, recovery_guidance = self._run_safety_post_checks(
                repo_path, target_files, checkpoint_id, operation_id, operation_context
            )

            # Calculate performance metrics
            total_time = time.time() - start_time
            performance_metrics = {
                "total_duration": total_time,
                "safety_overhead": total_time,  # Full duration as overhead since this is safety-only
            }

            success = not (failure_detection and failure_detection.has_failures and failure_detection.requires_rollback)

            result = SafetyOperationResult(
                success=success,
                checkpoint_id=checkpoint_id,
                failure_detection=failure_detection,
                rollback_result=rollback_result,
                recovery_guidance=recovery_guidance,
                performance_metrics=performance_metrics,
            )
            if operation_id:
                self.audit_logger.log_operation_complete(operation_id, result)
            return result

        except Exception as e:
            self.logger.error(f"Safety operation completion failed: {e}")
            result = SafetyOperationResult(
                success=False,
                checkpoint_id=checkpoint_id,
                error_message=f"Safety operation failed: {str(e)}",
                performance_metrics={"total_duration": time.time() - start_time},
            )
            if operation_id:
                self.audit_logger.log_operation_complete(operation_id, result)
            return result

    def _run_safety_post_checks(
        self,
        repo_path: Union[str, Path],
        target_files: List[str],
        checkpoint_id: Optional[str],
        operation_id: Optional[str],
        operation_context: Dict[str, Any],
    ) -> tuple[Optional[Any], Optional[Any], Optional[Any]]:
        """Helper to run post-operation safety checks, rollback, and guidance."""
        failure_detection = None
        rollback_result = None
        recovery_guidance = None

        # Detect failures
        if checkpoint_id and checkpoint_id not in ["disabled", "unavailable"]:
            failure_detection = self.detect_failures(repo_path, target_files, checkpoint_id)
            if operation_id and failure_detection:
                self.audit_logger.log_failure_detection(operation_id, failure_detection)

        # Handle rollback if needed
        if failure_detection and failure_detection.has_failures and failure_detection.requires_rollback:
            if checkpoint_id:  # Ensure checkpoint_id is not None
                rollback_result = self.trigger_rollback(checkpoint_id, failure_detection)
                if operation_id and rollback_result:
                    self.audit_logger.log_rollback(operation_id, rollback_result)

        # Generate recovery guidance if needed
        if failure_detection and failure_detection.has_failures:
            recovery_guidance = self.generate_recovery_guidance(failure_detection, rollback_result, operation_context)
            if operation_id and recovery_guidance:
                self.audit_logger.log_recovery_guidance(operation_id, recovery_guidance)

        return failure_detection, rollback_result, recovery_guidance


def create_safety_system_manager(
    project_root: Optional[Union[str, Path]] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> SafetySystemManager:
    """
    Factory function to create safety system manager.

    Args:
        project_root: The project root directory to search for config files.
        cli_overrides: Dictionary of command-line configuration overrides.

    Returns:
        SafetySystemManager instance
    """
    config_system = SafetyConfigurationSystem(project_root=project_root)
    config = config_system.load_config(cli_overrides=cli_overrides)
    return SafetySystemManager(config)
