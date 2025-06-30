"""
Maintenance Dashboard for visualizing project health and maintenance status.

This module provides a simple web-based dashboard that integrates with the
MaintenanceOrchestrator to display health metrics, maintenance plans, and
performance data in an accessible web interface.
"""

import json
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol
from aider_mcp_server.molecules.maintenance.orchestrator import MaintenanceOrchestrator


class MaintenanceDashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the maintenance dashboard."""

    def __init__(self, request: Any, client_address: Any, server: Any) -> None:
        self.orchestrator: MaintenanceOrchestrator = server.orchestrator
        super().__init__(request, client_address, server)

    def do_GET(self) -> None:
        """Handle GET requests."""
        path = urllib.parse.urlparse(self.path).path

        if path == "/" or path == "/dashboard":
            self._serve_dashboard()
        elif path == "/api/health":
            self._serve_api_health()
        elif path == "/api/maintenance-plan":
            self._serve_api_maintenance_plan()
        elif path == "/api/performance":
            self._serve_api_performance()
        elif path == "/api/history/health":
            self._serve_api_health_history()
        elif path == "/api/history/performance":
            self._serve_api_performance_history()
        else:
            self._send_response(404, "text/plain", "Not Found")

    def _send_response(self, status: int, content_type: str, content: str) -> None:
        """Send HTTP response."""
        self.send_response(status)
        self.send_header("Content-type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _serve_dashboard(self) -> None:
        """Serve the main dashboard HTML page."""
        html_content = self._get_dashboard_html()
        self._send_response(200, "text/html", html_content)

    def _serve_api_health(self) -> None:
        """Serve health data API endpoint."""
        try:
            # Simulate health data using orchestrator config
            project_info = self.orchestrator.get_project_info()
            health_data = {
                "overall_score": 85,
                "status": "healthy",
                "component_scores": {
                    "security": 88,
                    "dependencies": 82,
                    "performance": 90,
                    "code_quality": 85,
                    "test_coverage": 89,
                },
                "last_updated": datetime.now().isoformat(),
                "project_name": project_info.get("name", "aider-mcp-server"),
            }
            self._send_response(200, "application/json", json.dumps(health_data))
        except Exception as e:
            error_data = {"error": str(e), "status": "error"}
            self._send_response(500, "application/json", json.dumps(error_data))

    def _serve_api_maintenance_plan(self) -> None:
        """Serve maintenance plan API endpoint."""
        try:
            # Simulate maintenance plan data
            plan_data = {
                "tasks": [
                    {
                        "type": "dependency_update",
                        "description": "Update outdated dependencies",
                        "priority": "medium",
                        "automation": "semi-auto",
                        "scheduled_for": datetime.now().isoformat(),
                    },
                    {
                        "type": "security_scan",
                        "description": "Run security vulnerability scan",
                        "priority": "high",
                        "automation": "auto",
                        "scheduled_for": datetime.now().isoformat(),
                    },
                ],
                "next_maintenance": datetime.now().isoformat(),
                "automation_level": self.orchestrator.config.get("automation_levels", {}),
            }
            self._send_response(200, "application/json", json.dumps(plan_data))
        except Exception as e:
            error_data = {"error": str(e), "status": "error"}
            self._send_response(500, "application/json", json.dumps(error_data))

    def _serve_api_performance(self) -> None:
        """Serve performance data API endpoint."""
        try:
            # Simulate performance data
            performance_data = {
                "benchmarks": {
                    "api_request_processing": {"current": 0.025, "baseline": 0.020, "status": "regression"},
                    "file_io_operations": {"current": 0.015, "baseline": 0.018, "status": "improvement"},
                    "memory_usage": {"current": 245.5, "baseline": 250.0, "status": "stable"},
                },
                "trends": {
                    "response_time": [0.020, 0.022, 0.025, 0.023, 0.025],
                    "throughput": [100, 98, 95, 97, 95],
                    "memory": [250, 248, 245, 247, 245],
                },
                "last_updated": datetime.now().isoformat(),
            }
            self._send_response(200, "application/json", json.dumps(performance_data))
        except Exception as e:
            error_data = {"error": str(e), "status": "error"}
            self._send_response(500, "application/json", json.dumps(error_data))

    def _serve_api_health_history(self) -> None:
        """Serve health history data API endpoint."""
        try:
            # Simulate health history data
            history_data = {
                "data": [
                    {"date": "2024-01-01", "score": 88},
                    {"date": "2024-01-02", "score": 86},
                    {"date": "2024-01-03", "score": 85},
                    {"date": "2024-01-04", "score": 87},
                    {"date": "2024-01-05", "score": 85},
                ],
                "period": "5_days",
            }
            self._send_response(200, "application/json", json.dumps(history_data))
        except Exception as e:
            error_data = {"error": str(e), "status": "error"}
            self._send_response(500, "application/json", json.dumps(error_data))

    def _serve_api_performance_history(self) -> None:
        """Serve performance history data API endpoint."""
        try:
            # Simulate performance history data
            history_data = {
                "data": [
                    {"date": "2024-01-01", "response_time": 0.020, "throughput": 100},
                    {"date": "2024-01-02", "response_time": 0.022, "throughput": 98},
                    {"date": "2024-01-03", "response_time": 0.025, "throughput": 95},
                    {"date": "2024-01-04", "response_time": 0.023, "throughput": 97},
                    {"date": "2024-01-05", "response_time": 0.025, "throughput": 95},
                ],
                "period": "5_days",
            }
            self._send_response(200, "application/json", json.dumps(history_data))
        except Exception as e:
            error_data = {"error": str(e), "status": "error"}
            self._send_response(500, "application/json", json.dumps(error_data))

    def _get_dashboard_html(self) -> str:
        """Generate the dashboard HTML content."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Maintenance Dashboard - Aider MCP Server</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .health-score-gauge {
            text-align: center;
            padding: 20px;
        }
        .health-score-value {
            font-size: 3rem;
            font-weight: bold;
            margin: 10px 0;
        }
        .card-header {
            background-color: #f8f9fa;
            font-weight: bold;
        }
        .status-healthy { color: #28a745; }
        .status-warning { color: #ffc107; }
        .status-critical { color: #dc3545; }
        .refresh-indicator {
            font-size: 0.8rem;
            color: #6c757d;
        }
    </style>
</head>
<body>
    <div class="container mt-4">
        <div class="row">
            <div class="col-12">
                <h1 class="mb-4">
                    =' Aider MCP Server - Maintenance Dashboard
                    <small class="text-muted refresh-indicator" id="last-updated">Loading...</small>
                </h1>
            </div>
        </div>

        <div class="row mt-4">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Overall Health Score</h5>
                    </div>
                    <div class="card-body health-score-gauge">
                        <div class="health-score-value" id="health-score-value">--</div>
                        <p id="health-status" class="mb-0">Loading...</p>
                        <p class="text-muted" id="project-name">--</p>
                    </div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Component Health Scores</h5>
                    </div>
                    <div class="card-body">
                        <canvas id="component-scores-chart" height="200"></canvas>
                    </div>
                </div>
            </div>
        </div>

        <div class="row mt-4">
            <div class="col-md-12">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Maintenance Tasks</h5>
                    </div>
                    <div class="card-body">
                        <table class="table table-striped mb-0">
                            <thead>
                                <tr>
                                    <th>Type</th>
                                    <th>Description</th>
                                    <th>Priority</th>
                                    <th>Automation</th>
                                    <th>Scheduled For</th>
                                </tr>
                            </thead>
                            <tbody id="maintenance-tasks">
                                <tr>
                                    <td colspan="5" class="text-center">Loading tasks...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <div class="row mt-4">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Performance Trends</h5>
                    </div>
                    <div class="card-body">
                        <canvas id="performance-chart" height="300"></canvas>
                    </div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Health History</h5>
                    </div>
                    <div class="card-body">
                        <canvas id="health-history-chart" height="300"></canvas>
                    </div>
                </div>
            </div>
        </div>

        <div class="row mt-4 mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Current Benchmarks</h5>
                    </div>
                    <div class="card-body" id="benchmarks-container">
                        <p class="text-center">Loading benchmark data...</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let componentChart = null;
        let performanceChart = null;
        let healthHistoryChart = null;

        async function fetchData() {
            try {
                document.getElementById('last-updated').textContent = 'Updating...';

                const [healthResponse, planResponse, performanceResponse, healthHistoryResponse] = await Promise.all([
                    fetch('/api/health'),
                    fetch('/api/maintenance-plan'),
                    fetch('/api/performance'),
                    fetch('/api/history/health')
                ]);

                const health = await healthResponse.json();
                const plan = await planResponse.json();
                const performance = await performanceResponse.json();
                const healthHistory = await healthHistoryResponse.json();

                updateDashboard(health, plan, performance, healthHistory);

                const now = new Date();
                document.getElementById('last-updated').textContent =
                    `Last updated: ${now.toLocaleTimeString()}`;

            } catch (error) {
                console.error('Error fetching data:', error);
                document.getElementById('last-updated').textContent = 'Update failed';
            }
        }

        function updateDashboard(health, plan, performance, healthHistory) {
            // Update health score
            document.getElementById('health-score-value').textContent = health.overall_score + '/100';
            document.getElementById('project-name').textContent = health.project_name || 'Unknown Project';

            const statusElement = document.getElementById('health-status');
            statusElement.textContent = health.status;
            statusElement.className = health.status === 'healthy' ? 'status-healthy' :
                                    health.overall_score > 70 ? 'status-warning' : 'status-critical';

            // Update component scores chart
            updateComponentScoresChart(health.component_scores);

            // Update maintenance tasks table
            updateMaintenanceTasks(plan.tasks);

            // Update performance chart
            updatePerformanceChart(performance);

            // Update health history chart
            updateHealthHistoryChart(healthHistory);

            // Update benchmarks
            updateBenchmarks(performance.benchmarks);
        }

        function updateComponentScoresChart(componentScores) {
            const ctx = document.getElementById('component-scores-chart').getContext('2d');

            if (componentChart) {
                componentChart.destroy();
            }

            componentChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: Object.keys(componentScores).map(key =>
                        key.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase())
                    ),
                    datasets: [{
                        label: 'Component Scores',
                        data: Object.values(componentScores),
                        backgroundColor: Object.values(componentScores).map(score =>
                            score >= 80 ? 'rgba(40, 167, 69, 0.6)' :
                            score >= 60 ? 'rgba(255, 193, 7, 0.6)' :
                            'rgba(220, 53, 69, 0.6)'
                        ),
                        borderColor: Object.values(componentScores).map(score =>
                            score >= 80 ? 'rgba(40, 167, 69, 1)' :
                            score >= 60 ? 'rgba(255, 193, 7, 1)' :
                            'rgba(220, 53, 69, 1)'
                        ),
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 100,
                            ticks: {
                                callback: function(value) {
                                    return value + '%';
                                }
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        }
                    }
                }
            });
        }

        function updateMaintenanceTasks(tasks) {
            const tbody = document.getElementById('maintenance-tasks');
            tbody.innerHTML = '';

            if (tasks.length === 0) {
                const row = document.createElement('tr');
                row.innerHTML = '<td colspan="5" class="text-center text-success">No maintenance tasks needed <�</td>';
                tbody.appendChild(row);
            } else {
                tasks.forEach(task => {
                    const row = document.createElement('tr');
                    const priorityClass = task.priority === 'high' ? 'danger' :
                                         task.priority === 'medium' ? 'warning' : 'info';
                    const scheduledDate = new Date(task.scheduled_for).toLocaleDateString();

                    row.innerHTML = `
                        <td><code>${task.type.replace(/_/g, ' ')}</code></td>
                        <td>${task.description}</td>
                        <td><span class="badge bg-${priorityClass}">${task.priority}</span></td>
                        <td><span class="badge bg-secondary">${task.automation}</span></td>
                        <td>${scheduledDate}</td>
                    `;
                    tbody.appendChild(row);
                });
            }
        }

        function updatePerformanceChart(performance) {
            const ctx = document.getElementById('performance-chart').getContext('2d');

            if (performanceChart) {
                performanceChart.destroy();
            }

            performanceChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: ['T-4', 'T-3', 'T-2', 'T-1', 'Current'],
                    datasets: [{
                        label: 'Response Time (ms)',
                        data: performance.trends.response_time.map(v => v * 1000),
                        borderColor: 'rgba(54, 162, 235, 1)',
                        backgroundColor: 'rgba(54, 162, 235, 0.1)',
                        yAxisID: 'y'
                    }, {
                        label: 'Throughput (req/s)',
                        data: performance.trends.throughput,
                        borderColor: 'rgba(255, 99, 132, 1)',
                        backgroundColor: 'rgba(255, 99, 132, 0.1)',
                        yAxisID: 'y1'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    scales: {
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Response Time (ms)'
                            }
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Throughput (req/s)'
                            },
                            grid: {
                                drawOnChartArea: false,
                            },
                        }
                    }
                }
            });
        }

        function updateHealthHistoryChart(healthHistory) {
            const ctx = document.getElementById('health-history-chart').getContext('2d');

            if (healthHistoryChart) {
                healthHistoryChart.destroy();
            }

            healthHistoryChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: healthHistory.data.map(item => new Date(item.date).toLocaleDateString()),
                    datasets: [{
                        label: 'Health Score',
                        data: healthHistory.data.map(item => item.score),
                        borderColor: 'rgba(40, 167, 69, 1)',
                        backgroundColor: 'rgba(40, 167, 69, 0.1)',
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 100,
                            title: {
                                display: true,
                                text: 'Health Score'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        }
                    }
                }
            });
        }

        function updateBenchmarks(benchmarks) {
            const container = document.getElementById('benchmarks-container');
            container.innerHTML = '';

            Object.entries(benchmarks).forEach(([name, data]) => {
                const statusClass = data.status === 'improvement' ? 'success' :
                                  data.status === 'regression' ? 'danger' : 'secondary';
                const statusIcon = data.status === 'improvement' ? '=�' :
                                 data.status === 'regression' ? '=�' : '�';

                const benchmarkElement = document.createElement('div');
                benchmarkElement.className = 'row mb-2';
                benchmarkElement.innerHTML = `
                    <div class="col-md-3">
                        <strong>${name.replace(/_/g, ' ')}</strong>
                    </div>
                    <div class="col-md-3">
                        Current: <code>${typeof data.current === 'number' ? data.current.toFixed(3) : data.current}</code>
                    </div>
                    <div class="col-md-3">
                        Baseline: <code>${typeof data.baseline === 'number' ? data.baseline.toFixed(3) : data.baseline}</code>
                    </div>
                    <div class="col-md-3">
                        <span class="badge bg-${statusClass}">${statusIcon} ${data.status}</span>
                    </div>
                `;
                container.appendChild(benchmarkElement);
            });
        }

        // Initial data load
        fetchData();

        // Refresh data every 30 seconds
        setInterval(fetchData, 30000);
    </script>
