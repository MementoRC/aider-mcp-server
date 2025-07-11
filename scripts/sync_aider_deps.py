#!/usr/bin/env python3
"""
Script to sync aider dependencies from .taskmaster/config/aider-deps.toml
to pyproject.toml. This allows easy management and removal of aider dependencies
when aider becomes available as a conda package.

Usage:
    python scripts/sync_aider_deps.py [--remove]
    
    --remove: Remove aider dependencies instead of adding them
"""

import argparse
import toml
from pathlib import Path

def load_aider_deps():
    """Load aider dependencies from config file."""
    config_path = Path("aider-deps.toml")
    if not config_path.exists():
        raise FileNotFoundError(f"Aider deps config not found: {config_path}")
    
    return toml.load(config_path)

def load_pyproject():
    """Load pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        raise FileNotFoundError("pyproject.toml not found")
    
    return toml.load(pyproject_path), pyproject_path

def add_aider_deps():
    """Add aider dependencies to pyproject.toml."""
    aider_deps = load_aider_deps()
    pyproject, pyproject_path = load_pyproject()
    
    # Add conda dependencies
    conda_deps = aider_deps.get("conda-dependencies", {})
    pixi_deps = pyproject.setdefault("tool", {}).setdefault("pixi", {}).setdefault("dependencies", {})
    
    # Add comment marker for aider deps
    if conda_deps and "# Aider dependencies" not in str(pixi_deps):
        print("Adding conda aider dependencies...")
        for name, version in conda_deps.items():
            pixi_deps[name] = version
            print(f"  Added: {name} = {version}")
    
    # Add pypi dependencies  
    pypi_deps = aider_deps.get("pypi-dependencies", {})
    pixi_pypi_deps = pyproject.setdefault("tool", {}).setdefault("pixi", {}).setdefault("pypi-dependencies", {})
    
    if pypi_deps:
        print("Adding PyPI aider dependencies...")
        for name, version in pypi_deps.items():
            pixi_pypi_deps[name] = version
            print(f"  Added: {name} = {version}")
    
    # Save updated pyproject.toml
    with open(pyproject_path, 'w') as f:
        toml.dump(pyproject, f)
    
    print(f"Updated {pyproject_path}")

def remove_aider_deps():
    """Remove aider dependencies from pyproject.toml."""
    aider_deps = load_aider_deps()
    pyproject, pyproject_path = load_pyproject()
    
    # Remove conda dependencies
    conda_deps = aider_deps.get("conda-dependencies", {})
    pixi_deps = pyproject.get("tool", {}).get("pixi", {}).get("dependencies", {})
    
    removed_count = 0
    for name in conda_deps:
        if name in pixi_deps:
            del pixi_deps[name]
            print(f"  Removed: {name}")
            removed_count += 1
    
    # Remove pypi dependencies
    pypi_deps = aider_deps.get("pypi-dependencies", {})
    pixi_pypi_deps = pyproject.get("tool", {}).get("pixi", {}).get("pypi-dependencies", {})
    
    for name in pypi_deps:
        if name in pixi_pypi_deps:
            del pixi_pypi_deps[name]
            print(f"  Removed: {name}")
            removed_count += 1
    
    if removed_count > 0:
        # Save updated pyproject.toml
        with open(pyproject_path, 'w') as f:
            toml.dump(pyproject, f)
        print(f"Removed {removed_count} aider dependencies from {pyproject_path}")
    else:
        print("No aider dependencies found to remove")

def main():
    parser = argparse.ArgumentParser(description="Sync aider dependencies")
    parser.add_argument("--remove", action="store_true", 
                       help="Remove aider dependencies instead of adding them")
    
    args = parser.parse_args()
    
    try:
        if args.remove:
            remove_aider_deps()
        else:
            add_aider_deps()
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())