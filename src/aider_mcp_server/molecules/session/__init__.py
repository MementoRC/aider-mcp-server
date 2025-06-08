"""
Session management molecules.

This package provides session lifecycle management, security context handling,
and client session coordination functionality extracted from the legacy
templates during the Atomic Design Compliance Refactoring.
"""

from .session_context import SessionContext, SessionState
from .session_manager import SessionManager

__all__ = [
    "SessionManager",
    "SessionContext",
    "SessionState",
]
