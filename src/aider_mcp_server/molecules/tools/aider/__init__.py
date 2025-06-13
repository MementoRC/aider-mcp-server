"""
Aider AI Code Tool - Unified Public API

This module provides a clean, unified public API for the refactored aider tool components.
The decomposition follows atomic design principles, improving maintainability, reducing
complexity, and enhancing code organization while preserving backward compatibility.

The module provides access to all refactored components:
- CoreExecutor: Core Aider execution logic
- RateLimiter: Rate limit handling and fallback strategies
- ResponseFormatter: Response processing and formatting
- CacheManager: Diff cache integration and management
- APIValidator: API key validation and setup
- SessionCoordinator: Session lifecycle and event coordination

Additionally, it provides an AiderTool facade class that maintains backward compatibility
with the original aider_ai_code.py interface.
"""

import os
from typing import Any, Dict, List, Optional

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.utils.safety_system_manager import (
    SafetySystemManager,
    create_safety_system_manager,
)

# Import all refactored components
from .api_validation import APIValidator
from .cache_management import CacheManager
from .core_execution import CoreExecutor
from .rate_limiting import RateLimiter
from .response_formatting import ResponseFormatter
from .session_coordination import SessionCoordinator
from .shared import (
    ExecutionConfig,
    ExecutionResult,
    FileInfo,
    ModelConfig,
    ResponseDict,
    RetryConfig,
    SilentInputOutput,
)

logger = get_logger(__name__)


