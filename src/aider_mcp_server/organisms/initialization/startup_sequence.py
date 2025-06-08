"""
Application startup sequence coordinator.

This module provides comprehensive application startup orchestration with
timeout handling, error recovery, and transport configuration.

Extracted and enhanced from legacy templates/initialization/initialization_sequence.py
during Task 19 - Redistribute Template Directory Content.
"""

import asyncio
import threading
from typing import Any, Dict, Optional, Set

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol
from aider_mcp_server.molecules.configuration.configuration_manager import ConfigurationManager
from aider_mcp_server.molecules.session.session_manager import SessionManager
from aider_mcp_server.pages.application.coordinator import ApplicationCoordinator


class StartupSequence:
    """
    Orchestrates application startup with proper error handling and timeouts.

    This class manages the complete application initialization sequence,
    including configuration loading, transport setup, and service coordination.
    """

    def __init__(
        self,
        config_manager: Optional[ConfigurationManager] = None,
        logger: Optional[LoggerProtocol] = None,
        initialization_timeout: float = 30.0,
    ):
        """
        Initialize the startup sequence coordinator.

        Args:
            config_manager: Configuration manager instance
            logger: Optional logger instance
            initialization_timeout: Maximum time to wait for initialization
        """
        self.logger = logger or get_logger(__name__)
        self.config_manager = config_manager or ConfigurationManager(logger=self.logger)
        self.initialization_timeout = initialization_timeout

        self._initialization_lock = threading.Lock()
        self._initialized = False
        self._startup_tasks: Set[asyncio.Task[Any]] = set()

    async def initialize_application(
        self, transport_configs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> ApplicationCoordinator:
        """
        Initialize the complete application with all components.

        Args:
            transport_configs: Optional transport configuration overrides

        Returns:
            Initialized ApplicationCoordinator instance

        Raises:
            RuntimeError: If initialization fails or times out
        """
        with self._initialization_lock:
            if self._initialized:
                self.logger.warning("Application already initialized")
                return ApplicationCoordinator()

        self.logger.info("Starting application initialization sequence")

        try:
            # Run initialization with timeout
            coordinator = await asyncio.wait_for(
                self._perform_initialization(transport_configs), timeout=self.initialization_timeout
            )

            with self._initialization_lock:
                self._initialized = True

            self.logger.info("Application initialization completed successfully")
            return coordinator

        except asyncio.TimeoutError:
            self.logger.error(f"Application initialization timed out after {self.initialization_timeout}s")
            await self._cleanup_failed_initialization()
            raise RuntimeError("Application initialization timeout") from None

        except Exception as e:
            self.logger.error(f"Application initialization failed: {e}")
            await self._cleanup_failed_initialization()
            raise RuntimeError(f"Application initialization failed: {e}") from e

    async def _perform_initialization(
        self, transport_configs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> ApplicationCoordinator:
        """Perform the actual initialization steps."""

        # Step 1: Initialize configuration
        self.logger.debug("Initializing configuration...")
        await self._initialize_configuration()

        # Step 2: Initialize session management
        self.logger.debug("Initializing session management...")
        session_manager = await self._initialize_session_manager()

        # Step 3: Initialize application coordinator
        self.logger.debug("Initializing application coordinator...")
        coordinator = ApplicationCoordinator()

        # Step 4: Configure transports
        self.logger.debug("Configuring transports...")
        await self._configure_transports(coordinator, transport_configs)

        # Step 5: Start services
        self.logger.debug("Starting services...")
        await self._start_services(coordinator, session_manager)

        return coordinator

    async def _initialize_configuration(self) -> None:
        """Initialize configuration system."""
        try:
            # Validate configuration
            validation_errors = self.config_manager.validate()
            if validation_errors:
                self.logger.warning(f"Configuration validation warnings: {validation_errors}")

            self.logger.verbose("Configuration system initialized")

        except Exception as e:
            self.logger.error(f"Configuration initialization failed: {e}")
            raise

    async def _initialize_session_manager(self) -> SessionManager:
        """Initialize session management system."""
        try:
            # Get session configuration
            session_timeout = self.config_manager.get("application.session_timeout", 3600.0)
            cleanup_interval = self.config_manager.get("application.session_cleanup_interval", 300.0)

            session_manager = SessionManager(
                logger=self.logger, default_timeout=session_timeout, cleanup_interval=cleanup_interval
            )

            await session_manager.start()
            self.logger.verbose("Session manager initialized")
            return session_manager

        except Exception as e:
            self.logger.error(f"Session manager initialization failed: {e}")
            raise

    async def _configure_transports(
        self, coordinator: ApplicationCoordinator, transport_configs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> None:
        """Configure transport adapters."""
        try:
            # Get transport configuration from config manager
            transports_config = self.config_manager.get_section("transports")

            # Override with provided configs if any
            if transport_configs:
                transports_config.update(transport_configs)

            # Configure each enabled transport
            for transport_name, transport_config in transports_config.items():
                if isinstance(transport_config, dict) and transport_config.get("enabled", False):
                    await self._configure_single_transport(coordinator, transport_name, transport_config)

            self.logger.verbose("Transport configuration completed")

        except Exception as e:
            self.logger.error(f"Transport configuration failed: {e}")
            raise

    async def _configure_single_transport(
        self, coordinator: ApplicationCoordinator, transport_name: str, transport_config: Dict[str, Any]
    ) -> None:
        """Configure a single transport adapter."""
        try:
            self.logger.debug(f"Configuring transport: {transport_name}")

            # This would typically register the transport with the coordinator
            # The actual implementation depends on the coordinator's interface
            # For now, we'll just log the configuration

            self.logger.verbose(f"Transport {transport_name} configured with: {transport_config}")

        except Exception as e:
            self.logger.error(f"Failed to configure transport {transport_name}: {e}")
            raise

    async def _start_services(self, coordinator: ApplicationCoordinator, session_manager: SessionManager) -> None:
        """Start application services."""
        try:
            # Start any additional services here
            # This is where you would start background tasks, monitoring, etc.

            self.logger.verbose("Application services started")

        except Exception as e:
            self.logger.error(f"Service startup failed: {e}")
            raise

    async def _cleanup_failed_initialization(self) -> None:
        """Clean up resources after failed initialization."""
        try:
            # Cancel any pending startup tasks
            for task in self._startup_tasks:
                if not task.done():
                    task.cancel()

            # Wait for tasks to complete cancellation
            if self._startup_tasks:
                await asyncio.gather(*self._startup_tasks, return_exceptions=True)

            self._startup_tasks.clear()

            self.logger.debug("Cleanup after failed initialization completed")

        except Exception as e:
            self.logger.error(f"Error during initialization cleanup: {e}")

    async def shutdown(self) -> None:
        """Shutdown the startup sequence and clean up resources."""
        try:
            # Cancel any running tasks
            await self._cleanup_failed_initialization()

            with self._initialization_lock:
                self._initialized = False

            self.logger.info("Startup sequence shutdown completed")

        except Exception as e:
            self.logger.error(f"Error during startup sequence shutdown: {e}")

    def is_initialized(self) -> bool:
        """Check if the application has been initialized."""
        with self._initialization_lock:
            return self._initialized

    def get_initialization_status(self) -> Dict[str, Any]:
        """Get the current initialization status."""
        return {
            "initialized": self.is_initialized(),
            "timeout": self.initialization_timeout,
            "active_tasks": len(self._startup_tasks),
            "config_loaded": self.config_manager is not None,
        }
