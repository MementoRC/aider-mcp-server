"""
Rate limiting module for Aider AI operations.

This module provides comprehensive rate limiting functionality including:
- Provider-specific configuration management
- Exponential backoff calculations
- Fallback model selection
- Rate limit error detection and classification
- Integration with event system for monitoring
"""

import asyncio
import json
import os
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TypedDict


# Placeholder for a logger. In a real system, this would integrate with
# the existing logging infrastructure, e.g., from aider_mcp_server.atoms.logging.logger.
class _Logger:
    def info(self, msg: str, **kwargs: Any) -> None:
        print(f"INFO: {msg}")

    def warning(self, msg: str, **kwargs: Any) -> None:
        print(f"WARNING: {msg}")

    def error(self, msg: str, exc_info: bool = False, **kwargs: Any) -> None:
        print(f"ERROR: {msg}")
        if exc_info:
            import traceback

            traceback.print_exc()


logger = _Logger()


# --- 1. RateLimitConfig dataclass for configuration ---


class ProviderConfigDict(TypedDict):
    """
    Defines the structure for provider-specific rate limit and fallback settings.
    """

    rate_limit_errors: List[str]
    backoff_factor: float
    initial_delay: float
    max_retries: int
    fallback_models: List[str]


@dataclass
class RateLimitConfig:
    """
    Manages the configuration for rate limiting and fallback behavior across different providers.
    Loads default settings and can be overridden by a .rate-limit-fallback.json file.
    """

    provider_configs: Dict[str, ProviderConfigDict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Default fallback configuration - this will be overridden by .rate-limit-fallback.json if available
        default_config: Dict[str, ProviderConfigDict] = {
            "openai": {
                "rate_limit_errors": ["rate_limit_exceeded", "insufficient_quota", "429 Too Many Requests"],
                "backoff_factor": 2.0,
                "initial_delay": 1.0,
                "max_retries": 5,
                "fallback_models": ["gpt-3.5-turbo", "gpt-3.5-turbo-16k"],
            },
            "anthropic": {
                "rate_limit_errors": ["rate_limit_exceeded", "429 Too Many Requests"],
                "backoff_factor": 2.0,
                "initial_delay": 1.0,
                "max_retries": 5,
                "fallback_models": ["claude-3-sonnet-20240229", "claude-instant-1"],
            },
            "gemini": {
                "rate_limit_errors": ["quota_exceeded", "resource_exhausted", "429 Too Many Requests"],
                "backoff_factor": 2.0,
                "initial_delay": 1.0,
                "max_retries": 5,
                "fallback_models": ["gemini-pro", "gemini-1.0-pro"],
            },
        }
        self.provider_configs.update(default_config)
        self._load_config_from_file()

    def _load_config_from_file(self) -> None:
        """
        Attempts to load and update configuration from a .rate-limit-fallback.json file.
        Searches in the current directory and parent directories.
        """
        # Define potential paths for the config file, starting from the current directory
        # and moving up the directory tree.
        mcp_json_paths = [
            ".rate-limit-fallback.json",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".rate-limit-fallback.json"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".rate-limit-fallback.json"),
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                ".rate-limit-fallback.json",
            ),
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                ".rate-limit-fallback.json",
            ),
            os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                ),
                ".rate-limit-fallback.json",
            ),
        ]

        mcp_json_path = None
        for path in mcp_json_paths:
            if os.path.exists(path):
                mcp_json_path = path
                break

        if mcp_json_path:
            try:
                with open(mcp_json_path, "r") as f:
                    config_data = json.load(f)
                    if "fallback_config" in config_data:
                        self.provider_configs.update(config_data["fallback_config"])
                        logger.info(f"Loaded fallback config from {mcp_json_path}")
            except Exception as e:
                logger.warning(f"Error loading fallback config from {mcp_json_path}: {e}")

    def get_provider_config(self, provider: str) -> Optional[ProviderConfigDict]:
        """
        Retrieves configuration for a given provider, standardizing the provider name.

        Args:
            provider: The name of the provider (e.g., "openai", "anthropic", "google").

        Returns:
            A dictionary containing the provider's configuration, or None if not found.
        """
        normalized_provider = provider.lower()
        if normalized_provider == "google":
            normalized_provider = "gemini"
        return self.provider_configs.get(normalized_provider)


