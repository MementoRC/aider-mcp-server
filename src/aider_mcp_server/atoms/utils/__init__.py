"""
Utility atoms for the Aider MCP Server.

Provides atomic utility components including configuration constants,
diff caching, fallback configurations, and aider validation utilities.
"""

from aider_mcp_server.atoms.utils.aider_validation import (
    AiderMisfireError,
    AiderValidationError,
    detect_aider_misfire,
    raise_on_aider_misfire,
    validate_aider_parameters,
    validate_file_references,
)
from aider_mcp_server.atoms.utils.automatic_rollback import (
    AutomaticRollbackError,
    AutomaticRollbackManager,
    InvalidCheckpointError,
    RollbackExecutionError,
    RollbackLogEntry,
    RollbackResult,
)
from aider_mcp_server.atoms.utils.config_constants import (
    DEFAULT_EDITOR_MODEL,
    DEFAULT_WS_HOST,
    DEFAULT_WS_PORT,
)
from aider_mcp_server.atoms.utils.failure_detector import (
    FailureDetectionError,
    FailureDetectionResult,
    FailureDetector,
    FailureSeverity,
    FailureTrigger,
    FailureType,
)
from aider_mcp_server.atoms.utils.file_integrity import (
    FileIntegrityError,
    FileIntegrityFileNotFoundError,
    FileIntegrityManager,
    SyntaxValidationError,
)
from aider_mcp_server.atoms.utils.file_monitor import (
    ContentValidationError,
    FileAccessError,
    FileMonitor,
    FileMonitorError,
    MonitoringState,
    WritePatternError,
)
from aider_mcp_server.atoms.utils.functional_validator import (
    BuildError,
    FunctionalValidationError,
    FunctionalValidationResults,
    FunctionalValidator,
    LintingError,
    QualityGateError,
    TestingError,
    ValidationCategory,
    ValidationLevel,
    ValidationResult,
)
from aider_mcp_server.atoms.utils.git_checkpoint import (
    GitCheckpointError,
    GitCheckpointManager,
    GitCommandError,
    NotAGitRepositoryError,
    UncommittedChangesError,
)
from aider_mcp_server.atoms.utils.git_diff_analyzer import (
    DiffAnalysisFailedError,
    DiffAnalysisResult,
    FileChangeStats,
    GitDiffAnalysisError,
    GitDiffAnalyzer,
    InvalidGitReferenceError,
    SuspiciousPattern,
)
from aider_mcp_server.atoms.utils.model_response_validator import (
    ModelResponseValidator,
    ResponseValidationResult,
)
from aider_mcp_server.atoms.utils.model_response_validator import ValidationCategory as ModelValidationCategory
from aider_mcp_server.atoms.utils.model_response_validator import (
    ValidationError,
)
from aider_mcp_server.atoms.utils.operation_risk_assessor import (
    OperationRiskAssessment,
    OperationRiskAssessor,
    RiskFactor,
    RiskLevel,
)
from aider_mcp_server.atoms.utils.post_operation_verifier import (
    ContentVerificationError,
    FileVerificationMetrics,
    LineCountVerificationError,
    PostOperationVerifier,
    SemanticVerificationError,
    VerificationError,
    VerificationResult,
    VerificationResults,
)
from aider_mcp_server.atoms.utils.recovery_guidance import (
    GuidanceItem,
    GuidancePriority,
    GuidanceType,
    RecoveryGuidanceError,
    RecoveryGuidanceManager,
    RecoveryGuidanceResult,
)
from aider_mcp_server.atoms.utils.safety_configuration import (
    SafetyConfiguration,
    SafetyConfigurationError,
    SafetyConfigurationSystem,
    SafetyProfile,
)
from aider_mcp_server.atoms.utils.safety_system_manager import (
    CheckpointResult,
    PreExecutionResult,
    SafetyOperationError,
    SafetyOperationResult,
    SafetySystemError,
    SafetySystemManager,
    create_safety_system_manager,
)

__all__ = [
    # Configuration constants
    "DEFAULT_EDITOR_MODEL",
    "DEFAULT_WS_HOST",
    "DEFAULT_WS_PORT",
    # Aider validation utilities
    "AiderValidationError",
    "AiderMisfireError",
    "validate_aider_parameters",
    "validate_file_references",
    "detect_aider_misfire",
    "raise_on_aider_misfire",
    # Git checkpoint system
    "GitCheckpointManager",
    "GitCheckpointError",
    "NotAGitRepositoryError",
    "UncommittedChangesError",
    "GitCommandError",
    # Git diff analysis system
    "GitDiffAnalyzer",
    "GitDiffAnalysisError",
    "InvalidGitReferenceError",
    "DiffAnalysisFailedError",
    "DiffAnalysisResult",
    "FileChangeStats",
    "SuspiciousPattern",
    # File integrity system
    "FileIntegrityManager",
    "FileIntegrityError",
    "FileIntegrityFileNotFoundError",
    "SyntaxValidationError",
    # File monitor system
    "FileMonitor",
    "FileMonitorError",
    "FileAccessError",
    "ContentValidationError",
    "WritePatternError",
    "MonitoringState",
    # Functional validation system
    "FunctionalValidator",
    "FunctionalValidationError",
    "FunctionalValidationResults",
    "ValidationResult",
    "ValidationLevel",
    "ValidationCategory",
    "LintingError",
    "TestingError",
    "BuildError",
    "QualityGateError",
    # Model response validation system
    "ModelResponseValidator",
    "ResponseValidationResult",
    "ModelValidationCategory",
    "ValidationError",
    # Post-operation verification system
    "PostOperationVerifier",
    "VerificationError",
    "ContentVerificationError",
    "LineCountVerificationError",
    "SemanticVerificationError",
    "VerificationResult",
    "VerificationResults",
    "FileVerificationMetrics",
    # Operation risk assessment system
    "OperationRiskAssessor",
    "OperationRiskAssessment",
    "RiskLevel",
    "RiskFactor",
    # Failure detection system
    "FailureDetector",
    "FailureDetectionError",
    "FailureDetectionResult",
    "FailureTrigger",
    "FailureType",
    "FailureSeverity",
    # Automatic rollback system
    "AutomaticRollbackManager",
    "AutomaticRollbackError",
    "RollbackExecutionError",
    "InvalidCheckpointError",
    "RollbackResult",
    "RollbackLogEntry",
    # Recovery guidance system
    "RecoveryGuidanceManager",
    "RecoveryGuidanceError",
    "RecoveryGuidanceResult",
    "GuidanceItem",
    "GuidanceType",
    "GuidancePriority",
    # Safety system manager
    "SafetySystemManager",
    "SafetyConfiguration",
    "SafetyConfigurationSystem",
    "SafetyProfile",
    "SafetySystemError",
    "SafetyConfigurationError",
    "SafetyOperationError",
    "PreExecutionResult",
    "CheckpointResult",
    "SafetyOperationResult",
    "create_safety_system_manager",
]
