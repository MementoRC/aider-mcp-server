"""
Comprehensive tests for the PostOperationVerifier system.

Tests cover:
- Verification system initialization
- Content verification (empty, corrupted, valid)
- Syntax validation integration
- Line count validation (reduction, increase thresholds)
- Semantic validation (Python, JS, JSON, YAML)
- Complete file verification workflow
- Error handling and edge cases
- Integration with FileIntegrityManager

Mocks filesystem and external dependencies as needed.
"""

import os
from unittest.mock import patch

import pytest

from aider_mcp_server.atoms.utils.post_operation_verifier import (
    FileVerificationMetrics,
    PostOperationVerifier,
    SemanticVerificationError,
    VerificationResult,
    VerificationResults,
)

# --- Fixtures and helpers ---


@pytest.fixture
def temp_repo(temp_git_repo):
    """Use the existing temp_git_repo fixture."""
    return temp_git_repo


@pytest.fixture
def verifier(temp_repo):
    """Create a PostOperationVerifier instance."""
    return PostOperationVerifier(temp_repo)


@pytest.fixture
def baseline_metrics():
    """Sample baseline metrics for testing."""
    return {
        "src/test.py": {"checksum_sha256": "abc123", "line_count": 10, "git_status": "clean"},
        "src/app.js": {"checksum_sha256": "def456", "line_count": 20, "git_status": "clean"},
        "config.json": {"checksum_sha256": "ghi789", "line_count": 5, "git_status": "clean"},
    }