# --- 2. BackoffCalculator class for exponential backoff ---


class BackoffCalculator:
    """
    Calculates retry delays using exponential backoff with optional jitter.
    """

    def __init__(self, config: RateLimitConfig):
        self._config = config

    def get_retry_delay(
        self, attempt: int, provider: str, max_delay: float = 60.0, jitter_factor: float = 0.1
    ) -> float:
        """
        Calculate the retry delay using exponential backoff with jitter.

        Args:
            attempt: The current retry attempt (0-indexed).
            provider: The provider (e.g., "openai", "anthropic", "gemini").
            max_delay: The maximum delay in seconds to cap the backoff.
            jitter_factor: Factor for adding random jitter to the delay (e.g., 0.1 for +/- 10%).

        Returns:
            The delay in seconds before the next retry.
        """
        provider_config = self._config.get_provider_config(provider)
        if not provider_config:
            # Use default values if provider not found in config
            initial_delay = 1.0
            backoff_factor = 2.0
        else:
            initial_delay = provider_config.get("initial_delay", 1.0)
            backoff_factor = provider_config.get("backoff_factor", 2.0)

        delay = initial_delay * (backoff_factor**attempt)

        # Add jitter: a random value between -jitter_factor*delay and +jitter_factor*delay
        jitter = delay * jitter_factor * (secrets.SystemRandom().random() * 2 - 1)
        delay = delay + jitter

        return max(0.0, min(delay, max_delay))  # Ensure delay is non-negative and capped


# --- 3. ErrorClassifier class for rate limit error detection ---


class ErrorClassifier:
    """
    Detects if a given exception is a rate limit error based on provider-specific patterns.
    """

    def __init__(self, config: RateLimitConfig):
        self._config = config

    def detect_rate_limit_error(self, error: Exception, provider: str) -> bool:
        """
        Detect if the given error is a rate limit error for the specified provider.

        Args:
            error: The exception to check.
            provider: The provider (e.g., "openai", "anthropic", "gemini").

        Returns:
            True if it's a rate limit error, False otherwise.
        """
        error_message = str(error).lower()
        provider_config = self._config.get_provider_config(provider)

        if not provider_config:
            return False

        error_patterns = provider_config.get("rate_limit_errors", [])
        return any(err.lower() in error_message for err in error_patterns)


# --- 4. FallbackManager class for model fallback chains ---


class FallbackManager:
    """
    Manages the selection of fallback models for a given provider.
    """

    def __init__(self, config: RateLimitConfig):
        self._config = config

    def get_fallback_model(self, current_model: str, provider: str) -> str:
        """
        Get the next fallback model for the specified provider.

        Args:
            current_model: The current model that hit a rate limit.
            provider: The provider (e.g., "openai", "anthropic", "gemini").

        Returns:
            The next fallback model to try. If the current model is the last in the
            fallback chain, it cycles back to the first. If no fallbacks are configured
            or the current model is not in the list, it returns the current model or
            the first available fallback.
        """
        provider_config = self._config.get_provider_config(provider)
        if not provider_config:
            return current_model

        fallback_models = provider_config.get("fallback_models", [])

        if not fallback_models:
            return current_model

        try:
            idx = fallback_models.index(current_model)
            if idx + 1 < len(fallback_models):
                return fallback_models[idx + 1]
            else:
                # Cycle back to the first model if at the end of the list
                return fallback_models[0]
        except ValueError:
            # If the current model is not in the list, return the first fallback model
            return fallback_models[0] if fallback_models else current_model


