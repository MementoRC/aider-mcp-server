"""
Comprehensive tests for the GitDiffAnalyzer and related classes.

Covers:
- Git diff parsing and analysis
- Suspicious pattern detection
- Large change detection
- Rollback command generation
- Error handling for edge cases
- Recovery script generation

Mocks subprocess and filesystem as needed.
"""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from aider_mcp_server.atoms.utils.git_diff_analyzer import (
    DiffAnalysisFailedError,
    DiffAnalysisResult,
    FileChangeStats,
    GitDiffAnalysisError,
    GitDiffAnalyzer,
    InvalidGitReferenceError,
    SuspiciousPattern,
)

# --- Fixtures and helpers ---


@pytest.fixture
def fake_repo_path(tmp_path):
    """Create a proper git repository for testing."""
    # Initialize a proper git repository
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)  # noqa: S603,S607
    # Set basic git config to avoid warnings
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)  # noqa: S603,S607
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)  # noqa: S603,S607
    return str(tmp_path)


@pytest.fixture
def analyzer(fake_repo_path):
    """Create a GitDiffAnalyzer instance for testing."""
    return GitDiffAnalyzer(fake_repo_path)


@pytest.fixture
def sample_diff_stat_output():
    """Sample git diff --stat output for testing."""
    return """src/main.py                    | 25 +++++++++++++++++++------
tests/test_main.py              | 15 +++++++++++++++
config/settings.json           | 3 +++
old_file.txt                    | 50 --------------------------------------------------
{old_name.py => new_name.py}    | 10 +++++-----
binary_file.png                 | Bin 0 -> 1234 bytes
 6 files changed, 47 insertions(+), 56 deletions(-)"""


# --- Tests ---


class TestGitDiffAnalyzerInit:
    """Test GitDiffAnalyzer initialization."""

    def test_init_success(self, fake_repo_path):
        """Test successful initialization."""
        analyzer = GitDiffAnalyzer(fake_repo_path)
        assert analyzer.repo_path == os.path.abspath(fake_repo_path)
        assert analyzer.large_change_threshold == 100
        assert analyzer.mass_deletion_threshold == 100

    def test_init_custom_thresholds(self, fake_repo_path):
        """Test initialization with custom thresholds."""
        analyzer = GitDiffAnalyzer(
            fake_repo_path,
            large_change_threshold=50,
            mass_deletion_threshold=75,
            mass_deletion_ratio=0.3,
            complete_replacement_threshold=20,
            complete_replacement_ratio=0.15,
        )
        assert analyzer.large_change_threshold == 50
        assert analyzer.mass_deletion_threshold == 75
        assert analyzer.mass_deletion_ratio == 0.3
        assert analyzer.complete_replacement_threshold == 20
        assert analyzer.complete_replacement_ratio == 0.15

    def test_init_not_a_git_repo(self, tmp_path):
        """Test initialization failure for non-git directory."""
        with pytest.raises(GitDiffAnalysisError, match="Not a git repository"):
            GitDiffAnalyzer(str(tmp_path))


class TestFileChangeStats:
    """Test FileChangeStats dataclass."""

    def test_basic_properties(self):
        """Test basic properties of FileChangeStats."""
        stats = FileChangeStats("test.py", additions=30, deletions=10)
        assert stats.net_change == 20
        assert stats.total_change == 40
        assert stats.change_ratio == 0.75

    def test_zero_changes(self):
        """Test properties with zero changes."""
        stats = FileChangeStats("test.py", additions=0, deletions=0)
        assert stats.net_change == 0
        assert stats.total_change == 0
        assert stats.change_ratio == 0.0

    def test_file_flags(self):
        """Test file state flags."""
        stats = FileChangeStats(
            "test.py",
            additions=10,
            deletions=5,
            is_binary=True,
            is_new_file=True,
            is_renamed=True,
            old_filename="old_test.py",
        )
        assert stats.is_binary
        assert stats.is_new_file
        assert stats.is_renamed
        assert stats.old_filename == "old_test.py"


