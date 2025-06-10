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
from aider_mcp_server.atoms.utils.config_constants import (
    DEFAULT_EDITOR_MODEL,
    DEFAULT_WS_HOST,
    DEFAULT_WS_PORT,
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
from aider_mcp_server.atoms.utils.git_checkpoint import (
    GitCheckpointError,
    GitCheckpointManager,
    GitCommandError,
    NotAGitRepositoryError,
    UncommittedChangesError,
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
]
