import json
import os
import tempfile
from unittest.mock import patch

from aider_mcp_server.molecules.tools.aider.api_validation import APIValidator


class TestAPIValidator:
    """Test cases for the APIValidator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = APIValidator()

    def test_init(self):
        """Test APIValidator initialization."""
        assert self.validator is not None
        assert "openai" in self.validator.provider_keys
        assert "gemini" in self.validator.provider_keys
        assert "anthropic" in self.validator.provider_keys

    @patch.dict(os.environ, {}, clear=True)
    def test_check_individual_api_keys_no_keys(self):
        """Test checking individual API keys when no keys are set."""
        result = {
            "found": [],
            "missing": [],
            "any_keys_found": False,
            "available_providers": [],
            "missing_providers": [],
        }

        keys_to_check = {"OPENAI_API_KEY": "OpenAI", "GOOGLE_API_KEY": "Google/Gemini"}

        self.validator._check_individual_api_keys(keys_to_check, result)

        assert not result["any_keys_found"]
        assert "OPENAI_API_KEY" in result["missing"]
        assert "GOOGLE_API_KEY" in result["missing"]
        assert len(result["found"]) == 0

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_check_individual_api_keys_with_keys(self):
        """Test checking individual API keys when keys are set."""
        result = {
            "found": [],
            "missing": [],
            "any_keys_found": False,
            "available_providers": [],
            "missing_providers": [],
        }

        keys_to_check = {"OPENAI_API_KEY": "OpenAI", "GOOGLE_API_KEY": "Google/Gemini"}

        self.validator._check_individual_api_keys(keys_to_check, result)

        assert result["any_keys_found"]
        assert "OPENAI_API_KEY" in result["found"]
        assert "GOOGLE_API_KEY" in result["missing"]

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-gemini-key"}, clear=True)
    def test_handle_gemini_api_key_alias(self):
        """Test Gemini API key aliasing functionality."""
        result = {
            "found": ["GEMINI_API_KEY"],
            "missing": [],
            "any_keys_found": True,
            "available_providers": [],
            "missing_providers": [],
        }

        self.validator._handle_gemini_api_key_alias(result)

        assert os.environ.get("GOOGLE_API_KEY") == "test-gemini-key"
        assert "GOOGLE_API_KEY" in result["found"]

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GOOGLE_API_KEY": "existing-key"}, clear=True)
    def test_handle_gemini_api_key_alias_no_override(self):
        """Test that existing GOOGLE_API_KEY is not overridden."""
        result = {
            "found": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            "missing": [],
            "any_keys_found": True,
            "available_providers": [],
            "missing_providers": [],
        }

        self.validator._handle_gemini_api_key_alias(result)

        # Should not override existing GOOGLE_API_KEY
        assert os.environ.get("GOOGLE_API_KEY") == "existing-key"

    def test_determine_available_providers_no_keys(self):
        """Test provider determination when no keys are available."""
        result = {
            "found": [],
            "missing": [],
            "any_keys_found": False,
            "available_providers": [],
            "missing_providers": [],
        }

        provider_keys = {"openai": ["OPENAI_API_KEY"], "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"]}

        self.validator._determine_available_providers(provider_keys, result)

        assert len(result["available_providers"]) == 0
        assert "openai" in result["missing_providers"]
        assert "gemini" in result["missing_providers"]

    def test_determine_available_providers_with_keys(self):
        """Test provider determination when keys are available."""
        result = {
            "found": ["OPENAI_API_KEY", "GOOGLE_API_KEY"],
            "missing": [],
            "any_keys_found": True,
            "available_providers": [],
            "missing_providers": [],
        }

        provider_keys = {
            "openai": ["OPENAI_API_KEY"],
            "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY"],
        }

        self.validator._determine_available_providers(provider_keys, result)

        assert "openai" in result["available_providers"]
        assert "gemini" in result["available_providers"]
        assert "anthropic" in result["missing_providers"]

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_working_dir_and_api_keys_no_working_dir(self):
        """Test validation when working_dir is not provided."""
        result = self.validator.validate_working_dir_and_api_keys(None, "openai")

        assert result is not None
        result_dict = json.loads(result)
        assert not result_dict["success"]
        assert "working_dir is required" in result_dict["changes_summary"]["summary"]

    @patch.dict(os.environ, {}, clear=True)
    @patch("aider_mcp_server.molecules.tools.aider.api_validation.load_dotenv")
    def test_validate_working_dir_and_api_keys_no_keys(self, mock_load_dotenv):
        """Test validation when no API keys are available."""
        # Mock dotenv loading to do nothing
        mock_load_dotenv.return_value = None

        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.validator.validate_working_dir_and_api_keys(temp_dir, "openai")

            assert result is not None
            result_dict = json.loads(result)
            assert not result_dict["success"]
            assert "No API keys found" in result_dict["error"]

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_validate_working_dir_and_api_keys_success(self):
        """Test successful validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.validator.validate_working_dir_and_api_keys(temp_dir, "openai")

            assert result is None  # No error

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_handle_api_key_checks_and_warnings_success(self):
        """Test API key checks with available keys."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_status, provider_has_keys = self.validator.handle_api_key_checks_and_warnings(temp_dir, "openai")

            assert key_status["any_keys_found"]
            assert provider_has_keys
            assert "openai" in key_status["available_providers"]

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    @patch("aider_mcp_server.molecules.tools.aider.api_validation.load_dotenv")
    def test_handle_api_key_checks_and_warnings_different_provider(self, mock_load_dotenv):
        """Test API key checks when requesting unavailable provider."""
        # Mock dotenv loading to do nothing
        mock_load_dotenv.return_value = None

        with tempfile.TemporaryDirectory() as temp_dir:
            key_status, provider_has_keys = self.validator.handle_api_key_checks_and_warnings(temp_dir, "openai")

            assert key_status["any_keys_found"]
            assert not provider_has_keys  # OpenAI key not available
            assert "anthropic" in key_status["available_providers"]
            assert "openai" in key_status["missing_providers"]

    def test_update_api_key_status_in_response(self):
        """Test updating API key status in response."""
        response = {}
        key_status = {"available_providers": ["openai"], "missing_providers": ["gemini"]}

        with patch("aider_mcp_server.molecules.tools.aider_ai_code._determine_provider") as mock_determine:
            mock_determine.return_value = "openai"

            self.validator.update_api_key_status_in_response(response, key_status, "openai", "openai/gpt-4", "gpt-4")

            assert "api_key_status" in response
            api_status = response["api_key_status"]
            assert api_status["requested_provider"] == "openai"
            assert api_status["used_provider"] == "openai"
            assert api_status["original_model_requested"] == "gpt-4"
            assert api_status["actual_model_used"] == "openai/gpt-4"

    def test_add_provider_warning_to_response_missing_provider(self):
        """Test adding warning when requested provider is missing."""
        response = {}
        key_status = {"available_providers": ["anthropic"], "missing_providers": ["openai"]}

        self.validator.add_provider_warning_to_response(response, key_status, "openai", "anthropic", "claude-3")

        assert "warnings" in response
        assert len(response["warnings"]) == 1
        assert "openai" in response["warnings"][0]
        assert "anthropic" in response["warnings"][0]

    def test_add_provider_warning_to_response_available_provider(self):
        """Test no warning when requested provider is available."""
        response = {}
        key_status = {"available_providers": ["openai"], "missing_providers": ["anthropic"]}

        self.validator.add_provider_warning_to_response(response, key_status, "openai", "openai", "gpt-4")

        # No warnings should be added
        assert "warnings" not in response or len(response.get("warnings", [])) == 0

    @patch("aider_mcp_server.molecules.tools.aider.api_validation.HAS_DOTENV", False)
    def test_load_env_files_no_dotenv(self):
        """Test loading env files when dotenv is not available."""
        # Should not raise an exception
        self.validator.load_env_files("/tmp")

    @patch("aider_mcp_server.molecules.tools.aider.api_validation.HAS_DOTENV", True)
    @patch("aider_mcp_server.molecules.tools.aider.api_validation.load_dotenv")
    def test_load_env_files_with_dotenv(self, mock_load_dotenv):
        """Test loading env files when dotenv is available."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a .env file
            env_file_path = os.path.join(temp_dir, ".env")
            with open(env_file_path, "w") as f:
                f.write("TEST_KEY=test_value\n")

            self.validator.load_env_files(temp_dir)

            # Should have called load_dotenv with the env file
            mock_load_dotenv.assert_called()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_check_api_keys_integration(self):
        """Test complete API key checking integration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.validator.check_api_keys(temp_dir)

            assert result["any_keys_found"]
            assert "OPENAI_API_KEY" in result["found"]
            assert "openai" in result["available_providers"]
            assert len(result["missing_providers"]) > 0  # Should have some missing providers


class TestAPIValidatorErrorHandling:
    """Test error handling scenarios for APIValidator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = APIValidator()

    @patch("aider_mcp_server.molecules.tools.aider.api_validation.load_dotenv")
    def test_load_env_files_exception_handling(self, mock_load_dotenv):
        """Test that exceptions during env file loading are handled gracefully."""
        mock_load_dotenv.side_effect = Exception("Test exception")

        with tempfile.TemporaryDirectory() as temp_dir:
            env_file_path = os.path.join(temp_dir, ".env")
            with open(env_file_path, "w") as f:
                f.write("TEST_KEY=test_value\n")

            # Should not raise an exception
            self.validator.load_env_files(temp_dir)

    def test_response_dict_warnings_initialization(self):
        """Test that warnings list is properly initialized in response."""
        response = {"warnings": "not_a_list"}  # Invalid type
        key_status = {"available_providers": []}

        self.validator.add_provider_warning_to_response(
            response, key_status, "missing_provider", "available_provider", "model"
        )

        # Should fix the warnings field to be a list
        assert isinstance(response["warnings"], list)
        assert len(response["warnings"]) == 1
