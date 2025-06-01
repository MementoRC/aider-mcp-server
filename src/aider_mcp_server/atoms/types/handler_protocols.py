"""Handler protocols for the Aider MCP Server.

This module contains basic handler protocols that define the interface
for all request handling implementations in the system.

This was moved from interfaces/request_handler.py as part of the
Atomic Design Compliance Refactoring to place basic protocols at the atom level.
"""

from typing import Protocol

from typing_extensions import runtime_checkable

from aider_mcp_server.atoms.types.internal_types import InternalRequest, InternalResponse


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