# --- 5. RateLimiter main orchestrator class ---


class RateLimiter:
    """
    Orchestrates rate limiting, backoff, and model fallback logic.
    This class determines if a retry is needed, calculates the delay,
    and suggests a fallback model based on the encountered error and provider configuration.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self._config = config if config else RateLimitConfig()
        self._backoff_calculator = BackoffCalculator(self._config)
        self._error_classifier = ErrorClassifier(self._config)
        self._fallback_manager = FallbackManager(self._config)

    def _broadcast_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Placeholder for broadcasting events to a central event system.
        In a real system, this would integrate with an actual event bus
        (e.g., a pub/sub system or a dedicated event manager).
        """
        logger.info(f"RateLimiter Event: {event_type}, Payload: {payload}")

    async def handle_rate_limit(
        self,
        error: Exception,
        provider: str,
        attempt: int,
        current_model: str,
    ) -> Tuple[bool, float, str]:
        """
        Handles a potential rate limit error, determines if a retry is needed,
        calculates delay, and suggests a fallback model.

        Args:
            error: The exception that occurred.
            provider: The provider (e.g., "openai", "anthropic", "gemini").
            attempt: The current retry attempt (0-indexed).
            current_model: The model that was used when the error occurred.

        Returns:
            A tuple: (should_retry, delay_seconds, next_model_to_try).
            - should_retry: True if a retry is recommended, False otherwise.
            - delay_seconds: The recommended delay before the next attempt.
            - next_model_to_try: The model to use for the next attempt (could be the same).

        Raises:
            Exception: If the error is not a rate limit error or if max retries are exceeded
                       for a rate limit error.
        """
        provider_config = self._config.get_provider_config(provider)
        if not provider_config:
            # If no config, assume no retries for this provider and re-raise the original error.
            logger.warning(f"No rate limit configuration found for provider: {provider}. Not retrying.")
            self._broadcast_event("rate_limit_unconfigured_provider", {"provider": provider, "error": str(error)})
            raise error

        max_retries = provider_config.get("max_retries", 0)

        if self._error_classifier.detect_rate_limit_error(error, provider):
            logger.info(f"Rate limit detected for {provider} (attempt {attempt + 1}/{max_retries + 1}).")
            self._broadcast_event(
                "rate_limit_detected",
                {
                    "provider": provider,
                    "attempt": attempt,
                    "current_model": current_model,
                    "error": str(error),
                },
            )

            if attempt < max_retries:
                delay = self._backoff_calculator.get_retry_delay(attempt, provider)
                next_model = self._fallback_manager.get_fallback_model(current_model, provider)

                logger.info(f"Retrying with model '{next_model}' after {delay:.2f} seconds.")
                self._broadcast_event(
                    "rate_limit_retrying",
                    {
                        "provider": provider,
                        "attempt": attempt,
                        "delay": delay,
                        "old_model": current_model,
                        "new_model": next_model,
                    },
                )
                await asyncio.sleep(delay)  # Use asyncio.sleep for async context
                return True, delay, next_model
            else:
                error_msg = (
                    f"Max retries ({max_retries}) reached for rate limit on {provider}. Unable to complete request."
                )
                logger.error(f"{error_msg} Last error: {str(error)}")
                self._broadcast_event(
                    "rate_limit_max_retries_exceeded",
                    {
                        "provider": provider,
                        "attempt": attempt,
                        "current_model": current_model,
                        "error": str(error),
                        "message": error_msg,
                    },
                )
                raise Exception(error_msg) from error
        else:
            # Not a rate limit error, re-raise the original exception
            logger.error(f"Non-rate-limit error encountered for {provider}: {str(error)}", exc_info=True)
            self._broadcast_event(
                "non_rate_limit_error",
                {
                    "provider": provider,
                    "error": str(error),
                    "type": type(error).__name__,
                },
            )
            raise error
