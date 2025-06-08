"""
Tests for session manager molecule.
"""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from aider_mcp_server.atoms.security.permissions import Permissions
from aider_mcp_server.molecules.session.session_context import SessionContext, SessionState
from aider_mcp_server.molecules.session.session_manager import SessionManager


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return MagicMock()


@pytest.fixture
def session_manager(mock_logger):
    """Create a session manager instance."""
    return SessionManager(logger=mock_logger, default_timeout=60.0, cleanup_interval=10.0)


@pytest.mark.asyncio
class TestSessionManager:
    """Test the SessionManager class."""

    async def test_session_manager_lifecycle(self, session_manager):
        """Test session manager start and stop."""
        assert not session_manager._running

        await session_manager.start()
        assert session_manager._running

        await session_manager.stop()
        assert not session_manager._running

    async def test_create_session(self, session_manager):
        """Test creating a new session."""
        await session_manager.start()

        try:
            permissions = {Permissions.READ, Permissions.EXECUTE_AIDER}
            session = session_manager.create_session(
                transport_type="stdio", permissions=permissions, timeout_seconds=300.0, metadata={"test": "data"}
            )

            assert session.transport_type == "stdio"
            assert session.permissions == permissions
            assert session.timeout_seconds == 300.0
            assert session.metadata["test"] == "data"
            assert session.state == SessionState.ACTIVE

        finally:
            await session_manager.stop()

    async def test_get_session(self, session_manager):
        """Test getting a session by ID."""
        await session_manager.start()

        try:
            # Create a session
            session = session_manager.create_session("sse")
            session_id = session.session_id

            # Get the session
            retrieved = session_manager.get_session(session_id)
            assert retrieved is not None
            assert retrieved.session_id == session_id

            # Non-existent session
            assert session_manager.get_session("nonexistent") is None

        finally:
            await session_manager.stop()

    async def test_update_session_activity(self, session_manager):
        """Test updating session activity."""
        await session_manager.start()

        try:
            session = session_manager.create_session("http")
            session_id = session.session_id

            # Record initial activity time
            initial_activity = session.last_activity

            # Wait a bit and update activity
            await asyncio.sleep(0.1)
            success = session_manager.update_session_activity(session_id)

            assert success
            assert session.last_activity > initial_activity

            # Try to update non-existent session
            assert not session_manager.update_session_activity("nonexistent")

        finally:
            await session_manager.stop()

    async def test_terminate_session(self, session_manager):
        """Test terminating a session."""
        await session_manager.start()

        try:
            session = session_manager.create_session("stdio")
            session_id = session.session_id

            # Verify session exists
            assert session_manager.get_session(session_id) is not None

            # Terminate session
            success = session_manager.terminate_session(session_id)
            assert success

            # Verify session is gone
            assert session_manager.get_session(session_id) is None

            # Try to terminate non-existent session
            assert not session_manager.terminate_session("nonexistent")

        finally:
            await session_manager.stop()

    async def test_get_active_sessions(self, session_manager):
        """Test getting active sessions."""
        await session_manager.start()

        try:
            # Initially no sessions
            assert len(session_manager.get_active_sessions()) == 0

            # Create some sessions
            session1 = session_manager.create_session("stdio")
            session2 = session_manager.create_session("sse")
            session3 = session_manager.create_session("http")

            # Verify sessions were created with correct transport types
            assert session1.transport_type == "stdio"
            assert session3.transport_type == "http"

            active_sessions = session_manager.get_active_sessions()
            assert len(active_sessions) == 3

            # Terminate one session
            session_manager.terminate_session(session2.session_id)

            active_sessions = session_manager.get_active_sessions()
            assert len(active_sessions) == 2

        finally:
            await session_manager.stop()

    async def test_get_sessions_by_transport(self, session_manager):
        """Test getting sessions by transport type."""
        await session_manager.start()

        try:
            # Create sessions with different transports
            session_manager.create_session("stdio")
            session_manager.create_session("stdio")
            session_manager.create_session("sse")

            stdio_sessions = session_manager.get_sessions_by_transport("stdio")
            sse_sessions = session_manager.get_sessions_by_transport("sse")
            http_sessions = session_manager.get_sessions_by_transport("http")

            assert len(stdio_sessions) == 2
            assert len(sse_sessions) == 1
            assert len(http_sessions) == 0

        finally:
            await session_manager.stop()

    async def test_session_count(self, session_manager):
        """Test getting session count."""
        await session_manager.start()

        try:
            assert session_manager.get_session_count() == 0

            session_manager.create_session("stdio")
            session_manager.create_session("sse")

            assert session_manager.get_session_count() == 2

        finally:
            await session_manager.stop()

    async def test_session_summary(self, session_manager):
        """Test getting session summary."""
        await session_manager.start()

        try:
            # Create sessions
            session_manager.create_session("stdio")
            session_manager.create_session("stdio")
            session_manager.create_session("sse")

            summary = session_manager.get_session_summary()

            assert summary["total_sessions"] == 3
            assert summary["active_sessions"] == 3
            assert summary["expired_sessions"] == 0
            assert summary["sessions_by_transport"]["stdio"] == 2
            assert summary["sessions_by_transport"]["sse"] == 1
            assert summary["default_timeout"] == 60.0
            assert summary["cleanup_interval"] == 10.0

        finally:
            await session_manager.stop()

    async def test_session_expiration(self, session_manager):
        """Test session expiration handling."""
        # Use very short timeout for testing
        short_timeout_manager = SessionManager(
            logger=MagicMock(),
            default_timeout=0.1,  # 100ms timeout
            cleanup_interval=0.05,  # 50ms cleanup interval
        )

        await short_timeout_manager.start()

        try:
            # Create a session with short timeout
            session = short_timeout_manager.create_session("stdio", timeout_seconds=0.1)
            session_id = session.session_id

            # Initially session should exist
            assert short_timeout_manager.get_session(session_id) is not None

            # Wait for expiration
            await asyncio.sleep(0.2)

            # Session should be expired and return None
            assert short_timeout_manager.get_session(session_id) is None

        finally:
            await short_timeout_manager.stop()


