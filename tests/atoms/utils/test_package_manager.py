import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.utils.package_manager import PackageManagerError, PoetryPackageManager

# Initialize logger for tests if needed, though caplog handles it
logger = get_logger(__name__)


@pytest.fixture
def mock_project_path(tmp_path):
    """Fixture to create a temporary project path with a pyproject.toml."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text('[tool.poetry]\nname = "test-project"')
    return str(project_dir)


def test_poetry_package_manager_init_success(mock_project_path):
    """Test successful initialization of PoetryPackageManager."""
    manager = PoetryPackageManager(mock_project_path)
    assert manager.project_path == os.path.abspath(mock_project_path)


def test_poetry_package_manager_init_no_pyproject_toml(tmp_path, caplog):
    """Test initialization when pyproject.toml is missing."""
    project_dir = tmp_path / "test_project_no_toml"
    project_dir.mkdir()

    with caplog.at_level(pytest.logging.WARNING):
        manager = PoetryPackageManager(str(project_dir))
        assert "pyproject.toml not found" in caplog.text
        assert "This might not be a Poetry project." in caplog.text
    assert manager.project_path == os.path.abspath(str(project_dir))


def test_poetry_package_manager_init_invalid_path():
    """Test initialization with an invalid project path."""
    with pytest.raises(ValueError, match="Project path does not exist"):
        PoetryPackageManager("/non/existent/path")


@patch("subprocess.run")
def test_run_poetry_success(mock_run, mock_project_path):
    """Test _run_poetry for successful command execution."""
    mock_run.return_value = MagicMock(stdout="Success output", stderr="", returncode=0)
    manager = PoetryPackageManager(mock_project_path)
    output = manager._run_poetry(["install"])
    mock_run.assert_called_once_with(
        ["poetry", "install"],
        cwd=mock_project_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    assert output == "Success output"


@patch("subprocess.run")
def test_run_poetry_failure(mock_run, mock_project_path, caplog):
    """
    Test _run_poetry for failed command execution.
    FIX 3: Update the test to check for ERROR log level and correct message format.
    """
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["poetry", "install"], stderr="Error output from poetry"
    )
    manager = PoetryPackageManager(mock_project_path)

    with pytest.raises(PackageManagerError) as excinfo:
        with caplog.at_level(pytest.logging.ERROR):
            manager._run_poetry(["install"])

    assert "Poetry command failed: poetry install" in str(excinfo.value)
    assert "Error output from poetry" in str(excinfo.value.output)  # Check output attribute
    assert excinfo.value.output == "Error output from poetry"

    # Check log message
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "ERROR"
    assert "Poetry command failed: poetry install" in caplog.records[0].message
    assert "Error output from poetry" in caplog.records[0].message


@patch("subprocess.run")
def test_run_poetry_file_not_found(mock_run, mock_project_path, caplog):
    """Test _run_poetry when poetry executable is not found."""
    mock_run.side_effect = FileNotFoundError("poetry")
    manager = PoetryPackageManager(mock_project_path)

    with pytest.raises(PackageManagerError) as excinfo:
        with caplog.at_level(pytest.logging.ERROR):
            manager._run_poetry(["install"])

    assert "Poetry executable not found" in str(excinfo.value)
    assert excinfo.value.output is None  # FileNotFoundError doesn't have stderr output

    # Check log message
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "ERROR"
    assert "Poetry executable not found" in caplog.records[0].message


@patch("subprocess.run")
def test_list_outdated_packages_success(mock_run, mock_project_path):
    """Test list_outdated_packages for success."""
    mock_run.return_value = MagicMock(
        stdout="""
PackageA 1.0.0 -> 1.1.0
PackageB 2.0.0 -> 2.0.1
""",
        stderr="",
        returncode=0,
    )
    manager = PoetryPackageManager(mock_project_path)
    outdated = manager.list_outdated_packages()
    assert outdated == ["PackageA", "PackageB"]
    mock_run.assert_called_once_with(
        ["poetry", "show", "--outdated", "--no-ansi"],
        cwd=mock_project_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )


@patch("subprocess.run")
def test_list_outdated_packages_no_updates(mock_run, mock_project_path):
    """Test list_outdated_packages when no updates are available."""
    mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
    manager = PoetryPackageManager(mock_project_path)
    outdated = manager.list_outdated_packages()
    assert outdated == []


@patch("subprocess.run")
def test_list_outdated_packages_failure(mock_run, mock_project_path):
    """Test list_outdated_packages for failure."""
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["poetry", "show"], stderr="Error listing outdated"
    )
    manager = PoetryPackageManager(mock_project_path)
    with pytest.raises(PackageManagerError, match="Failed to list outdated packages"):
        manager.list_outdated_packages()


@patch("subprocess.run")
def test_update_packages_success(mock_run, mock_project_path):
    """Test update_packages for success."""
    mock_run.return_value = MagicMock(stdout="Updated PackageA", stderr="", returncode=0)
    manager = PoetryPackageManager(mock_project_path)
    manager.update_packages(["PackageA"])
    mock_run.assert_called_once_with(
        ["poetry", "update", "PackageA"],
        cwd=mock_project_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )


@patch("subprocess.run")
def test_update_packages_failure(mock_run, mock_project_path):
    """Test update_packages for failure."""
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["poetry", "update", "PackageA"], stderr="Error updating"
    )
    manager = PoetryPackageManager(mock_project_path)
    with pytest.raises(PackageManagerError, match="Failed to update packages PackageA"):
        manager.update_packages(["PackageA"])


@patch("subprocess.run")
def test_update_all_packages_success(mock_run, mock_project_path):
    """Test update_all_packages for success."""
    mock_run.return_value = MagicMock(stdout="Updated all", stderr="", returncode=0)
    manager = PoetryPackageManager(mock_project_path)
    manager.update_all_packages()
    mock_run.assert_called_once_with(
        ["poetry", "update"],
        cwd=mock_project_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )


@patch("subprocess.run")
def test_update_all_packages_failure(mock_run, mock_project_path):
    """Test update_all_packages for failure."""
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["poetry", "update"], stderr="Error updating all"
    )
    manager = PoetryPackageManager(mock_project_path)
    with pytest.raises(PackageManagerError, match="Failed to update all packages"):
        manager.update_all_packages()
