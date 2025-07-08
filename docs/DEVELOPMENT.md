# Development Environment Guide

This project uses **pixi** for all dependency management and environment control.

## Environment Overview

- **Pixi**: Manages all dependencies (runtime and development) using conda-forge packages
- **Conda-forge priority**: Maximizes use of conda packages to minimize dependency conflicts

## Quick Start

### 1. Initial Setup
```bash
# Install dependencies
pixi install
```

### 2. Daily Development Workflow
```bash
# Run tests
pixi run test

# Format and lint
pixi run format
pixi run lint

# All quality checks
pixi run check-all
```

### 3. When Dependencies Change
```bash
# After modifying pyproject.toml dependencies
pixi update                 # Update all dependencies
pixi install                # Install/sync dependencies

# Or use the convenience script
./scripts/sync-environments.sh
```

## Environment Management Commands

### Pixi Commands (for MCP server and development)
```bash
pixi install                # Install dependencies
pixi update                 # Update all dependencies
pixi run mcp-server         # Run MCP server
pixi run test               # Run tests
pixi run lint               # Run linter
pixi run format             # Format code
pixi run typecheck          # Run type checker
pixi list                   # List installed packages
```


## Troubleshooting

### "Module not found" or Import Errors
```bash
# Refresh pixi environment
pixi clean
pixi install
```

### MCP Server Issues
```bash
# Test MCP server directly
pixi run mcp-server --help

# Check pixi environment
pixi list
```

### Environment Conflicts
```bash
# Clean and recreate pixi environment
pixi clean
pixi install
```

## Quality Gates

Before committing:
```bash
pixi run check-all  # Runs format + lint + test
```

## Architecture Notes

- **Pixi manages everything**: All dependencies (runtime and development) are managed by pixi
- **Conda-forge priority**: Most packages come from conda-forge for consistency and compatibility
- **Lock file authority**: `pixi.lock` is the source of truth for dependency versions
- **Minimal PyPI usage**: Only packages not available in conda-forge are installed from PyPI