class AiderTool:
    """
    Main entry point for the Aider AI tool, providing backward compatibility.

    This facade class orchestrates all the refactored components to provide
    a unified interface that maintains compatibility with the original
    aider_ai_code.py implementation.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the AiderTool with configuration.

        Args:
            config: Configuration dictionary for all components
        """
        self.config = config or {}

        # Initialize all components
        self.api_validator = APIValidator()
        self.cache_manager = CacheManager()
        self.core_executor = CoreExecutor()
        self.rate_limiter = RateLimiter()
        self.response_formatter = ResponseFormatter()
        self.session_coordinator = SessionCoordinator()

        # Initialize safety system manager (lazy)
        self._safety_manager: Optional[SafetySystemManager] = None

        # Track initialization state
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all components asynchronously."""
        if self._initialized:
            return

        try:
            # Initialize cache manager
            await self.cache_manager.initialize_cache()

            # Load environment variables for API validation
            working_dir = self.config.get("working_dir")
            self.api_validator.load_env_files(working_dir)

            self._initialized = True
            logger.info("AiderTool initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize AiderTool: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown all components gracefully."""
        try:
            await self.cache_manager.shutdown_cache()
            self._initialized = False
            logger.info("AiderTool shutdown successfully")
        except Exception as e:
            logger.error(f"Error during AiderTool shutdown: {e}")
            raise

    def _get_safety_manager(self, working_dir: str, **kwargs: Any) -> Optional[SafetySystemManager]:
        """Get or create safety system manager with lazy initialization."""
        if self._safety_manager is None:
            # Extract safety configuration from kwargs
            safety_level = kwargs.get("safety_level", "balanced")
            custom_config = kwargs.get("safety_config")

            # Create safety manager
            self._safety_manager = create_safety_system_manager(
                safety_level=safety_level,
                custom_config=custom_config,
            )

        return self._safety_manager

    async def execute_command(
        self,
        ai_coding_prompt: str,
        relative_editable_files: List[str],
        relative_readonly_files: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ResponseDict:
        """
        Execute an Aider command with the given parameters.

        This is the main entry point that orchestrates all components
        to execute an aider coding session with integrated safety system.

        Args:
            ai_coding_prompt: The coding prompt for aider
            relative_editable_files: List of files that can be edited
            relative_readonly_files: List of files for context only
            **kwargs: Additional parameters including:
                - bypass_safety: Skip safety system (default: False)
                - safety_level: Safety level string (default: "balanced")
                - safety_config: Custom safety configuration

        Returns:
            ResponseDict containing the execution results
        """
        if not self._initialized:
            await self.initialize()

        # Extract common parameters
        working_dir = kwargs.get("working_dir", os.getcwd())

        # Check if safety should be bypassed
        bypass_safety = kwargs.get("bypass_safety", False)
        if bypass_safety:
            logger.info("Safety system bypassed via parameter")
            return await self._execute_without_safety(
                ai_coding_prompt, relative_editable_files, relative_readonly_files, **kwargs
            )

        # Check environment variable bypass
        if os.environ.get("AIDER_BYPASS_SAFETY", "").lower() in ("1", "true", "yes"):
            logger.info("Safety system bypassed via environment variable")
            return await self._execute_without_safety(
                ai_coding_prompt, relative_editable_files, relative_readonly_files, **kwargs
            )

        # Get safety manager
        safety_manager = self._get_safety_manager(
            working_dir, **{k: v for k, v in kwargs.items() if k != "working_dir"}
        )

        # Check if safety should be bypassed (includes disabled level check)
        operation_params = {
            "prompt": ai_coding_prompt,
            "files": relative_editable_files,
            "model": kwargs.get("model", "gpt-4"),
            "working_dir": working_dir,
            **kwargs,
        }

        if safety_manager and safety_manager.should_bypass_safety(operation_params):
            logger.info("Safety system bypassed")
            return await self._execute_without_safety(
                ai_coding_prompt, relative_editable_files, relative_readonly_files, **kwargs
            )

        # Check if working directory is a git repository
        import subprocess

        try:
            subprocess.run(["git", "status"], cwd=working_dir, check=True, capture_output=True)  # noqa: S603,S607
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Not a git repository or git not available, bypass safety system
            logger.info("Safety system bypassed - not a git repository")
            return await self._execute_without_safety(
                ai_coding_prompt, relative_editable_files, relative_readonly_files, **kwargs
            )

        # Execute with safety system
        return await self._execute_with_safety(
            ai_coding_prompt, relative_editable_files, relative_readonly_files, safety_manager, **kwargs
        )

    async def _execute_without_safety(
        self,
        ai_coding_prompt: str,
        relative_editable_files: List[str],
        relative_readonly_files: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ResponseDict:
        """Execute aider without safety system (original behavior)."""
        try:
            # Extract common parameters
            working_dir = kwargs.get("working_dir", os.getcwd())
            model = kwargs.get("model", "gpt-4")
            architect_mode = kwargs.get("architect_mode", False)
            editor_model = kwargs.get("editor_model")

            # Start session coordination
            request_id = await self.session_coordinator.start_session(
                ai_coding_prompt=ai_coding_prompt,
                relative_editable_files=relative_editable_files,
                relative_readonly_files=relative_readonly_files or [],
                original_model=model,
                working_dir=working_dir,
                architect_mode=architect_mode,
            )

            # Validate API credentials
            api_status = self.api_validator.check_api_keys(working_dir)
            if not api_status.get("any_keys_found", False):
                api_error_response: ResponseDict = {
                    "success": False,
                    "error": "API key validation failed",
                    "api_key_status": api_status,
                    "changes_summary": {},
                    "file_status": {},
                    "warnings": ["API key validation failed"],
                }
                return api_error_response

            # Generate cache key
            cache_key = self.cache_manager.generate_cache_key(working_dir=working_dir, files=relative_editable_files)

            # Cache will be checked during execution and result formatting
            # The cache manager works with raw diff output, not response dictionaries

            # Convert to absolute paths
            abs_editable_files = self.core_executor.convert_to_absolute_paths(relative_editable_files, working_dir)
            abs_readonly_files = self.core_executor.convert_to_absolute_paths(
                relative_readonly_files or [], working_dir
            )

            # Extract provider from model (simplified approach)
            provider = "openai"  # Default provider
            if "claude" in model.lower() or "anthropic" in model.lower():
                provider = "anthropic"
            elif "gemini" in model.lower() or "google" in model.lower():
                provider = "gemini"

            # Execute aider session with retry logic
            result = await self.core_executor.execute_with_retry(
                ai_coding_prompt=ai_coding_prompt,
                relative_editable_files=relative_editable_files,
                abs_editable_files=abs_editable_files,
                abs_readonly_files=abs_readonly_files,
                working_dir=working_dir,
                model=model,
                provider=provider,
                use_diff_cache=True,
                clear_cached_for_unchanged=True,
                architect_mode=architect_mode,
                editor_model=editor_model,
                auto_accept_architect=kwargs.get("auto_accept_architect", True),
                coordinator=self.session_coordinator.coordinator
                if hasattr(self.session_coordinator, "coordinator")
                else None,
            )

            # Format the response
            formatted_result = self.response_formatter.finalize_aider_response(response=result, include_diff=True)

            # Update API key status in response
            self.response_formatter.update_api_key_status_in_response(formatted_result, api_status)

            # Cache the result if successful and contains diff
            if (
                formatted_result.get("success", False)
                and self.cache_manager.diff_cache
                and formatted_result.get("diff")
            ):
                # Cache the raw diff output
                await self.cache_manager.process_diff_cache(
                    cache_key=cache_key, raw_diff_output=formatted_result["diff"], use_diff_cache=True
                )

            # Complete session coordination
            if request_id:
                await self.session_coordinator.complete_session(
                    response=dict(formatted_result),  # Convert ResponseDict to dict
                    actual_model_used=model,
                    original_model=model,
                    relative_editable_files=relative_editable_files,
                    success=formatted_result.get("success", False),
                )

            return formatted_result

        except Exception as e:
            logger.error(f"Error executing aider command: {e}")
            error_response: ResponseDict = {
                "success": False,
                "error": str(e),
                "changes_summary": {},
                "file_status": {},
                "warnings": [str(e)],
            }

            # Handle session error if we have a request_id
            if "request_id" in locals() and request_id:
                await self.session_coordinator.handle_session_error(e)

            return error_response

    async def _execute_with_safety(
        self,
        ai_coding_prompt: str,
        relative_editable_files: List[str],
        relative_readonly_files: Optional[List[str]] = None,
        safety_manager: Optional[SafetySystemManager] = None,
        **kwargs: Any,
    ) -> ResponseDict:
        """Execute aider with safety system protection."""
        if not safety_manager:
            logger.warning("Safety manager not available, falling back to standard execution")
            return await self._execute_without_safety(
                ai_coding_prompt, relative_editable_files, relative_readonly_files, **kwargs
            )

        working_dir = kwargs.get("working_dir", os.getcwd())

        try:
            # Phase 1: Pre-execution safety check
            operation_context = {
                "prompt": ai_coding_prompt,
                "model": kwargs.get("model", "gpt-4"),
                "architect_mode": kwargs.get("architect_mode", False),
                "working_dir": working_dir,
            }

            pre_check = safety_manager.pre_execution_check(
                working_directory=working_dir,
                target_files=relative_editable_files,
                operation_context=operation_context,
            )

            if not pre_check.is_safe:
                logger.warning(f"Pre-execution safety check failed: {pre_check.reason}")
                return {
                    "success": False,
                    "error": "Safety check failed",
                    "safety_details": {
                        "reason": pre_check.reason,
                        "user_message": pre_check.user_message,
                        "details": pre_check.details,
                    },
                    "changes_summary": {},
                    "file_status": {},
                    "warnings": [pre_check.user_message or "Operation blocked by safety system"],
                }

            # Phase 2: Create safety checkpoint
            checkpoint_result = safety_manager.create_checkpoint(
                repo_path=working_dir,
                files_to_track=relative_editable_files,
                operation_metadata=operation_context,
            )

            if not checkpoint_result.success:
                logger.warning(f"Checkpoint creation failed: {checkpoint_result.error_message}")
                # Continue without checkpoint but log the issue

            # Phase 3: Execute aider operation (original logic)
            result = await self._execute_without_safety(
                ai_coding_prompt, relative_editable_files, relative_readonly_files, **kwargs
            )

            # Phase 4: Post-execution safety validation
            if checkpoint_result.checkpoint_id:
                safety_result = safety_manager.complete_safety_operation(
                    repo_path=working_dir,
                    target_files=relative_editable_files,
                    checkpoint_id=checkpoint_result.checkpoint_id,
                    operation_context=operation_context,
                )

                # Add safety information to result
                result["safety_status"] = {
                    "enabled": True,
                    "level": safety_manager.config.safety_level.value,
                    "checkpoint_id": checkpoint_result.checkpoint_id,
                    "safety_success": safety_result.success,
                    "performance_metrics": safety_result.performance_metrics,
                }

                # Handle rollback if failures detected
                if not safety_result.success and safety_result.rollback_result:
                    logger.warning("Safety system triggered rollback")
                    result["success"] = False
                    result["error"] = "Safety system triggered rollback due to failures"
                    result["safety_details"] = {
                        "failure_detection": safety_result.failure_detection,
                        "rollback_result": safety_result.rollback_result,
                        "recovery_guidance": safety_result.recovery_guidance,
                    }

                    # Add recovery guidance to warnings
                    if safety_result.recovery_guidance:
                        guidance_message = (
                            f"Recovery guidance available: "
                            f"{safety_result.recovery_guidance.total_recommendations} recommendations"
                        )
                        result.setdefault("warnings", []).append(guidance_message)

            return result

        except Exception as e:
            logger.error(f"Safety system execution failed: {e}")
            # Fall back to standard execution on safety system failure
            logger.info("Falling back to standard execution due to safety system error")
            fallback_result = await self._execute_without_safety(
                ai_coding_prompt, relative_editable_files, relative_readonly_files, **kwargs
            )

            # Add warning about safety system failure
            fallback_result.setdefault("warnings", []).append(
                f"Safety system failed ({str(e)}), executed without safety protection"
            )
            fallback_result["safety_status"] = {
                "enabled": False,
                "error": str(e),
                "fallback_execution": True,
            }

            return fallback_result

    # Backward compatibility methods
    async def aider_ai_code(
        self,
        ai_coding_prompt: str,
        relative_editable_files: List[str],
        relative_readonly_files: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ResponseDict:
        """Legacy method name for backward compatibility."""
        return await self.execute_command(
            ai_coding_prompt=ai_coding_prompt,
            relative_editable_files=relative_editable_files,
            relative_readonly_files=relative_readonly_files,
            **kwargs,
        )

    def get_component(self, component_name: str) -> Any:
        """Get direct access to a specific component.

        Args:
            component_name: Name of the component to retrieve

        Returns:
            The requested component instance

        Raises:
            ValueError: If component name is not recognized
        """
        components = {
            "api_validator": self.api_validator,
            "cache_manager": self.cache_manager,
            "core_executor": self.core_executor,
            "rate_limiter": self.rate_limiter,
            "response_formatter": self.response_formatter,
            "session_coordinator": self.session_coordinator,
        }

        if component_name not in components:
            raise ValueError(f"Unknown component: {component_name}")

        return components[component_name]


# Convenience function for quick usage
async def execute_aider_command(
    ai_coding_prompt: str,
    relative_editable_files: List[str],
    relative_readonly_files: Optional[List[str]] = None,
    **kwargs: Any,
) -> ResponseDict:
    """
    Convenience function to execute an aider command without managing an AiderTool instance.

    This function creates a temporary AiderTool instance, executes the command,
    and cleans up automatically.

    Args:
        ai_coding_prompt: The coding prompt for aider
        relative_editable_files: List of files that can be edited
        relative_readonly_files: List of files for context only
        **kwargs: Additional parameters

    Returns:
        ResponseDict containing the execution results
    """
    tool = AiderTool(kwargs.get("config", {}))
    try:
        return await tool.execute_command(
            ai_coding_prompt=ai_coding_prompt,
            relative_editable_files=relative_editable_files,
            relative_readonly_files=relative_readonly_files,
            **kwargs,
        )
    finally:
        await tool.shutdown()


# Export all public components and types
__all__ = [
    # Main facade class
    "AiderTool",
    # Individual components (for direct access)
    "CoreExecutor",
    "RateLimiter",
    "ResponseFormatter",
    "CacheManager",
    "APIValidator",
    "SessionCoordinator",
    # Shared types
    "ResponseDict",
    "ExecutionConfig",
    "ModelConfig",
    "ExecutionResult",
    "FileInfo",
    "RetryConfig",
    "SilentInputOutput",
    # Convenience function
    "execute_aider_command",
]
