"""
GitDiffAnalyzer for Aider Safety Operations.

Provides comprehensive analysis of git diffs to detect suspicious change patterns,
validate file modifications, and prepare rollback commands for safety operations.

Features:
- Detection of suspicious patterns (mass deletions, complete replacements)
- Large change detection with configurable thresholds
- File addition/deletion validation
- Rollback command generation for recovery scenarios
- Integration with GitCheckpointManager for safety operations
- Comprehensive logging and error handling

Author: Aider MCP Server Team
"""

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)


class GitDiffAnalysisError(Exception):
    """Base exception for git diff analysis operations."""

    pass


class InvalidGitReferenceError(GitDiffAnalysisError):
    """Raised when a git reference (commit, branch, tag) is invalid."""

    pass


class DiffAnalysisFailedError(GitDiffAnalysisError):
    """Raised when diff analysis fails due to git command errors."""

    def __init__(self, message: str, output: Optional[str] = None):
        super().__init__(message)
        self.output = output


@dataclass
class FileChangeStats:
    """Statistics for changes in a single file."""

    filename: str
    additions: int
    deletions: int
    is_binary: bool = False
    is_new_file: bool = False
    is_deleted_file: bool = False
    is_renamed: bool = False
    old_filename: Optional[str] = None

    @property
    def net_change(self) -> int:
        """Net change in lines (additions - deletions)."""
        return self.additions - self.deletions

    @property
    def total_change(self) -> int:
        """Total change in lines (additions + deletions)."""
        return self.additions + self.deletions

    @property
    def change_ratio(self) -> float:
        """Ratio of additions to total changes (0.0 to 1.0)."""
        if self.total_change == 0:
            return 0.0
        return self.additions / self.total_change


@dataclass
class SuspiciousPattern:
    """Represents a detected suspicious change pattern."""

    pattern_type: str
    filename: str
    severity: str  # "low", "medium", "high", "critical"
    description: str
    details: Dict[str, Any]
    recommended_action: str


@dataclass
class DiffAnalysisResult:
    """Comprehensive result of git diff analysis."""

    from_ref: str
    to_ref: str
    file_changes: List[FileChangeStats]
    suspicious_patterns: List[SuspiciousPattern]
    large_changes: List[str]  # Filenames with large changes
    rollback_commands: List[str]
    selective_rollback_files: List[str]
    total_files_changed: int
    total_additions: int
    total_deletions: int
    has_critical_issues: bool
    analysis_summary: str


