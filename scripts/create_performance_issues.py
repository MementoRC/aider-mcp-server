#!/usr/bin/env python3
"""
Performance Regression Issue Creator for Systematic Maintenance Framework.

This script creates GitHub issues based on detected performance regressions,
with intelligent issue management to avoid duplicates and provide actionable tasks.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml

# Add src to path for importing existing monitoring systems
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from aider_mcp_server.molecules.monitoring.performance_benchmarking import (
        BenchmarkType,
        RegressionSeverity,
    )
except ImportError as e:
    print(f"Error: Could not import performance benchmarking enums: {e}", file=sys.stderr)
    print("Please ensure 'src' is in your Python path and dependencies are installed.", file=sys.stderr)
    sys.exit(1)


class PerformanceIssueCreator:
    """Creates and manages GitHub issues for performance regressions."""

    def __init__(self, github_token: Optional[str] = None, config_path: Path = Path("maintenance.yml")):
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.config_path = config_path
        self.config = self.load_config()
        self.repo_info = self.get_repo_info()

        if not self.github_token:
            raise ValueError("GitHub token is required. Set GITHUB_TOKEN environment variable.")

    def load_config(self) -> Dict[str, Any]:
        """Load maintenance configuration."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            print(f"⚠️ Configuration file {self.config_path} not found. Using defaults.")
            return self.get_default_config()
        except Exception as e:
            print(f"⚠️ Error loading config {self.config_path}: {e}. Using defaults.")
            return self.get_default_config()

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for performance issue creation."""
        return {
            "automation": {
                "issue_labels": ["maintenance", "automated", "health-alert"],
                "max_open_issues": 3,
                "consolidate_similar": True,
            },
            "github": {"default_assignees": [], "team_mentions": []},
            "performance_monitoring": {
                "issue_labels": ["performance", "regression", "automated"],
                "max_open_regression_issues": 5,
            },
        }

    def get_repo_info(self) -> Dict[str, str]:
        """Get repository information from environment or Git."""
        # Try to get from GitHub Actions environment
        repo = os.environ.get("GITHUB_REPOSITORY")
        if repo:
            owner, name = repo.split("/")
            return {"owner": owner, "name": name}

        # Fallback: try to parse from git remote
        try:
            import subprocess

            result = subprocess.run(  # noqa: S603
                ["git", "remote", "get-url", "origin"],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
            )
            remote_url = result.stdout.strip()
            if "github.com" in remote_url:
                # Parse GitHub URL (handles both SSH and HTTPS)
                if remote_url.startswith("git@"):
                    # SSH format: git@github.com:owner/repo.git
                    repo_part = remote_url.split(":")[-1]
                else:
                    # HTTPS format: https://github.com/owner/repo.git
                    repo_part = "/".join(remote_url.split("/")[-2:])

                repo_part = repo_part.replace(".git", "")
                owner, name = repo_part.split("/")
                return {"owner": owner, "name": name}
        except Exception:  # noqa: S110
            pass  # Fallback to default repo info if git parsing fails

        # Ultimate fallback
        return {"owner": "unknown", "name": "unknown"}

    def create_performance_issues(self, report_data: Dict[str, Any], dry_run: bool = False) -> List[Dict[str, Any]]:
        """Create GitHub issues for performance regressions."""
        regression_reports = report_data.get("regression_reports", [])

        if not regression_reports:
            print("✅ No performance regressions detected. No issues to create.")
            return []

        print(f"📊 Processing {len(regression_reports)} performance regression reports...")

        # Generate issue data
        issues_to_create = self.generate_issue_data(regression_reports)

        if not issues_to_create:
            print("ℹ️ No new performance issues to create after duplicate filtering.")
            return []

        if dry_run:
            print("🧪 DRY RUN - Issues that would be created:")
            for issue in issues_to_create:
                print(f"  • {issue['title']}")
                print(f"    Labels: {', '.join(issue['labels'])}")
                print(f"    Priority: {issue['priority']}")
            return issues_to_create

        # Create issues via GitHub API
        created_issues = []
        for issue_data in issues_to_create:
            try:
                created_issue = self.create_github_issue(issue_data)
                created_issues.append(created_issue)
                print(f"✅ Created issue: {issue_data['title']}")
            except Exception as e:
                print(f"❌ Failed to create issue '{issue_data['title']}': {e}")

        return created_issues

    def generate_issue_data(self, regression_reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate issue data for regression reports."""
        issues = []

        for reg in regression_reports:
            # Convert string enums back to enum objects for proper handling
            try:
                severity_enum = RegressionSeverity(reg["severity"])
                benchmark_type_enum = BenchmarkType(reg["benchmark_type"])
            except ValueError as e:
                print(f"⚠️ Unknown enum value in regression report: {e}")
                continue

            title = (
                f"⚡ Performance Regression: {reg['operation_name']} "
                f"({severity_enum.value.upper()} - {reg['regression_percent']:.1%})"
            )
            body = self._generate_issue_body(reg, severity_enum, benchmark_type_enum)
            labels = self.config.get("performance_monitoring", {}).get("issue_labels", [])
            labels.append(f"{severity_enum.value}-priority")
            labels.append("systematic-maintenance")  # Add common label

            issues.append(
                {
                    "title": title,
                    "body": body,
                    "labels": labels,
                    "priority": severity_enum.value,
                    "type": "performance_regression",
                    "operation_name": reg["operation_name"],  # For duplicate checking
                    "benchmark_type": reg["benchmark_type"],  # For duplicate checking
                }
            )
        return issues

    def _generate_issue_body(
        self, regression: Dict[str, Any], severity: RegressionSeverity, benchmark_type: BenchmarkType
    ) -> str:
        """Generate body for a performance regression issue."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        recommendations = regression.get("recommendations", [])

        body = f"""## 🚨 Performance Regression Detected

