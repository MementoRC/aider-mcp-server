"""Artifact Manager for sandbox experiments."""

import os
from typing import Optional


class ArtifactManager:
    """Minimal ArtifactManager class for testing purposes."""

    def __init__(self, base_path: Optional[str] = None):
        """Initialize ArtifactManager."""
        self.base_path = base_path or "/tmp/artifacts"  # noqa: S108

    def save_artifact(self, artifact_name: str, content: str) -> str:
        """Save artifact to storage (mock implementation)."""
        # Mock implementation - just return path
        path = os.path.join(self.base_path, artifact_name)
        return path

    def get_artifact(self, artifact_name: str) -> Optional[str]:
        """Get artifact from storage (mock implementation)."""
        return f"Mock content for {artifact_name}"