"""
Session context and state management.

This module provides session context and state definitions for managing
client sessions with proper security context and lifecycle tracking.

Extracted from legacy templates/initialization/session_manager.py during
Task 19 - Redistribute Template Directory Content.
"""

import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Optional, Set
from uuid import uuid4

from aider_mcp_server.atoms.security.context import SecurityContext
from aider_mcp_server.atoms.security.permissions import Permissions


class SessionState(Enum):
    """Possible states of a client session."""

    CREATED = auto()
    ACTIVE = auto()
    IDLE = auto()
    EXPIRED = auto()
    TERMINATED = auto()


@dataclass
class SessionContext:
    """
    Context information for a client session.

    This class encapsulates all the information needed to manage
    a client session including security context, state, and metadata.
    """

    session_id: str
    transport_type: str
    security_context: SecurityContext
    permissions: Set[Permissions]
    state: SessionState = SessionState.CREATED
    created_at: float = 0.0
    last_activity: float = 0.0
    timeout_seconds: float = 3600.0  # 1 hour default
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Initialize computed fields."""
        if not self.session_id:
            self.session_id = str(uuid4())

        current_time = time.time()
        if self.created_at == 0.0:
            self.created_at = current_time
        if self.last_activity == 0.0:
            self.last_activity = current_time

        if self.metadata is None:
            self.metadata = {}

    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = time.time()

        # Update state if currently idle
        if self.state == SessionState.IDLE:
            self.state = SessionState.ACTIVE

    def is_expired(self) -> bool:
        """Check if the session has expired based on timeout."""
        if self.state in (SessionState.EXPIRED, SessionState.TERMINATED):
            return True

        current_time = time.time()
        return (current_time - self.last_activity) > self.timeout_seconds

    def mark_idle(self) -> None:
        """Mark the session as idle."""
        if self.state == SessionState.ACTIVE:
            self.state = SessionState.IDLE

    def mark_expired(self) -> None:
        """Mark the session as expired."""
        self.state = SessionState.EXPIRED

    def terminate(self) -> None:
        """Terminate the session."""
        self.state = SessionState.TERMINATED

    def activate(self) -> None:
        """Activate the session."""
        self.state = SessionState.ACTIVE
        self.update_activity()

    def get_session_info(self) -> Dict[str, Any]:
        """Get session information as a dictionary."""
        return {
            "session_id": self.session_id,
            "transport_type": self.transport_type,
            "state": self.state.name,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "timeout_seconds": self.timeout_seconds,
            "is_expired": self.is_expired(),
            "permissions": [perm.value for perm in self.permissions],
            "metadata": self.metadata.copy() if self.metadata else {},
        }
