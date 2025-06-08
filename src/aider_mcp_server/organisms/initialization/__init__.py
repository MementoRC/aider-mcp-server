"""
Initialization organisms for application lifecycle management.

This package provides application initialization, startup orchestration,
and lifecycle management functionality extracted from the legacy
templates during the Atomic Design Compliance Refactoring.
"""

from .initialization_coordinator import InitializationCoordinator
from .startup_sequence import StartupSequence

__all__ = [
    "InitializationCoordinator",
    "StartupSequence",
]
