"""Error handling interface for centralized error processing.

This module contains error handling protocols that define the interface
for all error handling implementations at the molecule level.

This was moved from interfaces/error_handler.py as part of the
Atomic Design Compliance Refactoring to colocate interfaces with their implementations.
"""

from typing import Optional, Protocol

from typing_extensions import runtime_checkable

from aider_mcp_server.atoms.types.internal_types import ErrorContext


@runtime_checkable
class IErrorHandler(Protocol):
    """Protocol for components that handle errors.

    This protocol defines the core contract that error handler implementations
    must implement to process and handle errors in the system.

    Moved from interfaces/error_handler.py as part of the Atomic Design
    Compliance Refactoring to be colocated with handler implementations.
    """

    async def handle_error(self, error: Exception, context: Optional[ErrorContext] = None) -> None:
        """
        Handles an error, potentially logging it or taking other actions.

        Args:
            error: The exception that occurred.
            context: Optional context about the error.
        """
        ...