**Operation:** `{regression["operation_name"]}`
**Benchmark Type:** `{benchmark_type.value.replace("_", " ").title()}`
**Severity:** {severity.value.upper()}
**Regression:** {regression["regression_percent"]:.1%} slower than baseline

### 📊 Performance Details

- **Baseline Mean Time:** {regression["baseline_time"]:.4f}s
- **Current Mean Time:** {regression["current_time"]:.4f}s
- **Baseline Throughput:** {regression["details"].get("baseline_throughput", "N/A"):.2f} ops/s
- **Current Throughput:** {regression["details"].get("current_throughput", "N/A"):.2f} ops/s
- **Baseline P95:** {regression["details"].get("baseline_p95", "N/A"):.4f}s
- **Current P95:** {regression["details"].get("current_p95", "N/A"):.4f}s
- **Iterations:** {regression["details"].get("iterations", "N/A")}

### 🎯 Recommendations

"""
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                body += f"{i}. {rec}\n"
        else:
            body += "- Run detailed profiling to identify bottlenecks\n"
            body += "- Compare with previous performance baselines\n"
            body += "- Review recent code changes that might affect performance\n"

        body += f"""
### 🔗 Detection Details

**Detected At:** {timestamp}
**Threshold:** {regression.get("threshold_percent", 0.05):.1%}
**Detection System:** Performance Benchmarking Framework

### 🚀 Next Steps

1. **Investigate** the performance regression using profiling tools
2. **Identify** the root cause of the performance degradation
3. **Implement** fixes to restore baseline performance
4. **Verify** the fix with new benchmark runs
5. **Update** this issue with resolution details

---

**Auto-generated by:** Systematic Maintenance Framework
**Monitoring Integration:** PerformanceBenchmarking, MetricsCollector
**Framework Phase:** Performance Monitoring Implementation
"""
        return body

    def filter_duplicate_issues(self, new_issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out issues that might be duplicates of existing ones."""
        try:
            existing_issues = self.get_existing_performance_issues()
        except Exception as e:
            print(f"⚠️ Could not fetch existing issues: {e}. Proceeding without duplicate check.")
            return new_issues

        filtered = []
        for new_issue in new_issues:
            is_duplicate = False
            for existing in existing_issues:
                # Check for exact match on operation name and benchmark type in title/body
                # Or a very similar title
                if (
                    new_issue["operation_name"] in existing["title"]
                    and new_issue["benchmark_type"] in existing["title"]
                ) or (
                    new_issue["operation_name"] in existing["body"] and new_issue["benchmark_type"] in existing["body"]
                ):
                    print(f"⏭️ Skipping duplicate performance issue: {new_issue['title']}")
                    is_duplicate = True
                    break

            if not is_duplicate:
                filtered.append(new_issue)

        return filtered

    def get_existing_performance_issues(self) -> List[Dict[str, Any]]:
        """Get existing performance regression issues."""
        url = f"https://api.github.com/repos/{self.repo_info['owner']}/{self.repo_info['name']}/issues"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        params = {
            "labels": "performance,regression",
            "state": "open",
            "per_page": 50,
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        issues = response.json()
        return [{"title": issue["title"], "body": issue["body"], "number": issue["number"]} for issue in issues]

    def create_github_issue(self, issue_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a GitHub issue via API."""
        url = f"https://api.github.com/repos/{self.repo_info['owner']}/{self.repo_info['name']}/issues"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        payload = {
            "title": issue_data["title"],
            "body": issue_data["body"],
            "labels": issue_data["labels"],
        }

        # Add assignees if configured
        assignees = self.config.get("github", {}).get("default_assignees", [])
        if assignees:
            payload["assignees"] = assignees

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        return response.json()


def main():
    """Main function for performance issue creation."""
    parser = argparse.ArgumentParser(description="Create GitHub issues for performance regressions")
    parser.add_argument("--report", required=True, help="Path to performance results JSON file")
    parser.add_argument("--config", default="maintenance.yml", help="Path to maintenance configuration file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what issues would be created without actually creating them",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    print("🎫 Starting Performance Issue Creator")
    print(f"Report: {args.report}")
    print(f"Config: {args.config}")
    print(f"Dry Run: {args.dry_run}")

    try:
        # Load performance results
        report_path = Path(args.report)
        if not report_path.exists():
            print(f"❌ Performance report file not found: {args.report}")
            sys.exit(1)

        with open(report_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)

        # Create issue creator
        creator = PerformanceIssueCreator(config_path=Path(args.config))

        # Create performance issues
        created_issues = creator.create_performance_issues(report_data, dry_run=args.dry_run)

        if created_issues:
            print(f"✅ Successfully processed {len(created_issues)} performance issues.")
        else:
            print("ℹ️ No performance issues created.")

    except Exception as e:
        print(f"❌ Performance issue creation failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
