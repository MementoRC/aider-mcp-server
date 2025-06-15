#!/usr/bin/env python3
"""
Security scan result processor for automated vulnerability management.

This script processes security scan results from pip-audit, safety, and bandit,
then creates GitHub issues for vulnerabilities that exceed configured thresholds.
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class SecurityIssue:
    """Represents a security vulnerability or issue."""

    source: str  # "pip-audit", "safety", "bandit"
    severity: str  # "critical", "high", "medium", "low"
    title: str
    description: str
    package: Optional[str] = None
    vulnerability_id: Optional[str] = None
    remediation: Optional[str] = None


class SecurityScanProcessor:
    """Processes security scan results and manages GitHub issue creation."""

    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.github_repo = os.getenv("GITHUB_REPOSITORY")
        self.reports_dir = Path("reports")

        # Severity thresholds for issue creation
        self.severity_thresholds = {
            "critical": 0,  # Always create issues for critical
            "high": int(os.getenv("HIGH_SEVERITY_THRESHOLD", "0")),
            "medium": int(os.getenv("MEDIUM_SEVERITY_THRESHOLD", "5")),
            "low": int(os.getenv("LOW_SEVERITY_THRESHOLD", "10")),
        }

        # Initialize HTTP session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if self.github_token:
            self.session.headers.update(
                {"Authorization": f"token {self.github_token}", "Accept": "application/vnd.github.v3+json"}
            )

    def load_json_report(self, filename: str) -> Dict[str, Any]:
        """Load and parse a JSON report file safely."""
        file_path = self.reports_dir / filename

        if not file_path.exists():
            print(f"Warning: Report file {file_path} does not exist")
            return {}

        try:
            with open(file_path, "r") as f:
                content = f.read().strip()
                if not content:
                    print(f"Warning: Report file {file_path} is empty")
                    return {}
                return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from {file_path}: {e}")
            return {}
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return {}

    def parse_pip_audit_results(self) -> List[SecurityIssue]:
        """Parse pip-audit vulnerability report."""
        data = self.load_json_report("pip-audit.json")
        issues = []

        vulnerabilities = data.get("vulnerabilities", [])
        for vuln in vulnerabilities:
            package = vuln.get("package", "unknown")
            vuln_id = vuln.get("id", "unknown")
            description = vuln.get("description", "No description available")

            # Map pip-audit severity to our severity levels
            severity = "medium"  # Default for pip-audit findings
            if any(keyword in description.lower() for keyword in ["critical", "severe"]):
                severity = "high"

            issue = SecurityIssue(
                source="pip-audit",
                severity=severity,
                title=f"Dependency Vulnerability: {package} ({vuln_id})",
                description=f"**Package:** {package}\n**Vulnerability ID:** {vuln_id}\n\n{description}",
                package=package,
                vulnerability_id=vuln_id,
                remediation=f"Update {package} to a version that fixes {vuln_id}",
            )
            issues.append(issue)

        return issues

    def parse_safety_results(self) -> List[SecurityIssue]:
        """Parse safety vulnerability report."""
        data = self.load_json_report("safety-scan.json")
        issues = []

        # Safety can return different formats, handle both list and dict
        vulnerabilities = data if isinstance(data, list) else data.get("vulnerabilities", [])

        for vuln in vulnerabilities:
            package = vuln.get("package_name", vuln.get("package", "unknown"))
            vuln_id = vuln.get("vulnerability_id", vuln.get("id", "unknown"))
            description = vuln.get("advisory", vuln.get("description", "No description available"))

            issue = SecurityIssue(
                source="safety",
                severity="high",  # Safety findings are generally high severity
                title=f"Security Advisory: {package} ({vuln_id})",
                description=f"**Package:** {package}\n**Advisory ID:** {vuln_id}\n\n{description}",
                package=package,
                vulnerability_id=vuln_id,
                remediation=f"Update {package} to address security advisory {vuln_id}",
            )
            issues.append(issue)

        return issues

    def parse_bandit_results(self) -> List[SecurityIssue]:
        """Parse bandit security linting report."""
        data = self.load_json_report("bandit-scan.json")
        issues = []

        results = data.get("results", [])
        for result in results:
            filename = result.get("filename", "unknown")
            test_name = result.get("test_name", "unknown")
            severity = result.get("issue_severity", "MEDIUM").lower()
            confidence = result.get("issue_confidence", "MEDIUM")
            issue_text = result.get("issue_text", "No description available")
            line_number = result.get("line_number", "unknown")

            # Only create issues for high/critical bandit findings
            if severity not in ["high", "critical"]:
                continue

            issue = SecurityIssue(
                source="bandit",
                severity=severity,
                title=f"Security Issue: {test_name} in {filename}",
                description=f"**File:** {filename}:{line_number}\n**Test:** {test_name}\n**Confidence:** {confidence}\n\n{issue_text}",
                remediation=f"Review and fix the security issue identified by bandit test {test_name}",
            )
            issues.append(issue)

        return issues

    def get_existing_security_issues(self) -> List[Dict[str, Any]]:
        """Fetch existing security-related GitHub issues to avoid duplicates."""
        if not self.github_token or not self.github_repo:
            print("GitHub token or repository not configured, skipping duplicate check")
            return []

        try:
            url = f"https://api.github.com/repos/{self.github_repo}/issues"
            params = {"labels": "security,vulnerability", "state": "open", "per_page": 100}

            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            print(f"Error fetching existing issues: {e}")
            return []

    def is_duplicate_issue(self, issue: SecurityIssue, existing_issues: List[Dict[str, Any]]) -> bool:
        """Check if a security issue already has an open GitHub issue."""
        for existing in existing_issues:
            title = existing.get("title", "")
            body = existing.get("body", "")

            # Check for duplicate based on title similarity and package/vulnerability ID
            if issue.package and issue.package in title:
                if issue.vulnerability_id and issue.vulnerability_id in (title + body):
                    return True

            # Check for bandit issues by test name and file
            if issue.source == "bandit" and any(keyword in title for keyword in issue.title.split()):
                return True

        return False

    def create_github_issue(self, issue: SecurityIssue) -> bool:
        """Create a GitHub issue for a security vulnerability."""
        if not self.github_token or not self.github_repo:
            print(f"Would create issue: {issue.title} (GitHub not configured)")
            return False

        try:
            url = f"https://api.github.com/repos/{self.github_repo}/issues"

            # Prepare issue data
            labels = ["security", "vulnerability", issue.severity, f"source:{issue.source}"]
            if issue.package:
                labels.append(f"package:{issue.package}")

            body = f"{issue.description}\n\n"
            if issue.remediation:
                body += f"## Remediation\n{issue.remediation}\n\n"

            body += f"**Source:** {issue.source}\n"
            body += f"**Severity:** {issue.severity}\n"
            body += "**Auto-generated:** This issue was automatically created by security scanning\n"

            issue_data = {"title": issue.title, "body": body, "labels": labels}

            response = self.session.post(url, json=issue_data)
            response.raise_for_status()

            issue_url = response.json().get("html_url", "unknown")
            print(f"Created security issue: {issue_url}")
            return True

        except Exception as e:
            print(f"Error creating GitHub issue for {issue.title}: {e}")
            return False

    def should_create_issue(self, issue: SecurityIssue, issues_by_severity: Dict[str, int]) -> bool:
        """Determine if an issue should be created based on severity thresholds."""
        current_count = issues_by_severity.get(issue.severity, 0)
        threshold = self.severity_thresholds.get(issue.severity, 0)

        return current_count < threshold

    def process_all_reports(self) -> None:
        """Main processing function that handles all security reports."""
        print("Processing security scan results...")

        # Parse all reports
        all_issues = []
        all_issues.extend(self.parse_pip_audit_results())
        all_issues.extend(self.parse_safety_results())
        all_issues.extend(self.parse_bandit_results())

        if not all_issues:
            print("No security issues found in reports")
            return

        print(f"Found {len(all_issues)} total security issues")

        # Count issues by severity
        issues_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for issue in all_issues:
            issues_by_severity[issue.severity] = issues_by_severity.get(issue.severity, 0) + 1

        print("Issues by severity:")
        for severity, count in issues_by_severity.items():
            print(f"  {severity}: {count}")

        # Get existing issues to avoid duplicates
        existing_issues = self.get_existing_security_issues()
        print(f"Found {len(existing_issues)} existing security issues")

        # Create GitHub issues for new vulnerabilities
        created_count = 0
        skipped_count = 0

        for issue in all_issues:
            if self.is_duplicate_issue(issue, existing_issues):
                print(f"Skipping duplicate issue: {issue.title}")
                skipped_count += 1
                continue

            if self.should_create_issue(issue, issues_by_severity):
                if self.create_github_issue(issue):
                    created_count += 1
            else:
                print(f"Skipping issue due to threshold: {issue.title}")
                skipped_count += 1

        print(f"Created {created_count} new security issues")
        print(f"Skipped {skipped_count} issues (duplicates or threshold limits)")

        # Exit with non-zero status if critical/high issues found
        critical_high_count = issues_by_severity["critical"] + issues_by_severity["high"]
        if critical_high_count > 0:
            print(f"WARNING: {critical_high_count} critical/high severity issues found")
            # Don't exit with error code here - let the workflow handle this


def main():
    """Main entry point."""
    processor = SecurityScanProcessor()

    try:
        processor.process_all_reports()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error processing security reports: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
