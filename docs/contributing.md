# Contributing

Thank you for your interest in contributing to Aider MCP Server! This guide will help you get started with contributing to this AI-powered coding server built with Atomic Design principles.

## Quick Start

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Set up the development environment**
4. **Create a feature branch**
5. **Make your changes**
6. **Run tests and quality checks**
7. **Submit a pull request**

## Development Setup

### Prerequisites

- **Python 3.12+**
- **Git**
- **hatch** (recommended) or **pip**
- **AI API keys** for testing

### Environment Setup

=== "Using hatch (recommended)"

    ```bash
    git clone https://github.com/YOUR_USERNAME/aider-mcp-server.git
    cd aider-mcp-server
    
    # Install in development mode
    hatch env create dev
    hatch shell dev
    
    # Install pre-commit hooks
    hatch run dev:pre-commit install
    ```

=== "Using pip"

    ```bash
    git clone https://github.com/YOUR_USERNAME/aider-mcp-server.git
    cd aider-mcp-server
    
    # Create virtual environment
    python -m venv venv
    source venv/bin/activate  # or `venv\Scripts\activate` on Windows
    
    # Install in development mode
    pip install -e ".[dev]"
    
    # Install pre-commit hooks
    pre-commit install
    ```

### Configuration

Create a `.env` file for testing:

```bash
# Required: At least one API key
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
GOOGLE_API_KEY=your_google_key

# Optional: Test configuration
AIDER_MODEL=gpt-4o-mini  # Use cheaper model for testing
TEST_WORKING_DIR=/tmp/aider-test
```

## Project Architecture

Aider MCP Server follows **Atomic Design** principles:

```
src/aider_mcp_server/
├── atoms/          # Basic building blocks
│   ├── types/      # Data types and protocols
│   ├── utils/      # Utility functions
│   ├── errors/     # Error definitions
│   └── logging/    # Logging components
├── molecules/      # Functional components
│   ├── tools/      # Tool implementations
│   ├── configuration/  # Config management
│   ├── events/     # Event handling
│   └── security/   # Security services
├── organisms/      # Complex features
│   ├── coordinators/   # Orchestration
│   ├── transports/     # Transport adapters
│   └── processors/     # Request processing
└── pages/          # Application entry points
    └── application/    # Main app coordination
```

### Key Principles

1. **Atoms** don't import from higher layers
2. **Molecules** can import atoms
3. **Organisms** can import atoms and molecules
4. **Pages** can import from any layer
5. **Clear separation of concerns**
6. **High testability**

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Development Process

#### Follow Atomic Design

When adding new functionality:

1. **Start with atoms** - Create basic types, utilities
2. **Build molecules** - Combine atoms into functional components
3. **Create organisms** - Orchestrate molecules for complex features
4. **Wire in pages** - Connect to application entry points

#### Example: Adding a New Tool

```python
# 1. Atom: Define the tool protocol
# atoms/types/tool_protocols.py
from typing import Protocol

class ToolProtocol(Protocol):
    def execute(self, params: dict) -> dict: ...

# 2. Molecule: Implement the tool
# molecules/tools/my_new_tool.py  
from ..types.tool_protocols import ToolProtocol

class MyNewTool:
    def execute(self, params: dict) -> dict:
        # Implementation
        return {"result": "success"}

# 3. Organism: Register with handler
# organisms/processors/handlers.py
def register_tools():
    # Register the new tool
    pass

# 4. Tests
# tests/molecules/tools/test_my_new_tool.py
def test_my_new_tool():
    tool = MyNewTool()
    result = tool.execute({"param": "value"})
    assert result["result"] == "success"
```

### 3. Quality Standards

#### Testing Requirements

All contributions must include tests:

```bash
# Run specific test file
hatch run dev:pytest tests/molecules/tools/test_my_tool.py -v

# Run all tests
hatch run dev:pytest

# Run with coverage
hatch run dev:pytest --cov=src/aider_mcp_server --cov-report=html
```

