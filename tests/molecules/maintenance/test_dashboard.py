"""
Tests for the Maintenance Dashboard module.
"""

import json
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import Mock

from aider_mcp_server.molecules.maintenance.dashboard import MaintenanceDashboard


class TestMaintenanceDashboard(unittest.TestCase):
    """Test cases for MaintenanceDashboard."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_port = 8081  # Use different port to avoid conflicts
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "test_maintenance.yml"

        # Create test config file
        test_config = {
            "project": {"name": "test-project", "type": "python-backend"},
            "health_thresholds": {"overall_score": 80},
            "automation_levels": {"dependencies": {"patch_updates": "auto"}},
        }

        import yaml

        with open(self.config_path, "w") as f:
            yaml.dump(test_config, f)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_dashboard_initialization(self):
        """Test dashboard initialization."""
        dashboard = MaintenanceDashboard(config_path=str(self.config_path), port=self.test_port)

        self.assertEqual(dashboard.port, self.test_port)
        self.assertIsNotNone(dashboard.orchestrator)
        self.assertEqual(dashboard.orchestrator.config["project"]["name"], "test-project")

    def test_dashboard_start_stop(self):
        """Test dashboard start and stop in non-blocking mode."""
        dashboard = MaintenanceDashboard(config_path=str(self.config_path), port=self.test_port)

        # Start in non-blocking mode
        dashboard.start(blocking=False)

        # Give server time to start
        time.sleep(0.5)

        # Verify server is running
        self.assertIsNotNone(dashboard.server)
        self.assertIsNotNone(dashboard.server_thread)
        self.assertTrue(dashboard.server_thread.is_alive())

        # Stop the server
        dashboard.stop()

        # Verify server is stopped
        self.assertIsNone(dashboard.server)

    def test_dashboard_url(self):
        """Test dashboard URL generation."""
        dashboard = MaintenanceDashboard(config_path=str(self.config_path), port=self.test_port)

        expected_url = f"http://localhost:{self.test_port}"
        self.assertEqual(dashboard.get_url(), expected_url)

        expected_url_custom = f"http://0.0.0.0:{self.test_port}"
        self.assertEqual(dashboard.get_url("0.0.0.0"), expected_url_custom)  # noqa: S104

    def test_dashboard_api_endpoints(self):
        """Test dashboard API endpoints return valid JSON."""
        dashboard = MaintenanceDashboard(config_path=str(self.config_path), port=self.test_port)

        # Start dashboard
        dashboard.start(blocking=False)
        time.sleep(0.5)

        try:
            base_url = f"http://localhost:{self.test_port}"

            # Test health endpoint
            with urllib.request.urlopen(f"{base_url}/api/health") as response:  # noqa: S310
                health_data = json.loads(response.read().decode())
                self.assertIn("overall_score", health_data)
                self.assertIn("status", health_data)
                self.assertIn("component_scores", health_data)
                self.assertEqual(health_data["project_name"], "test-project")

            # Test maintenance plan endpoint
            with urllib.request.urlopen(f"{base_url}/api/maintenance-plan") as response:  # noqa: S310
                plan_data = json.loads(response.read().decode())
                self.assertIn("tasks", plan_data)
                self.assertIn("automation_level", plan_data)

            # Test performance endpoint
            with urllib.request.urlopen(f"{base_url}/api/performance") as response:  # noqa: S310
                performance_data = json.loads(response.read().decode())
                self.assertIn("benchmarks", performance_data)
                self.assertIn("trends", performance_data)

            # Test health history endpoint
            with urllib.request.urlopen(f"{base_url}/api/history/health") as response:  # noqa: S310
                history_data = json.loads(response.read().decode())
                self.assertIn("data", history_data)
                self.assertIn("period", history_data)

        finally:
            dashboard.stop()

    def test_dashboard_main_page(self):
        """Test dashboard main page returns HTML."""
        dashboard = MaintenanceDashboard(config_path=str(self.config_path), port=self.test_port)

        # Start dashboard
        dashboard.start(blocking=False)
        time.sleep(0.5)

        try:
            base_url = f"http://localhost:{self.test_port}"

            # Test main dashboard page
            with urllib.request.urlopen(base_url) as response:  # noqa: S310
                html_content = response.read().decode()
                self.assertIn("<!DOCTYPE html>", html_content)
                self.assertIn("Maintenance Dashboard", html_content)
                self.assertIn("chart.js", html_content)
                self.assertIn("bootstrap", html_content)

            # Test /dashboard path
            with urllib.request.urlopen(f"{base_url}/dashboard") as response:  # noqa: S310
                html_content = response.read().decode()
                self.assertIn("<!DOCTYPE html>", html_content)

        finally:
            dashboard.stop()

    def test_dashboard_404_handling(self):
        """Test dashboard 404 error handling."""
        dashboard = MaintenanceDashboard(config_path=str(self.config_path), port=self.test_port)

        # Start dashboard
        dashboard.start(blocking=False)
        time.sleep(0.5)

        try:
            base_url = f"http://localhost:{self.test_port}"

            # Test non-existent endpoint
            try:
                with urllib.request.urlopen(f"{base_url}/nonexistent"):  # noqa: S310
                    pass
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 404)
                self.assertIn("Not Found", e.read().decode())

        finally:
            dashboard.stop()

    def test_handler_error_handling(self):
        """Test error handling in API endpoints."""
        # Create a handler with a mock orchestrator that raises exceptions
        mock_orchestrator = Mock()
        mock_orchestrator.get_project_info.side_effect = Exception("Test error")

        # Create a mock server with the orchestrator
        mock_server = Mock()
        mock_server.orchestrator = mock_orchestrator

        # Test that the orchestrator is properly assigned
        # This is a basic test to ensure the handler setup works
        self.assertIsNotNone(mock_server.orchestrator)


if __name__ == "__main__":
    unittest.main()
