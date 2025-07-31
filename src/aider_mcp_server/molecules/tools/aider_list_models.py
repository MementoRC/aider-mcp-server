from typing import List

# External import - no stubs available
try:
    from aider.models import fuzzy_match_models
except ImportError:

    def fuzzy_match_models(substring: str) -> List[str]:
        """Fallback implementation when aider.models is not available."""
        # Basic fallback models for testing
        basic_models = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4",
            "gpt-3.5-turbo",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ]
        return [model for model in basic_models if substring.lower() in model.lower()]


def list_models(substring: str) -> List[str]:
    """
    List available models that match the provided substring.

    Args:
        substring (str): Substring to match against available models.

    Returns:
        List[str]: List of model names matching the substring.
    """
    return list(fuzzy_match_models(substring))  # Ensure return type is List[str]
