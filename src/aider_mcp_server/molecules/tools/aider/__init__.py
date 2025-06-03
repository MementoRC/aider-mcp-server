"""
Aider AI Code Tool - Decomposed Module

This module provides a decomposed version of the original aider_ai_code.py
following atomic design principles. The decomposition improves maintainability,
reduces complexity, and enhances code organization while preserving backward
compatibility.

The module is organized into focused components:
- core_execution: Core Aider execution logic
- shared: Common types and utilities

Future modules will include:
- rate_limiting: Rate limit handling and fallback
- response_formatting: Response processing and formatting
- cache_management: Diff cache integration
- api_validation: API key validation and setup
- session_coordination: Session lifecycle and events
"""

from .core_execution import CoreExecutor
from .shared import (
    ExecutionConfig,
    ExecutionResult,
    FileInfo,
    ModelConfig,
    ResponseDict,
    RetryConfig,
    SilentInputOutput,
)

__all__ = [
    "CoreExecutor",
    "ResponseDict",
    "ExecutionConfig",
    "ModelConfig",
    "ExecutionResult",
    "FileInfo",
    "RetryConfig",
    "SilentInputOutput",
]
