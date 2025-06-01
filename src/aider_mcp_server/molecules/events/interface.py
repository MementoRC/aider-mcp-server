"""Event handling interface for centralized event processing.

This module contains event handling protocols that define the interface
for all event handling implementations at the molecule level.

This was moved from interfaces/event_handler.py as part of the
Atomic Design Compliance Refactoring to colocate interfaces with their implementations.
"""

from typing import Optional, Protocol

from typing_extensions import runtime_checkable

from aider_mcp_server.atoms.types.internal_types import InternalEvent


@runtime_checkable
class IEventHandler(Protocol):
    """Protocol for components that process internal events.

    This protocol defines the core contract that event handler implementations
    must implement to process events in the system.

    Moved from interfaces/event_handler.py as part of the Atomic Design
    Compliance Refactoring to be colocated with event implementations.
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
