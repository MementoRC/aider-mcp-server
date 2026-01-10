"""
Framework module for the Aider MCP Server.

This module provides comprehensive testing and quality assurance frameworks
for systematic software development and maintenance.
"""

from .testing_framework import (
    CoverageReport,
    CoverageThreshold,
    TestingFramework,
    TestResult,
    TestSuiteType,
    main,
)

__all__ = [
    "CoverageReport",
    "CoverageThreshold",
    "TestingFramework",
    "TestResult",
    "TestSuiteType",
    "main",
]
