"""Handler protocols for the Aider MCP Server.

This module contains basic handler protocols that define the interface
for all request handling implementations in the system.

This was moved from interfaces/request_handler.py as part of the
Atomic Design Compliance Refactoring to place basic protocols at the atom level.
"""

from typing import Optional, Protocol

from typing_extensions import runtime_checkable

from aider_mcp_server.atoms.types.internal_types import ErrorContext, InternalEvent, InternalRequest, InternalResponse


@runtime_checkable
class IErrorHandler(Protocol):
    """Protocol for components that handle errors.
    
    This protocol specifies the core contract that all error handlers
    must implement to process errors in the MCP server.
    
    Moved from interfaces/error_handler.py as part of the Atomic Design
    Compliance Refactoring.
    """

    async def handle_error(self, error: Exception, context: Optional[ErrorContext] = None) -> None:
        """
        Handles an error, potentially logging it or taking other actions.

        Args:
            error: The exception that occurred.
            context: Optional context about the error.
        """
        ...


@runtime_checkable
class IEventHandler(Protocol):
    """Protocol for components that process internal events.
    
    This protocol specifies the core contract that all event handlers
    must implement to process events in the MCP server.
    
    Moved from interfaces/event_handler.py as part of the Atomic Design
    Compliance Refactoring.
    """

    async def handle_event(self, event: InternalEvent) -> Optional[InternalEvent]:
        """
        Process an incoming internal event.

        Args:
            event: The event to handle.

        Returns:
            An optional event to be published as a result of handling this event,
            or None if no further event needs to be published.
        """
        ...


@runtime_checkable
class IRequestHandler(Protocol):
    """Protocol for components that process internal requests.

    This protocol specifies the core contract that all request handlers
    must implement to process requests in the MCP server.

    Moved from interfaces/request_handler.py as part of the Atomic Design
    Compliance Refactoring.
    """

    async def handle_request(self, request: InternalRequest) -> InternalResponse:
        """
        Process an incoming internal request.

        Args:
            request: The request to handle.

        Returns:
            The response to the request.
        """
        ...
