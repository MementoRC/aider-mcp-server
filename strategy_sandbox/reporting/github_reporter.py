"""GitHub Reporter for sandbox experiments."""


class GitHubReporter:
    """Minimal GitHubReporter class for testing purposes."""

    def __init__(self, token=None, repo=None):
        """Initialize GitHubReporter."""
        self.token = token
        self.repo = repo

    def create_issue(self, title, body):
        """Create GitHub issue (mock implementation)."""
        return {"title": title, "body": body, "number": 1}

    def update_pr(self, pr_number, body):
        """Update PR description (mock implementation)."""
        return {"pr_number": pr_number, "body": body}

    def publish_report(self, report_html):
        """Publish report to GitHub (mock implementation)."""
        return {"report": "published", "content_length": len(report_html)}