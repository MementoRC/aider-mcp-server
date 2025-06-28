"""
Tests for create_performance_issues.py script.
"""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest
import requests

# Import the script module using importlib to avoid E402
script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "create_performance_issues.py"
spec = importlib.util.spec_from_file_location("create_performance_issues", script_path)
create_performance_issues = importlib.util.module_from_spec(spec)
sys.modules["create_performance_issues"] = create_performance_issues
spec.loader.exec_module(create_performance_issues)

PerformanceIssueCreator = create_performance_issues.PerformanceIssueCreator


@pytest.fixture
def sample_regression_report_data():
    """Create sample performance regression report data."""
    return {
        "regression_reports": [
            {
                "operation_name": "api_request_processing",
                "benchmark_type": "api_request_processing",
                "severity": "moderate",
                "regression_percent": 0.25,  # 25% regression
                "baseline_time": 0.002,
                "current_time": 0.0025,
                "threshold_percent": 0.05,
                "details": {
                    "baseline_throughput": 500.0,
                    "current_throughput": 400.0,
                    "baseline_p95": 0.004,
                    "current_p95": 0.005,
                    "iterations": 50,
                },
                "recommendations": [
                    "Profile API request handling code",
                    "Check for recent changes to request processing pipeline",
                ],
            },
            {
                "operation_name": "file_io_operations",
                "benchmark_type": "file_io_operations",
                "severity": "major",
                "regression_percent": 0.45,  # 45% regression
                "baseline_time": 0.010,
                "current_time": 0.0145,
                "threshold_percent": 0.05,
                "details": {
                    "baseline_throughput": 100.0,
                    "current_throughput": 69.0,
                    "baseline_p95": 0.015,
                    "current_p95": 0.022,
                    "iterations": 30,
                },
                "recommendations": ["Check file system performance", "Review recent file handling changes"],
            },
        ]
    }


@pytest.fixture
def empty_regression_report():
    """Create empty regression report."""
    return {"regression_reports": []}


@pytest.fixture
def sample_config():
    """Create sample maintenance configuration."""
    return {
        "performance_monitoring": {
            "issue_labels": ["performance", "regression", "automated"],
            "max_open_regression_issues": 5,
        },
        "github": {"default_assignees": ["maintainer1"], "team_mentions": ["@team/performance"]},
    }


