"""
Session manager for client session lifecycle management.

This module provides comprehensive session management functionality including
session creation, lifecycle tracking, timeout handling, and cleanup.

Extracted and enhanced from legacy templates/initialization/session_manager.py
during Task 19 - Redistribute Template Directory Content.
"""

import asyncio
import threading
from typing import Any, Dict, List, Optional, Set, Union, cast
from uuid import uuid4

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.security.context import SecurityContext
from aider_mcp_server.atoms.security.permissions import Permissions
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol

from .session_context import SessionContext


class SessionManager:
    """
    Manager for client session lifecycle and security contexts.

    This class provides thread-safe session management with automatic
    cleanup, timeout handling, and security context management.
    """

    def __init__(
        self,
        logger: Optional[LoggerProtocol] = None,
        default_timeout: float = 3600.0,
        cleanup_interval: float = 300.0,  # 5 minutes
    ):
        """
        Initialize the session manager.

        Args:
            logger: Optional logger instance
            default_timeout: Default session timeout in seconds
            cleanup_interval: Interval for automatic cleanup in seconds
        """
        self.logger = logger or get_logger(__name__)
        self.default_timeout = default_timeout
        self.cleanup_interval = cleanup_interval

        self._sessions: Dict[str, SessionContext] = {}
        self._lock = threading.RLock()
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._running = False

    async def start(self) -> None:
        """Start the session manager and automatic cleanup."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.info("Session manager started")

    async def stop(self) -> None:
        """Stop the session manager and cleanup all sessions."""
        if not self._running:
            return

        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Cleanup all sessions
        with self._lock:
            for session in self._sessions.values():
                session.terminate()
            self._sessions.clear()

        self.logger.info("Session manager stopped")

    def create_session(
        self,
        transport_type: str,
        permissions: Optional[Set[Union[Permissions, str]]] = None,
        timeout_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> SessionContext:
        """
        Create a new client session.

        Args:
            transport_type: Type of transport (stdio, sse, http)
            permissions: Session permissions (default: anonymous permissions)
            timeout_seconds: Session timeout (default: manager default)
            metadata: Additional session metadata
            session_id: Optional explicit session ID

        Returns:
            Created session context
        """
        if session_id is None:
            session_id = str(uuid4())

        if permissions is None:
            # Default to basic read permissions for anonymous users
            filtered_permissions = {Permissions.READ}
        else:
            # Filter to only Permissions enum values
            filtered_permissions = {p for p in permissions if isinstance(p, Permissions)}

        if timeout_seconds is None:
            timeout_seconds = self.default_timeout

        # Create security context for the session
        # Cast to satisfy mypy - Set[Permissions] is compatible with Set[Union[Permissions, str]]
        permissions_for_context = cast(Optional[Set[Union[Permissions, str]]], filtered_permissions)
        security_context = SecurityContext(
            user_id="anonymous", permissions=permissions_for_context, is_anonymous=True, transport_id=transport_type
        )

        session = SessionContext(
            session_id=session_id,
            transport_type=transport_type,
            security_context=security_context,
            permissions=filtered_permissions,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {},
        )

        with self._lock:
            self._sessions[session_id] = session

        session.activate()

        self.logger.verbose(f"Created session {session_id} for transport {transport_type}")
        return session

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """
        Get a session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session context if found, None otherwise
        """
        with self._lock:
            session = self._sessions.get(session_id)

        if session and session.is_expired():
            self._expire_session(session_id)
            return None

        return session

    def update_session_activity(self, session_id: str) -> bool:
        """
        Update session activity timestamp.

        Args:
            session_id: Session identifier

        Returns:
            True if session was updated, False if not found or expired
        """
        session = self.get_session(session_id)
        if session:
            session.update_activity()
            self.logger.debug(f"Updated activity for session {session_id}")
            return True
        return False

    def terminate_session(self, session_id: str) -> bool:
        """
        Terminate a session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was terminated, False if not found
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.terminate()
                del self._sessions[session_id]
                self.logger.verbose(f"Terminated session {session_id}")
                return True
        return False

    def get_active_sessions(self) -> List[SessionContext]:
        """
        Get all active (non-expired) sessions.

        Returns:
            List of active session contexts
        """
        active_sessions = []

        with self._lock:
            for session in self._sessions.values():
                if not session.is_expired():
                    active_sessions.append(session)

        return active_sessions

    def get_sessions_by_transport(self, transport_type: str) -> List[SessionContext]:
        """
        Get all sessions for a specific transport type.

        Args:
            transport_type: Transport type to filter by

        Returns:
            List of session contexts for the transport
        """
        sessions = []

        with self._lock:
            for session in self._sessions.values():
                if session.transport_type == transport_type and not session.is_expired():
                    sessions.append(session)

        return sessions

    def get_session_count(self) -> int:
        """
        Get the total number of active sessions.

        Returns:
            Number of active sessions
        """
        return len(self.get_active_sessions())

    def get_session_summary(self) -> Dict[str, Any]:
        """
        Get a summary of session statistics.

        Returns:
            Dictionary with session statistics
        """
        active_sessions = self.get_active_sessions()

        transport_counts: Dict[str, int] = {}
        for session in active_sessions:
            transport = session.transport_type
            transport_counts[transport] = transport_counts.get(transport, 0) + 1

        with self._lock:
            total_sessions = len(self._sessions)

        return {
            "total_sessions": total_sessions,
            "active_sessions": len(active_sessions),
            "expired_sessions": total_sessions - len(active_sessions),
            "sessions_by_transport": transport_counts,
            "default_timeout": self.default_timeout,
            "cleanup_interval": self.cleanup_interval,
        }

    def _expire_session(self, session_id: str) -> None:
        """Mark a session as expired and remove it."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.mark_expired()
                del self._sessions[session_id]
                self.logger.verbose(f"Expired session {session_id}")

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of expired sessions."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                if self._running:  # Only proceed if still running
                    await self._perform_cleanup_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in session cleanup: {e}")

        self.logger.debug("Session cleanup loop stopped")

    async def _perform_cleanup_cycle(self) -> None:
        """Perform one cycle of session cleanup."""
        expired_sessions = []

        with self._lock:
            for session_id, session in list(self._sessions.items()):
                if session.is_expired():
                    expired_sessions.append(session_id)

        for session_id in expired_sessions:
            self._expire_session(session_id)

        if expired_sessions:
            self.logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
