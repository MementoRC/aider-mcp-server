"""
Model Response Validation System for Aider MCP Server.

This module provides the ModelResponseValidator class, which validates
model behavior and responses during aider operations.

Features:
1. Validates response completeness (checks for truncated/incomplete responses)
2. Ensures model consistency (verifies requested model is actually used)
3. Detects API errors (catches and logs API errors or rate limiting)
4. Tracks fallbacks (logs when model fallbacks occur)
"""

from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)


class ValidationCategory(Enum):
    """Categories of validation checks."""
    COMPLETENESS = "completeness"
    MODEL_CONSISTENCY = "model_consistency" 
    API_ERROR = "api_error"
    FALLBACK = "fallback"


class ValidationError(Exception):
    """Raised when a model response fails validation."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class ResponseValidationResult(TypedDict, total=False):
    """Result of model response validation."""
    valid: bool
    errors: List[str]
    warnings: List[str]
    fallback_info: Optional[Dict[str, Any]]
    api_error: Optional[str]


# Keep backward compatibility
ModelResponseValidationError = ValidationError


class ModelResponseValidator:
    """
    Validates model responses for completeness, consistency, API errors, and fallbacks.
    """

    def __init__(self) -> None:
        self.logger = logger

    def validate_response(
        self,
        response: Dict[str, Any],
        requested_model: Optional[str] = None,
        allow_fallback: bool = True,
        min_content_length: int = 10,
    ) -> Dict[str, Any]:
        """
        Perform all model response validations.

        Args:
            response: The model response dictionary (Aider ResponseDict or similar)
            requested_model: The model that was originally requested
            allow_fallback: Whether to allow fallback models without error
            min_content_length: Minimum content length for completeness

        Returns:
            The validated response (may be modified in-place)

        Raises:
            ModelResponseValidationError: If validation fails
        """
        errors: List[str] = []

        # 1. Validate completeness
        if not self.is_response_complete(response, min_content_length):
            msg = "Model response appears incomplete or truncated."
            errors.append(msg)
            self.logger.warning(msg)

        # 2. Validate model consistency
        if requested_model:
            if not self.is_model_consistent(response, requested_model):
                actual_model = self.get_actual_model_used(response)
                msg = (
                    f"Model inconsistency: requested '{requested_model}', "
                    f"but actual model used was '{actual_model}'."
                )
                if not allow_fallback:
                    errors.append(msg)
                self.logger.warning(msg)

        # 3. Detect API errors
        api_error = self.detect_api_error(response)
        if api_error:
            msg = f"API error detected: {api_error}"
            errors.append(msg)
            self.logger.error(msg)

        # 4. Track fallbacks
        fallback_info = self.detect_fallback(response, requested_model)
        if fallback_info:
            msg = (
                f"Model fallback occurred: requested '{requested_model}', "
                f"used '{fallback_info['used_model']}' (provider: {fallback_info.get('used_provider')})"
            )
            self.logger.info(msg)
            # Optionally, add to response warnings
            if "warnings" not in response:
                response["warnings"] = []
            response["warnings"].append(msg)

        if errors:
            raise ValidationError(
                "Model response validation failed.",
                details={"errors": errors, "response": response},
            )

        return response

    def is_response_complete(self, response: Dict[str, Any], min_content_length: int = 10) -> bool:
        """
        Checks if the response is complete (not truncated or empty).

        Args:
            response: The model response dictionary
            min_content_length: Minimum content length for completeness

        Returns:
            True if response is complete, False otherwise
        """
        # Check for a 'diff' or 'changes_summary' with meaningful content
        diff = response.get("diff", "")
        if diff and len(diff.strip()) >= min_content_length:
            return True

        # Check for summary text
        summary = ""
        if "changes_summary" in response and isinstance(response["changes_summary"], dict):
            summary = response["changes_summary"].get("summary", "")
        if summary and len(summary.strip()) >= min_content_length:
            return True

        # Optionally, check for files changed
        files = []
        if "changes_summary" in response and isinstance(response["changes_summary"], dict):
            files = response["changes_summary"].get("files", [])
        if files:
            return True

        return False

    def is_model_consistent(self, response: Dict[str, Any], requested_model: str) -> bool:
        """
        Checks if the model actually used matches the requested model.

        Args:
            response: The model response dictionary
            requested_model: The model that was originally requested

        Returns:
            True if consistent, False otherwise
        """
        actual_model = self.get_actual_model_used(response)
        if not actual_model:
            return True  # Can't check, so don't fail
        return actual_model == requested_model

    def get_actual_model_used(self, response: Dict[str, Any]) -> Optional[str]:
        """
        Extracts the actual model used from the response.

        Args:
            response: The model response dictionary

        Returns:
            The actual model used, or None if not found
        """
        # Try to get from api_key_status or similar
        api_key_status = response.get("api_key_status", {})
        if isinstance(api_key_status, dict):
            actual_model = api_key_status.get("actual_model_used")
            if actual_model:
                return str(actual_model)
        # Try other locations if needed
        return None

    def detect_api_error(self, response: Dict[str, Any]) -> Optional[str]:
        """
        Detects if an API error or rate limit occurred.

        Args:
            response: The model response dictionary

        Returns:
            Error message if detected, else None
        """
        # Check for error field
        error = response.get("error")
        if error:
            return str(error)
        # Check for rate limit info
        rate_limit_info = response.get("rate_limit_info", {})
        if isinstance(rate_limit_info, dict) and rate_limit_info.get("encountered"):
            return "Rate limit encountered"
        return None

    def detect_fallback(self, response: Dict[str, Any], requested_model: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Detects if a fallback model was used.

        Args:
            response: The model response dictionary
            requested_model: The model that was originally requested

        Returns:
            Dict with fallback info if fallback occurred, else None
        """
        api_key_status = response.get("api_key_status", {})
        if not isinstance(api_key_status, dict):
            return None
        actual_model = api_key_status.get("actual_model_used")
        used_provider = api_key_status.get("used_provider")
        if requested_model and actual_model and actual_model != requested_model:
            return {
                "requested_model": requested_model,
                "used_model": actual_model,
                "used_provider": used_provider,
            }
        # Also check for fallback_model in rate_limit_info
        rate_limit_info = response.get("rate_limit_info", {})
        if isinstance(rate_limit_info, dict):
            fallback_model = rate_limit_info.get("fallback_model")
            if fallback_model and requested_model and fallback_model != requested_model:
                return {
                    "requested_model": requested_model,
                    "used_model": fallback_model,
                    "used_provider": used_provider,
                }
        return None
