"""
Security sandbox module for experimental security tools and utilities.

This module contains prototype security analysis tools that are being evaluated
for integration into the main aider-mcp-server codebase.
"""

from .sbom_generator import SBOMGenerator

__all__ = [
    "SBOMGenerator",
]
