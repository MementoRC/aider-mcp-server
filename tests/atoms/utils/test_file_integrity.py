"""
Comprehensive tests for the FileIntegrityManager and related classes.

Covers:
- Initialization (success/failure)
- Checksum calculation (MD5/SHA256)
- Line counting (empty, single, multi-line)
- Syntax validation (Python, JS, TS, valid/invalid)
- Git status (clean, modified, untracked)
- Baseline capture (multiple files, edge cases)
- Error handling (all exception types)
- Edge cases (binary, empty, non-existent files)

Mocks subprocess and filesystem as needed.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from aider_mcp_server.atoms.utils.file_integrity import (
    FileIntegrityManager,
    FileIntegrityError,
    FileIntegrityFileNotFoundError,
    SyntaxValidationError,
)

# --- Fixtures and helpers ---

@pytest.fixture
def fake_repo_path(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    return str(tmp_path)

@pytest.fixture
def manager(fake_repo_path):
    return FileIntegrityManager(fake_repo_path)

@pytest.fixture
def make_file(tmp_path, fake_repo_path):
    def _make_file(rel_path, content=""):
        abs_path = os.path.join(fake_repo_path, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return rel_path, abs_path
    return _make_file

# --- Tests ---

class TestFileIntegrityManagerInit:
    def test_init_success(self, fake_repo_path):
        mgr = FileIntegrityManager(fake_repo_path)
        assert mgr.repo_path == os.path.abspath(fake_repo_path)

    def test_init_not_a_git_repo(self, tmp_path):
        with pytest.raises(FileIntegrityError):
            FileIntegrityManager(str(tmp_path))

    def test_is_git_repo_true(self, fake_repo_path):
        mgr = FileIntegrityManager(fake_repo_path)
        assert mgr.is_git_repo() is True

    def test_is_git_repo_false(self, tmp_path):
        mgr = object.__new__(FileIntegrityManager)
        mgr.repo_path = str(tmp_path)
        assert mgr.is_git_repo() is False

class TestChecksumCalculation:
    @pytest.mark.parametrize("content,md5,sha256", [
        ("", "d41d8cd98f00b204e9800998ecf8427e", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        ("abc", "900150983cd24fb0d6963f7d28e17f72", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
        ("hello\nworld", "9195d0beb2a889e1be05ed6bb1954837", "26c60a61d01db5836ca70fefd44a6a016620413c8ef5f259a6c5612d4f79d3b8"),
    ])
    def test_checksum_md5_sha256(self, manager, content, md5, sha256):
        assert manager.calculate_checksum(content, algorithm="md5") == md5
        assert manager.calculate_checksum(content, algorithm="sha256") == sha256

    def test_checksum_unsupported_algorithm(self, manager):
        with pytest.raises(ValueError):
            manager.calculate_checksum("abc", algorithm="sha1")

class TestLineCounting:
    @pytest.mark.parametrize("content,expected", [
        ("", 0),
        ("one line", 1),
        ("line1\nline2", 2),
        ("line1\nline2\n", 2),
        ("\n\n", 2),
    ])
    def test_count_lines(self, manager, content, expected):
        assert manager.count_lines(content) == expected

class TestSyntaxValidationPython:
    def test_valid_python(self, manager, make_file):
        rel, abs_path = make_file("good.py", "a = 1\nb = 2\n")
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert manager.validate_syntax(abs_path, content) is True

    def test_invalid_python(self, manager, make_file):
        rel, abs_path = make_file("bad.py", "def foo(:\n")
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        with pytest.raises(SyntaxValidationError):
            manager.validate_syntax(abs_path, content)

class TestSyntaxValidationJS:
    @patch("aider_mcp_server.atoms.utils.file_integrity.subprocess.run")
    def test_valid_js(self, mock_run, manager, make_file):
        rel, abs_path = make_file("good.js", "var x = 1;")
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert manager.validate_syntax(abs_path, content) is True

    @patch("aider_mcp_server.atoms.utils.file_integrity.subprocess.run")
    def test_invalid_js(self, mock_run, manager, make_file):
        rel, abs_path = make_file("bad.js", "var = ;")
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="SyntaxError")
        with pytest.raises(SyntaxValidationError):
            manager.validate_syntax(abs_path, content)

class TestSyntaxValidationTS:
    @patch("aider_mcp_server.atoms.utils.file_integrity.subprocess.run")
    def test_valid_ts(self, mock_run, manager, make_file):
        rel, abs_path = make_file("good.ts", "let x: number = 1;")
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert manager.validate_syntax(abs_path, content) is True

    @patch("aider_mcp_server.atoms.utils.file_integrity.subprocess.run")
    def test_invalid_ts(self, mock_run, manager, make_file):
        rel, abs_path = make_file("bad.ts", "let = ;")
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="TS1005")
        with pytest.raises(SyntaxValidationError):
            manager.validate_syntax(abs_path, content)

class TestSyntaxValidationOther:
    def test_unsupported_extension(self, manager, make_file):
        rel, abs_path = make_file("file.txt", "not code")
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Should not raise
        assert manager.validate_syntax(abs_path, content) is True

class TestGitStatus:
    @patch("aider_mcp_server.atoms.utils.file_integrity.FileIntegrityManager._run_git")
    def test_git_status_clean(self, mock_run_git, manager, make_file):
        rel, abs_path = make_file("foo.py", "a=1")
        mock_run_git.return_value = ""
        assert manager.get_git_status(abs_path) == "clean"

    @patch("aider_mcp_server.atoms.utils.file_integrity.FileIntegrityManager._run_git")
    def test_git_status_untracked(self, mock_run_git, manager, make_file):
        rel, abs_path = make_file("bar.py", "b=2")
        mock_run_git.return_value = "?? bar.py"
        assert manager.get_git_status(abs_path) == "untracked"

    @patch("aider_mcp_server.atoms.utils.file_integrity.FileIntegrityManager._run_git")
    def test_git_status_modified(self, mock_run_git, manager, make_file):
        rel, abs_path = make_file("baz.py", "c=3")
        mock_run_git.return_value = " M baz.py"
        assert manager.get_git_status(abs_path) == "M baz.py"

class TestCaptureFileIntegrityBaseline:
    @patch("aider_mcp_server.atoms.utils.file_integrity.FileIntegrityManager.get_git_status")
    @patch("aider_mcp_server.atoms.utils.file_integrity.FileIntegrityManager.validate_syntax")
    def test_capture_baseline_success(self, mock_validate, mock_git_status, manager, make_file):
        rel1, abs1 = make_file("a.py", "a=1")
        rel2, abs2 = make_file("b.py", "b=2\nc=3")
        mock_validate.return_value = True
        mock_git_status.side_effect = ["clean", "modified"]
        baseline = manager.capture_file_integrity_baseline([rel1, rel2])
        assert rel1 in baseline and rel2 in baseline
        assert baseline[rel1]["line_count"] == 1
        assert baseline[rel2]["line_count"] == 2
        assert baseline[rel1]["git_status"] == "clean"
        assert baseline[rel2]["git_status"] == "modified"
        assert "checksum_sha256" in baseline[rel1]

    def test_capture_baseline_file_not_found(self, manager):
        with pytest.raises(FileIntegrityFileNotFoundError):
            manager.capture_file_integrity_baseline(["nope.py"])

    @patch("aider_mcp_server.atoms.utils.file_integrity.FileIntegrityManager.validate_syntax")
    def test_capture_baseline_syntax_error(self, mock_validate, manager, make_file):
        rel, abs_path = make_file("bad.py", "def foo(:\n")
        mock_validate.side_effect = SyntaxValidationError("bad syntax")
        with pytest.raises(SyntaxValidationError):
            manager.capture_file_integrity_baseline([rel])

    @patch("aider_mcp_server.atoms.utils.file_integrity.FileIntegrityManager.get_git_status")
    @patch("aider_mcp_server.atoms.utils.file_integrity.FileIntegrityManager.validate_syntax")
    def test_capture_baseline_multiple_files(self, mock_validate, mock_git_status, manager, make_file):
        rel1, abs1 = make_file("a.py", "a=1")
        rel2, abs2 = make_file("b.js", "var x = 1;")
        rel3, abs3 = make_file("c.txt", "plain text")
        mock_validate.return_value = True
        mock_git_status.side_effect = ["clean", "untracked", "modified"]
        baseline = manager.capture_file_integrity_baseline([rel1, rel2, rel3])
        assert set(baseline.keys()) == {rel1, rel2, rel3}

class TestEdgeCases:
    def test_empty_file(self, manager, make_file):
        rel, abs_path = make_file("empty.py", "")
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert manager.count_lines(content) == 0
        assert manager.calculate_checksum(content) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_binary_file(self, manager, fake_repo_path):
        # Write binary data to a file and try to read as text
        rel_path = "binfile.py"
        abs_path = os.path.join(fake_repo_path, rel_path)
        with open(abs_path, "wb") as f:
            f.write(b"\x00\x01\x02\x03")
        # Should raise FileIntegrityError when reading as utf-8
        with pytest.raises(FileIntegrityError):
            manager.capture_file_integrity_baseline([rel_path])

    def test_nonexistent_file(self, manager):
        with pytest.raises(FileIntegrityFileNotFoundError):
            manager.capture_file_integrity_baseline(["doesnotexist.py"])

class TestErrorClasses:
    def test_file_integrity_error(self):
        err = FileIntegrityError("msg")
        assert isinstance(err, Exception)
        assert str(err) == "msg"

    def test_file_not_found_error(self):
        err = FileIntegrityFileNotFoundError("msg")
        assert isinstance(err, FileIntegrityError)
        assert str(err) == "msg"

    def test_syntax_validation_error(self):
        err = SyntaxValidationError("msg")
        assert isinstance(err, FileIntegrityError)
        assert str(err) == "msg"
