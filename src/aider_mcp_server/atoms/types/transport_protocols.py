"""Transport protocols for the Aider MCP Server.

This module contains basic transport adapter protocols that define the interface
for all transport implementations in the system.

This was moved from interfaces/transport_adapter.py as part of the
Atomic Design Compliance Refactoring to place basic protocols at the atom level.
"""

from typing import Any, Dict, Optional, Protocol, Set

from typing_extensions import runtime_checkable

from aider_mcp_server.atoms.security.context import SecurityContext
from aider_mcp_server.atoms.types.event_types import EventTypes


@runtime_checkable
class ITransportAdapter(Protocol):
    """Protocol defining the interface for transport adapters.
    
    This protocol specifies the core contract that all transport adapters
    must implement to handle communication in the MCP server.
    
    Moved from interfaces/transport_adapter.py as part of the Atomic Design
    Compliance Refactoring.
    """

    def get_transport_id(self) -> str: ...
    async def shutdown(self) -> None: ...

    # Additional methods specific to ITransportAdapter
    def get_transport_type(self) -> str: ...
    def get_capabilities(self) -> Set[EventTypes]: ...
    async def send_event(self, event_type: EventTypes, data: Dict[str, Any]) -> None: ...
    def should_receive_event(
        self,
        event_type: EventTypes,
        data: Dict[str, Any],
        request_details: Optional[Dict[str, Any]] = None,
    ) -> bool: ...
    async def initialize(self) -> None: ...
    async def start_listening(self) -> None: ...
    async def handle_sse_request(self, request_details: Any) -> Any: ...
    async def handle_message_request(self, request_details: Any) -> Any: ...
    def validate_request_security(self, request_details: Dict[str, Any]) -> SecurityContext: ...


class TransportAdapterBase(ITransportAdapter):
    """Base implementation of the transport adapter protocol.
    
    Provides common functionality for transport adapters while requiring
    concrete implementations to define transport-specific behavior.
    
    Moved from interfaces/transport_adapter.py as part of the Atomic Design
    Compliance Refactoring.
    """
    
    _transport_id: str
    _transport_type: str

    def __init__(self, transport_id: str, transport_type: str):
        self._transport_id = transport_id
        self._transport_type = transport_type

    def get_transport_id(self) -> str:
        return self._transport_id

    def get_transport_type(self) -> str:
        return self._transport_type

    def get_capabilities(self) -> Set[EventTypes]:
        return set()

    async def send_event(self, event_type: EventTypes, data: Dict[str, Any]) -> None:
        raise NotImplementedError

    def should_receive_event(
        self,
        event_type: EventTypes,
        data: Dict[str, Any],
        request_details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return True

    async def initialize(self) -> None:
        raise NotImplementedError

    async def shutdown(self) -> None:
        raise NotImplementedError

    async def start_listening(self) -> None:
        raise NotImplementedError

    async def handle_sse_request(self, request_details: Any) -> Any:
        raise NotImplementedError

    async def handle_message_request(self, request_details: Any) -> Any:
        raise NotImplementedError

    def validate_request_security(self, request_details: Dict[str, Any]) -> SecurityContext:
        raise NotImplementedError