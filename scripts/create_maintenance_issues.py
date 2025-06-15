#!/usr/bin/env python3
"""
Maintenance Issue Creator for Systematic Maintenance Framework.

This script creates GitHub issues based on health assessment results,
with intelligent issue management to avoid duplicates and provide actionable tasks.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
import yaml


class MaintenanceIssueCreator:
    """Creates and manages maintenance issues based on health assessment results."""

    def __init__(self, github_token: Optional[str] = None, config_path: str = "maintenance.yml"):
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.config_path = config_path
        self.config = self.load_config()
        self.repo_info = self.get_repo_info()

        if not self.github_token:
            raise ValueError("GitHub token is required. Set GITHUB_TOKEN environment variable.")

    def load_config(self) -> Dict[str, Any]:
        """Load maintenance configuration."""
        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            print(f"⚠️ Configuration file {self.config_path} not found, using defaults")
            return self._get_default_config()
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            "maintenance_automation": {
                "auto_create_issues": True,
                "auto_assign_reviewers": False,
                "issue_labels": ["maintenance", "automated", "health-alert"],
                "max_open_issues": 3,
                "consolidate_similar": True,
            },
            "github": {"default_assignees": [], "team_mentions": []},
        }

    def get_repo_info(self) -> Dict[str, str]:
        """Get repository information from environment or Git."""
        # Try to get from GitHub Actions environment
        repo = os.environ.get("GITHUB_REPOSITORY")
        if repo:
            owner, name = repo.split("/")
            return {"owner": owner, "repo": name}

        # Try to parse from git remote
        try:
            import subprocess

            result = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True)  # noqa: S603,S607
            remote_url = result.stdout.strip()

            # Parse GitHub URL
            if "github.com" in remote_url:
                if remote_url.startswith("git@"):
                    # SSH format: git@github.com:owner/repo.git
                    path = remote_url.split(":")[-1].replace(".git", "")
                else:
                    # HTTPS format: https://github.com/owner/repo.git
                    path = remote_url.split("github.com/")[-1].replace(".git", "")

                owner, repo = path.split("/")
                return {"owner": owner, "repo": repo}
        except Exception:  # noqa: S110
            pass

        raise ValueError("Could not determine repository information. Set GITHUB_REPOSITORY environment variable.")

    def create_maintenance_issues(self, report_path: str) -> List[Dict[str, Any]]:
        """Create maintenance issues based on health assessment report."""
        try:
            with open(report_path, "r") as f:
                health_data = json.load(f)
            print(f"✅ Loaded health report from {report_path}")
        except Exception as e:
            print(f"❌ Error loading health report: {e}")
            return []

        # Check if issue creation is enabled
        if not self.config.get("maintenance_automation", {}).get("auto_create_issues", True):
            print("⚠️ Automatic issue creation is disabled in configuration")
            return []

        # Analyze health data and determine what issues to create
        issues_to_create = self._analyze_health_for_issues(health_data)

        # Check for existing issues to avoid duplicates
        existing_issues = self._get_existing_maintenance_issues()
        filtered_issues = self._filter_duplicate_issues(issues_to_create, existing_issues)

        # Create the issues
        created_issues = []
        for issue_data in filtered_issues:
            try:
                created_issue = self._create_github_issue(issue_data)
                created_issues.append(created_issue)
                print(f"✅ Created issue: {created_issue['title']}")
            except Exception as e:
                print(f"❌ Error creating issue '{issue_data['title']}': {e}")

        return created_issues

    def _analyze_health_for_issues(self, health_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze health data and determine what maintenance issues to create."""
        issues = []

        composite_score = health_data.get("composite_score", 0)
        if composite_score <= 1.0:
            composite_score *= 100

        # Main maintenance issue if overall score is low
        if composite_score < 80:
            urgency = "critical" if composite_score < 50 else "high" if composite_score < 70 else "medium"

            main_issue = {
                "title": f"🔧 {urgency.upper()} Maintenance Required - Health Score: {composite_score:.0f}/100",
                "body": self._generate_main_issue_body(health_data, composite_score, urgency),
                "labels": ["maintenance", "automated", "health-alert", f"{urgency}-priority", "systematic-maintenance"],
                "priority": urgency,
                "type": "main_maintenance",
            }
            issues.append(main_issue)

        return issues

    def _generate_main_issue_body(self, health_data: Dict[str, Any], score: float, urgency: str) -> str:
        """Generate body for main maintenance issue."""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        recommendations = health_data.get("recommendations", [])
        component_scores = health_data.get("component_scores", {})

        # Convert scores to percentages
        normalized_scores = {}
        for component, component_score in component_scores.items():
            if component_score <= 1.0:
                component_score *= 100
            normalized_scores[component] = component_score

        body = f"""## 🚨 Systematic Maintenance Alert

**Health Score:** {score:.0f}/100
**Urgency Level:** {urgency}
**Assessment Date:** {timestamp}
**Framework:** Systematic Maintenance Phase 1

### 📊 Component Breakdown

"""

        for component, component_score in normalized_scores.items():
            status_emoji = "🔴" if component_score < 50 else "🟡" if component_score < 70 else "🟢"
            component_name = component.replace("_", " ").title()
            body += f"- **{component_name}:** {status_emoji} {component_score:.0f}/100\n"

        body += """
### 🎯 Priority Actions

Based on the health assessment, the following areas need immediate attention:

"""

        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                body += f"{i}. {rec}\n"
        else:
            body += """1. **Security Review** - Check for vulnerabilities and apply patches
2. **Dependency Updates** - Review and update outdated packages
3. **Code Quality** - Address linting violations and complexity issues
4. **Performance** - Review performance metrics and optimize if needed
"""

        body += f"""
### 📋 Maintenance Checklist

- [ ] **Download and review** detailed health reports from workflow artifacts
- [ ] **Security Scan** - Review and fix security vulnerabilities
- [ ] **Dependency Audit** - Update outdated packages and dependencies
- [ ] **Code Quality** - Address linting issues and reduce complexity
- [ ] **Performance Review** - Check for performance regressions
- [ ] **Test Coverage** - Ensure adequate test coverage
- [ ] **Documentation** - Update docs if needed
- [ ] **Re-run Health Check** - Verify improvements

### 🔗 Resources

- **Workflow Run:** {os.environ.get("GITHUB_SERVER_URL", "https://github.com")}/{self.repo_info["owner"]}/{self.repo_info["repo"]}/actions/runs/{os.environ.get("GITHUB_RUN_ID", "N/A")}
- **Configuration:** See `maintenance.yml` for thresholds and automation settings
- **Health Reports:** Check workflow artifacts for detailed analysis

---

**Auto-generated by:** Systematic Maintenance Framework
**Framework Version:** Phase 1 Implementation
**Auto-generated on:** {timestamp}
"""

        return body

    def _get_existing_maintenance_issues(self) -> List[Dict[str, Any]]:
        """Get existing maintenance issues to avoid duplicates."""
        url = f"https://api.github.com/repos/{self.repo_info['owner']}/{self.repo_info['repo']}/issues"
        headers = {"Authorization": f"token {self.github_token}", "Accept": "application/vnd.github.v3+json"}

        params = {"labels": "maintenance,automated", "state": "open", "per_page": 50}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)  # noqa: S113
            response.raise_for_status()
            issues = response.json()
            print(f"📋 Found {len(issues)} existing maintenance issues")
            return issues
        except Exception as e:
            print(f"⚠️ Could not fetch existing issues: {e}")
            return []

    def _filter_duplicate_issues(
        self, new_issues: List[Dict[str, Any]], existing_issues: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter out duplicate issues."""
        filtered = []

        max_issues = self.config.get("maintenance_automation", {}).get("max_open_issues", 3)

        if len(existing_issues) >= max_issues:
            print(f"⚠️ Maximum open maintenance issues ({max_issues}) reached. Skipping new issue creation.")
            return []

        for new_issue in new_issues:
            is_duplicate = False

            for existing in existing_issues:
                # Check for similar titles or types
                if new_issue["type"] in existing["title"].lower() or any(
                    word in existing["title"].lower() for word in new_issue["title"].lower().split()[:3]
                ):
                    print(f"⏭️ Skipping duplicate issue: {new_issue['title']}")
                    is_duplicate = True
                    break

            if not is_duplicate:
                filtered.append(new_issue)

        return filtered

    def _create_github_issue(self, issue_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a GitHub issue."""
        url = f"https://api.github.com/repos/{self.repo_info['owner']}/{self.repo_info['repo']}/issues"
        headers = {"Authorization": f"token {self.github_token}", "Accept": "application/vnd.github.v3+json"}

        # Add assignees if configured
        assignees = self.config.get("github", {}).get("default_assignees", [])

        payload = {"title": issue_data["title"], "body": issue_data["body"], "labels": issue_data["labels"]}

        if assignees:
            payload["assignees"] = assignees

        response = requests.post(url, headers=headers, json=payload, timeout=10)  # noqa: S113
        response.raise_for_status()

        created_issue = response.json()
        return {
            "number": created_issue["number"],
            "title": created_issue["title"],
            "url": created_issue["html_url"],
            "priority": issue_data["priority"],
            "type": issue_data["type"],
        }


def main():
    """Main entry point for issue creation."""
    parser = argparse.ArgumentParser(description="Create maintenance issues based on health assessment results")
    parser.add_argument("--report", required=True, help="Path to health assessment report JSON file")
    parser.add_argument("--config", default="maintenance.yml", help="Path to maintenance configuration file")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what issues would be created without actually creating them"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    if args.verbose:
        print("🎫 Starting Maintenance Issue Creator")
        print(f"Report: {args.report}")
        print(f"Config: {args.config}")
        print(f"Dry Run: {args.dry_run}")

    try:
        # Initialize creator
        creator = MaintenanceIssueCreator(config_path=args.config)

        if args.dry_run:
            print("🔍 DRY RUN MODE - No issues will be created")
            print("✅ Dry run completed")
            return

        # Create issues
        created_issues = creator.create_maintenance_issues(args.report)

        # Summary
        if created_issues:
            print(f"\n✅ Successfully created {len(created_issues)} maintenance issues:")
            for issue in created_issues:
                print(f"   #{issue['number']}: {issue['title']}")
                print(f"   URL: {issue['url']}")
                print(f"   Priority: {issue['priority']}")
                print()
        else:
            print("\n✅ No new maintenance issues needed or issue creation disabled")

    except Exception as e:
        print(f"❌ Issue creation failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
