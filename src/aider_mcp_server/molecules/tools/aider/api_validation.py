import json
import os
from typing import Any, Dict, List, Optional, TypedDict

from aider_mcp_server.atoms.logging.logger import get_logger

# Configure logging for this module
logger = get_logger(__name__)

# Try to import dotenv for environment variable loading
try:
    from dotenv import load_dotenv

    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


class ResponseDict(TypedDict, total=False):
    """Type for Aider response dictionary."""

    success: bool
    changes_summary: Dict[str, Any]
    file_status: Dict[str, Any]
    rate_limit_info: Optional[Dict[str, Any]]
    is_cached_diff: bool
    diff: Optional[str]
    api_key_status: Optional[Dict[str, Any]]
    warnings: Optional[List[str]]


class APIValidator:
    """Handles validation and setup of API credentials for various providers."""

    def __init__(self) -> None:
        """Initialize the API validator."""
        self.provider_keys = {
            "openai": ["OPENAI_API_KEY"],
            "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY"],
            "vertexai": ["VERTEX_AI_API_KEY"],
            "azure": ["AZURE_OPENAI_API_KEY"],
        }

    def load_env_files(self, working_dir: Optional[str] = None) -> None:
        """Load environment variables from .env files in relevant directories."""
        if not HAS_DOTENV:
            logger.info("python-dotenv not available, skipping .env file loading")
            return

        directories_to_check = []

        if working_dir:
            directories_to_check.append(working_dir)

        # Add current directory, parent directory, and home directory
        directories_to_check.extend([os.getcwd(), os.path.dirname(os.getcwd()), os.path.expanduser("~")])

        logger.info("Loading .env files from relevant directories...")

        for directory in directories_to_check:
            env_file_path = os.path.join(directory, ".env")
            if os.path.exists(env_file_path):
                logger.info(f"Loading .env file from: {env_file_path}")
                try:
                    load_dotenv(env_file_path, override=False)
                except Exception as e:
                    logger.warning(f"Failed to load .env file from {env_file_path}: {e}")
            else:
                logger.debug(f"No .env file found at: {env_file_path}")

    def check_api_keys(self, working_dir: Optional[str] = None) -> Dict[str, Any]:
        """Check if necessary API keys are set in the environment."""
        logger.info("Checking API key availability...")

        # Load environment files first
        self.load_env_files(working_dir)

        result = {
            "found": [],
            "missing": [],
            "any_keys_found": False,
            "available_providers": [],
            "missing_providers": [],
        }

        # Check individual API keys
        keys_to_check = {
            "OPENAI_API_KEY": "OpenAI",
            "GOOGLE_API_KEY": "Google/Gemini",
            "GEMINI_API_KEY": "Google/Gemini (alternative)",
            "ANTHROPIC_API_KEY": "Anthropic/Claude",
            "AZURE_OPENAI_API_KEY": "Azure OpenAI",
            "VERTEX_AI_API_KEY": "Vertex AI",
        }

        self._check_individual_api_keys(keys_to_check, result)

        # Handle Gemini API key alias
        self._handle_gemini_api_key_alias(result)

        # Determine available providers
        self._determine_available_providers(self.provider_keys, result)

        logger.info(f"API key check completed. Found keys: {result['found']}")
        return result

    def _check_individual_api_keys(self, keys_to_check: Dict[str, str], result: Dict[str, Any]) -> None:
        """Helper to check individual API keys and update result."""
        logger.info("Checking API keys in environment...")
        for key, provider in keys_to_check.items():
            if os.environ.get(key):
                logger.info(f"✓ {provider} API key found ({key})")
                result["found"].append(key)
                result["any_keys_found"] = True
            else:
                logger.warning(f"✗ {provider} API key missing ({key})")
                result["missing"].append(key)

    def _handle_gemini_api_key_alias(self, result: Dict[str, Any]) -> None:
        """Handle GEMINI_API_KEY and GOOGLE_API_KEY aliasing for compatibility."""
        # If GEMINI_API_KEY is set but GOOGLE_API_KEY is not, set GOOGLE_API_KEY
        if os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
            logger.info("Set GOOGLE_API_KEY from GEMINI_API_KEY for compatibility")
            if "GOOGLE_API_KEY" not in result["found"]:
                result["found"].append("GOOGLE_API_KEY")
                result["any_keys_found"] = True

    def _determine_available_providers(self, provider_keys: Dict[str, List[str]], result: Dict[str, Any]) -> None:
        """Determine available providers based on found keys."""
        logger.info("Determining available providers...")

        for provider, required_keys in provider_keys.items():
            # Check if any of the required keys for this provider are available
            provider_has_key = any(key in result["found"] for key in required_keys)

            if provider_has_key:
                result["available_providers"].append(provider)
                logger.info(f"✓ Provider {provider} is available")
            else:
                result["missing_providers"].append(provider)
                logger.warning(f"✗ Provider {provider} is missing API key")

    def validate_working_dir_and_api_keys(self, working_dir: Optional[str], provider: str) -> Optional[str]:
        """Validate working directory and API keys. Returns error JSON string if validation fails."""
        if not working_dir:
            error_msg = "Error: working_dir is required for code_with_aider"
            logger.error(error_msg)
            return json.dumps(
                {
                    "success": False,
                    "changes_summary": {"summary": error_msg},
                    "error": error_msg,
                    "api_key_status": self.check_api_keys(None),
                }
            )

        key_status, _ = self.handle_api_key_checks_and_warnings(working_dir, provider)
        if not key_status["any_keys_found"]:
            error_msg = "Error: No API keys found for any provider. Please set at least one API key."
            logger.error(error_msg)
            return json.dumps(
                {
                    "success": False,
                    "error": error_msg,
                    "api_key_status": key_status,
                    "warnings": [error_msg],
                    "changes_summary": {"summary": error_msg},
                }
            )

        return None  # No error

    def handle_api_key_checks_and_warnings(
        self, working_dir: Optional[str], provider_requested: str
    ) -> tuple[Dict[str, Any], bool]:
        """Checks API keys and returns status with provider-specific warnings."""
        key_status = self.check_api_keys(working_dir)  # Loads .env files

        # Log general API key status
        if not key_status["any_keys_found"]:
            logger.error("CRITICAL: No API keys found for ANY provider.")
        else:
            logger.info(f"Available providers with keys: {key_status['available_providers']}")
            if key_status["missing_providers"]:
                logger.warning(f"Providers missing keys: {key_status['missing_providers']}")

        # Check for the specifically requested provider
        provider_has_keys = provider_requested in key_status["available_providers"]
        if not provider_has_keys:
            logger.warning(
                f"API key for the initially requested provider '{provider_requested}' is missing or invalid."
                " Fallback mechanisms will be attempted if other provider keys are available."
            )
        return key_status, provider_has_keys

    def update_api_key_status_in_response(
        self,
        response: ResponseDict,
        key_status: Dict[str, Any],
        requested_provider: str,
        actual_model_used: str,
        original_model_requested: str,
    ) -> None:
        """Updates the API key status information in the response."""
        from aider_mcp_server.molecules.tools.aider_ai_code import _determine_provider

        actual_provider_used = _determine_provider(actual_model_used)
        response["api_key_status"] = {
            "available_providers": key_status.get("available_providers", []),
            "missing_providers": key_status.get("missing_providers", []),
            "requested_provider": requested_provider,
            "used_provider": actual_provider_used,
            "original_model_requested": original_model_requested,
            "actual_model_used": actual_model_used,
        }

    def add_provider_warning_to_response(
        self,
        response: ResponseDict,
        key_status: Dict[str, Any],
        requested_provider: str,
        actual_provider_used: str,
        actual_model_used: str,
    ) -> None:
        """Adds warnings if the requested provider's key was missing."""
        if requested_provider not in key_status.get("available_providers", []):
            warning_msg = (
                f"Warning: API key for the initially requested provider '{requested_provider}' was missing. "
                f"The system attempted to use provider '{actual_provider_used}' with model '{actual_model_used}'."
            )
            if "warnings" not in response:
                response["warnings"] = []
            # Ensure warnings is a list
            if not isinstance(response.get("warnings"), list):
                response["warnings"] = []

            if warning_msg not in response["warnings"]:  # type: ignore
                response["warnings"].append(warning_msg)  # type: ignore
