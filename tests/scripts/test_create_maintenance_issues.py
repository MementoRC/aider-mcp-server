"""
Tests for Create Maintenance Issues Script (Task 8).

Tests the script that creates GitHub issues based on health assessment results.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

# Import the script module using importlib to avoid E402
script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "create_maintenance_issues.py"
spec = importlib.util.spec_from_file_location("create_maintenance_issues", script_path)
create_maintenance_issues = importlib.util.module_from_spec(spec)
sys.modules["create_maintenance_issues"] = create_maintenance_issues
spec.loader.exec_module(create_maintenance_issues)

MaintenanceIssueCreator = create_maintenance_issues.MaintenanceIssueCreator


class TestMaintenanceIssueCreator(unittest.TestCase):
    """Test cases for MaintenanceIssueCreator."""

    def setUp(self):
        """Set up test fixtures."""
        self.github_token = "test-token-123"
        self.repo_owner = "test-owner"
        self.repo_name = "test-repo"

        # Create temporary config file
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "maintenance.yml"

        self.test_config = {
            "maintenance_automation": {
                "auto_create_issues": True,
                "auto_assign_reviewers": False,
                "issue_labels": ["maintenance", "automated", "health-alert"],
                "max_open_issues": 3,
                "consolidate_similar": True,
            },
            "github": {"default_assignees": [], "team_mentions": []},
        }

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.test_config, f)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    def test_initialization_with_token(self):
        """Test successful initialization with GitHub token."""
        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        self.assertEqual(creator.github_token, self.github_token)
        self.assertEqual(creator.repo_info["owner"], "test-owner")
        self.assertEqual(creator.repo_info["repo"], "test-repo")
        self.assertEqual(creator.config, self.test_config)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    def test_initialization_without_token(self):
        """Test initialization failure without GitHub token."""
        with self.assertRaises(ValueError) as context:
            MaintenanceIssueCreator(github_token=None, config_path=self.config_path)

        self.assertIn("GitHub token is required", str(context.exception))

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    def test_load_config_success(self):
        """Test successful configuration loading."""
        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        self.assertEqual(creator.config["maintenance_automation"]["auto_create_issues"], True)
        self.assertEqual(creator.config["maintenance_automation"]["max_open_issues"], 3)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    def test_load_config_file_not_found(self):
        """Test configuration loading with missing file."""
        non_existent_path = Path(self.temp_dir) / "nonexistent.yml"
        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=non_existent_path)

        # Should fall back to default config
        self.assertIsInstance(creator.config, dict)
        self.assertIn("maintenance_automation", creator.config)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    def test_get_repo_info_from_environment(self):
        """Test repository info extraction from environment."""
        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        self.assertEqual(creator.repo_info["owner"], "test-owner")
        self.assertEqual(creator.repo_info["repo"], "test-repo")

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    @patch("requests.get")
    def test_create_maintenance_issues_no_recommendations(self, mock_get):
        """Test issue creation with health report that needs no maintenance."""
        # Create test health report with high scores
        health_report = {
            "composite_score": 95,
            "component_scores": {"security": 98, "dependencies": 96, "performance": 94},
            "recommendations": [],
        }

        report_path = Path(self.temp_dir) / "health_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(health_report, f)

        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        # Mock GitHub API to return no existing issues
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        created_issues = creator.create_maintenance_issues(report_path)

        # Should not create any issues for high health score
        self.assertEqual(len(created_issues), 0)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    def test_analyze_health_for_issues_critical(self):
        """Test health analysis for critical maintenance needs."""
        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        # Create health data requiring critical maintenance
        health_data = {
            "composite_score": 45,  # Critical level
            "component_scores": {"security": 30, "dependencies": 40, "performance": 65},
            "recommendations": ["Update critical security vulnerabilities", "Fix dependency conflicts"],
        }

        issues = creator._analyze_health_for_issues(health_data)

        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertIn("CRITICAL", issue["title"])
        self.assertIn("45/100", issue["title"])
        self.assertEqual(issue["priority"], "critical")
        self.assertIn("systematic-maintenance", issue["labels"])

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    def test_generate_issue_body(self):
        """Test issue body generation with health data."""
        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        health_data = {
            "composite_score": 65,
            "component_scores": {"security": 60, "dependencies": 70, "performance": 65},
            "recommendations": ["Update dependencies", "Review security settings"],
        }

        body = creator._generate_main_issue_body(health_data, 65, "medium")

        self.assertIn("Health Score:** 65/100", body)
        self.assertIn("Urgency Level:** medium", body)
        self.assertIn("Security:** 🟡 60/100", body)
        self.assertIn("Dependencies:** 🟢 70/100", body)  # 70 is good (green)
        self.assertIn("Performance:** 🟡 65/100", body)
        self.assertIn("Update dependencies", body)
        self.assertIn("Review security settings", body)
        self.assertIn("Systematic Maintenance Framework", body)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    @patch("requests.get")
    def test_get_existing_maintenance_issues(self, mock_get):
        """Test fetching existing maintenance issues."""
        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        existing_issues = [
            {"number": 1, "title": "🔧 MEDIUM Maintenance Required - Health Score: 70/100"},
            {"number": 2, "title": "Security Update Required"},
        ]

        mock_response = Mock()
        mock_response.json.return_value = existing_issues
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        issues = creator._get_existing_maintenance_issues()

        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0]["number"], 1)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    def test_filter_duplicate_issues(self):
        """Test duplicate issue filtering."""
        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        new_issues = [
            {
                "title": "🔧 MEDIUM Maintenance Required - Health Score: 70/100",
                "type": "main_maintenance",
                "priority": "medium",
                "labels": [],
            }
        ]

        existing_issues = [{"title": "🔧 MEDIUM Maintenance Required - Health Score: 65/100"}]

        filtered = creator._filter_duplicate_issues(new_issues, existing_issues)

        # Should filter out duplicate maintenance issue
        self.assertEqual(len(filtered), 0)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    @patch("requests.post")
    def test_create_github_issue(self, mock_post):
        """Test GitHub issue creation."""
        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        issue_data = {
            "title": "Test Maintenance Issue",
            "body": "Test issue body",
            "labels": ["maintenance", "test"],
            "priority": "medium",
            "type": "main_maintenance",
        }

        mock_response_data = {
            "number": 123,
            "title": "Test Maintenance Issue",
            "html_url": "https://github.com/test-owner/test-repo/issues/123",
        }

        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        created_issue = creator._create_github_issue(issue_data)

        self.assertEqual(created_issue["number"], 123)
        self.assertEqual(created_issue["title"], "Test Maintenance Issue")
        self.assertEqual(created_issue["priority"], "medium")
        self.assertEqual(created_issue["type"], "main_maintenance")

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    @patch("requests.post")
    def test_create_github_issue_api_error(self, mock_post):
        """Test GitHub issue creation with API error."""
        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        issue_data = {
            "title": "Test Issue",
            "body": "Test body",
            "labels": ["test"],
            "priority": "medium",
            "type": "test",
        }

        import requests

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("HTTP 403: Forbidden")
        mock_post.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            creator._create_github_issue(issue_data)

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "test-owner/test-repo"})
    @patch("requests.post")
    @patch("requests.get")
    def test_create_maintenance_issues_success(self, mock_get, mock_post):
        """Test successful maintenance issue creation end-to-end."""
        # Create health report requiring maintenance
        health_report = {
            "composite_score": 60,  # Requires maintenance
            "component_scores": {"security": 55, "dependencies": 65, "performance": 60},
            "recommendations": ["Update security patches", "Review dependency versions"],
        }

        report_path = Path(self.temp_dir) / "health_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(health_report, f)

        creator = MaintenanceIssueCreator(github_token=self.github_token, config_path=self.config_path)

        # Mock no existing issues
        mock_get_response = Mock()
        mock_get_response.json.return_value = []
        mock_get_response.raise_for_status.return_value = None
        mock_get.return_value = mock_get_response

        # Mock successful issue creation
        mock_created_issue = {
            "number": 456,
            "title": "🔧 MEDIUM Maintenance Required - Health Score: 60/100",
            "html_url": "https://github.com/test-owner/test-repo/issues/456",
        }

        mock_post_response = Mock()
        mock_post_response.json.return_value = mock_created_issue
        mock_post_response.raise_for_status.return_value = None
        mock_post.return_value = mock_post_response

        created_issues = creator.create_maintenance_issues(report_path)

        self.assertEqual(len(created_issues), 1)
        issue = created_issues[0]
        self.assertEqual(issue["number"], 456)
        self.assertIn("MEDIUM Maintenance Required", issue["title"])


if __name__ == "__main__":
    unittest.main()