</body>
</html>"""


class MaintenanceDashboard:
    """
    Simple web-based maintenance dashboard that provides visualization
    of project health, maintenance status, and performance metrics.
    """

    def __init__(self, config_path: str = "maintenance.yml", port: int = 8080) -> None:
        """
        Initialize the maintenance dashboard.

        Args:
            config_path: Path to the maintenance configuration file
            port: Port number for the web server
        """
        self._logger: LoggerProtocol = get_logger(__name__)
        self.port = port
        self.orchestrator = MaintenanceOrchestrator(config_path=config_path)
        self.server: Optional[HTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None

        self._logger.info(f"MaintenanceDashboard initialized on port {port}")

    def start(self, host: str = "localhost", blocking: bool = True) -> None:
        """
        Start the dashboard web server.

        Args:
            host: Host interface to bind to
            blocking: Whether to run in blocking mode
        """
        try:
            # Create a custom HTTPServer class that carries the orchestrator
            class DashboardServer(HTTPServer):
                def __init__(self, server_address: Any, handler_class: Any, orchestrator: MaintenanceOrchestrator):
                    super().__init__(server_address, handler_class)
                    self.orchestrator = orchestrator

            self.server = DashboardServer((host, self.port), MaintenanceDashboardHandler, self.orchestrator)

            self._logger.info(f"Starting Maintenance Dashboard at http://{host}:{self.port}")
            print(f"🚀 Maintenance Dashboard running at: http://{host}:{self.port}")
            print("📊 Dashboard features:")
            print("   • Real-time health monitoring")
            print("   • Component score visualization")
            print("   • Maintenance task tracking")
            print("   • Performance trend analysis")
            print("   • Historical health data")
            print("\n💡 Tip: The dashboard auto-refreshes every 30 seconds")
            print("🛑 Press Ctrl+C to stop the server")

            if blocking:
                self.server.serve_forever()
            else:
                self.server_thread = threading.Thread(target=self.server.serve_forever)
                self.server_thread.daemon = True
                self.server_thread.start()

        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            self._logger.error(f"Error starting dashboard server: {e}")
            raise

    def stop(self) -> None:
        """Stop the dashboard web server."""
        if self.server:
            self._logger.info("Stopping Maintenance Dashboard")
            print("\n🛑 Stopping Maintenance Dashboard...")
            self.server.shutdown()
            self.server.server_close()
            self.server = None

        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5.0)
            self.server_thread = None

    def get_url(self, host: str = "localhost") -> str:
        """Get the dashboard URL."""
        return f"http://{host}:{self.port}"


def main() -> None:
    """Main entry point for running the dashboard standalone."""
    import argparse

    parser = argparse.ArgumentParser(description="Aider MCP Server Maintenance Dashboard")
    parser.add_argument("--config", default="maintenance.yml", help="Path to maintenance configuration file")
    parser.add_argument("--port", type=int, default=8080, help="Port number for the web server")
    parser.add_argument("--host", default="localhost", help="Host interface to bind to")
    args = parser.parse_args()

    dashboard = MaintenanceDashboard(config_path=args.config, port=args.port)
    try:
        dashboard.start(host=args.host, blocking=True)
    except KeyboardInterrupt:
        dashboard.stop()


if __name__ == "__main__":
    main()