#### Code Quality Checks

Before committing, ensure all checks pass:

```bash
# Lint checks
hatch run dev:ruff check --select=F,E9

# Type checking
hatch run dev:mypy src/

# Format code
hatch run dev:ruff format

# Pre-commit hooks (runs automatically)
hatch run dev:pre-commit run --all-files
```

#### Test Coverage Requirements

- **Minimum 85% coverage** for new code
- **Unit tests** for all new functions/classes
- **Integration tests** for new features
- **Error handling tests** for failure scenarios

### 4. Documentation

#### Code Documentation

```python
def my_function(param: str) -> dict:
    """Brief description of the function.
    
    Args:
        param: Description of the parameter
        
    Returns:
        Description of the return value
        
    Raises:
        ValueError: When param is invalid
        
    Example:
        >>> result = my_function("test")
        >>> assert result["status"] == "success"
    """
    pass
```

#### Update Documentation

When adding features:

1. **Update relevant `.md` files** in `docs/`
2. **Add examples** to `docs/examples.md`
3. **Update API reference** if needed
4. **Add to changelog** (see below)

## Testing Guidelines

### Test Structure

```python
import pytest
from unittest.mock import Mock, patch
from aider_mcp_server.molecules.tools.my_tool import MyTool

class TestMyTool:
    """Test suite for MyTool"""
    
    @pytest.fixture
    def tool(self):
        """Create a tool instance for testing"""
        return MyTool()
    
    def test_successful_execution(self, tool):
        """Test normal operation"""
        result = tool.execute({"valid": "params"})
        assert result["status"] == "success"
    
    def test_error_handling(self, tool):
        """Test error scenarios"""
        with pytest.raises(ValueError):
            tool.execute({"invalid": "params"})
    
    @patch('aider_mcp_server.molecules.tools.my_tool.external_api')
    def test_with_mocks(self, mock_api, tool):
        """Test with external dependencies mocked"""
        mock_api.return_value = {"data": "mocked"}
        result = tool.execute({"test": "params"})
        assert result["data"] == "mocked"
```

### Integration Tests

```python
import pytest
import asyncio
from aider_mcp_server.pages.application.coordinator import ApplicationCoordinator

@pytest.mark.asyncio
async def test_full_request_flow():
    """Test complete request processing"""
    coordinator = ApplicationCoordinator()
    await coordinator.initialize()
    
    # Test actual request flow
    result = await coordinator.process_request({
        "method": "tools/call",
        "params": {"name": "my_tool", "arguments": {...}}
    })
    
    assert result["status"] == "success"
```

### Test Data and Fixtures

```python
# conftest.py
import pytest
import tempfile
from pathlib import Path

@pytest.fixture
def temp_project():
    """Create a temporary Git repository for testing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=project_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], 
                      cwd=project_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], 
                      cwd=project_path, check=True)
        
        # Create initial commit
        (project_path / "README.md").write_text("# Test Project")
        subprocess.run(["git", "add", "."], cwd=project_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], 
                      cwd=project_path, check=True)
        
        yield project_path
```

## Pull Request Process

### 1. Before Submitting

- [ ] All tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation is updated
- [ ] Changelog entry added
- [ ] No merge conflicts with main branch

### 2. PR Requirements

#### Title Format
```
type(scope): brief description

Examples:
feat(tools): add new code analysis tool
fix(sse): resolve connection timeout issue
docs(api): update transport documentation
test(molecules): add coverage for event system
```

#### Description Template

```markdown
## Summary

Brief description of the changes.

## Changes Made

- [ ] Feature/fix description
- [ ] Documentation updates
- [ ] Test additions

## Testing

- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Breaking Changes

None / List any breaking changes

## Related Issues

Closes #123
Related to #456
```

### 3. Review Process

1. **Automated checks** must pass
2. **Code review** by maintainers
3. **Testing** in development environment
4. **Documentation review**
5. **Approval** and merge

## Code Style Guide