class TestGitCommands:
    """Test git command execution."""

    @patch("subprocess.run")
    def test_run_git_success(self, mock_run, analyzer):
        """Test successful git command execution."""
        mock_result = MagicMock()
        mock_result.stdout = "success output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = analyzer._run_git(["status"], capture_output=True)
        assert result == "success output"

    @patch("subprocess.run")
    def test_run_git_failure(self, mock_run, analyzer):
        """Test git command failure handling."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, ["git", "status"], stderr="error output")

        with pytest.raises(DiffAnalysisFailedError) as exc_info:
            analyzer._run_git(["status"], capture_output=True)
        assert "error output" in exc_info.value.output

    @patch("subprocess.run")
    def test_run_git_unexpected_error(self, mock_run, analyzer):
        """Test unexpected error handling."""
        mock_run.side_effect = OSError("Unexpected error")

        with pytest.raises(DiffAnalysisFailedError) as exc_info:
            analyzer._run_git(["status"], capture_output=True)
        assert "Unexpected error" in exc_info.value.output

    @patch("aider_mcp_server.atoms.utils.git_diff_analyzer.GitDiffAnalyzer._run_git")
    def test_validate_git_reference_valid(self, mock_run_git, analyzer):
        """Test validation of valid git reference."""
        mock_run_git.return_value = "abc123"
        assert analyzer._validate_git_reference("main") is True

    @patch("aider_mcp_server.atoms.utils.git_diff_analyzer.GitDiffAnalyzer._run_git")
    def test_validate_git_reference_invalid(self, mock_run_git, analyzer):
        """Test validation of invalid git reference."""
        mock_run_git.side_effect = DiffAnalysisFailedError("Invalid reference")
        assert analyzer._validate_git_reference("invalid-ref") is False


class TestDiffStatParsing:
    """Test parsing of git diff --stat output."""

    def test_parse_diff_stats_comprehensive(self, analyzer, sample_diff_stat_output):
        """Test comprehensive parsing of diff stat output."""
        file_changes = analyzer._parse_diff_stats(sample_diff_stat_output)

        assert len(file_changes) == 6

        # Check main.py
        main_py = next(fc for fc in file_changes if fc.filename == "src/main.py")
        assert main_py.additions > 0
        assert main_py.deletions > 0
        assert not main_py.is_binary

        # Check test file (new file)
        test_py = next(fc for fc in file_changes if fc.filename == "tests/test_main.py")
        assert test_py.additions > 0
        assert test_py.deletions == 0

        # Check deleted file
        old_file = next(fc for fc in file_changes if fc.filename == "old_file.txt")
        assert old_file.deletions == 50
        assert old_file.additions == 0

        # Check renamed file
        renamed_file = next(fc for fc in file_changes if fc.filename == "new_name.py")
        assert renamed_file.is_renamed
        assert renamed_file.old_filename == "old_name.py"

        # Check binary file
        binary_file = next(fc for fc in file_changes if fc.filename == "binary_file.png")
        assert binary_file.is_binary
        assert binary_file.additions == 0
        assert binary_file.deletions == 0

    def test_parse_diff_stats_empty(self, analyzer):
        """Test parsing empty diff stat output."""
        file_changes = analyzer._parse_diff_stats("")
        assert file_changes == []

    def test_parse_diff_stats_summary_only(self, analyzer):
        """Test parsing diff stat with only summary line."""
        output = " 1 file changed, 5 insertions(+), 2 deletions(-)"
        file_changes = analyzer._parse_diff_stats(output)
        assert file_changes == []

    def test_parse_diff_stats_malformed_lines(self, analyzer):
        """Test parsing with malformed lines."""
        output = """src/main.py | 25 +++++++++++++++++++------
        malformed line without pipe
        another/file.py | 10 +++++-----"""
        file_changes = analyzer._parse_diff_stats(output)
        assert len(file_changes) == 2
        assert file_changes[0].filename == "src/main.py"
        assert file_changes[1].filename == "another/file.py"


class TestSuspiciousPatternDetection:
    """Test detection of suspicious change patterns."""

    def test_detect_mass_deletion(self, analyzer):
        """Test detection of mass deletion pattern."""
        file_changes = [
            FileChangeStats("massive_delete.py", additions=10, deletions=200),
            FileChangeStats("normal.py", additions=50, deletions=30),
        ]

        patterns = analyzer._detect_suspicious_patterns(file_changes)
        mass_deletion_patterns = [p for p in patterns if p.pattern_type == "mass_deletion"]
        assert len(mass_deletion_patterns) == 1
        assert mass_deletion_patterns[0].filename == "massive_delete.py"
        assert mass_deletion_patterns[0].severity == "high"

    def test_detect_complete_replacement(self, analyzer):
        """Test detection of complete file replacement pattern."""
        file_changes = [
            FileChangeStats("replaced.py", additions=55, deletions=45),  # Ratio ~0.55, close to 0.5
            FileChangeStats("normal.py", additions=80, deletions=10),  # Ratio 0.89, not close to 0.5
        ]

        patterns = analyzer._detect_suspicious_patterns(file_changes)
        replacement_patterns = [p for p in patterns if p.pattern_type == "complete_replacement"]
        assert len(replacement_patterns) == 1
        assert replacement_patterns[0].filename == "replaced.py"
        assert replacement_patterns[0].severity == "medium"

    def test_detect_unexpected_operations(self, analyzer):
        """Test detection of unexpected file operations."""
        file_changes = [
            FileChangeStats("new_file.py", additions=50, deletions=0, is_new_file=True),
            FileChangeStats("deleted_file.py", additions=0, deletions=30, is_deleted_file=True),
        ]

        # Test unexpected creation during deletion operation
        patterns = analyzer._detect_suspicious_patterns(file_changes, operation_intent="delete old files")
        creation_patterns = [p for p in patterns if p.pattern_type == "unexpected_file_creation"]
        assert len(creation_patterns) == 1

        # Test unexpected deletion during addition operation
        patterns = analyzer._detect_suspicious_patterns(file_changes, operation_intent="add new feature")
        deletion_patterns = [p for p in patterns if p.pattern_type == "unexpected_file_deletion"]
        assert len(deletion_patterns) == 1

    def test_no_suspicious_patterns(self, analyzer):
        """Test when no suspicious patterns are detected."""
        file_changes = [
            FileChangeStats("normal1.py", additions=20, deletions=5),
            FileChangeStats("normal2.py", additions=8, deletions=2),  # Lower total to avoid replacement detection
        ]

        patterns = analyzer._detect_suspicious_patterns(file_changes)
        assert patterns == []


class TestLargeChangeDetection:
    """Test detection of large changes."""

    def test_detect_large_changes(self, analyzer):
        """Test detection of files with large changes."""
        file_changes = [
            FileChangeStats("large_file.py", additions=80, deletions=50),  # 130 total
            FileChangeStats("small_file.py", additions=20, deletions=10),  # 30 total
            FileChangeStats("medium_file.py", additions=60, deletions=30),  # 90 total
        ]

        large_changes = analyzer._detect_large_changes(file_changes)
        assert large_changes == ["large_file.py"]

    def test_no_large_changes(self, analyzer):
        """Test when no large changes are detected."""
        file_changes = [
            FileChangeStats("small1.py", additions=20, deletions=10),
            FileChangeStats("small2.py", additions=30, deletions=15),
        ]

        large_changes = analyzer._detect_large_changes(file_changes)
        assert large_changes == []


class TestRollbackCommandGeneration:
    """Test rollback command generation."""

    def test_generate_rollback_commands(self, analyzer):
        """Test generation of rollback commands."""
        suspicious_files = {"suspicious.py", "problematic.py"}
        large_change_files = {"large.py", "problematic.py"}  # overlap with suspicious

        commands, selective_files = analyzer._generate_rollback_commands("abc123", suspicious_files, large_change_files)

        # Check stash command is first
        assert commands[0] == "git stash push -u -m 'Pre-rollback stash'"

        # Check full rollback command exists
        assert "git reset --hard abc123" in commands

        # Check selective rollback commands for unique files
        expected_files = {"suspicious.py", "problematic.py", "large.py"}
        for filename in expected_files:
            assert f"git checkout abc123 -- '{filename}'" in commands

        # Check selective files list
        assert set(selective_files) == expected_files

    def test_generate_rollback_commands_no_problems(self, analyzer):
        """Test rollback command generation with no problematic files."""
        commands, selective_files = analyzer._generate_rollback_commands("abc123", set(), set())

        assert "git stash push -u -m 'Pre-rollback stash'" in commands
        assert "git reset --hard abc123" in commands
        assert selective_files == []


class TestDiffAnalysis:
    """Test complete diff analysis workflow."""

    @patch("aider_mcp_server.atoms.utils.git_diff_analyzer.GitDiffAnalyzer._validate_git_reference")
    @patch("aider_mcp_server.atoms.utils.git_diff_analyzer.GitDiffAnalyzer._run_git")
    def test_analyze_diff_success(self, mock_run_git, mock_validate, analyzer, sample_diff_stat_output):
        """Test successful diff analysis."""
        mock_validate.return_value = True
        mock_run_git.return_value = sample_diff_stat_output

        result = analyzer.analyze_diff("checkpoint123", "HEAD", operation_intent="refactor code")

        assert isinstance(result, DiffAnalysisResult)
        assert result.from_ref == "checkpoint123"
        assert result.to_ref == "HEAD"
        assert result.total_files_changed > 0
        assert result.total_additions > 0
        assert result.total_deletions > 0
        assert len(result.rollback_commands) > 0
        assert "refactor code" not in result.analysis_summary  # Intent not included in summary

    @patch("aider_mcp_server.atoms.utils.git_diff_analyzer.GitDiffAnalyzer._validate_git_reference")
    def test_analyze_diff_invalid_from_ref(self, mock_validate, analyzer):
        """Test diff analysis with invalid from reference."""
        mock_validate.side_effect = lambda ref: ref != "invalid-ref"

        with pytest.raises(InvalidGitReferenceError, match="Invalid git reference: invalid-ref"):
            analyzer.analyze_diff("invalid-ref", "HEAD")

    @patch("aider_mcp_server.atoms.utils.git_diff_analyzer.GitDiffAnalyzer._validate_git_reference")
    def test_analyze_diff_invalid_to_ref(self, mock_validate, analyzer):
        """Test diff analysis with invalid to reference."""
        mock_validate.side_effect = lambda ref: ref != "invalid-to"

        with pytest.raises(InvalidGitReferenceError, match="Invalid git reference: invalid-to"):
            analyzer.analyze_diff("abc123", "invalid-to")

    @patch("aider_mcp_server.atoms.utils.git_diff_analyzer.GitDiffAnalyzer._validate_git_reference")
    @patch("aider_mcp_server.atoms.utils.git_diff_analyzer.GitDiffAnalyzer._run_git")
    def test_analyze_diff_git_command_failure(self, mock_run_git, mock_validate, analyzer):
        """Test diff analysis with git command failure."""
        mock_validate.return_value = True
        mock_run_git.side_effect = DiffAnalysisFailedError("Git command failed")

        with pytest.raises(DiffAnalysisFailedError):
            analyzer.analyze_diff("abc123", "HEAD")

    @patch("aider_mcp_server.atoms.utils.git_diff_analyzer.GitDiffAnalyzer._validate_git_reference")
    @patch("aider_mcp_server.atoms.utils.git_diff_analyzer.GitDiffAnalyzer._run_git")
    def test_analyze_diff_with_critical_issues(self, mock_run_git, mock_validate, analyzer):
        """Test diff analysis that detects critical issues."""
        mock_validate.return_value = True
        # Create diff output that will trigger mass deletion pattern
        diff_output = "problematic.py                | 150 " + "-" * 140 + "+" * 10
        mock_run_git.return_value = diff_output

        result = analyzer.analyze_diff("abc123", "HEAD")

        assert result.has_critical_issues
        assert len(result.suspicious_patterns) > 0
        high_severity_patterns = [p for p in result.suspicious_patterns if p.severity in ["high", "critical"]]
        assert len(high_severity_patterns) > 0


class TestRecoveryScript:
    """Test recovery script generation."""

    def test_get_recovery_script_basic(self, analyzer, tmp_path):
        """Test basic recovery script generation."""
        # Create a sample analysis result
        result = DiffAnalysisResult(
            from_ref="abc123",
            to_ref="HEAD",
            file_changes=[],
            suspicious_patterns=[],
            large_changes=[],
            rollback_commands=["git stash push -u -m 'Pre-rollback stash'", "git reset --hard abc123"],
            selective_rollback_files=[],
            total_files_changed=5,
            total_additions=50,
            total_deletions=20,
            has_critical_issues=False,
            analysis_summary="Test analysis summary",
        )

        script_path = str(tmp_path / "recovery.sh")
        generated_path = analyzer.get_recovery_script(result, script_path)

        assert generated_path == script_path
        assert os.path.exists(script_path)
        assert os.access(script_path, os.X_OK)  # Check if executable

        # Read and check script content
        with open(script_path, encoding="utf-8") as f:
            content = f.read()

        assert "#!/bin/bash" in content
        assert "Git Diff Analysis Recovery Script" in content
        assert "git stash push -u -m 'Pre-rollback stash'" in content
        assert "git reset --hard abc123" in content

    def test_get_recovery_script_with_critical_issues(self, analyzer, tmp_path):
        """Test recovery script generation with critical issues."""
        # Create analysis result with critical patterns
        critical_pattern = SuspiciousPattern(
            pattern_type="mass_deletion",
            filename="critical.py",
            severity="critical",
            description="Critical mass deletion detected",
            details={},
            recommended_action="Review carefully",
        )

        result = DiffAnalysisResult(
            from_ref="abc123",
            to_ref="HEAD",
            file_changes=[],
            suspicious_patterns=[critical_pattern],
            large_changes=[],
            rollback_commands=["git reset --hard abc123"],
            selective_rollback_files=["critical.py"],
            total_files_changed=1,
            total_additions=10,
            total_deletions=200,
            has_critical_issues=True,
            analysis_summary="Critical issues detected",
        )

        script_path = str(tmp_path / "critical_recovery.sh")
        analyzer.get_recovery_script(result, script_path)

        with open(script_path, encoding="utf-8") as f:
            content = f.read()

        assert "WARNING: Critical issues detected" in content
        assert "critical.py: Critical mass deletion detected" in content
        assert "read -p 'Continue with rollback? (y/N):" in content


class TestErrorClasses:
    """Test custom exception classes."""

    def test_git_diff_analysis_error(self):
        """Test base GitDiffAnalysisError."""
        error = GitDiffAnalysisError("Base error message")
        assert str(error) == "Base error message"
        assert isinstance(error, Exception)

    def test_invalid_git_reference_error(self):
        """Test InvalidGitReferenceError."""
        error = InvalidGitReferenceError("Invalid reference")
        assert str(error) == "Invalid reference"
        assert isinstance(error, GitDiffAnalysisError)

    def test_diff_analysis_failed_error(self):
        """Test DiffAnalysisFailedError with output."""
        error = DiffAnalysisFailedError("Analysis failed", output="Git error output")
        assert str(error) == "Analysis failed"
        assert error.output == "Git error output"
        assert isinstance(error, GitDiffAnalysisError)

    def test_diff_analysis_failed_error_no_output(self):
        """Test DiffAnalysisFailedError without output."""
        error = DiffAnalysisFailedError("Analysis failed")
        assert str(error) == "Analysis failed"
        assert error.output is None
