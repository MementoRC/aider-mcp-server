# Testing Guide - Aider MCP Server

## Overview

The Aider MCP Server follows a comprehensive testing strategy aligned with atomic design architecture principles and Task 1: REQ-QA-001 quality assurance requirements.

## Test Organization

Tests are organized following the atomic design architecture:

```
tests/
├── atoms/           # Unit tests for basic building blocks
│   ├── tools/       # Tool-related atomic tests
│   └── utils/       # Utility atomic tests
├── molecules/       # Tests for combined components
│   ├── configuration/
│   ├── execution/
│   ├── maintenance/
│   ├── monitoring/
│   ├── session/
│   └── tools/aider/
├── organisms/       # Integration tests for complex components
│   └── transports/http/
└── pages/           # End-to-end workflow tests (to be created)
```

## Test Markers

Tests can be marked with the following pytest markers:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.performance` / `@pytest.mark.perf` - Performance tests
- `@pytest.mark.security` - Security-related tests
- `@pytest.mark.api` - Tests requiring API keys
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.e2e` - End-to-end tests

## Coverage Requirements

### Quality Gates (Task 1: REQ-QA-001)

- **Minimum Coverage**: 85% (CI will fail below this threshold)
- **Target Coverage**: 90%
- **Branch Coverage**: Enabled
- **Coverage Reports**: XML, HTML, and terminal output

### Running Tests with Coverage

```bash
# Run all tests with coverage
pixi run test-cov

# Run tests with coverage enforcement (85% minimum)
pixi run test-cov-check

# Run unit tests only
pixi run test-unit

# Run integration tests only
pixi run test-integration
```

### Coverage Configuration

Coverage settings are defined in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src/aider_mcp_server"]
branch = true
parallel = true

[tool.coverage.report]
fail_under = 85  # Minimum coverage threshold
precision = 2
show_missing = true
```

## CI Integration

### Automated Coverage Reporting

The CI pipeline automatically:

1. Runs all tests with coverage using `pytest-xdist` for parallel execution
2. Enforces the 85% minimum coverage threshold
3. Generates XML and HTML coverage reports
4. Uploads HTML reports as GitHub Actions artifacts (30-day retention)
5. Uploads coverage to Codecov for tracking and visualization

### CI Commands

```bash
# CI test execution (in .github/workflows/ci.yml)
pixi run -e ci python -m pytest tests/ \
  -n auto \
  --cov=src/aider_mcp_server \
  --cov-report=term-missing \
  --cov-report=xml \
  --cov-report=html \
  --cov-fail-under=85 \
  --tb=short \
  --maxfail=5
```

## Test Writing Guidelines

### Test Structure

Follow atomic design principles when writing tests:

1. **Atoms**: Test individual functions, classes, and utilities in isolation
2. **Molecules**: Test interactions between 2-3 components
3. **Organisms**: Test complex workflows and multi-component integrations
4. **Pages**: Test complete end-to-end user workflows

### Example Test Structure

```python
import pytest
from aider_mcp_server.atoms.tools import ToolValidator

@pytest.mark.unit
def test_tool_validator_accepts_valid_input():
    """Test that tool validator accepts valid input."""
    validator = ToolValidator()
    result = validator.validate({"type": "function", "name": "test"})
    assert result.is_valid is True

@pytest.mark.integration
@pytest.mark.slow
async def test_http_transport_end_to_end():
    """Test complete HTTP transport workflow."""
    # Integration test code
    pass
```

### Coverage Best Practices

1. **Focus on critical paths**: Ensure MCP operations, Aider integration, and transport protocols are well-covered
2. **Use markers**: Tag tests appropriately for selective execution
3. **Avoid testing implementation details**: Focus on public APIs and contracts
4. **Use coverage exclusions sparingly**: Only exclude truly untestable code (see `pyproject.toml`)

## Local Development

### Viewing Coverage Reports

After running `pixi run test-cov`:

```bash
# View HTML coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows

# View terminal coverage summary
# (automatically displayed after test-cov command)
```

### Pre-Commit Testing

```bash
# Run quality gates before committing
pixi run quality  # Runs: test + lint + typecheck

# Run complete validation
pixi run check-all  # Runs: quality + static-analysis
```

## Continuous Improvement

### Adding New Tests

When adding new functionality:

1. Write tests first (TDD approach recommended)
2. Ensure coverage meets or exceeds 85% for new code
3. Use appropriate test markers
4. Place tests in correct atomic architecture layer
5. Run `pixi run test-cov-check` to verify coverage threshold

### Regression Prevention

- Performance regression testing (Task 2: REQ-PERF-001) - Coming soon
- Security regression testing (Task 4: REQ-SEC-001) - Coming soon
- All tests run on every commit via CI

## Troubleshooting

### Coverage Below 85%

If CI fails due to coverage:

```bash
# Run coverage and view missing lines
pixi run test-cov

# Check HTML report for detailed view
open htmlcov/index.html

# Focus on files with low coverage
# Add tests for uncovered lines
```

### Slow Test Execution

```bash
# Use parallel execution (enabled by default in test-cov)
pixi run test-cov  # Uses -n auto for pytest-xdist

# Run only fast tests
pixi run pytest tests/ -m "not slow"

# Profile test execution
pixi run pytest tests/ --durations=10
```

## References

- Task 1: REQ-QA-001 - Comprehensive test coverage analysis
- Quality Gates: 85% minimum, 90% target
- Atomic Design Architecture: atoms → molecules → organisms → pages
- pytest documentation: https://docs.pytest.org/
- coverage.py documentation: https://coverage.readthedocs.io/