### Python Style

Follow **PEP 8** with these specific guidelines:

```python
# Line length: 120 characters
# Use type hints
def process_request(request: dict[str, Any]) -> dict[str, Any]:
    """Process an incoming request."""
    pass

# Use descriptive names
user_authentication_service = AuthenticationService()

# Group imports: stdlib, third-party, local
import asyncio
import json
from typing import Dict, List

import httpx
import pytest

from aider_mcp_server.atoms.types import EventType
from aider_mcp_server.molecules.tools import AiderTool
```

### File Organization

```python
"""Module docstring describing the purpose."""

# Imports (grouped and sorted)
import asyncio
from typing import Dict, Optional

from aider_mcp_server.atoms.types import EventType

# Constants
DEFAULT_TIMEOUT = 30.0

# Classes
class MyClass:
    """Class docstring."""
    
    def __init__(self, param: str) -> None:
        """Initialize the class."""
        self._param = param
    
    def public_method(self) -> str:
        """Public method with docstring."""
        return self._private_method()
    
    def _private_method(self) -> str:
        """Private method (single underscore)."""
        return f"processed: {self._param}"

# Functions
def utility_function(data: dict) -> bool:
    """Utility function with clear purpose."""
    return bool(data.get("valid"))
```

## Debugging and Development Tips

### Local Development Server

```bash
# Start in debug mode
AIDER_LOG_LEVEL=DEBUG mcp-aider-sse \
  --current-working-dir /path/to/test/project \
  --port 5005

# Monitor logs
tail -f ~/.aider-mcp-server/logs/aider-mcp-server.log
```

### Testing with Different Models

```python
# Test with multiple models
@pytest.mark.parametrize("model", ["gpt-4o", "gpt-4o-mini", "claude-3-sonnet"])
def test_with_different_models(model):
    tool = AiderTool(model=model)
    result = tool.execute(test_params)
    assert result["status"] == "success"
```

### Performance Profiling

```python
import cProfile
import pstats

def profile_function():
    """Profile function performance"""
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Your code here
    result = expensive_function()
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('tottime')
    stats.print_stats(10)
    
    return result
```

## Release Process

### Versioning

We use **Semantic Versioning** (SemVer):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Changelog

Update `docs/changelog.md` with:

```markdown
## [1.2.0] - 2024-01-15

### Added
- New code analysis tool for complexity metrics
- Support for custom model configurations

### Changed  
- Improved error handling in SSE transport
- Updated atomic design documentation

### Fixed
- Memory leak in long-running sessions
- Race condition in multi-client scenarios

### Deprecated
- Legacy configuration format (will be removed in 2.0.0)
```

## Community Guidelines

### Code of Conduct

- **Be respectful** and inclusive
- **Constructive feedback** in reviews
- **Help newcomers** get started
- **Focus on the code**, not the person

### Communication

- **GitHub Issues** for bugs and feature requests
- **GitHub Discussions** for questions and ideas
- **Pull Requests** for code contributions
- **Documentation** for usage questions

### Recognition

Contributors are recognized in:

- Release notes
- Contributor list
- Special recognition for significant contributions

## Getting Help

### Documentation

- **[Architecture Guide](atomic-design-architecture.md)** - Understanding the codebase
- **[API Reference](api-reference.md)** - Technical details
- **[Examples](examples.md)** - Practical usage

### Support Channels

- **GitHub Issues** - Bug reports and feature requests
- **GitHub Discussions** - Questions and community support
- **Documentation** - Comprehensive guides and examples

### Mentorship

New contributors can:

- Look for **"good first issue"** labels
- Ask questions in GitHub Discussions
- Request code review feedback
- Pair with experienced contributors

## Thank You!

Your contributions make Aider MCP Server better for everyone. Whether it's:

- **Bug reports** and feature requests
- **Code contributions** and reviews  
- **Documentation** improvements
- **Community support** and discussions

Every contribution is valuable and appreciated! 🚀