class TestSessionContext:
    """Test the SessionContext class."""

    def test_session_context_creation(self):
        """Test creating a session context."""
        from aider_mcp_server.atoms.security.context import SecurityContext

        permissions = {Permissions.READ, Permissions.WRITE}
        security_context = SecurityContext(user_id="test", permissions=permissions)

        session = SessionContext(
            session_id="test-123",
            transport_type="stdio",
            security_context=security_context,
            permissions=permissions,
            timeout_seconds=1800.0,
            metadata={"client": "test"},
        )

        assert session.session_id == "test-123"
        assert session.transport_type == "stdio"
        assert session.permissions == permissions
        assert session.timeout_seconds == 1800.0
        assert session.metadata["client"] == "test"
        assert session.state == SessionState.CREATED

    def test_session_context_auto_fields(self):
        """Test auto-generated fields in session context."""
        from aider_mcp_server.atoms.security.context import SecurityContext

        permissions = {Permissions.READ}
        security_context = SecurityContext(user_id="test", permissions=permissions)

        session = SessionContext(
            session_id="",  # Should auto-generate
            transport_type="sse",
            security_context=security_context,
            permissions=permissions,
        )

        assert session.session_id != ""  # Should be auto-generated
        assert session.created_at > 0
        assert session.last_activity > 0
        assert session.metadata == {}

    def test_session_activity_tracking(self):
        """Test session activity tracking."""
        from aider_mcp_server.atoms.security.context import SecurityContext

        permissions = {Permissions.READ}
        security_context = SecurityContext(user_id="test", permissions=permissions)

        session = SessionContext(
            session_id="test", transport_type="stdio", security_context=security_context, permissions=permissions
        )

        initial_activity = session.last_activity

        # Update activity
        time.sleep(0.01)  # Small delay
        session.update_activity()

        assert session.last_activity > initial_activity

    def test_session_expiration_check(self):
        """Test session expiration checking."""
        from aider_mcp_server.atoms.security.context import SecurityContext

        permissions = {Permissions.READ}
        security_context = SecurityContext(user_id="test", permissions=permissions)

        # Create session with very short timeout
        session = SessionContext(
            session_id="test",
            transport_type="stdio",
            security_context=security_context,
            permissions=permissions,
            timeout_seconds=0.01,  # 10ms timeout
        )

        # Initially not expired
        assert not session.is_expired()

        # Wait for expiration
        time.sleep(0.02)

        # Should be expired now
        assert session.is_expired()

    def test_session_state_transitions(self):
        """Test session state transitions."""
        from aider_mcp_server.atoms.security.context import SecurityContext

        permissions = {Permissions.READ}
        security_context = SecurityContext(user_id="test", permissions=permissions)

        session = SessionContext(
            session_id="test", transport_type="stdio", security_context=security_context, permissions=permissions
        )

        # Initial state
        assert session.state == SessionState.CREATED

        # Activate
        session.activate()
        assert session.state == SessionState.ACTIVE

        # Mark idle
        session.mark_idle()
        assert session.state == SessionState.IDLE

        # Update activity (should reactivate)
        session.update_activity()
        assert session.state == SessionState.ACTIVE

        # Mark expired
        session.mark_expired()
        assert session.state == SessionState.EXPIRED

        # Terminate
        session.terminate()
        assert session.state == SessionState.TERMINATED

    def test_session_info(self):
        """Test getting session info."""
        from aider_mcp_server.atoms.security.context import SecurityContext

        permissions = {Permissions.READ, Permissions.EXECUTE_AIDER}
        security_context = SecurityContext(user_id="test", permissions=permissions)

        session = SessionContext(
            session_id="test-info",
            transport_type="sse",
            security_context=security_context,
            permissions=permissions,
            metadata={"key": "value"},
        )

        info = session.get_session_info()

        assert info["session_id"] == "test-info"
        assert info["transport_type"] == "sse"
        assert info["state"] == "CREATED"
        assert "created_at" in info
        assert "last_activity" in info
        assert "read" in info["permissions"]
        assert "execute_aider" in info["permissions"]
        assert info["metadata"]["key"] == "value"