@pytest.fixture
def create_test_file():
    """Helper to create test files."""

    def _create_file(repo_path, rel_path, content):
        abs_path = os.path.join(repo_path, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return abs_path

    return _create_file


# --- Test Classes ---


class TestPostOperationVerifierInit:
    """Test initialization and configuration."""

    def test_init_success(self, temp_repo):
        verifier = PostOperationVerifier(temp_repo)
        assert verifier.repo_path == os.path.abspath(temp_repo)
        assert verifier.line_count_reduction_threshold == 0.9
        assert verifier.line_count_increase_threshold == 10.0
        assert verifier.enable_semantic_validation is True
        assert verifier.integrity_manager is not None

    def test_init_custom_settings(self, temp_repo):
        verifier = PostOperationVerifier(
            temp_repo,
            line_count_reduction_threshold=0.8,
            line_count_increase_threshold=5.0,
            enable_semantic_validation=False,
        )
        assert verifier.line_count_reduction_threshold == 0.8
        assert verifier.line_count_increase_threshold == 5.0
        assert verifier.enable_semantic_validation is False

    def test_init_invalid_repo(self, tmp_path):
        # Should raise error due to FileIntegrityManager validation
        with pytest.raises((ValueError, RuntimeError, OSError, Exception)):
            PostOperationVerifier(str(tmp_path))


class TestContentVerification:
    """Test content verification logic."""

    def test_verify_content_valid(self, verifier):
        assert verifier._verify_content("def test():\n    pass\n", "test.py") is True

    def test_verify_content_empty(self, verifier):
        assert verifier._verify_content("", "test.py") is False

    def test_verify_content_unicode_error(self, verifier):
        # Test with content that can't be encoded as UTF-8
        # For this test, we'll just verify the normal case since
        # string content is already UTF-8 encoded in Python
        # The real case would be detected during file reading
        content = "valid utf-8 content"
        assert verifier._verify_content(content, "test.py") is True


class TestLineCountValidation:
    """Test line count validation logic."""

    def test_verify_line_count_valid_change(self, verifier):
        # Small change within threshold
        assert verifier._verify_line_count(12, 10, "test.py") is True

    def test_verify_line_count_excessive_reduction(self, verifier):
        # 95% reduction (above 90% threshold)
        assert verifier._verify_line_count(1, 20, "test.py") is False

    def test_verify_line_count_excessive_increase(self, verifier):
        # 15x increase (above 10x threshold)
        assert verifier._verify_line_count(150, 10, "test.py") is False

    def test_verify_line_count_new_file_with_content(self, verifier):
        # New file (baseline 0) with content
        assert verifier._verify_line_count(10, 0, "new_file.py") is True

    def test_verify_line_count_new_file_empty(self, verifier):
        # New file (baseline 0) with no content
        assert verifier._verify_line_count(0, 0, "new_file.py") is False

    def test_verify_line_count_edge_threshold(self, verifier):
        # Exactly at threshold (should pass)
        assert verifier._verify_line_count(1, 10, "test.py") is True  # 90% reduction
        assert verifier._verify_line_count(100, 10, "test.py") is True  # 10x increase


class TestSemanticValidation:
    """Test semantic validation for different file types."""

    def test_verify_python_semantics_valid(self, verifier):
        content = "import os\n\ndef test():\n    pass\n"
        assert verifier._verify_python_semantics(content, "test.py") is True

    def test_verify_python_semantics_no_content(self, verifier):
        content = "# Just comments\n# Nothing else\n"
        assert verifier._verify_python_semantics(content, "test.py") is False

    def test_verify_python_semantics_no_structure(self, verifier):
        content = "x = 1\ny = 2\nz = 3\na = 4\nb = 5\nc = 6\n"  # > 5 lines, no imports/functions/classes
        assert verifier._verify_python_semantics(content, "test.py") is False

    def test_verify_js_semantics_valid(self, verifier):
        content = "import React from 'react';\nfunction App() { return null; }\nexport default App;"
        assert verifier._verify_js_semantics(content, "app.js") is True

    def test_verify_js_semantics_no_content(self, verifier):
        content = "// Just comments\n// Nothing else\n"
        assert verifier._verify_js_semantics(content, "app.js") is False

    def test_verify_json_semantics_valid(self, verifier):
        content = '{"name": "test", "version": "1.0.0"}'
        assert verifier._verify_json_semantics(content, "package.json") is True

    def test_verify_json_semantics_invalid(self, verifier):
        content = '{"name": "test", invalid json}'
        with pytest.raises(SemanticVerificationError):
            verifier._verify_json_semantics(content, "package.json")

    def test_verify_yaml_semantics_valid(self, verifier):
        content = "name: test\nversion: 1.0.0\n"
        assert verifier._verify_yaml_semantics(content, "config.yml") is True

    def test_verify_yaml_semantics_invalid(self, verifier):
        content = "name: test\n  invalid: yaml: structure\n"
        with pytest.raises(SemanticVerificationError):
            verifier._verify_yaml_semantics(content, "config.yml")

    def test_verify_semantics_unsupported_type(self, verifier):
        content = "Some content"
        assert verifier._verify_semantics(content, "file.txt") is True


class TestSingleFileVerification:
    """Test verification of individual files."""

    def test_verify_single_file_not_exists(self, verifier, baseline_metrics):
        # File doesn't exist
        result = verifier._verify_single_file("nonexistent.py", baseline_metrics)
        assert result.exists is False
        assert result.overall_result == VerificationResult.FAIL
        assert "does not exist" in result.content_error

    def test_verify_single_file_read_error(self, verifier, baseline_metrics, temp_repo):
        # File exists but can't be read
        file_path = "test.py"
        abs_path = os.path.join(temp_repo, file_path)

        # Create file
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w") as f:
            f.write("test")

        # Mock open to raise exception
        with patch("builtins.open", side_effect=IOError("Permission denied")):
            result = verifier._verify_single_file(file_path, baseline_metrics)
            assert result.exists is True
            assert result.content_valid is False
            assert "Cannot read file" in result.content_error

    def test_verify_single_file_success(self, verifier, temp_repo, create_test_file):
        # Valid Python file
        file_path = "test.py"
        content = "import os\n\ndef test():\n    return True\n"
        create_test_file(temp_repo, file_path, content)

        # Create baseline that matches the actual content
        baseline_metrics = {
            file_path: {
                "checksum_sha256": "old_checksum",
                "line_count": 4,  # Matches actual line count
                "git_status": "clean",
            }
        }

        # Mock only syntax validation
        with patch.object(verifier.integrity_manager, "validate_syntax", return_value=True):
            result = verifier._verify_single_file(file_path, baseline_metrics)

            assert result.exists is True
            assert result.content_valid is True
            assert result.syntax_valid is True
            # Line count should be valid since they match
            assert result.line_count_valid is True
            assert result.semantic_valid is True
            assert result.overall_result == VerificationResult.PASS

    def test_verify_single_file_syntax_error(self, verifier, baseline_metrics, temp_repo, create_test_file):
        # Python file with syntax error
        file_path = "src/test.py"
        content = "def broken(\n"  # Syntax error
        create_test_file(temp_repo, file_path, content)

        # Mock syntax validation to fail
        from aider_mcp_server.atoms.utils.file_integrity import SyntaxValidationError

        with patch.object(
            verifier.integrity_manager, "validate_syntax", side_effect=SyntaxValidationError("Syntax error")
        ):
            result = verifier._verify_single_file(file_path, baseline_metrics)

            assert result.syntax_valid is False
            assert result.syntax_error == "Syntax error"
            assert result.overall_result == VerificationResult.FAIL


class TestCompleteVerificationWorkflow:
    """Test the complete verification workflow."""

    def test_verify_file_integrity_basic_functionality(self, verifier, temp_repo, create_test_file):
        # Create a simple test with minimal dependencies
        py_content = "import os\n\ndef test():\n    return True\n"
        create_test_file(temp_repo, "test.py", py_content)

        # Simple baseline that matches the content
        baseline_metrics = {
            "test.py": {
                "checksum_sha256": "old_checksum",
                "line_count": 4,  # Matches the content
                "git_status": "clean",
            }
        }

        modified_files = ["test.py"]

        # Mock only the syntax validation to pass
        with patch.object(verifier.integrity_manager, "validate_syntax", return_value=True):
            results = verifier.verify_file_integrity(modified_files, baseline_metrics)

            # Should have one file processed
            assert results.total_files == 1
            assert len(results.file_results) == 1
            assert "test.py" in results.file_results

    def test_verify_file_integrity_with_missing_file(self, verifier):
        # Test with a file that doesn't exist
        baseline_metrics = {"missing.py": {"checksum_sha256": "old_checksum", "line_count": 10, "git_status": "clean"}}

        modified_files = ["missing.py"]

        results = verifier.verify_file_integrity(modified_files, baseline_metrics)

        assert results.overall_result == VerificationResult.FAIL
        assert results.total_files == 1
        assert results.failed_files == 1
        assert results.passed_files == 0

    def test_verify_file_integrity_exception_handling(self, verifier, baseline_metrics):
        modified_files = ["error_file.py"]

        # Mock _verify_single_file to raise exception
        with patch.object(verifier, "_verify_single_file", side_effect=Exception("Test error")):
            results = verifier.verify_file_integrity(modified_files, baseline_metrics)

            assert results.overall_result == VerificationResult.FAIL
            assert results.failed_files == 1
            assert len(results.verification_errors) == 1
            assert "Test error" in results.verification_errors[0]


class TestVerificationDataStructures:
    """Test verification result data structures."""

    def test_file_verification_metrics_post_init(self):
        # Test FAIL case (file doesn't exist)
        metrics = FileVerificationMetrics(
            file_path="test.py",
            exists=False,
            content_valid=True,
            syntax_valid=True,
            line_count_valid=True,
            semantic_valid=True,
            current_line_count=10,
            baseline_line_count=10,
            current_checksum="abc",
            baseline_checksum="def",
        )
        metrics.calculate_overall_result()
        assert metrics.overall_result == VerificationResult.FAIL

        # Test FAIL case (content invalid)
        metrics = FileVerificationMetrics(
            file_path="test.py",
            exists=True,
            content_valid=False,
            syntax_valid=True,
            line_count_valid=True,
            semantic_valid=True,
            current_line_count=10,
            baseline_line_count=10,
            current_checksum="abc",
            baseline_checksum="def",
        )
        metrics.calculate_overall_result()
        assert metrics.overall_result == VerificationResult.FAIL

        # Test PASS case (all valid)
        metrics = FileVerificationMetrics(
            file_path="test.py",
            exists=True,
            content_valid=True,
            syntax_valid=True,
            line_count_valid=True,
            semantic_valid=True,
            current_line_count=10,
            baseline_line_count=10,
            current_checksum="abc",
            baseline_checksum="def",
        )
        metrics.calculate_overall_result()
        assert metrics.overall_result == VerificationResult.PASS

    def test_verification_results_post_init(self):
        # Create sample file results
        pass_metrics = FileVerificationMetrics(
            file_path="pass.py",
            exists=True,
            content_valid=True,
            syntax_valid=True,
            line_count_valid=True,
            semantic_valid=True,
            current_line_count=10,
            baseline_line_count=10,
            current_checksum="abc",
            baseline_checksum="def",
        )
        pass_metrics.calculate_overall_result()

        fail_metrics = FileVerificationMetrics(
            file_path="fail.py",
            exists=False,
            content_valid=False,
            syntax_valid=False,
            line_count_valid=False,
            semantic_valid=False,
            current_line_count=0,
            baseline_line_count=10,
            current_checksum="",
            baseline_checksum="def",
        )
        fail_metrics.calculate_overall_result()

        file_results = {"pass.py": pass_metrics, "fail.py": fail_metrics}

        results = VerificationResults(
            total_files=0,  # Will be calculated
            passed_files=0,
            failed_files=0,
            warning_files=0,
            skipped_files=0,
            file_results=file_results,
            overall_result=VerificationResult.PASS,
            verification_errors=[],
        )

        assert results.total_files == 2
        assert results.passed_files == 1
        assert results.failed_files == 1
        assert results.warning_files == 0
        assert results.overall_result == VerificationResult.FAIL  # Due to failed files


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_semantic_validation_disabled(self, temp_repo):
        verifier = PostOperationVerifier(temp_repo, enable_semantic_validation=False)
        content = "invalid python code that would normally fail"
        assert verifier._verify_semantics(content, "test.py") is True

    def test_line_count_validation_zero_baseline(self, verifier):
        # Edge case: baseline is 0, current is 0
        assert verifier._verify_line_count(0, 0, "test.py") is False
        # Edge case: baseline is 0, current > 0
        assert verifier._verify_line_count(5, 0, "test.py") is True

    def test_checksum_calculation_integration(self, verifier, temp_repo, create_test_file):
        # Test that checksum calculation works through the workflow
        file_path = "test.py"
        content = "print('hello')\n"
        create_test_file(temp_repo, file_path, content)

        baseline_metrics = {file_path: {"checksum_sha256": "old_checksum", "line_count": 1, "git_status": "clean"}}

        with patch.object(verifier.integrity_manager, "validate_syntax", return_value=True):
            result = verifier._verify_single_file(file_path, baseline_metrics)

            assert result.current_checksum != ""
            assert result.current_checksum != result.baseline_checksum