class GitDiffAnalyzer:
    """
    Analyzes git diffs to detect suspicious patterns and prepare rollback commands.

    Usage:
        analyzer = GitDiffAnalyzer(repo_path)
        result = analyzer.analyze_diff("checkpoint-id", "HEAD")
        if result.has_critical_issues:
            # Execute rollback commands
            for cmd in result.rollback_commands:
                print(f"Run: {cmd}")
    """

    def __init__(
        self,
        repo_path: str,
        large_change_threshold: int = 100,
        mass_deletion_threshold: int = 100,
        mass_deletion_ratio: float = 0.5,
        complete_replacement_threshold: int = 10,
        complete_replacement_ratio: float = 0.1,
    ):
        """
        Initialize the analyzer with configurable thresholds.

        Args:
            repo_path: Path to the git repository root.
            large_change_threshold: Threshold for flagging large changes per file.
            mass_deletion_threshold: Minimum deletions to trigger mass deletion check.
            mass_deletion_ratio: Max ratio of additions to deletions for mass deletion detection.
            complete_replacement_threshold: Min changes to check for complete replacement.
            complete_replacement_ratio: Max ratio difference for complete replacement detection.
        """
        self.repo_path = os.path.abspath(repo_path)
        self.large_change_threshold = large_change_threshold
        self.mass_deletion_threshold = mass_deletion_threshold
        self.mass_deletion_ratio = mass_deletion_ratio
        self.complete_replacement_threshold = complete_replacement_threshold
        self.complete_replacement_ratio = complete_replacement_ratio

        if not self._is_git_repo():
            logger.error(f"Not a git repository: {self.repo_path}")
            raise GitDiffAnalysisError(f"Not a git repository: {self.repo_path}")

    def _is_git_repo(self) -> bool:
        """Check if the current directory is a git repository (supports worktrees)."""
        try:
            git_env = {**os.environ, "CLAUDECODE": "0"}
            subprocess.run(  # noqa: S603
                ["git", "rev-parse", "--git-dir"],  # noqa: S607
                cwd=self.repo_path,
                capture_output=True,
                check=True,
                env=git_env,
            )
            logger.debug(f"Checking if {self.repo_path} is a git repo: True")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.debug(f"Checking if {self.repo_path} is a git repo: False")
            return False

    def _run_git(self, args: List[str], capture_output: bool = True) -> str:
        """
        Run a git command in the repository.

        Args:
            args: List of git command arguments.
            capture_output: If True, return stdout.

        Returns:
            Output of the command if capture_output is True, else empty string.

        Raises:
            DiffAnalysisFailedError: If the git command fails.
        """
        cmd = ["git"] + args
        try:
            logger.debug(f"Running git command: {' '.join(cmd)}")
            git_env = {**os.environ, "CLAUDECODE": "0"}
            result = subprocess.run(  # noqa: S603
                cmd,
                cwd=self.repo_path,
                check=True,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                encoding="utf-8",
                env=git_env,
            )
            if capture_output:
                logger.verbose(f"Git output length: {len(result.stdout)} chars")
                return result.stdout
            return ""
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {' '.join(cmd)}\n{e.stderr}")
            raise DiffAnalysisFailedError(f"Git command failed: {' '.join(cmd)}", output=e.stderr) from e
        except Exception as e:
            logger.error(f"Unexpected error running git command: {' '.join(cmd)}\n{e}")
            raise DiffAnalysisFailedError(
                f"Unexpected error running git command: {' '.join(cmd)}", output=str(e)
            ) from e

    def _validate_git_reference(self, ref: str) -> bool:
        """
        Validate that a git reference exists and is valid.

        Args:
            ref: Git reference (commit hash, branch, tag, etc.)

        Returns:
            True if the reference is valid, False otherwise.
        """
        try:
            self._run_git(["rev-parse", "--verify", f"{ref}^{{commit}}"])
            return True
        except DiffAnalysisFailedError:
            return False

    def _parse_diff_stats(self, diff_output: str) -> List[FileChangeStats]:
        """
        Parse git diff --stat output to extract file change statistics.

        Args:
            diff_output: Output from git diff --stat command.

        Returns:
            List of FileChangeStats objects.
        """
        file_changes = []
        lines = diff_output.strip().split("\n")

        for line in lines:
            if not line.strip() or "file changed" in line or "files changed" in line:
                continue

            # Parse patterns like:
            # "src/file.py | 25 ++++++++++++++++++++-----"
            # "path/to/file.txt | Bin 0 -> 1234 bytes"
            # "{old_name => new_name} | 10 +++++-----"
            match = re.match(r"^(.+?)\s*\|\s*(.+)$", line.strip())
            if not match:
                continue

            filename_part = match.group(1).strip()
            changes_part = match.group(2).strip()

            # Handle renames
            is_renamed = False
            old_filename = None
            if " => " in filename_part:
                is_renamed = True
                # Handle patterns like "old_name => new_name" or "{common/old => common/new}"
                if filename_part.startswith("{") and filename_part.endswith("}"):
                    # Pattern: {common/old => common/new}
                    inner = filename_part[1:-1]
                    if " => " in inner:
                        old_part, new_part = inner.split(" => ", 1)
                        # Extract common prefix/suffix if any
                        old_filename = old_part
                        filename = new_part
                    else:
                        filename = filename_part
                else:
                    # Pattern: old_name => new_name
                    old_filename, filename = filename_part.split(" => ", 1)
            else:
                filename = filename_part

            # Parse binary files
            if "Bin" in changes_part:
                file_changes.append(
                    FileChangeStats(
                        filename=filename,
                        additions=0,
                        deletions=0,
                        is_binary=True,
                        is_renamed=is_renamed,
                        old_filename=old_filename,
                    )
                )
                continue

            # Parse additions and deletions from patterns like "25 ++++++++++++++++++++-----"
            additions = 0
            deletions = 0

            # Extract numeric part (e.g., "25" from "25 ++++++++++++++++++++-----")
            number_match = re.match(r"(\d+)", changes_part)
            if number_match:
                total_changes = int(number_match.group(1))
                # Count + and - symbols
                plus_count = changes_part.count("+")
                minus_count = changes_part.count("-")

                if plus_count + minus_count > 0:
                    # Proportionally distribute the total changes
                    additions = int((plus_count / (plus_count + minus_count)) * total_changes)
                    deletions = total_changes - additions

            file_changes.append(
                FileChangeStats(
                    filename=filename,
                    additions=additions,
                    deletions=deletions,
                    is_renamed=is_renamed,
                    old_filename=old_filename,
                )
            )

        return file_changes

    def _detect_suspicious_patterns(
        self, file_changes: List[FileChangeStats], operation_intent: Optional[str] = None
    ) -> List[SuspiciousPattern]:
        """
        Detect suspicious change patterns in the diff.

        Args:
            file_changes: List of file change statistics.
            operation_intent: Optional description of the intended operation.

        Returns:
            List of detected suspicious patterns.
        """
        patterns = []

        for file_change in file_changes:
            # Check for mass deletions
            if (
                file_change.deletions >= self.mass_deletion_threshold
                and file_change.change_ratio < self.mass_deletion_ratio
            ):
                patterns.append(
                    SuspiciousPattern(
                        pattern_type="mass_deletion",
                        filename=file_change.filename,
                        severity="high",
                        description=f"Mass deletion detected: {file_change.deletions} lines deleted, "
                        f"only {file_change.additions} lines added",
                        details={
                            "deletions": file_change.deletions,
                            "additions": file_change.additions,
                            "change_ratio": file_change.change_ratio,
                        },
                        recommended_action="Review changes carefully before proceeding",
                    )
                )

            # Check for complete file replacements
            if (
                file_change.total_change >= self.complete_replacement_threshold
                and abs(file_change.change_ratio - 0.5) <= self.complete_replacement_ratio
            ):
                patterns.append(
                    SuspiciousPattern(
                        pattern_type="complete_replacement",
                        filename=file_change.filename,
                        severity="medium",
                        description=f"File appears to be completely replaced: "
                        f"{file_change.additions} additions, {file_change.deletions} deletions",
                        details={
                            "additions": file_change.additions,
                            "deletions": file_change.deletions,
                            "change_ratio": file_change.change_ratio,
                        },
                        recommended_action="Verify that complete file replacement was intended",
                    )
                )

            # Check for unexpected file operations
            if file_change.is_new_file and operation_intent and "delete" in operation_intent.lower():
                patterns.append(
                    SuspiciousPattern(
                        pattern_type="unexpected_file_creation",
                        filename=file_change.filename,
                        severity="medium",
                        description="New file created during an operation intended for deletion",
                        details={"operation_intent": operation_intent},
                        recommended_action="Verify that file creation was intended",
                    )
                )

            if file_change.is_deleted_file and operation_intent and "add" in operation_intent.lower():
                patterns.append(
                    SuspiciousPattern(
                        pattern_type="unexpected_file_deletion",
                        filename=file_change.filename,
                        severity="high",
                        description="File deleted during an operation intended for addition",
                        details={"operation_intent": operation_intent},
                        recommended_action="Investigate unintended file deletion",
                    )
                )

        return patterns

    def _detect_large_changes(self, file_changes: List[FileChangeStats]) -> List[str]:
        """
        Detect files with large changes that exceed the threshold.

        Args:
            file_changes: List of file change statistics.

        Returns:
            List of filenames with large changes.
        """
        large_changes = []
        for file_change in file_changes:
            if file_change.total_change >= self.large_change_threshold:
                large_changes.append(file_change.filename)
                logger.warning(
                    f"Large change detected in {file_change.filename}: {file_change.total_change} total changes"
                )
        return large_changes

    def _generate_rollback_commands(
        self, from_ref: str, suspicious_files: Set[str], large_change_files: Set[str]
    ) -> Tuple[List[str], List[str]]:
        """
        Generate rollback commands for recovery scenarios.

        Args:
            from_ref: Reference to rollback to (checkpoint commit).
            suspicious_files: Set of files with suspicious patterns.
            large_change_files: Set of files with large changes.

        Returns:
            Tuple of (general_rollback_commands, selective_rollback_files).
        """
        rollback_commands = []
        problematic_files = suspicious_files.union(large_change_files)

        # Full rollback command
        rollback_commands.append(f"git reset --hard {from_ref}")

        # Selective rollback commands for specific files
        if problematic_files:
            rollback_commands.append("# Selective rollback for problematic files:")
            for filename in sorted(problematic_files):
                rollback_commands.append(f"git checkout {from_ref} -- '{filename}'")

        # Stash current changes before rollback
        rollback_commands.insert(0, "git stash push -u -m 'Pre-rollback stash'")

        return rollback_commands, list(problematic_files)

    def analyze_diff(
        self,
        from_ref: str,
        to_ref: str = "HEAD",
        operation_intent: Optional[str] = None,
        target_files: Optional[List[str]] = None,
    ) -> DiffAnalysisResult:
        """
        Analyze differences between two git references.

        Args:
            from_ref: Starting reference (e.g., checkpoint commit hash).
            to_ref: Ending reference (default: HEAD).
            operation_intent: Optional description of the intended operation.
            target_files: Optional list of files that were supposed to be modified.

        Returns:
            Comprehensive analysis result.

        Raises:
            InvalidGitReferenceError: If git references are invalid.
            DiffAnalysisFailedError: If analysis fails.
        """
        logger.info(f"Analyzing git diff from {from_ref} to {to_ref}")

        # Validate git references
        if not self._validate_git_reference(from_ref):
            raise InvalidGitReferenceError(f"Invalid git reference: {from_ref}")
        if not self._validate_git_reference(to_ref):
            raise InvalidGitReferenceError(f"Invalid git reference: {to_ref}")

        # Get diff statistics
        try:
            diff_stat_output = self._run_git(["diff", "--stat", from_ref, to_ref])
            file_changes = self._parse_diff_stats(diff_stat_output)
            logger.info(f"Parsed {len(file_changes)} file changes")
        except DiffAnalysisFailedError as e:
            logger.error(f"Failed to get diff statistics: {e}")
            raise

        # Detect suspicious patterns
        suspicious_patterns = self._detect_suspicious_patterns(file_changes, operation_intent)
        suspicious_files = {pattern.filename for pattern in suspicious_patterns}

        # Detect large changes
        large_change_files = set(self._detect_large_changes(file_changes))

        # Calculate totals
        total_additions = sum(fc.additions for fc in file_changes)
        total_deletions = sum(fc.deletions for fc in file_changes)

        # Generate rollback commands
        rollback_commands, selective_rollback_files = self._generate_rollback_commands(
            from_ref, suspicious_files, large_change_files
        )

        # Determine if there are critical issues
        has_critical_issues = any(pattern.severity in ["high", "critical"] for pattern in suspicious_patterns)

        # Generate analysis summary
        summary_parts = [
            f"Analyzed diff from {from_ref} to {to_ref}",
            f"Files changed: {len(file_changes)}",
            f"Total additions: {total_additions}",
            f"Total deletions: {total_deletions}",
            f"Suspicious patterns: {len(suspicious_patterns)}",
            f"Large changes: {len(large_change_files)}",
        ]
        analysis_summary = "; ".join(summary_parts)

        result = DiffAnalysisResult(
            from_ref=from_ref,
            to_ref=to_ref,
            file_changes=file_changes,
            suspicious_patterns=suspicious_patterns,
            large_changes=list(large_change_files),
            rollback_commands=rollback_commands,
            selective_rollback_files=selective_rollback_files,
            total_files_changed=len(file_changes),
            total_additions=total_additions,
            total_deletions=total_deletions,
            has_critical_issues=has_critical_issues,
            analysis_summary=analysis_summary,
        )

        logger.info(f"Diff analysis complete: {analysis_summary}")
        if has_critical_issues:
            logger.warning("Critical issues detected in diff analysis!")

        return result

    def get_recovery_script(self, analysis_result: DiffAnalysisResult, script_path: str) -> str:
        """
        Generate a recovery script file for easy rollback execution.

        Args:
            analysis_result: Result from analyze_diff.
            script_path: Path where to save the recovery script.

        Returns:
            Path to the generated recovery script.
        """
        script_content = [
            "#!/bin/bash",
            "# Git Diff Analysis Recovery Script",
            f"# Generated for diff from {analysis_result.from_ref} to {analysis_result.to_ref}",
            f"# Analysis summary: {analysis_result.analysis_summary}",
            "",
            "set -e  # Exit on any error",
            "",
        ]

        if analysis_result.has_critical_issues:
            script_content.extend(
                [
                    "echo 'WARNING: Critical issues detected in diff analysis!'",
                    "echo 'Review the following suspicious patterns before proceeding:'",
                    "",
                ]
            )
            for pattern in analysis_result.suspicious_patterns:
                if pattern.severity in ["high", "critical"]:
                    script_content.append(f"echo '  - {pattern.filename}: {pattern.description}'")
            script_content.extend(
                [
                    "",
                    "read -p 'Continue with rollback? (y/N): ' confirm",
                    "if [[ $confirm != [yY] ]]; then",
                    "  echo 'Rollback cancelled'",
                    "  exit 1",
                    "fi",
                    "",
                ]
            )

        script_content.extend(["echo 'Executing rollback commands...'", ""])
        for cmd in analysis_result.rollback_commands:
            if cmd.startswith("#"):
                script_content.append(f"echo '{cmd}'")
            else:
                script_content.append(f"echo 'Running: {cmd}'")
                script_content.append(cmd)

        script_content.extend(["", "echo 'Rollback completed successfully!'"])

        # Write script to file
        with open(script_path, "w", encoding="utf-8") as f:
            f.write("\n".join(script_content))

        # Make script executable (owner read/write/execute only)
        os.chmod(script_path, 0o700)

        logger.info(f"Recovery script generated: {script_path}")
        return script_path
