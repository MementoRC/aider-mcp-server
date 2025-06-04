"""Transport registry interface for transport management.

This module contains transport registry protocols that define the interface
for all transport registry implementations at the organism level.

This interface was created as part of the Atomic Design Compliance Refactoring
to provide a proper protocol for the transport registry implementations.
"""

from typing import Any, List, Optional, Protocol, Set, Type

from typing_extensions import runtime_checkable

from aider_mcp_server.atoms.types.event_types import EventTypes
from aider_mcp_server.atoms.types.transport_protocols import ITransportAdapter
from aider_mcp_server.interfaces.transport_registry import TransportAdapterRegistry


@runtime_checkable
class ITransportRegistry(Protocol):
    """Protocol for transport registry implementations.

    Manages transport adapter registration, discovery, and lifecycle
    at the organism level for high-level transport orchestration.

    Created as part of the Atomic Design Compliance Refactoring to properly
    organize transport registry interfaces with their implementations.
    """

    def register_adapter_class(
        self,
        transport_type: str,
        adapter_class: Type[ITransportAdapter],
        **kwargs: Any,
    ) -> None:
        """
        Register a transport adapter class.

        Args:
            transport_type: The type identifier for the transport.
            adapter_class: The transport adapter class to register.
            **kwargs: Additional configuration for the adapter.
        """
        ...

    def unregister_adapter_class(self, transport_type: str) -> None:
        """
        Unregister a transport adapter class.

        Args:
            transport_type: The type identifier for the transport to unregister.
        """
        ...

    def get_adapter_capabilities(self, transport_type: str) -> Set[EventTypes]:
        """
        Get the capabilities of a registered transport adapter.

        Args:
            transport_type: The type identifier for the transport.

        Returns:
            Set of event types the transport can handle.
        """
        ...

    def create_adapter(self, transport_type: str, **kwargs: Any) -> Optional[ITransportAdapter]:
        """
        Create an instance of a registered transport adapter.

        Args:
            transport_type: The type identifier for the transport.
            **kwargs: Configuration parameters for the adapter.

        Returns:
            An instance of the transport adapter, or None if not found.
        """
        ...

    def get_registered_types(self) -> List[str]:
        """
        Get all registered transport types.

        Returns:
            List of registered transport type identifiers.
        """
        ...

    def initialize(self) -> None:
        """Initialize the registry and discover available transports."""
        ...

    async def shutdown_all(self) -> None:
        """Shutdown all registered transport adapters."""
        ...


__all__ = ["ITransportRegistry", "TransportAdapterRegistry"]
