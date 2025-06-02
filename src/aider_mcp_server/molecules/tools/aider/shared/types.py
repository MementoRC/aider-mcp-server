"""
Shared types and data structures for the Aider tool modules.

This module contains common type definitions and data structures used across
the decomposed Aider modules following atomic design principles.
"""

from typing import Any, Dict, Optional, TypedDict


class ResponseDict(TypedDict, total=False):
    """
    Response dictionary for Aider operations.
    
    Preserves backward compatibility with the original aider_ai_code.py response format.
    """
    success: bool
    changes_summary: Dict[str, Any]
    file_status: Dict[str, Any]
    is_cached_diff: bool
    diff: str
    rate_limit_info: Dict[str, Any]
    api_key_status: Dict[str, Any]


class ExecutionConfig(TypedDict, total=False):
    """Configuration for Aider execution."""
    working_dir: str
    use_diff_cache: bool
    clear_cached_for_unchanged: bool
    architect_mode: bool
    auto_accept_architect: bool
    editor_model: Optional[str]


class ModelConfig(TypedDict, total=False):
    """Model configuration for Aider."""
    model_name: str
    provider: str
    editor_model: Optional[str]
    architect_mode: bool


class ExecutionResult(TypedDict, total=False):
    """Result of an Aider execution session."""
    success: bool
    changes_summary: Dict[str, Any]
    file_status: Dict[str, Any]
    is_cached_diff: bool
    run_result: Optional[str]


class FileInfo(TypedDict):
    """Information about a file."""
    path: str
    exists: bool
    size: int
    content_preview: str


class RetryConfig(TypedDict):
    """Configuration for retry logic."""
    max_retries: int
    initial_delay: float
    backoff_factor: float


# Re-export SilentInputOutput from the original location for backward compatibility
try:
    from ....atoms.types.data_types import SilentInputOutput
except ImportError:
    # Fallback definition if import fails
    class SilentInputOutput:
        """Silent input/output for Aider operations."""
        pass


__all__ = [
    "ResponseDict",
    "ExecutionConfig", 
    "ModelConfig",
    "ExecutionResult",
    "FileInfo",
    "RetryConfig",
    "SilentInputOutput",
]