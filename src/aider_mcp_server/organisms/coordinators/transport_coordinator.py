"""
Transport Coordinator for managing transport adapter lifecycle and registration.
Handles transport discovery, initialization, registration, and cleanup.
"""

import asyncio
from typing import Any, Dict, List, Optional

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol
from aider_mcp_server.interfaces.transport_adapter import ITransportAdapter
from aider_mcp_server.organisms.registries.transport_adapter_registry_enhanced import EnhancedTransportAdapterRegistry


class TransportCoordinator:
    """
    Manages the lifecycle of transport adapters.
    Provides centralized transport registration, initialization, and cleanup.
    """

    def __init__(self) -> None:
        """Initialize the transport coordinator."""
        self._logger: LoggerProtocol = get_logger(__name__)
        self._transport_registry = EnhancedTransportAdapterRegistry()
        self._registered_transports: Dict[str, ITransportAdapter] = {}
        self._lock = asyncio.Lock()
        self._logger.info("TransportCoordinator initialized.")

    async def initialize(self) -> None:
        """Initialize the transport coordinator and discover available adapters."""
        async with self._lock:
            self._logger.info("Initializing TransportCoordinator...")
            # Discover available transport adapters
            self._transport_registry.discover_adapters(package_name="transports")
            self._logger.info("Transport adapters discovery initiated.")

    async def register_transport(
        self, transport_name: str, **kwargs: Any
    ) -> Optional[ITransportAdapter]:
        """Register and initialize a transport adapter."""
        self._logger.info(f"Registering transport: {transport_name} with config: {kwargs}")
        
        async with self._lock:
            # Initialize the transport using the registry
            transport = await self._transport_registry.initialize_adapter(
                transport_name, self, {}
            )

            if transport:
                transport_id = transport.get_transport_id()
                self._registered_transports[transport_id] = transport
                self._logger.info(f"Transport '{transport_name}' (ID: {transport_id}) registered successfully.")
                return transport
            else:
                self._logger.error(f"Failed to initialize transport '{transport_name}'.")
                return None

    async def register_transport_adapter(self, transport_adapter: ITransportAdapter) -> None:
        """Register an already-instantiated transport adapter."""
        transport_id = transport_adapter.get_transport_id()
        transport_type = transport_adapter.get_transport_type()
        self._logger.info(f"Registering instantiated transport adapter: {transport_id} ({transport_type})")

        async with self._lock:
            self._registered_transports[transport_id] = transport_adapter
            self._logger.info(f"Transport adapter '{transport_id}' registered.")

    async def unregister_transport(self, transport_id: str) -> bool:
        """Unregister a transport adapter."""
        self._logger.info(f"Unregistering transport: {transport_id}")
        
        async with self._lock:
            if transport_id in self._registered_transports:
                del self._registered_transports[transport_id]
                self._logger.info(f"Transport '{transport_id}' unregistered successfully.")
                return True
            else:
                self._logger.warning(f"Transport '{transport_id}' not found for unregistration.")
                return False

    def get_transport(self, transport_id: str) -> Optional[ITransportAdapter]:
        """Get a registered transport by ID."""
        return self._registered_transports.get(transport_id)

    def get_all_transports(self) -> Dict[str, ITransportAdapter]:
        """Get all registered transports."""
        return dict(self._registered_transports)

    def get_active_transport_ids(self) -> List[str]:
        """Get the list of active transport IDs."""
        return list(self._registered_transports.keys())

    async def shutdown(self) -> None:
        """Shut down the transport coordinator and all registered transports."""
        async with self._lock:
            self._logger.info("Shutting down TransportCoordinator...")
            
            # Shutdown all registered transports
            for transport_id, transport in self._registered_transports.items():
                try:
                    if hasattr(transport, 'shutdown') and callable(getattr(transport, 'shutdown')):
                        await transport.shutdown()
                        self._logger.debug(f"Transport '{transport_id}' shut down successfully.")
                except Exception as e:
                    self._logger.error(f"Error shutting down transport '{transport_id}': {e}")

            # Shutdown the transport registry
            if hasattr(self._transport_registry, "shutdown_all"):
                await self._transport_registry.shutdown_all()
            else:
                self._logger.warning("TransportAdapterRegistry does not have shutdown_all method.")

            self._registered_transports.clear()
            self._logger.info("TransportCoordinator shutdown complete.")

    @property
    def transport_count(self) -> int:
        """Get the number of registered transports."""
        return len(self._registered_transports)

    def is_transport_registered(self, transport_id: str) -> bool:
        """Check if a transport is registered."""
        return transport_id in self._registered_transports