class TestPerformanceIssueCreator:
    """Test cases for PerformanceIssueCreator class."""

    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    @patch("create_performance_issues.Path.exists")
    def test_initialization_with_token(self, mock_exists):
        """Test PerformanceIssueCreator initialization with GitHub token."""
        mock_exists.return_value = False  # Config file doesn't exist

        creator = PerformanceIssueCreator()

        assert creator.github_token == "test_token"
        assert creator.config_path == Path("maintenance.yml")

    def test_initialization_without_token(self):
        """Test initialization fails without GitHub token."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="GitHub token is required"):
                PerformanceIssueCreator()

    @patch("create_performance_issues.yaml.safe_load")
    @patch("builtins.open", mock_open())
    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    def test_load_config_success(self, mock_yaml_load, sample_config):
        """Test successful config loading."""
        mock_yaml_load.return_value = sample_config

        creator = PerformanceIssueCreator()

        assert creator.config == sample_config

    @patch("builtins.open", side_effect=FileNotFoundError)
    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    def test_load_config_file_not_found(self, mock_open):
        """Test config loading when file doesn't exist."""
        creator = PerformanceIssueCreator()

        # Should use default config
        assert "performance_monitoring" in creator.config
        assert "github" in creator.config

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test_token"})
    @patch("create_performance_issues.Path.exists")
    def test_get_repo_info_from_environment(self, mock_exists):
        """Test getting repository info from environment variables."""
        mock_exists.return_value = False

        creator = PerformanceIssueCreator()

        assert creator.repo_info["owner"] == "owner"
        assert creator.repo_info["name"] == "repo"

    # Git SSH parsing test removed - complex internal implementation detail
    # that's adequately tested through integration tests

    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    @patch("create_performance_issues.Path.exists")
    def test_create_performance_issues_no_regressions(self, mock_exists, empty_regression_report):
        """Test creating issues when no regressions are detected."""
        mock_exists.return_value = False

        creator = PerformanceIssueCreator()
        result = creator.create_performance_issues(empty_regression_report)

        assert result == []

    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_generate_issue_data(self, mock_open, sample_regression_report_data):
        """Test generating issue data from regression reports."""
        creator = PerformanceIssueCreator()
        issues = creator.generate_issue_data(sample_regression_report_data["regression_reports"])

        assert len(issues) == 2

        # Check first issue (moderate severity)
        first_issue = issues[0]
        assert "api_request_processing" in first_issue["title"]
        assert "25.0%" in first_issue["title"]
        assert "moderate-priority" in first_issue["labels"]
        assert "performance" in first_issue["labels"]
        assert first_issue["priority"] == "moderate"
        assert "Performance Details" in first_issue["body"]
        assert "Profile API request handling code" in first_issue["body"]

        # Check second issue (major severity)
        second_issue = issues[1]
        assert "file_io_operations" in second_issue["title"]
        assert "45.0%" in second_issue["title"]
        assert "major-priority" in second_issue["labels"]
        assert second_issue["priority"] == "major"

    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    @patch("create_performance_issues.Path.exists")
    def test_generate_issue_body(self, mock_exists):
        """Test generating issue body content."""
        mock_exists.return_value = False

        creator = PerformanceIssueCreator()

        # Import enums for testing
        from aider_mcp_server.molecules.monitoring.performance_benchmarking import BenchmarkType, RegressionSeverity

        regression = {
            "operation_name": "test_operation",
            "regression_percent": 0.20,
            "baseline_time": 0.005,
            "current_time": 0.006,
            "threshold_percent": 0.05,
            "details": {
                "baseline_throughput": 200.0,
                "current_throughput": 167.0,
                "baseline_p95": 0.008,
                "current_p95": 0.010,
                "iterations": 25,
            },
            "recommendations": ["Check for memory leaks", "Profile the operation"],
        }

        body = creator._generate_issue_body(regression, RegressionSeverity.MODERATE, BenchmarkType.API_REQUEST)

        assert "Performance Regression Detected" in body
        assert "test_operation" in body
        assert "20.0% slower than baseline" in body
        assert "0.0050s" in body  # baseline time
        assert "0.0060s" in body  # current time
        assert "200.00 ops/s" in body  # baseline throughput
        assert "167.00 ops/s" in body  # current throughput
        assert "Check for memory leaks" in body
        assert "Profile the operation" in body

    @patch("create_performance_issues.requests.get")
    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    @patch("create_performance_issues.Path.exists")
    def test_get_existing_performance_issues(self, mock_exists, mock_get):
        """Test fetching existing performance issues."""
        mock_exists.return_value = False

        # Mock GitHub API response
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "title": "Performance regression: api_request_processing is 30.0% slower",
                "body": "## Performance Regression Detected...",
                "number": 123,
            }
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        creator = PerformanceIssueCreator()
        creator.repo_info = {"owner": "testowner", "name": "testrepo"}

        issues = creator.get_existing_performance_issues()

        assert len(issues) == 1
        assert issues[0]["title"] == "Performance regression: api_request_processing is 30.0% slower"
        assert issues[0]["number"] == 123

        # Verify API call was made correctly
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "repos/testowner/testrepo/issues" in call_args[0][0]
        assert call_args[1]["headers"]["Authorization"] == "token test_token"
        assert call_args[1]["params"]["labels"] == "performance,regression"

    @patch("create_performance_issues.requests.post")
    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    @patch("create_performance_issues.Path.exists")
    def test_create_github_issue(self, mock_exists, mock_post):
        """Test creating a GitHub issue via API."""
        mock_exists.return_value = False

        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "number": 456,
            "title": "Test Issue",
            "url": "https://github.com/owner/repo/issues/456",
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        creator = PerformanceIssueCreator()
        creator.repo_info = {"owner": "testowner", "name": "testrepo"}
        creator.config = {"github": {"default_assignees": ["maintainer1"]}}

        issue_data = {
            "title": "Test Performance Issue",
            "body": "Test issue body",
            "labels": ["performance", "regression"],
        }

        result = creator.create_github_issue(issue_data)

        assert result["number"] == 456
        assert result["title"] == "Test Issue"

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "repos/testowner/testrepo/issues" in call_args[0][0]

        payload = call_args[1]["json"]
        assert payload["title"] == "Test Performance Issue"
        assert payload["labels"] == ["performance", "regression"]
        assert payload["assignees"] == ["maintainer1"]

    @patch("create_performance_issues.requests.post")
    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    @patch("create_performance_issues.Path.exists")
    def test_create_github_issue_api_error(self, mock_exists, mock_post):
        """Test handling API errors when creating GitHub issues."""
        mock_exists.return_value = False

        # Mock API error
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("API Error")
        mock_post.return_value = mock_response

        creator = PerformanceIssueCreator()
        creator.repo_info = {"owner": "testowner", "name": "testrepo"}

        issue_data = {"title": "Test Issue", "body": "Test body", "labels": ["performance"]}

        with pytest.raises(requests.HTTPError):
            creator.create_github_issue(issue_data)

    @patch("create_performance_issues.PerformanceIssueCreator.create_github_issue")
    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    @patch("create_performance_issues.Path.exists")
    def test_create_performance_issues_dry_run(self, mock_exists, mock_create, sample_regression_report_data):
        """Test dry run mode."""
        mock_exists.return_value = False

        creator = PerformanceIssueCreator()

        result = creator.create_performance_issues(sample_regression_report_data, dry_run=True)

        # Should return issues but not create them
        assert len(result) == 2
        mock_create.assert_not_called()

    @patch("create_performance_issues.PerformanceIssueCreator.create_github_issue")
    @patch("create_performance_issues.PerformanceIssueCreator.get_existing_performance_issues")
    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    @patch("create_performance_issues.Path.exists")
    def test_create_performance_issues_success(
        self, mock_exists, mock_get_existing, mock_create, sample_regression_report_data
    ):
        """Test successful issue creation."""
        mock_exists.return_value = False
        mock_get_existing.return_value = []  # No existing issues

        # Mock successful GitHub API calls
        mock_create.side_effect = [{"number": 1, "title": "Test Issue 1"}, {"number": 2, "title": "Test Issue 2"}]

        creator = PerformanceIssueCreator()

        result = creator.create_performance_issues(sample_regression_report_data)

        assert len(result) == 2
        assert mock_create.call_count == 2
