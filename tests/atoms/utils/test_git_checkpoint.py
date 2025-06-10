"""
Comprehensive tests for the GitCheckpointManager and related classes.

Covers:
- Repository state checking
- Checkpoint creation with different strategies for uncommitted changes
- Error handling for edge cases
- Metadata parsing and retrieval
- Git command failures

Mocks subprocess and filesystem as needed.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from aider_mcp_server.atoms.utils.git_checkpoint import (
    GitCheckpointError,
    GitCheckpointManager,
    GitCommandError,
    NotAGitRepositoryError,
    UncommittedChangesError,
)

# --- Fixtures and helpers ---


@pytest.fixture
def fake_repo_path(tmp_path):
    # Create a fake .git directory to simulate a git repo
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    return str(tmp_path)


@pytest.fixture
def manager(fake_repo_path):
    return GitCheckpointManager(fake_repo_path)


# --- Tests ---


class TestGitCheckpointManagerInit:
    def test_init_success(self, fake_repo_path):
        mgr = GitCheckpointManager(fake_repo_path)
        assert mgr.repo_path == os.path.abspath(fake_repo_path)

    def test_init_not_a_git_repo(self, tmp_path):
        # No .git directory
        with pytest.raises(NotAGitRepositoryError):
            GitCheckpointManager(str(tmp_path))

    def test_is_git_repo_true(self, fake_repo_path):
        mgr = GitCheckpointManager(fake_repo_path)
        assert mgr.is_git_repo() is True

    def test_is_git_repo_false(self, tmp_path):
        mgr = object.__new__(GitCheckpointManager)
        mgr.repo_path = str(tmp_path)
        assert mgr.is_git_repo() is False


class TestUncommittedChanges:
    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_has_uncommitted_changes_true(self, mock_run_git, manager):
        mock_run_git.return_value = " M file.py\n"
        assert manager.has_uncommitted_changes() is True

    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_has_uncommitted_changes_false(self, mock_run_git, manager):
        mock_run_git.return_value = ""
        assert manager.has_uncommitted_changes() is False


class TestHandleUncommittedChanges:
    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager.has_uncommitted_changes")
    def test_handle_no_changes(self, mock_has_changes, manager):
        mock_has_changes.return_value = False
        # Should not raise
        manager.handle_uncommitted_changes(strategy="error")

    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager.has_uncommitted_changes")
    def test_handle_error_strategy(self, mock_has_changes, manager):
        mock_has_changes.return_value = True
        with pytest.raises(UncommittedChangesError):
            manager.handle_uncommitted_changes(strategy="error")

    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager.has_uncommitted_changes")
    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_handle_stash_strategy(self, mock_run_git, mock_has_changes, manager):
        mock_has_changes.return_value = True
        manager.handle_uncommitted_changes(strategy="stash")
        mock_run_git.assert_called_with(["stash", "push", "-u", "-m", "Aider safety checkpoint stash"])

    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager.has_uncommitted_changes")
    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_handle_commit_strategy(self, mock_run_git, mock_has_changes, manager):
        mock_has_changes.return_value = True
        manager.handle_uncommitted_changes(strategy="commit")
        assert mock_run_git.call_count == 2
        mock_run_git.assert_any_call(["add", "-A"])
        mock_run_git.assert_any_call(
            ["commit", "-m", "Aider safety auto-commit: uncommitted changes before checkpoint"]
        )

    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager.has_uncommitted_changes")
    def test_handle_unknown_strategy(self, mock_has_changes, manager):
        mock_has_changes.return_value = True
        with pytest.raises(ValueError):
            manager.handle_uncommitted_changes(strategy="nonsense")


class TestRunGit:
    @patch("subprocess.run")
    def test_run_git_success(self, mock_run, manager):
        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        out = manager._run_git(["status"], capture_output=True)
        assert out == "output"

    @patch("subprocess.run")
    def test_run_git_failure(self, mock_run, manager):
        mock_run.side_effect = Exception("fail")
        with patch("aider_mcp_server.atoms.utils.git_checkpoint.logger"):
            with pytest.raises(GitCommandError):
                manager._run_git(["status"], capture_output=True)

    @patch("subprocess.run")
    def test_run_git_git_command_error(self, mock_run, manager):
        from subprocess import CalledProcessError

        err = CalledProcessError(1, ["git", "status"], output="", stderr="fail")
        mock_run.side_effect = err
        with patch("aider_mcp_server.atoms.utils.git_checkpoint.logger"):
            with pytest.raises(GitCommandError) as exc_info:
                manager._run_git(["status"], capture_output=True)
            assert "fail" in exc_info.value.output


class TestCreateCheckpoint:
    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager.handle_uncommitted_changes")
    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_create_checkpoint_success(self, mock_run_git, mock_handle, manager):
        # Simulate successful add, commit, and rev-parse
        mock_run_git.side_effect = ["", "", "abc123"]
        commit_hash = manager.create_checkpoint(
            operation_id="op1",
            model="gpt-4",
            target_files=["main.py"],
            operation_params={"foo": "bar"},
            uncommitted_strategy="error",
        )
        assert commit_hash == "abc123"
        assert mock_run_git.call_args_list[-1][0][0] == ["rev-parse", "HEAD"]

    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager.handle_uncommitted_changes")
    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_create_checkpoint_nothing_to_commit(self, mock_run_git, mock_handle, manager):
        # Simulate add, commit raises GitCommandError with "nothing to commit", then rev-parse
        def side_effect(args, capture_output=False):
            if args[0] == "add":
                return ""
            if args[0] == "commit":
                raise GitCommandError("fail", output="nothing to commit")
            if args[0] == "rev-parse":
                return "deadbeef"

        mock_run_git.side_effect = side_effect
        commit_hash = manager.create_checkpoint(
            operation_id="op2",
            model="gpt-4",
            target_files=["main.py"],
            operation_params=None,
            uncommitted_strategy="error",
        )
        assert commit_hash == "deadbeef"

    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager.handle_uncommitted_changes")
    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_create_checkpoint_other_commit_error(self, mock_run_git, mock_handle, manager):
        # Simulate add, commit raises GitCommandError with other error
        def side_effect(args, capture_output=False):
            if args[0] == "add":
                return ""
            if args[0] == "commit":
                raise GitCommandError("fail", output="some other error")

        mock_run_git.side_effect = side_effect
        with pytest.raises(GitCommandError):
            manager.create_checkpoint(
                operation_id="op3",
                model="gpt-4",
                target_files=["main.py"],
                operation_params=None,
                uncommitted_strategy="error",
            )


class TestGetLatestCheckpoint:
    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_get_latest_checkpoint_found(self, mock_run_git, manager):
        mock_run_git.return_value = "abc123\n"
        commit = manager.get_latest_checkpoint()
        assert commit == "abc123"

    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_get_latest_checkpoint_none(self, mock_run_git, manager):
        mock_run_git.return_value = ""
        commit = manager.get_latest_checkpoint()
        assert commit is None

    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_get_latest_checkpoint_with_operation_id(self, mock_run_git, manager):
        mock_run_git.return_value = "def456\n"
        commit = manager.get_latest_checkpoint(operation_id="opid")
        assert commit == "def456"

    @patch("aider_mcp_server.atoms.utils.git_checkpoint.GitCheckpointManager._run_git")
    def test_get_latest_checkpoint_git_command_error(self, mock_run_git, manager):
        mock_run_git.side_effect = GitCommandError("fail", output="fail")
        with patch("aider_mcp_server.atoms.utils.git_checkpoint.logger"):
            commit = manager.get_latest_checkpoint()
            assert commit is None


class TestErrorClasses:
    def test_git_checkpoint_error(self):
        err = GitCheckpointError("msg")
        assert isinstance(err, Exception)
        assert str(err) == "msg"

    def test_not_a_git_repository_error(self):
        err = NotAGitRepositoryError("msg")
        assert isinstance(err, GitCheckpointError)
        assert str(err) == "msg"

    def test_uncommitted_changes_error(self):
        err = UncommittedChangesError("msg")
        assert isinstance(err, GitCheckpointError)
        assert str(err) == "msg"

    def test_git_command_error(self):
        err = GitCommandError("msg", output="oops")
        assert isinstance(err, GitCheckpointError)
        assert err.output == "oops"
        assert str(err) == "msg"
