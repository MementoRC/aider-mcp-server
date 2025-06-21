"""
Tests for the Maintenance Orchestration System.

This module provides comprehensive tests for the MaintenanceOrchestrator class,
covering configuration loading, health assessment, maintenance plan generation,
and task execution workflows.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import yaml

from aider_mcp_server.molecules.maintenance.orchestrator import MaintenanceOrchestrator


class TestMaintenanceOrchestrator:
    """Test suite for MaintenanceOrchestrator functionality."""

    def test_initialization_with_valid_config(self, tmp_path):
        """Test orchestrator initialization with a valid configuration file."""
        # Create test config
        config_data = {
            "project": {"name": "test-project", "type": "python-backend", "criticality": "high"},
            "health_thresholds": {"overall_score": 90, "security_vulnerabilities": 0},
            "automation_levels": {"dependencies": {"patch_updates": "auto"}},
        }

        config_path = tmp_path / "test_maintenance.yml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        # Initialize orchestrator
        orchestrator = MaintenanceOrchestrator(str(config_path))

        # Verify configuration loaded correctly
        assert orchestrator.get_project_info()["name"] == "test-project"
        assert orchestrator.get_health_thresholds()["overall_score"] == 90
        assert orchestrator.get_automation_levels()["dependencies"]["patch_updates"] == "auto"

    def test_initialization_with_missing_config(self):
        """Test orchestrator initialization when config file is missing."""
        orchestrator = MaintenanceOrchestrator("nonexistent.yml")

        # Should use default configuration
        project_info = orchestrator.get_project_info()
        assert project_info["name"] == "aider-mcp-server"
        assert project_info["type"] == "python-backend"

        # Verify default thresholds
        thresholds = orchestrator.get_health_thresholds()
        assert thresholds["overall_score"] == 85
        assert thresholds["security_vulnerabilities"] == 0

    def test_initialization_with_invalid_config(self, tmp_path):
        """Test orchestrator initialization with invalid YAML config."""
        config_path = tmp_path / "invalid.yml"
        with open(config_path, "w") as f:
            f.write("invalid: yaml: content: [\n")

        orchestrator = MaintenanceOrchestrator(str(config_path))

        # Should fallback to default configuration
        assert orchestrator.get_project_info()["name"] == "aider-mcp-server"

    def test_assess_health_basic(self):
        """Test basic health assessment functionality."""
        orchestrator = MaintenanceOrchestrator()

        health = orchestrator.assess_health()

        # Verify assessment structure
        assert "timestamp" in health
        assert "overall_score" in health
        assert "component_scores" in health
        assert "health_state" in health
        assert "recommendations" in health
        assert "metrics" in health

        # Verify component scores
        component_scores = health["component_scores"]
        assert "security" in component_scores
        assert "performance" in component_scores
        assert "dependencies" in component_scores
        assert "code_quality" in component_scores
        assert "test_coverage" in component_scores

        # Verify recommendations structure
        for rec in health["recommendations"]:
            assert "type" in rec
            assert "description" in rec
            assert "priority" in rec

    def test_check_performance_basic(self):
        """Test basic performance checking functionality."""
        orchestrator = MaintenanceOrchestrator()

        performance = orchestrator.check_performance()

        # Verify performance check structure
        assert "timestamp" in performance
        assert "overall_performance_score" in performance
        assert "benchmarks" in performance
        assert "regressions" in performance
        assert "recommendations" in performance

        # Verify benchmarks structure
        benchmarks = performance["benchmarks"]
        assert "api_request_processing" in benchmarks
        assert "database_query" in benchmarks

        for benchmark in benchmarks.values():
            assert "mean_time" in benchmark
            assert "p95_time" in benchmark
            assert "throughput" in benchmark

    def test_generate_maintenance_plan_healthy_system(self, tmp_path):
        """Test maintenance plan generation for a healthy system."""
        # Create config with high threshold
        config_data = {
            "health_thresholds": {"overall_score": 80},
            "automation_levels": {
                "dependencies": {"minor_updates": "semi-auto"},
                "security": {"patch_application": "auto"},
            },
        }

        config_path = tmp_path / "config.yml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        orchestrator = MaintenanceOrchestrator(str(config_path))

        plan = orchestrator.generate_maintenance_plan()

        # Verify plan structure
        assert "needs_maintenance" in plan
        assert "overall_health_score" in plan
        assert "threshold" in plan
        assert "generated_at" in plan
        assert "assessment_summary" in plan
        assert "tasks" in plan
        assert "execution_summary" in plan

        # Verify system doesn't need maintenance (health score 87 > threshold 80)
        assert plan["needs_maintenance"] is False
        assert plan["overall_health_score"] >= plan["threshold"]

        # Should still have some routine maintenance tasks
        assert len(plan["tasks"]) > 0

    def test_generate_maintenance_plan_unhealthy_system(self, tmp_path):
        """Test maintenance plan generation for an unhealthy system."""
        # Create config with very high threshold to trigger maintenance
        config_data = {
            "health_thresholds": {"overall_score": 95},
            "automation_levels": {
                "dependencies": {"patch_updates": "auto"},
                "security": {"vulnerability_fixes": "semi-auto"},
            },
        }

        config_path = tmp_path / "config.yml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        orchestrator = MaintenanceOrchestrator(str(config_path))

        plan = orchestrator.generate_maintenance_plan()

        # System should need maintenance (health score 87 < threshold 95)
        assert plan["needs_maintenance"] is True
        assert plan["overall_health_score"] < plan["threshold"]

        # Verify tasks are properly prioritized
        tasks = plan["tasks"]
        assert len(tasks) > 0

        # Check task structure
        for task in tasks:
            assert "id" in task
            assert "type" in task
            assert "description" in task
            assert "priority" in task
            assert "automation" in task
            assert "scheduled_for" in task
            assert "source" in task

    def test_execute_maintenance_plan(self):
        """Test maintenance plan execution."""
        orchestrator = MaintenanceOrchestrator()

        # Generate a plan first
        plan = orchestrator.generate_maintenance_plan()

        # Execute the plan
        results = orchestrator.execute_maintenance_plan(plan)

        # Verify execution results structure
        assert "execution_id" in results
        assert "executed_at" in results
        assert "plan_id" in results
        assert "tasks_executed" in results
        assert "tasks_pending" in results
        assert "tasks_failed" in results
        assert "task_results" in results

        # Verify task execution
        total_tasks = len(plan["tasks"])
        executed = results["tasks_executed"]
        pending = results["tasks_pending"]
        failed = results["tasks_failed"]

        assert executed + pending + failed == total_tasks

        # Verify task results structure
        for task_result in results["task_results"]:
            assert "task_id" in task_result
            assert "status" in task_result
            assert task_result["status"] in ["completed", "pending", "failed"]

    def test_automation_level_determination(self, tmp_path):
        """Test automation level determination for different recommendation types."""
        # Create test config with specific automation levels
        config_data = {
            "automation_levels": {
                "dependencies": {"patch_updates": "semi-auto", "minor_updates": "semi-auto", "major_updates": "manual"},
                "security": {"patch_application": "auto", "vulnerability_fixes": "semi-auto"},
            }
        }

        config_path = tmp_path / "config.yml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        orchestrator = MaintenanceOrchestrator(str(config_path))

        # Test dependency update recommendations
        patch_rec = {"type": "dependency_update", "description": "Update patch version"}
        minor_rec = {"type": "dependency_update", "description": "Update minor version"}
        major_rec = {"type": "dependency_update", "description": "Update major version"}

        assert orchestrator._get_automation_level_for_recommendation(patch_rec) == "semi-auto"
        assert orchestrator._get_automation_level_for_recommendation(minor_rec) == "semi-auto"
        assert orchestrator._get_automation_level_for_recommendation(major_rec) == "manual"

        # Test security recommendations
        security_patch_rec = {"type": "security", "description": "Apply security patch"}
        security_other_rec = {"type": "security", "description": "Fix vulnerability"}

        assert orchestrator._get_automation_level_for_recommendation(security_patch_rec) == "auto"
        assert orchestrator._get_automation_level_for_recommendation(security_other_rec) == "semi-auto"

        # Test unknown type (should default to manual)
        unknown_rec = {"type": "unknown", "description": "Unknown task"}
        assert orchestrator._get_automation_level_for_recommendation(unknown_rec) == "manual"

    def test_task_scheduling(self):
        """Test task scheduling based on priority."""
        orchestrator = MaintenanceOrchestrator()

        high_priority_rec = {"priority": "high"}
        medium_priority_rec = {"priority": "medium"}
        low_priority_rec = {"priority": "low"}

        # Get scheduled dates
        high_date = orchestrator._get_scheduled_date(high_priority_rec)
        medium_date = orchestrator._get_scheduled_date(medium_priority_rec)
        low_date = orchestrator._get_scheduled_date(low_priority_rec)

        # Parse dates for comparison
        high_datetime = datetime.fromisoformat(high_date.replace("Z", "+00:00"))
        medium_datetime = datetime.fromisoformat(medium_date.replace("Z", "+00:00"))
        low_datetime = datetime.fromisoformat(low_date.replace("Z", "+00:00"))

        # High priority should be scheduled immediately (within 1 hour)
        now = datetime.now(timezone.utc)
        assert abs((high_datetime - now).total_seconds()) < 3600

        # Medium priority should be scheduled later than high priority
        assert medium_datetime > high_datetime

        # Low priority should be scheduled later than medium priority
        assert low_datetime > medium_datetime

    def test_effort_estimation(self):
        """Test effort estimation for different task types."""
        orchestrator = MaintenanceOrchestrator()

        # Test dependency update estimations
        patch_rec = {"type": "dependency_update", "description": "patch update"}
        minor_rec = {"type": "dependency_update", "description": "minor update"}
        major_rec = {"type": "dependency_update", "description": "major update"}

        patch_effort = orchestrator._estimate_task_effort(patch_rec)
        minor_effort = orchestrator._estimate_task_effort(minor_rec)
        major_effort = orchestrator._estimate_task_effort(major_rec)

        assert "15-30 minutes" in patch_effort
        assert "1-2 hours" in minor_effort
        assert "4-8 hours" in major_effort

        # Test security task estimation
        high_security_rec = {"type": "security", "priority": "high"}
        medium_security_rec = {"type": "security", "priority": "medium"}

        high_security_effort = orchestrator._estimate_task_effort(high_security_rec)
        medium_security_effort = orchestrator._estimate_task_effort(medium_security_rec)

        assert "2-4 hours" in high_security_effort
        assert "1-2 hours" in medium_security_effort

    def test_maintenance_status(self):
        """Test maintenance status retrieval."""
        orchestrator = MaintenanceOrchestrator()

        # Run an assessment to set last assessment time
        orchestrator.assess_health()

        status = orchestrator.get_maintenance_status()

        # Verify status structure
        assert "last_assessment" in status
        assert "active_tasks" in status
        assert "maintenance_history_count" in status
        assert "recent_executions" in status
        assert "system_health" in status
        assert "next_scheduled_check" in status

        # Verify last assessment is set
        assert status["last_assessment"] is not None

        # Verify next scheduled check is in the future
        next_check = datetime.fromisoformat(status["next_scheduled_check"].replace("Z", "+00:00"))
        assert next_check > datetime.now(timezone.utc)

    def test_task_prioritization(self):
        """Test task prioritization logic."""
        orchestrator = MaintenanceOrchestrator()

        # Create test tasks with different priorities and schedules
        tasks = [
            {"priority": "low", "scheduled_for": "2024-01-01T00:00:00"},
            {"priority": "high", "scheduled_for": "2024-01-02T00:00:00"},
            {"priority": "medium", "scheduled_for": "2024-01-01T12:00:00"},
            {"priority": "high", "scheduled_for": "2024-01-01T06:00:00"},
        ]

        prioritized = orchestrator._prioritize_tasks(tasks)

        # High priority tasks should come first
        assert prioritized[0]["priority"] == "high"
        assert prioritized[1]["priority"] == "high"

        # Among high priority tasks, earlier scheduled should come first
        assert prioritized[0]["scheduled_for"] < prioritized[1]["scheduled_for"]

        # Medium priority should come after high
        assert prioritized[2]["priority"] == "medium"

        # Low priority should come last
        assert prioritized[3]["priority"] == "low"

    def test_execution_summary_generation(self):
        """Test execution summary generation."""
        orchestrator = MaintenanceOrchestrator()

        # Create test tasks with different automation levels and priorities
        tasks = [
            {"automation": "auto", "priority": "high"},
            {"automation": "semi-auto", "priority": "medium"},
            {"automation": "manual", "priority": "low"},
            {"automation": "auto", "priority": "medium"},
        ]

        summary = orchestrator._generate_execution_summary(tasks)

        # Verify summary structure
        assert "total_tasks" in summary
        assert "automated_tasks" in summary
        assert "semi_automated_tasks" in summary
        assert "manual_tasks" in summary
        assert "estimated_total_effort" in summary
        assert "priority_breakdown" in summary

        # Verify counts
        assert summary["total_tasks"] == 4
        assert summary["automated_tasks"] == 2
        assert summary["semi_automated_tasks"] == 1
        assert summary["manual_tasks"] == 1

        # Verify priority breakdown
        priority_breakdown = summary["priority_breakdown"]
        assert priority_breakdown["high"] == 1
        assert priority_breakdown["medium"] == 2
        assert priority_breakdown["low"] == 1

    def test_config_property_accessors(self, tmp_path):
        """Test configuration property accessor methods."""
        config_data = {
            "project": {"name": "test-project", "type": "web-app"},
            "health_thresholds": {"overall_score": 75},
            "automation_levels": {"dependencies": {"patch_updates": "manual"}},
            "maintenance_schedule": {"trigger_type": "calendar_based"},
        }

        config_path = tmp_path / "config.yml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        orchestrator = MaintenanceOrchestrator(str(config_path))

        # Test all property accessors
        assert orchestrator.get_project_info() == config_data["project"]
        assert orchestrator.get_health_thresholds() == config_data["health_thresholds"]
        assert orchestrator.get_automation_levels() == config_data["automation_levels"]
        assert orchestrator.get_maintenance_schedule() == config_data["maintenance_schedule"]

    def test_integration_with_performance_monitoring(self):
        """Test integration with performance monitoring system."""
        orchestrator = MaintenanceOrchestrator()

        # Mock performance results with regressions
        with patch.object(orchestrator, "check_performance") as mock_perf:
            mock_perf.return_value = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "overall_performance_score": 75.0,
                "benchmarks": {},
                "regressions": [{"operation": "api_processing", "regression_pct": 0.25}],
                "recommendations": [],
            }

            plan = orchestrator.generate_maintenance_plan()

            # Should include performance regression tasks
            perf_tasks = [t for t in plan["tasks"] if t["type"] == "performance"]
            assert len(perf_tasks) > 0

            # Performance regression task should be high priority
            perf_task = perf_tasks[0]
            assert perf_task["priority"] == "medium"  # 25% regression is medium priority
            assert "api_processing" in perf_task["description"]

    def test_maintenance_history_tracking(self):
        """Test maintenance history tracking functionality."""
        orchestrator = MaintenanceOrchestrator()

        # Generate and execute a plan
        plan = orchestrator.generate_maintenance_plan()
        orchestrator.execute_maintenance_plan(plan)

        # Check maintenance history was updated
        status = orchestrator.get_maintenance_status()
        assert status["maintenance_history_count"] == 1
        assert len(status["recent_executions"]) == 1

        # Execute another plan
        plan2 = orchestrator.generate_maintenance_plan()
        orchestrator.execute_maintenance_plan(plan2)

        # History should be updated
        status = orchestrator.get_maintenance_status()
        assert status["maintenance_history_count"] == 2
        assert len(status["recent_executions"]) == 2
